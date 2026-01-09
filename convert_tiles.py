"""
GeoTIFF to Web Tiles Converter for MahaMap-Lite

Converts GeoTIFF files to XYZ web tiles and uploads to Cloudflare R2.
Auto-detects geographic extent and optimizes zoom levels automatically.

Prerequisites:
    - Install GDAL: sudo apt install gdal-bin python3-gdal
    - Set up Cloudflare credentials in .env file

Usage:
    python convert_tiles.py <input_geotiff> <layer_name> [--zoom-min N] [--zoom-max N]

Example:
    python convert_tiles.py data_banjir.tif banjir-sby-2025
    python convert_tiles.py region.tif my-layer --zoom-min 8 --zoom-max 16
"""

import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import requests
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

# R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "map-tiles")

# D1 Configuration
D1_API_TOKEN = os.getenv("D1_API_TOKEN")
D1_ACCOUNT_ID = os.getenv("D1_ACCOUNT_ID")
D1_DATABASE_ID = os.getenv("D1_DATABASE_ID")


def get_geotiff_bounds(input_tif):
    """Extract geographic bounds from GeoTIFF using gdalinfo."""
    try:
        result = subprocess.run(
            ["gdalinfo", "-json", input_tif],
            capture_output=True, text=True, check=True
        )
        info = json.loads(result.stdout)

        # Get corner coordinates
        corners = info.get("cornerCoordinates", {})
        if not corners:
            return None

        ul = corners.get("upperLeft", [])
        lr = corners.get("lowerRight", [])

        if len(ul) >= 2 and len(lr) >= 2:
            min_lon, max_lat = ul[0], ul[1]
            max_lon, min_lat = lr[0], lr[1]
            return {
                "min_lon": min_lon,
                "max_lon": max_lon,
                "min_lat": min_lat,
                "max_lat": max_lat,
                "width": abs(max_lon - min_lon),
                "height": abs(max_lat - min_lat)
            }
    except Exception as e:
        print(f"Warning: Could not read bounds: {e}")
    return None


def calculate_optimal_zoom(bounds, file_size_kb):
    """
    Calculate optimal zoom levels based on geographic extent and file size.

    Returns (min_zoom, max_zoom) tuple.
    """
    if not bounds:
        # Fallback to conservative defaults
        return 10, 14

    width = bounds["width"]
    height = bounds["height"]
    area_deg = width * height

    # Classify by coverage area
    # Neighborhood/building level: < 0.01 deg² (~1km²)
    # City/district level: 0.01 - 0.5 deg² (~1-50km²)
    # Provincial/regional level: 0.5 - 10 deg² (~50-1000km²)
    # Country level: > 10 deg²

    if area_deg < 0.001:
        # Very small area (neighborhood)
        min_zoom, max_zoom = 14, 19
    elif area_deg < 0.01:
        # Small area (district/village)
        min_zoom, max_zoom = 12, 18
    elif area_deg < 0.1:
        # City level
        min_zoom, max_zoom = 10, 16
    elif area_deg < 1.0:
        # Regional/provincial level
        min_zoom, max_zoom = 8, 14
    elif area_deg < 10:
        # Large region
        min_zoom, max_zoom = 6, 12
    else:
        # Country/continent level
        min_zoom, max_zoom = 0, 6

    # Adjust max zoom based on file size (higher resolution = allow higher zoom)
    if file_size_kb > 10000:  # > 10MB
        max_zoom = min(max_zoom + 2, 20)
    elif file_size_kb > 1000:  # > 1MB
        max_zoom = min(max_zoom + 1, 19)
    elif file_size_kb < 100:  # < 100KB
        max_zoom = max(max_zoom - 1, min_zoom + 2)

    return min_zoom, max_zoom


def estimate_tile_count(bounds, min_zoom, max_zoom):
    """Estimate number of tiles that will be generated."""
    if not bounds:
        return "unknown"

    total = 0
    for z in range(min_zoom, max_zoom + 1):
        n = 2 ** z
        # Convert lat/lon to tile coordinates
        min_x = int((bounds["min_lon"] + 180) / 360 * n)
        max_x = int((bounds["max_lon"] + 180) / 360 * n)

        min_lat_rad = math.radians(bounds["min_lat"])
        max_lat_rad = math.radians(bounds["max_lat"])
        min_y = int((1 - math.asinh(math.tan(max_lat_rad)) / math.pi) / 2 * n)
        max_y = int((1 - math.asinh(math.tan(min_lat_rad)) / math.pi) / 2 * n)

        tiles_at_zoom = (max_x - min_x + 1) * (max_y - min_y + 1)
        total += tiles_at_zoom

    return total


def classify_region(bounds):
    """Classify the region type based on extent."""
    if not bounds:
        return "Unknown region"

    area = bounds["width"] * bounds["height"]

    if area < 0.001:
        return "Neighborhood/Building level"
    elif area < 0.01:
        return "District/Village level"
    elif area < 0.1:
        return "City level"
    elif area < 1.0:
        return "Regional/Provincial level"
    elif area < 10:
        return "Large region"
    else:
        return "Country/Continent level"


def get_r2_client():
    """Initialize R2 client."""
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY]):
        return None
    return boto3.client(
        's3',
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto'
    )


def d1_query(sql, params=None):
    """Execute SQL on D1."""
    if not all([D1_API_TOKEN, D1_ACCOUNT_ID, D1_DATABASE_ID]):
        return None

    url = f"https://api.cloudflare.com/client/v4/accounts/{D1_ACCOUNT_ID}/d1/database/{D1_DATABASE_ID}/query"
    headers = {"Authorization": f"Bearer {D1_API_TOKEN}", "Content-Type": "application/json"}
    body = {"sql": sql}
    if params:
        body["params"] = params

    try:
        res = requests.post(url, headers=headers, json=body)
        return res.json().get("success", False)
    except:
        return False


def check_gdal():
    """Check if GDAL is installed."""
    try:
        subprocess.run(["gdal2tiles.py", "--version"], capture_output=True, check=True)
        return True
    except:
        return False


def process_geotiff(input_tif, layer_name, zoom_min=None, zoom_max=None):
    """Convert GeoTIFF to tiles and upload to R2 with auto-optimization."""
    import os
    if not os.path.exists(input_tif):
        print(f"Error: File '{input_tif}' not found!")
        return False

    if not check_gdal():
        print("Error: GDAL not installed! Run: sudo apt install gdal-bin python3-gdal")
        return False

    r2 = get_r2_client()
    if not r2:
        print("Error: R2 credentials not configured in .env!")
        return False

    # Get file size
    file_size_kb = os.path.getsize(input_tif) / 1024
    print(f"\n📂 Input: {input_tif} ({file_size_kb:.1f} KB)")

    # Auto-detect bounds and optimal zoom
    print("🔍 Analyzing GeoTIFF...")
    bounds = get_geotiff_bounds(input_tif)

    if bounds:
        print(f"   Bounds: {bounds['min_lat']:.4f}°, {bounds['min_lon']:.4f}° → {bounds['max_lat']:.4f}°, {bounds['max_lon']:.4f}°")
        print(f"   Coverage: {bounds['width']:.4f}° × {bounds['height']:.4f}°")
        print(f"   Region: {classify_region(bounds)}")

    # Calculate optimal zoom if not specified
    if zoom_min is None or zoom_max is None:
        auto_min, auto_max = calculate_optimal_zoom(bounds, file_size_kb)
        zoom_min = zoom_min or auto_min
        zoom_max = zoom_max or auto_max
        print(f"   Auto-selected zoom: {zoom_min} - {zoom_max}")
    else:
        print(f"   Using specified zoom: {zoom_min} - {zoom_max}")

    # Estimate tiles
    est_tiles = estimate_tile_count(bounds, zoom_min, zoom_max)
    print(f"   Estimated tiles: ~{est_tiles}")

    output_dir = f"temp_tiles/{layer_name}"
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n⚙️ Converting to tiles (zoom {zoom_min}-{zoom_max})...")

    # Convert with GDAL
    import os  # Pastikan sudah ada import os di atas

    # Ubah baris subprocess menjadi:
    result = subprocess.run([
        "gdal2tiles.py",
        f"--zoom={zoom_min}-{zoom_max}",
        "--xyz",
        f"--processes={os.cpu_count()}", # Otomatis pakai 8 untuk i7 Gen 11
        input_tif,
        output_dir
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ GDAL Error: {result.stderr}")
        return False

    print("✅ Conversion complete!")

    # Collect all tiles to upload
    tiles_to_upload = []
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file.endswith('.png'):
                local_path = os.path.join(root, file)
                rel_path = os.path.relpath(local_path, output_dir)
                remote_path = f"{layer_name}/{rel_path}"
                tiles_to_upload.append((local_path, remote_path))

    total_tiles = len(tiles_to_upload)
    print(f"\n☁️ Uploading {total_tiles} tiles to R2 (parallel)...")

    # Parallel upload function
    def upload_tile(args):
        local_path, remote_path = args
        try:
            r2.upload_file(local_path, R2_BUCKET, remote_path,
                          ExtraArgs={'ContentType': 'image/png'})
            return True
        except Exception:
            return False

    # Upload with ThreadPoolExecutor (10 concurrent uploads)
    uploaded = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(upload_tile, t): t for t in tiles_to_upload}
        for future in as_completed(futures):
            if future.result():
                uploaded += 1
            else:
                failed += 1

            # Progress update every 50 tiles
            done = uploaded + failed
            if done % 50 == 0 or done == total_tiles:
                pct = (done / total_tiles) * 100
                print(f"   Progress: {done}/{total_tiles} ({pct:.0f}%)")

    print(f"✅ Upload complete! {uploaded} tiles uploaded, {failed} failed.")

    # Save to D1
    print("Saving metadata to D1...")
    layer_id = str(uuid.uuid4())
    success = d1_query(
        "INSERT INTO map_layers (id, name, folder_path, description) VALUES (?, ?, ?, ?)",
        [layer_id, layer_name, layer_name, f"Layer from {os.path.basename(input_tif)}"]
    )

    if success:
        print("✓ Metadata saved!")
    else:
        print("Warning: Could not save to D1")

    # Cleanup
    cleanup = input("Delete temp tiles? (y/n): ").lower()
    if cleanup == 'y':
        shutil.rmtree(output_dir)
        print("Cleaned up.")

    print(f"\n✓ Done! Layer '{layer_name}' ready.")
    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert GeoTIFF to web tiles with auto-optimization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python convert_tiles.py data.tif my-layer        # Auto-detect zoom
  python convert_tiles.py data.tif my-layer --zoom-min 8 --zoom-max 14
        """
    )
    parser.add_argument('input_tif', help='Input GeoTIFF file')
    parser.add_argument('layer_name', help='Name for the tile layer')
    parser.add_argument('--zoom-min', type=int, default=None, help='Minimum zoom level (auto-detected if not specified)')
    parser.add_argument('--zoom-max', type=int, default=None, help='Maximum zoom level (auto-detected if not specified)')

    args = parser.parse_args()

    success = process_geotiff(args.input_tif, args.layer_name, args.zoom_min, args.zoom_max)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
