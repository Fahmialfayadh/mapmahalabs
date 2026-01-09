"""
Standalone script to compress GeoTIFF to Cloud Optimized GeoTIFF (COG).
Target: Maximum compression (>80% size reduction possible depending on data/method).

Usage:
    python compress_cog.py <input.tif> [output.tif] [--method=lossy]

Methods:
    --method=lossless (Default) Uses ZSTD+Predictor (Best balance)
    --method=lossy    Uses LERC (Limited Error) or WEBP (Images) for max compression
"""

import sys
import os
import subprocess
import time

def check_gdal():
    try:
        subprocess.run(["gdal_translate", "--version"], capture_output=True, check=True)
        return True
    except:
        return False

def get_file_size(path):
    return os.path.getsize(path) / (1024 * 1024)  # MB

def compress_cog(input_path, output_path, method="lossless"):
    if not os.path.exists(input_path):
        print(f"Error: Path {input_path} not found")
        return False

    if not check_gdal():
        print("Error: GDAL tools (gdal_translate) not found. Install gdal-bin.")
        return False

    print(f"Processing: {input_path}")
    original_size = get_file_size(input_path)
    print(f"Original Size: {original_size:.2f} MB")
    
    start_time = time.time()
    
    # Base command
    cmd = [
        "gdal_translate",
        input_path,
        output_path,
        "-of", "COG",
        "-co", "TILED=YES",
        "-co", "COPY_SRC_OVERVIEWS=YES",
        "-co", "BLOCKSIZE=512",
        "-co", "BIGTIFF=IF_NEEDED"
    ]

    # Compression Settings
    if method == "lossy":
        # Aggressive compression (LERC_ZSTD or WEBP)
        # LERC is great for data, WEBP for RGB images.
        # We'll use LERC_ZSTD with a small max error which allows huge compression.
        print("Using Aggressive Lossy Compression (LERC_ZSTD, MaxError=0.01)")
        cmd.extend([
            "-co", "COMPRESS=LERC_ZSTD",
            "-co", "MAX_Z_ERROR=0.01", # Adjust tolerance if needed
            "-co", "LEVEL=22" # Max ZSTD level
        ])
    elif method == "visual":
        # For Satellite Imagery (RGB) -> WEBP is amazing (often >90% reduction)
        print("Using Visual Compression (WEBP)")
        cmd.extend([
            "-co", "COMPRESS=WEBP",
            "-co", "QUALITY=75"
        ])
    else:
        # High Compression Lossless (DEFLATE or ZSTD)
        print("Using High Compression Lossless (ZSTD)")
        cmd.extend([
            "-co", "COMPRESS=ZSTD",
            "-co", "PREDICTOR=2",
            "-co", "LEVEL=22" # Max compression level
        ])

    try:
        subprocess.run(cmd, check=True)
        
        end_time = time.time()
        final_size = get_file_size(output_path)
        reduction = (1 - (final_size / original_size)) * 100
        
        print(f"\nSuccess!")
        print(f"Original: {original_size:.2f} MB")
        print(f"Compressed: {final_size:.2f} MB")
        print(f"Reduction: {reduction:.1f}%")
        print(f"Time: {end_time - start_time:.1f}s")
        print(f"Output: {output_path}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error compressing: {e}")
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
        except:
            pass
        return False

if __name__ == "__main__":
    # Interactive mode if no args
    if len(sys.argv) < 2:
        print("Model Kompresi GeoTIFF ke COG")
        print("=============================")
        input_file = input("Masukkan path file GeoTIFF input: ").strip().strip("'").strip('"')
        if not input_file:
            print("Path tidak boleh kosong.")
            sys.exit(1)
            
        method_choice = input("Pilih metode (1=Lossless [Default], 2=Lossy/LERC, 3=Visual/WEBP): ").strip()
        method = "lossless"
        if method_choice == "2": method = "lossy"
        if method_choice == "3": method = "visual"
        
        base, ext = os.path.splitext(input_file)
        output_file = f"{base}_cog{ext}"
        print(f"Output akan disimpan ke: {output_file}")
        
        compress_cog(input_file, output_file, method)
        sys.exit(0)

    # Command line mode
    input_file = sys.argv[1]
    
    if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
        output_file = sys.argv[2]
    else:
        base, ext = os.path.splitext(input_file)
        output_file = f"{base}_cog{ext}"

    # Simple arg parsing
    method = "lossless"
    for arg in sys.argv:
        if arg.startswith("--method="):
            method = arg.split("=")[1]
            break

    compress_cog(input_file, output_file, method)
