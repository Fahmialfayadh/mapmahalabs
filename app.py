import csv
import json
import os
import shutil
import subprocess
import threading
import uuid
import zipfile
import pycountry

import boto3
import requests
from botocore.config import Config
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB max
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('temp_tiles', exist_ok=True)

# ============================
# Cloudflare Configuration
# ============================

# R2 Storage (S3-compatible)
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "map-tiles")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")

# D1 Database
D1_API_TOKEN = os.getenv("D1_API_TOKEN")
D1_ACCOUNT_ID = os.getenv("D1_ACCOUNT_ID")
D1_DATABASE_ID = os.getenv("D1_DATABASE_ID")

# Initialize R2 client
r2_client = None
if R2_ACCOUNT_ID and R2_ACCESS_KEY and R2_SECRET_KEY:
    try:
        r2_client = boto3.client(
            's3',
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        print("✓ R2 client initialized")
    except Exception as e:
        print(f"Warning: R2 init failed: {e}")

# Task progress tracking
conversion_tasks = {}

# Generate Country Name Mapping (ISO2 & ISO3 -> Name)
COUNTRY_MAPPING = {}
for country in pycountry.countries:
    if hasattr(country, 'alpha_2'):
        COUNTRY_MAPPING[country.alpha_2] = country.name
    if hasattr(country, 'alpha_3'):
        COUNTRY_MAPPING[country.alpha_3] = country.name

# Manually add Indonesia Provinces if needed, or handle in JS
# For now just countries as requested


# ============================
# D1 Schema Migration
# ============================

# Add missing columns to D1 tables if needed.
def migrate_d1_schema():
    print("Checking D1 schema migration...")
    
    if not all([D1_API_TOKEN, D1_ACCOUNT_ID, D1_DATABASE_ID]):
        return

    # Check/Migrate source_link
    # d1_query returns None if error (e.g. column missing), empty list if success but no data
    res = d1_query("SELECT source_link FROM map_layers LIMIT 1")
    if res is None:
        print("Migrating: Adding source_link column...")
        d1_query("ALTER TABLE map_layers ADD COLUMN source_link TEXT", is_select=False)

    # Check/Migrate layer_type (existing logic)
    url = f"https://api.cloudflare.com/client/v4/accounts/{D1_ACCOUNT_ID}/d1/database/{D1_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {D1_API_TOKEN}",
        "Content-Type": "application/json"
    }
    # ... rest of existing migration if needed, but easier to just append the new column check above
    print("✓ Schema migration checks complete")




# ============================
# D1 Database Functions
# ============================

def d1_query(sql, params=None, is_select=True):
    """Execute SQL query on Cloudflare D1.

    Args:
        sql: SQL query string
        params: Query parameters
        is_select: If True, returns results list. If False, returns True/False for success.
    """
    if not all([D1_API_TOKEN, D1_ACCOUNT_ID, D1_DATABASE_ID]):
        print("D1 error: Missing credentials (D1_API_TOKEN, D1_ACCOUNT_ID, or D1_DATABASE_ID)")
        return None if is_select else False

    url = f"https://api.cloudflare.com/client/v4/accounts/{D1_ACCOUNT_ID}/d1/database/{D1_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {D1_API_TOKEN}",
        "Content-Type": "application/json"
    }

    body = {"sql": sql}
    if params:
        body["params"] = params

    try:
        response = requests.post(url, headers=headers, json=body)
        data = response.json()
        print(f"D1 response: success={data.get('success')}, sql={sql[:50]}...")

        if data.get("success"):
            if is_select:
                return data.get("result", [{}])[0].get("results", [])
            else:
                return True
        else:
            print(f"D1 error: {data.get('errors')}")
            return None if is_select else False
    except Exception as e:
        print(f"D1 request error: {e}")
        return None if is_select else False


def get_layers():
    """Get all layers from D1."""
    result = d1_query("SELECT * FROM map_layers ORDER BY created_at DESC", is_select=True)
    print(f"get_layers: Found {len(result) if result else 0} layers")
    return result if result else []


def insert_layer(name, folder_path, description="", source_link="", layer_type="tiles"):
    """Insert a new layer into D1."""
    sql = "INSERT INTO map_layers (id, name, folder_path, description, source_link, layer_type) VALUES (?, ?, ?, ?, ?, ?)"
    layer_id = str(uuid.uuid4())
    success = d1_query(sql, [layer_id, name, folder_path, description, source_link, layer_type], is_select=False)
    if success:
        print(f"✓ Layer '{name}' saved to D1 with ID: {layer_id}")
    else:
        print(f"✗ Failed to save layer '{name}' to D1")
    return layer_id if success else None


def delete_layer(layer_id):
    """Delete a layer from D1."""
    success = d1_query("DELETE FROM map_layers WHERE id = ?", [layer_id], is_select=False)
    print(f"delete_layer: {'success' if success else 'failed'} for ID {layer_id}")
    return success


def update_layer(layer_id, name=None, description=None, source_link=None):
    """Update a layer's metadata in D1."""
    # Build dynamic UPDATE query based on provided fields
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if source_link is not None:
        updates.append("source_link = ?")
        params.append(source_link)
    
    if not updates:
        return False
    
    params.append(layer_id)
    sql = f"UPDATE map_layers SET {', '.join(updates)} WHERE id = ?"
    success = d1_query(sql, params, is_select=False)
    print(f"update_layer: {'success' if success else 'failed'} for ID {layer_id}")
    return success


# Run migration on startup (after DB functions are defined)
migrate_d1_schema()

# ============================
# R2 Storage Functions
# ============================

def check_gdal():
    """Check if GDAL is installed."""
    try:
        subprocess.run(["gdal2tiles.py", "--version"], capture_output=True, check=True)
        return True
    except:
        return False


def upload_to_r2(local_path, remote_path):
    """Upload a single file to R2."""
    if not r2_client:
        return False
    try:
        r2_client.upload_file(
            local_path, R2_BUCKET, remote_path,
            ExtraArgs={'ContentType': 'image/png'}
        )
        return True
    except Exception as e:
        print(f"R2 upload error: {e}")
        return False


def upload_tiles_to_r2(layer_name, tiles_dir, task_id=None):
    """Upload all tiles to R2."""
    if not r2_client:
        return False, "R2 tidak terhubung"

    total = sum(1 for r, d, f in os.walk(tiles_dir) for x in f if x.endswith('.png'))
    if total == 0:
        return False, "Tidak ada tiles PNG"

    uploaded = 0
    for root, dirs, files in os.walk(tiles_dir):
        for file in files:
            if not file.endswith('.png'):
                continue

            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, tiles_dir)
            remote_path = f"{layer_name}/{rel_path}"

            if upload_to_r2(local_path, remote_path):
                uploaded += 1
                if task_id and uploaded % 50 == 0:
                    conversion_tasks[task_id] = {
                        'status': 'uploading',
                        'progress': int((uploaded / total) * 100),
                        'detail': f'{uploaded}/{total} tiles'
                    }

    return True, f"{uploaded} tiles uploaded"


# ============================
# Background Tasks
# ============================

def process_xyz_zip(task_id, zip_path, layer_name, description, source_link=""):
    """Process XYZ tiles ZIP."""
    global conversion_tasks
    try:
        conversion_tasks[task_id] = {'status': 'uploading', 'progress': 0, 'detail': 'Extracting...'}

        extract_dir = f"temp_tiles/{layer_name}_extract"
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)

        # Find tiles dir
        tiles_dir = extract_dir
        contents = os.listdir(extract_dir)
        if len(contents) == 1 and os.path.isdir(os.path.join(extract_dir, contents[0])):
            tiles_dir = os.path.join(extract_dir, contents[0])

        success, msg = upload_tiles_to_r2(layer_name, tiles_dir, task_id)

        if success:
            insert_layer(layer_name, layer_name, description or "XYZ tiles layer", source_link=source_link)
            conversion_tasks[task_id] = {'status': 'done', 'progress': 100, 'message': f'Layer "{layer_name}" berhasil!'}
        else:
            conversion_tasks[task_id] = {'status': 'error', 'error': msg}

        shutil.rmtree(extract_dir, ignore_errors=True)
        os.remove(zip_path)
    except Exception as e:
        conversion_tasks[task_id] = {'status': 'error', 'error': str(e)}



def process_csv_choropleth(task_id, csv_path, layer_name, description, value_col_name=None, source_link=""):
    """
    Process CSV for Choropleth.
    Supports:
    1. World Countries (auto-detected via ISO codes)
    2. Indonesian Provinces (auto-detected via 'provinsi' column) -> Uses Polygon GeoJSON
    """
    global conversion_tasks
    
    try:
        conversion_tasks[task_id] = {'status': 'converting', 'progress': 10, 'detail': 'Reading CSV for choropleth...'}
        
        # Read all rows first to analyze structure
        rows = []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
        
        if not rows:
            conversion_tasks[task_id] = {'status': 'error', 'error': 'CSV kosong'}
            os.remove(csv_path)
            return

        # Detect columns
        year_candidates = ['Year', 'year', 'YEAR', 'TIME_PERIOD', 'Date', 'date', 'TIME', 
                          'TIMEE', 'Timee', 'timee', 'TAHUN', 'Tahun', 'tahun']
        country_candidates = ['REF_AREA', 'Code', 'code', 'ISO2', 'ISO3', 'ISO_A2', 'ISO_A3',
                              'country_code', 'CountryCode', 'COUNTRY', 'Country', 'country',
                              'iso_code', 'ISO_CODE', 'iso2', 'iso3']
        indo_candidates = ['provinsi', 'PROVINSI', 'province', 'daerah', 'Propinsi', 'location', 'region']
        value_candidates = ['Value', 'value', 'VALUE', 'OBS_VALUE', 'GDP', 'gdp', 
                           'GDP per capita, PPP (constant 2021 international $)',
                           'Amount', 'amount', 'Count', 'count', 'Total', 'total']
        
        # Prioritize Indonesian provinces if found
        indo_col = next((h for h in headers if h in indo_candidates), None)
        country_col = next((h for h in headers if h in country_candidates), None)
        
        use_indo_geojson = False
        geojson_file = None

        if indo_col:
            use_indo_geojson = True
            country_col = indo_col # Reuse variable for simplicity
            conversion_tasks[task_id] = {'status': 'converting', 'progress': 20,
                                            'detail': f'Using Indonesian provinces from "{indo_col}"...'}
        elif not country_col:
             # Fallback: try to find any column that looks like a country/region
             for h in headers:
                 first_val = rows[0].get(h, '').lower()
                 if 'indonesia' in first_val or 'jawa' in first_val or 'sumatera' in first_val:
                     country_col = h
                     use_indo_geojson = True
                     break
        
        year_col = next((h for h in headers if h in year_candidates), None)
        
        # Use explicit value column if provided
        value_col = None
        if value_col_name:
            if value_col_name in headers:
                value_col = value_col_name
                conversion_tasks[task_id] = {'status': 'converting', 'progress': 25, 
                                             'detail': f'Using column "{value_col}" for values'}
            else:
                 conversion_tasks[task_id] = {'status': 'error', 
                                              'error': f'Kolom "{value_col_name}" tidak ditemukan di CSV'}
                 os.remove(csv_path)
                 return
        else:
            # Auto-detect value column
            value_col = next((h for h in headers if h in value_candidates), None)
        
        # If no specific value column, try to find a numeric column
        if not value_col:
            for h in headers:
                if h not in [year_col, country_col]:
                    # Check if column has numeric values
                    sample_val = rows[0].get(h, '')
                    try:
                        float(sample_val.replace(',', ''))
                        value_col = h
                        break
                    except:
                        continue
        
        if not country_col:
            conversion_tasks[task_id] = {'status': 'error', 
                                         'error': f'Kolom negara/wilayah tidak ditemukan. Headers: {headers}'}
            os.remove(csv_path)
            return
        
        if not value_col:
            conversion_tasks[task_id] = {'status': 'error', 
                                         'error': f'Kolom nilai tidak ditemukan. Headers: {headers}'}
            os.remove(csv_path)
            return
        
        conversion_tasks[task_id] = {'status': 'converting', 'progress': 30, 
                                     'detail': f'Parsing: {country_col}, {year_col or "no year"}, {value_col}'}
        
        # Build data structure
        data = {}
        years_set = set()
        min_value = float('inf')
        max_value = float('-inf')
        
        for row in rows:
            region = str(row.get(country_col, '')).strip().upper()
            
            # Normalization for Indonesia Provinces if needed (basic)
            if use_indo_geojson:
                region = region.replace('PROVINSI', '').strip()
                # Handle common variations if necessary (e.g. "DIY" -> "DAERAH ISTIMEWA YOGYAKARTA")
                if region == 'DIY' or region == 'DI YOGYAKARTA': region = 'DAERAH ISTIMEWA YOGYAKARTA'
                if region == 'DKI' or region == 'DKI JAKARTA': region = 'DKI JAKARTA'

            if not region:
                continue
                
            # Get year (default to 'all' if no year column)
            if year_col:
                year_raw = str(row.get(year_col, '')).strip()
                # Extract just the year if it's a date
                if '-' in year_raw:
                    year = year_raw.split('-')[0]
                else:
                    year = year_raw
            else:
                year = 'all'
            
            # Get value
            try:
                val_raw = str(row.get(value_col, '')).replace(',', '').strip()
                value = float(val_raw) if val_raw else 0
            except:
                continue
            
            # Store data
            if region not in data:
                data[region] = {}
            data[region][year] = value
            years_set.add(year)
            
            if value < min_value:
                min_value = value
            if value > max_value:
                max_value = value
        
        if not data:
            conversion_tasks[task_id] = {'status': 'error', 'error': 'Tidak ada data valid'}
            os.remove(csv_path)
            return
        
        # Sort years
        years = sorted(list(years_set), key=lambda x: int(x) if x.isdigit() else 0)
        
        geo_upload_msg = ""
        # IF INDONESIA: Upload the static GeoJSON to R2 for this layer
        if use_indo_geojson:
            static_geo_path = os.path.join(app.root_path, 'static', 'data', 'indonesia-provinces.geojson')
            if os.path.exists(static_geo_path):
                geojson_filename = "indonesia-provinces.geojson"
                if r2_client:
                    remote_geo_path = f"{layer_name}/{geojson_filename}"
                    print(f"Uploading Geometry to R2: {static_geo_path} -> {remote_geo_path}")
                    r2_client.upload_file(
                        static_geo_path, R2_BUCKET, remote_geo_path,
                        ExtraArgs={'ContentType': 'application/json'}
                    )
                    geo_upload_msg = " + Geometry Uploaded"
            else:
                print(f"Warning: {static_geo_path} not found. Layer might not render correctly.")

        conversion_tasks[task_id] = {'status': 'converting', 'progress': 60, 
                                     'detail': f'{len(data)} regions, {len(years)} years'}
        
        # Create choropleth data structure
        choropleth_data = {
            'type': 'choropleth',
            'years': years,
            'value_column': value_col,
            'country_column': country_col,
            'data': data,
            'min_value': min_value if min_value != float('inf') else 0,
            'max_value': max_value if max_value != float('-inf') else 100,
            'geojson_file': geojson_filename if use_indo_geojson else None
        }
        
        # Save and upload to R2
        json_path = f"temp_tiles/{layer_name}_choropleth.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(choropleth_data, f)
        
        if r2_client:
            try:
                remote_path = f"{layer_name}/choropleth.json"
                print(f"Uploading choropleth to R2: {json_path} -> {R2_BUCKET}/{remote_path}")
                r2_client.upload_file(
                    json_path, R2_BUCKET, remote_path,
                    ExtraArgs={'ContentType': 'application/json'}
                )
                print(f"✓ Choropleth upload successful: {remote_path}")
                
                conversion_tasks[task_id] = {'status': 'converting', 'progress': 90, 'detail': 'Saving metadata...'}
                
                # Use 'choropleth' as layer_type
                layer_id = insert_layer(layer_name, layer_name, 
                                       description or f"Heatmap ({len(data)} regions, {len(years)} periods)", 
                                       source_link=source_link,
                                       layer_type='choropleth')
                
                if layer_id:
                    conversion_tasks[task_id] = {
                        'status': 'done', 
                        'progress': 100, 
                        'message': f'Layer "{layer_name}" berhasil! ({len(data)} wilayah)'
                    }
                else:
                    conversion_tasks[task_id] = {'status': 'error', 'error': 'R2 OK, tapi D1 gagal'}
            except Exception as e:
                print(f"✗ R2 upload error: {str(e)}")
                conversion_tasks[task_id] = {'status': 'error', 'error': f'Upload error: {str(e)}'}
        else:
            conversion_tasks[task_id] = {'status': 'error', 'error': 'R2 tidak terhubung'}
        
        # Cleanup
        if os.path.exists(json_path):
            os.remove(json_path)
        os.remove(csv_path)
        
    except Exception as e:
        print(f"Choropleth processing error: {str(e)}")
        conversion_tasks[task_id] = {'status': 'error', 'error': str(e)}


def process_csv(task_id, csv_path, layer_name, description, lat_col, lon_col, popup_col, source_link=""):
    """Process CSV file - convert to GeoJSON and upload to R2.

    Supports:
    - Direct lat/lon columns
    - Country code geocoding (ISO2, ISO3, REF_AREA)
    """
    global conversion_tasks

    # Country centroids mapping (ISO2/ISO3 -> [lat, lon])
    COUNTRY_CENTROIDS = {

        # ISO2 codes
        'AF': [33.93911, 67.709953], 'AL': [41.153332, 20.168331], 'DZ': [28.033886, 1.659626],
        'AD': [42.546245, 1.601554], 'AO': [-11.202692, 17.873887], 'AR': [-38.416097, -63.616672],
        'AM': [40.069099, 45.038189], 'AU': [-25.274398, 133.775136], 'AT': [47.516231, 14.550072],
        'AZ': [40.143105, 47.576927], 'BS': [25.03428, -77.39628], 'BH': [26.0667, 50.5577],
        'BD': [23.684994, 90.356331], 'BY': [53.709807, 27.953389], 'BE': [50.503887, 4.469936],
        'BZ': [17.189877, -88.49765], 'BJ': [9.30769, 2.315834], 'BT': [27.514162, 90.433601],
        'BO': [-16.290154, -63.588653], 'BA': [43.915886, 17.679076], 'BW': [-22.328474, 24.684866],
        'BR': [-14.235004, -51.92528], 'BN': [4.535277, 114.727669], 'BG': [42.733883, 25.48583],
        'BF': [12.238333, -1.561593], 'BI': [-3.373056, 29.918886], 'KH': [12.565679, 104.990963],
        'CM': [7.369722, 12.354722], 'CA': [56.130366, -106.346771], 'CV': [16.002082, -24.013197],
        'CF': [6.611111, 20.939444], 'TD': [15.454166, 18.732207], 'CL': [-35.675147, -71.542969],
        'CN': [35.86166, 104.195397], 'CO': [4.570868, -74.297333], 'KM': [-11.875001, 43.872219],
        'CG': [-0.228021, 15.827659], 'CD': [-4.038333, 21.758664], 'CR': [9.748917, -83.753428],
        'CI': [7.539989, -5.54708], 'HR': [45.1, 15.2], 'CU': [21.521757, -77.781167],
        'CY': [35.126413, 33.429859], 'CZ': [49.817492, 15.472962], 'DK': [56.26392, 9.501785],
        'DJ': [11.825138, 42.590275], 'DM': [15.414999, -61.370976], 'DO': [18.735693, -70.162651],
        'EC': [-1.831239, -78.183406], 'EG': [26.820553, 30.802498], 'SV': [13.794185, -88.89653],
        'GQ': [1.650801, 10.267895], 'ER': [15.179384, 39.782334], 'EE': [58.595272, 25.013607],
        'ET': [9.145, 40.489673], 'FJ': [-17.713371, 178.065032], 'FI': [61.92411, 25.748151],
        'FR': [46.227638, 2.213749], 'GA': [-0.803689, 11.609444], 'GM': [13.443182, -15.310139],
        'GE': [42.315407, 43.356892], 'DE': [51.165691, 10.451526], 'GH': [7.946527, -1.023194],
        'GR': [39.074208, 21.824312], 'GT': [15.783471, -90.230759], 'GN': [9.945587, -9.696645],
        'GW': [11.803749, -15.180413], 'GY': [4.860416, -58.93018], 'HT': [18.971187, -72.285215],
        'HN': [15.199999, -86.241905], 'HU': [47.162494, 19.503304], 'IS': [64.963051, -19.020835],
        'IN': [20.593684, 78.96288], 'ID': [-0.789275, 113.921327], 'IR': [32.427908, 53.688046],
        'IQ': [33.223191, 43.679291], 'IE': [53.41291, -8.24389], 'IL': [31.046051, 34.851612],
        'IT': [41.87194, 12.56738], 'JM': [18.109581, -77.297508], 'JP': [36.204824, 138.252924],
        'JO': [30.585164, 36.238414], 'KZ': [48.019573, 66.923684], 'KE': [-0.023559, 37.906193],
        'KI': [-3.370417, -168.734039], 'KP': [40.339852, 127.510093], 'KR': [35.907757, 127.766922],
        'KW': [29.31166, 47.481766], 'KG': [41.20438, 74.766098], 'LA': [19.85627, 102.495496],
        'LV': [56.879635, 24.603189], 'LB': [33.854721, 35.862285], 'LS': [-29.609988, 28.233608],
        'LR': [6.428055, -9.429499], 'LY': [26.3351, 17.228331], 'LI': [47.166, 9.555373],
        'LT': [55.169438, 23.881275], 'LU': [49.815273, 6.129583], 'MK': [41.512386, 21.747419],
        'MG': [-18.766947, 46.869107], 'MW': [-13.254308, 34.301525], 'MY': [4.210484, 101.975766],
        'MV': [3.202778, 73.22068], 'ML': [17.570692, -3.996166], 'MT': [35.937496, 14.375416],
        'MR': [21.00789, -10.940835], 'MU': [-20.348404, 57.552152], 'MX': [23.634501, -102.552784],
        'MD': [47.411631, 28.369885], 'MC': [43.750298, 7.412841], 'MN': [46.862496, 103.846656],
        'ME': [42.708678, 19.37439], 'MA': [31.791702, -7.09262], 'MZ': [-18.665695, 35.529562],
        'MM': [21.913965, 95.956223], 'NA': [-22.95764, 18.49041], 'NP': [28.394857, 84.124008],
        'NL': [52.132633, 5.291266], 'NZ': [-40.900557, 174.885971], 'NI': [12.865416, -85.207229],
        'NE': [17.607789, 8.081666], 'NG': [9.081999, 8.675277], 'NO': [60.472024, 8.468946],
        'OM': [21.512583, 55.923255], 'PK': [30.375321, 69.345116], 'PA': [8.537981, -80.782127],
        'PG': [-6.314993, 143.95555], 'PY': [-23.442503, -58.443832], 'PE': [-9.189967, -75.015152],
        'PH': [12.879721, 121.774017], 'PL': [51.919438, 19.145136], 'PT': [39.399872, -8.224454],
        'QA': [25.354826, 51.183884], 'RO': [45.943161, 24.96676], 'RU': [61.52401, 105.318756],
        'RW': [-1.940278, 29.873888], 'SA': [23.885942, 45.079162], 'SN': [14.497401, -14.452362],
        'RS': [44.016521, 21.005859], 'SL': [8.460555, -11.779889], 'SG': [1.352083, 103.819836],
        'SK': [48.669026, 19.699024], 'SI': [46.151241, 14.995463], 'SB': [-9.64571, 160.156194],
        'SO': [5.152149, 46.199616], 'ZA': [-30.559482, 22.937506], 'SS': [6.876991, 31.306978],
        'ES': [40.463667, -3.74922], 'LK': [7.873054, 80.771797], 'SD': [12.862807, 30.217636],
        'SR': [3.919305, -56.027783], 'SZ': [-26.522503, 31.465866], 'SE': [60.128161, 18.643501],
        'CH': [46.818188, 8.227512], 'SY': [34.802075, 38.996815], 'TW': [23.69781, 120.960515],
        'TJ': [38.861034, 71.276093], 'TZ': [-6.369028, 34.888822], 'TH': [15.870032, 100.992541],
        'TL': [-8.874217, 125.727539], 'TG': [8.619543, 0.824782], 'TN': [33.886917, 9.537499],
        'TR': [38.963745, 35.243322], 'TM': [38.969719, 59.556278], 'UG': [1.373333, 32.290275],
        'UA': [48.379433, 31.16558], 'AE': [23.424076, 53.847818], 'GB': [55.378051, -3.435973],
        'US': [37.09024, -95.712891], 'UY': [-32.522779, -55.765835], 'UZ': [41.377491, 64.585262],
        'VU': [-15.376706, 166.959158], 'VE': [6.42375, -66.58973], 'VN': [14.058324, 108.277199],
        'YE': [15.552727, 48.516388], 'ZM': [-13.133897, 27.849332], 'ZW': [-19.015438, 29.154857],
        # ISO3 codes (mapped to same coordinates)
        'AFG': [33.93911, 67.709953], 'ALB': [41.153332, 20.168331], 'DZA': [28.033886, 1.659626],
        'AND': [42.546245, 1.601554], 'AGO': [-11.202692, 17.873887], 'ARG': [-38.416097, -63.616672],
        'ARM': [40.069099, 45.038189], 'AUS': [-25.274398, 133.775136], 'AUT': [47.516231, 14.550072],
        'AZE': [40.143105, 47.576927], 'BHS': [25.03428, -77.39628], 'BHR': [26.0667, 50.5577],
        'BGD': [23.684994, 90.356331], 'BLR': [53.709807, 27.953389], 'BEL': [50.503887, 4.469936],
        'BLZ': [17.189877, -88.49765], 'BEN': [9.30769, 2.315834], 'BTN': [27.514162, 90.433601],
        'BOL': [-16.290154, -63.588653], 'BIH': [43.915886, 17.679076], 'BWA': [-22.328474, 24.684866],
        'BRA': [-14.235004, -51.92528], 'BRN': [4.535277, 114.727669], 'BGR': [42.733883, 25.48583],
        'BFA': [12.238333, -1.561593], 'BDI': [-3.373056, 29.918886], 'KHM': [12.565679, 104.990963],
        'CMR': [7.369722, 12.354722], 'CAN': [56.130366, -106.346771], 'CPV': [16.002082, -24.013197],
        'CAF': [6.611111, 20.939444], 'TCD': [15.454166, 18.732207], 'CHL': [-35.675147, -71.542969],
        'CHN': [35.86166, 104.195397], 'COL': [4.570868, -74.297333], 'COM': [-11.875001, 43.872219],
        'COG': [-0.228021, 15.827659], 'COD': [-4.038333, 21.758664], 'CRI': [9.748917, -83.753428],
        'CIV': [7.539989, -5.54708], 'HRV': [45.1, 15.2], 'CUB': [21.521757, -77.781167],
        'CYP': [35.126413, 33.429859], 'CZE': [49.817492, 15.472962], 'DNK': [56.26392, 9.501785],
        'DJI': [11.825138, 42.590275], 'DMA': [15.414999, -61.370976], 'DOM': [18.735693, -70.162651],
        'ECU': [-1.831239, -78.183406], 'EGY': [26.820553, 30.802498], 'SLV': [13.794185, -88.89653],
        'GNQ': [1.650801, 10.267895], 'ERI': [15.179384, 39.782334], 'EST': [58.595272, 25.013607],
        'ETH': [9.145, 40.489673], 'FJI': [-17.713371, 178.065032], 'FIN': [61.92411, 25.748151],
        'FRA': [46.227638, 2.213749], 'GAB': [-0.803689, 11.609444], 'GMB': [13.443182, -15.310139],
        'GEO': [42.315407, 43.356892], 'DEU': [51.165691, 10.451526], 'GHA': [7.946527, -1.023194],
        'GRC': [39.074208, 21.824312], 'GTM': [15.783471, -90.230759], 'GIN': [9.945587, -9.696645],
        'GNB': [11.803749, -15.180413], 'GUY': [4.860416, -58.93018], 'HTI': [18.971187, -72.285215],
        'HND': [15.199999, -86.241905], 'HUN': [47.162494, 19.503304], 'ISL': [64.963051, -19.020835],
        'IND': [20.593684, 78.96288], 'IDN': [-0.789275, 113.921327], 'IRN': [32.427908, 53.688046],
        'IRQ': [33.223191, 43.679291], 'IRL': [53.41291, -8.24389], 'ISR': [31.046051, 34.851612],
        'ITA': [41.87194, 12.56738], 'JAM': [18.109581, -77.297508], 'JPN': [36.204824, 138.252924],
        'JOR': [30.585164, 36.238414], 'KAZ': [48.019573, 66.923684], 'KEN': [-0.023559, 37.906193],
        'KIR': [-3.370417, -168.734039], 'PRK': [40.339852, 127.510093], 'KOR': [35.907757, 127.766922],
        'KWT': [29.31166, 47.481766], 'KGZ': [41.20438, 74.766098], 'LAO': [19.85627, 102.495496],
        'LVA': [56.879635, 24.603189], 'LBN': [33.854721, 35.862285], 'LSO': [-29.609988, 28.233608],
        'LBR': [6.428055, -9.429499], 'LBY': [26.3351, 17.228331], 'LIE': [47.166, 9.555373],
        'LTU': [55.169438, 23.881275], 'LUX': [49.815273, 6.129583], 'MKD': [41.512386, 21.747419],
        'MDG': [-18.766947, 46.869107], 'MWI': [-13.254308, 34.301525], 'MYS': [4.210484, 101.975766],
        'MDV': [3.202778, 73.22068], 'MLI': [17.570692, -3.996166], 'MLT': [35.937496, 14.375416],
        'MRT': [21.00789, -10.940835], 'MUS': [-20.348404, 57.552152], 'MEX': [23.634501, -102.552784],
        'MDA': [47.411631, 28.369885], 'MCO': [43.750298, 7.412841], 'MNG': [46.862496, 103.846656],
        'MNE': [42.708678, 19.37439], 'MAR': [31.791702, -7.09262], 'MOZ': [-18.665695, 35.529562],
        'MMR': [21.913965, 95.956223], 'NAM': [-22.95764, 18.49041], 'NPL': [28.394857, 84.124008],
        'NLD': [52.132633, 5.291266], 'NZL': [-40.900557, 174.885971], 'NIC': [12.865416, -85.207229],
        'NER': [17.607789, 8.081666], 'NGA': [9.081999, 8.675277], 'NOR': [60.472024, 8.468946],
        'OMN': [21.512583, 55.923255], 'PAK': [30.375321, 69.345116], 'PAN': [8.537981, -80.782127],
        'PNG': [-6.314993, 143.95555], 'PRY': [-23.442503, -58.443832], 'PER': [-9.189967, -75.015152],
        'PHL': [12.879721, 121.774017], 'POL': [51.919438, 19.145136], 'PRT': [39.399872, -8.224454],
        'QAT': [25.354826, 51.183884], 'ROU': [45.943161, 24.96676], 'RUS': [61.52401, 105.318756],
        'RWA': [-1.940278, 29.873888], 'SAU': [23.885942, 45.079162], 'SEN': [14.497401, -14.452362],
        'SRB': [44.016521, 21.005859], 'SLE': [8.460555, -11.779889], 'SGP': [1.352083, 103.819836],
        'SVK': [48.669026, 19.699024], 'SVN': [46.151241, 14.995463], 'SLB': [-9.64571, 160.156194],
        'SOM': [5.152149, 46.199616], 'ZAF': [-30.559482, 22.937506], 'SSD': [6.876991, 31.306978],
        'ESP': [40.463667, -3.74922], 'LKA': [7.873054, 80.771797], 'SDN': [12.862807, 30.217636],
        'SUR': [3.919305, -56.027783], 'SWZ': [-26.522503, 31.465866], 'SWE': [60.128161, 18.643501],
        'CHE': [46.818188, 8.227512], 'SYR': [34.802075, 38.996815], 'TWN': [23.69781, 120.960515],
        'TJK': [38.861034, 71.276093], 'TZA': [-6.369028, 34.888822], 'THA': [15.870032, 100.992541],
        'TLS': [-8.874217, 125.727539], 'TGO': [8.619543, 0.824782], 'TUN': [33.886917, 9.537499],
        'TUR': [38.963745, 35.243322], 'TKM': [38.969719, 59.556278], 'UGA': [1.373333, 32.290275],
        'UKR': [48.379433, 31.16558], 'ARE': [23.424076, 53.847818], 'GBR': [55.378051, -3.435973],
        'USA': [37.09024, -95.712891], 'URY': [-32.522779, -55.765835], 'UZB': [41.377491, 64.585262],
        'VUT': [-15.376706, 166.959158], 'VEN': [6.42375, -66.58973], 'VNM': [14.058324, 108.277199],
        'YEM': [15.552727, 48.516388], 'ZMB': [-13.133897, 27.849332], 'ZWE': [-19.015438, 29.154857],
        # Common numeric codes (used in UN data)
        '4': [33.93911, 67.709953], '8': [41.153332, 20.168331], '12': [28.033886, 1.659626],
        '36': [-25.274398, 133.775136], '40': [47.516231, 14.550072], '50': [23.684994, 90.356331],
        '76': [-14.235004, -51.92528], '124': [56.130366, -106.346771], '156': [35.86166, 104.195397],
        '250': [46.227638, 2.213749], '276': [51.165691, 10.451526], '356': [20.593684, 78.96288],
        '360': [-0.789275, 113.921327], '392': [36.204824, 138.252924], '410': [35.907757, 127.766922],
        '484': [23.634501, -102.552784], '528': [52.132633, 5.291266], '643': [61.52401, 105.318756],
        '710': [-30.559482, 22.937506], '826': [55.378051, -3.435973], '840': [37.09024, -95.712891],
    }

    # Indonesian Province Coordinates (Centroids)
    INDONESIA_PROVINCES = {
        'ACEH': [4.695135, 96.749399],
        'SUMATERA UTARA': [2.115355, 99.545097],
        'SUMATERA BARAT': [-0.739940, 100.800005],
        'RIAU': [0.293347, 101.706829],
        'JAMBI': [-1.610123, 103.613120],
        'SUMATERA SELATAN': [-3.319437, 103.914399],
        'BENGKULU': [-3.577847, 102.346388],
        'LAMPUNG': [-4.558585, 105.406808],
        'KEPULAUAN BANGKA BELITUNG': [-2.741051, 106.440587],
        'KEPULAUAN RIAU': [3.945651, 108.142867],
        'DKI JAKARTA': [-6.214620, 106.845130],
        'JAWA BARAT': [-6.920432, 107.603708],
        'JAWA TENGAH': [-7.150975, 110.140259],
        'DI YOGYAKARTA': [-7.875385, 110.426209],
        'JAWA TIMUR': [-7.536064, 112.238402],
        'BANTEN': [-6.405817, 106.064018],
        'BALI': [-8.409518, 115.188916],
        'NUSA TENGGARA BARAT': [-8.652933, 117.361648],
        'NUSA TENGGARA TIMUR': [-8.657382, 121.079370],
        'KALIMANTAN BARAT': [-0.278781, 111.475285],
        'KALIMANTAN TENGAH': [-1.681488, 113.382355],
        'KALIMANTAN SELATAN': [-3.092642, 115.283759],
        'KALIMANTAN TIMUR': [0.538659, 116.419389],
        'KALIMANTAN UTARA': [3.073093, 116.041389],
        'SULAWESI UTARA': [0.624693, 123.975002],
        'SULAWESI TENGAH': [-1.430025, 121.445618],
        'SULAWESI SELATAN': [-3.668799, 119.974053],
        'SULAWESI TENGGARA': [-4.144910, 122.174605],
        'GORONTALO': [0.699937, 122.446724],
        'SULAWESI BARAT': [-2.844137, 119.232078],
        'MALUKU': [-3.238462, 130.145273],
        'MALUKU UTARA': [1.570999, 127.808769],
        'PAPUA BARAT': [-1.336115, 133.174716],
        'PAPUA': [-4.269928, 138.080353],
        'PAPUA TENGAH': [-4.0, 136.0],
        'PAPUA PEGUNUNGAN': [-4.0, 139.5],
        'PAPUA SELATAN': [-7.0, 139.0],
        'PAPUA BARAT DAYA': [-1.0, 131.5],
    }

    try:
        conversion_tasks[task_id] = {'status': 'converting', 'progress': 10, 'detail': 'Reading CSV...'}

        features = []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

            # Auto-detect lat/lon columns if not specified
            if not lat_col:
                lat_candidates = ['latitude', 'lat', 'y', 'LAT', 'Latitude', 'LATITUDE']
                lat_col = next((h for h in headers if h in lat_candidates), None)
            if not lon_col:
                lon_candidates = ['longitude', 'lon', 'lng', 'x', 'long', 'LON', 'Longitude', 'LONGITUDE']
                lon_col = next((h for h in headers if h in lon_candidates), None)

            # If no lat/lon found, try country code columns
            country_col = None
            use_country_geocoding = False
            use_indo_geocoding = False

            if not lat_col or not lon_col:
                # Look for country code columns
                country_candidates = ['REF_AREA', 'REF_AREA_ISO2', 'REF_AREA_ISO3', 'ISO2', 'ISO3',
                                     'country_code', 'CountryCode', 'COUNTRY', 'Country', 'country',
                                     'iso_code', 'ISO_CODE', 'iso2', 'iso3', 'code','Code']
                
                # Look for Indonesian Province columns
                indo_candidates = ['provinsi', 'PROVINSI', 'province', 'Province', 'daerah', 'DAERAH', 'wilayah', 'WILAYAH']

                # Prioritize Indonesian provinces if found
                indo_col = next((h for h in headers if h in indo_candidates), None)
                country_col = next((h for h in headers if h in country_candidates), None)

                if indo_col:
                    use_indo_geocoding = True
                    country_col = indo_col # Reuse variable for simplicity
                    conversion_tasks[task_id] = {'status': 'converting', 'progress': 20,
                                                 'detail': f'Using Indonesian provinces from "{indo_col}"...'}
                elif country_col:
                    use_country_geocoding = True
                    conversion_tasks[task_id] = {'status': 'converting', 'progress': 20,
                                                 'detail': f'Using country codes from "{country_col}"...'}
                else:
                    conversion_tasks[task_id] = {'status': 'error',
                                                 'error': f'Kolom lat/lon, kode negara, atau provinsi tidak ditemukan. Headers: {headers}'}
                    os.remove(csv_path)
                    return
            else:
                conversion_tasks[task_id] = {'status': 'converting', 'progress': 30,
                                             'detail': f'Parsing data ({lat_col}, {lon_col})...'}

            row_count = 0
            skipped_countries = set()

            for row in reader:
                try:
                    if use_indo_geocoding:
                        # Geocode Indo Province
                        raw_val = str(row.get(country_col, '')).strip().upper()
                        # Cleanup common prefixes
                        clean_val = raw_val.replace('PROVINSI', '').strip()
                        
                        if clean_val in INDONESIA_PROVINCES:
                            lat, lon = INDONESIA_PROVINCES[clean_val]
                        # Try exact match with original just in case
                        elif raw_val in INDONESIA_PROVINCES:
                            lat, lon = INDONESIA_PROVINCES[raw_val]
                        else:
                            skipped_countries.add(raw_val)
                            continue

                    elif use_country_geocoding:
                        # Get coordinates from country code
                        country_code = str(row.get(country_col, '')).strip().upper()
                        if country_code in COUNTRY_CENTROIDS:
                            lat, lon = COUNTRY_CENTROIDS[country_code]
                        else:
                            skipped_countries.add(country_code)
                            continue
                    else:
                        lat = float(row.get(lat_col, 0))
                        lon = float(row.get(lon_col, 0))
                        if lat == 0 and lon == 0:
                            continue

                    # Build properties from all columns
                    exclude_cols = [lat_col, lon_col] if not (use_country_geocoding or use_indo_geocoding) else []
                    properties = {k: v for k, v in row.items() if k not in exclude_cols}

                    # Add popup content if specified
                    if popup_col and popup_col in row:
                        properties['_popup'] = row[popup_col]

                    feature = {
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [lon, lat]
                        },
                        'properties': properties
                    }
                    features.append(feature)
                    row_count += 1
                except (ValueError, TypeError):
                    continue

        if skipped_countries:
            print(f"Skipped unknown country codes: {skipped_countries}")

        if not features:
            conversion_tasks[task_id] = {'status': 'error', 'error': 'Tidak ada data valid ditemukan'}
            os.remove(csv_path)
            return

        mode_info = "country geocoding" if use_country_geocoding else "indo geocoding" if use_indo_geocoding else "coordinates"
        conversion_tasks[task_id] = {'status': 'converting', 'progress': 60,
                                     'detail': f'{row_count} titik ({mode_info}). Uploading...'}

        # Create GeoJSON
        geojson = {
            'type': 'FeatureCollection',
            'features': features
        }

        # Save temporarily and upload to R2
        geojson_path = f"temp_tiles/{layer_name}_data.geojson"
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f)

        # Upload to R2
        if r2_client:
            try:
                remote_path = f"{layer_name}/data.geojson"
                print(f"Uploading to R2: {geojson_path} -> {R2_BUCKET}/{remote_path}")
                r2_client.upload_file(
                    geojson_path, R2_BUCKET, remote_path,
                    ExtraArgs={'ContentType': 'application/json'}
                )
                print(f"✓ R2 upload successful: {remote_path}")

                conversion_tasks[task_id] = {'status': 'converting', 'progress': 90, 'detail': 'Saving metadata...'}

                # GeoJSON generation complete, now upload to R2
                # (For CSV geojson we just save the GeoJSON file, but for map we usually want tiles or just direct GeoJSON)
                # Here we will upload the geojson file to R2 so frontend can fetch it.
                
                # ... existing R2 upload logic ...
                # Assuming R2 upload is handled via api_layer_data fetch from D1/R2? 
                # Actually below logic uploads to R2.
                
                geojson_filename = "data.geojson"
                remote_path = f"{layer_name}/{geojson_filename}"
                
                if r2_client:
                    r2_client.put_object(
                         Bucket=R2_BUCKET,
                         Key=remote_path,
                         Body=json.dumps(geojson).encode('utf-8'),
                         ContentType='application/json'
                    )
                
                # Insert into D1
                layer_id = insert_layer(layer_name, layer_name, description or f"CSV layer ({row_count} points)", source_link=source_link, layer_type='geojson')

                if layer_id:
                    conversion_tasks[task_id] = {'status': 'done', 'progress': 100, 'message': f'Layer "{layer_name}" berhasil! ({row_count} titik)'}
                else:
                    conversion_tasks[task_id] = {'status': 'error', 'error': 'R2 upload OK, tapi D1 gagal menyimpan metadata'}
            except Exception as e:
                print(f"✗ R2 upload error: {str(e)}")
                conversion_tasks[task_id] = {'status': 'error', 'error': f'Upload error: {str(e)}'}
        else:
            print("✗ R2 client not connected")
            conversion_tasks[task_id] = {'status': 'error', 'error': 'R2 tidak terhubung'}

        # Cleanup
        if os.path.exists(geojson_path):
            os.remove(geojson_path)
        os.remove(csv_path)

    except Exception as e:
        conversion_tasks[task_id] = {'status': 'error', 'error': str(e)}


def process_geotiff(task_id, input_path, layer_name, description, zoom_min, zoom_max, source_link=""):
    """Process GeoTIFF - convert to 8-bit first then generate tiles."""
    global conversion_tasks
    import time

    # 1. Definisi fungsi log HARUS di paling atas biar bisa dipanggil
    def log(msg):
        """Log with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [GeoTIFF] {msg}")

    try:
        start_time = time.time()

        # Get file size for progress estimation
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)

        # -------------------------------------------------------------
        # 🔥 TAMBAHAN: PAKSA ZOOM (HARDCODE)
        # -------------------------------------------------------------
        # Kita paksa override di sini sebelum log pertama kali
        zoom_min = 0
        zoom_max = 12
        # -------------------------------------------------------------

        log("═══════════════════════════════════════════════════")
        log(f"Starting conversion: {os.path.basename(input_path)}")
        log(f"  File size: {file_size_mb:.2f} MB")
        log(f"  Layer name: {layer_name}")
        log(f"⚡ FORCE ZOOM: {zoom_min} - {zoom_max} (Anti Kerja Rodi)")
        log("═══════════════════════════════════════════════════")

        conversion_tasks[task_id] = {
            'status': 'converting',
            'progress': 0,
            'detail': f'Preparing ({file_size_mb:.1f}MB)...',
            'file_size_mb': file_size_mb
        }

        output_dir = f"temp_tiles/{layer_name}"
        os.makedirs(output_dir, exist_ok=True)

        # Step 1: Convert to 8-bit RGBA (preserves color palette!)
        # -expand rgba converts color table to RGBA bands (keeps colors!)
        vrt_path = f"temp_tiles/{layer_name}_temp.vrt"
        log("[Step 1/3] Converting to 8-bit RGBA...")
        step1_start = time.time()

        conversion_tasks[task_id] = {
            'status': 'converting',
            'progress': 10,
            'detail': f'Converting to 8-bit RGBA ({file_size_mb:.1f}MB)...'
        }

        # Try -expand rgba first (for color-indexed rasters)
        # If that fails, fallback to -ot Byte -scale (for float rasters)
        convert_result = subprocess.run([
            "gdal_translate", "-of", "VRT", "-ot", "Byte", "-scale", "-expand", "rgba",
            input_path, vrt_path
        ], capture_output=True, text=True)

        # If -expand rgba failed (raster has no color table), try without it
        if convert_result.returncode != 0:
            log("  Color table not found, trying standard 8-bit conversion...")
            convert_result = subprocess.run([
                "gdal_translate", "-of", "VRT", "-ot", "Byte", "-scale",
                input_path, vrt_path
            ], capture_output=True, text=True)

        step1_time = time.time() - step1_start

        if convert_result.returncode != 0:
            log(f"✗ 8-bit conversion FAILED after {step1_time:.1f}s")
            log(f"  Error: {convert_result.stderr}")
            conversion_tasks[task_id] = {'status': 'error', 'error': f'8-bit conversion failed: {convert_result.stderr}'}
            return

        log(f"✓ 8-bit conversion done in {step1_time:.1f}s")

        # Step 2: Generate tiles from VRT
        log(f"[Step 2/3] Generating tiles (zoom {zoom_min}-{zoom_max})...")
        step2_start = time.time()

        conversion_tasks[task_id] = {
            'status': 'converting',
            'progress': 30,
            'detail': f'Generating tiles (zoom {zoom_min}-{zoom_max})...'
        }

        result = subprocess.run([
            "gdal2tiles.py", 
            f"--zoom={zoom_min}-{zoom_max}", 
            "--xyz", 
            "--processes=4",
            "--resampling=average",
            vrt_path, output_dir
        ], capture_output=True, text=True)

        step2_time = time.time() - step2_start

        # Cleanup VRT
        if os.path.exists(vrt_path):
            os.remove(vrt_path)

        if result.returncode != 0:
            log(f"✗ Tile generation FAILED after {step2_time:.1f}s")
            log(f"  Error: {result.stderr}")
            conversion_tasks[task_id] = {'status': 'error', 'error': f'GDAL: {result.stderr}'}
            return

        # Count generated tiles
        tile_count = sum(1 for r, d, f in os.walk(output_dir) for x in f if x.endswith('.png'))
        log(f"✓ Tile generation done in {step2_time:.1f}s ({tile_count} tiles)")

        conversion_tasks[task_id] = {'status': 'converting', 'progress': 60, 'detail': f'{tile_count} tiles generated! Uploading...'}

        # Step 3: Upload to R2
        log(f"[Step 3/4] Uploading {tile_count} tiles to R2...")
        step3_start = time.time()

        success, msg = upload_tiles_to_r2(layer_name, output_dir, task_id)

        step3_time = time.time() - step3_start

        if not success:
            log(f"✗ R2 upload FAILED after {step3_time:.1f}s")
            conversion_tasks[task_id] = {'status': 'error', 'error': msg}
            return

        log(f"✓ R2 upload done in {step3_time:.1f}s")

        # Step 4: Save to D1
        log("[Step 4/4] Saving metadata to D1...")
        layer_id = insert_layer(layer_name, layer_name, description or "GeoTIFF layer", source_link=source_link)

        if layer_id:
            conversion_tasks[task_id] = {'status': 'done', 'progress': 100, 'message': f'Layer "{layer_name}" berhasil!'}
        else:
            conversion_tasks[task_id] = {'status': 'error', 'error': 'R2 OK tapi D1 gagal'}

        # Cleanup
        shutil.rmtree(output_dir, ignore_errors=True)
        if os.path.exists(input_path):
            os.remove(input_path)

        total_time = time.time() - start_time
        log("═══════════════════════════════════════════════════")
        log("✓ CONVERSION COMPLETE!")
        log(f"  Total time: {total_time:.1f}s")
        log("═══════════════════════════════════════════════════")

    except Exception as e:
        # Pake print biasa kalau log belum siap, atau pake log kalau error di tengah jalan
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [GeoTIFF] ✗ EXCEPTION: {str(e)}")
        conversion_tasks[task_id] = {'status': 'error', 'error': str(e)}
# ============================
# Routes
# ============================

@app.route('/')
def index():
    layers = get_layers()
    return render_template('index.html', layers=layers, storage_url=R2_PUBLIC_URL, country_mapping=COUNTRY_MAPPING)
    
    


@app.route('/admin')
def admin():
    layers = get_layers()
    return render_template('admin.html',
                         layers=layers,
                         supabase_connected=r2_client is not None,  # Reusing template var name
                         gdal_installed=check_gdal())


@app.route('/admin/upload', methods=['POST'])
def admin_upload():
    if not r2_client:
        return jsonify({'success': False, 'error': 'R2 tidak terhubung. Konfigurasi .env!'})

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file'})

    file = request.files['file']
    upload_type = request.form.get('upload_type', 'xyz')
    layer_name = secure_filename(request.form.get('layer_name', '')).lower().replace('_', '-')

    if not layer_name:
        return jsonify({'success': False, 'error': 'Nama layer wajib'})

    description = request.form.get('description', '')
    source_link = request.form.get('source_link', '')
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{layer_name}_{secure_filename(file.filename)}")
    file.save(filepath)

    task_id = str(uuid.uuid4())
    conversion_tasks[task_id] = {'status': 'starting', 'progress': 0}

    if upload_type == 'xyz':
        thread = threading.Thread(target=process_xyz_zip, args=(task_id, filepath, layer_name, description, source_link))
    elif upload_type == 'csv':
        lat_col = request.form.get('lat_col', '')
        lon_col = request.form.get('lon_col', '')
        popup_col = request.form.get('popup_col', '')
        thread = threading.Thread(target=process_csv, args=(task_id, filepath, layer_name, description, lat_col, lon_col, popup_col, source_link))
    elif upload_type == 'choropleth':
        # CSV for choropleth heatmap with time-series support
        value_col = request.form.get('value_col', '')
        thread = threading.Thread(target=process_csv_choropleth, args=(task_id, filepath, layer_name, description, value_col, source_link))
    else:  # geotiff
        if not check_gdal():
            os.remove(filepath)
            return jsonify({'success': False, 'error': 'GDAL tidak terinstall'})
        zoom_min = int(request.form.get('zoom_min', 10))
        zoom_max = int(request.form.get('zoom_max', 14))
        thread = threading.Thread(target=process_geotiff, args=(task_id, filepath, layer_name, description, zoom_min, zoom_max, source_link))

    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'task_id': task_id})


@app.route('/admin/progress/<task_id>')
def admin_progress(task_id):
    return jsonify(conversion_tasks.get(task_id, {'status': 'error', 'error': 'Not found'}))


@app.route('/admin/delete/<layer_id>', methods=['DELETE'])
def admin_delete(layer_id):
    try:
        delete_layer(layer_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/update/<layer_id>', methods=['PUT'])
def admin_update(layer_id):
    """Update layer metadata (name, description, source_link)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        name = data.get('name')
        description = data.get('description')
        source_link = data.get('source_link')
        
        success = update_layer(layer_id, name=name, description=description, source_link=source_link)
        
        if success:
            return jsonify({'success': True, 'message': 'Layer berhasil diupdate'})
        else:
            return jsonify({'success': False, 'error': 'Gagal update layer'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/layers')
def api_layers():
    layers = get_layers()
    return jsonify({
        'success': True,
        'layers': layers,
        'storage_url': R2_PUBLIC_URL
    })


@app.route('/api/layer-data/<folder>')
def api_layer_data(folder):
    """Proxy endpoint to fetch layer GeoJSON from R2 (bypasses CORS)."""
    try:
        # Fetch from R2 public URL
        url = f"{R2_PUBLIC_URL}/{folder}/data.geojson"
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': f'Failed to fetch: HTTP {response.status_code}'}), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/choropleth-data/<folder>')
def api_choropleth_data(folder):
    """Proxy endpoint to fetch choropleth data from R2."""
    try:
        url = f"{R2_PUBLIC_URL}/{folder}/choropleth.json"
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': f'Failed to fetch: HTTP {response.status_code}'}), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/layer-geometry/<folder>/<filename>')
def api_layer_geometry(folder, filename):
    """Proxy endpoint to fetch custom geometry GeoJSON from R2."""
    try:
        url = f"{R2_PUBLIC_URL}/{folder}/{filename}"
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': f'Failed to fetch: HTTP {response.status_code}'}), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/countries-geojson')
def api_countries_geojson():
    """Serve world countries GeoJSON for choropleth rendering."""
    try:
        geojson_path = os.path.join(app.root_path, 'static', 'data', 'countries.geojson')
        if os.path.exists(geojson_path):
            with open(geojson_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        else:
            return jsonify({'error': 'Countries GeoJSON not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================
# Open-Meteo Weather Data API
# ============================

# Weather data cache (simple in-memory cache)
weather_cache = {}
WEATHER_CACHE_DURATION = 1800  # 30 minutes in seconds

# Weather variable metadata
WEATHER_VARIABLES = {
    'temperature_2m': {'name': 'Temperature', 'unit': '°C', 'min': 15, 'max': 40},
    'relative_humidity_2m': {'name': 'Humidity', 'unit': '%', 'min': 0, 'max': 100},
    'precipitation': {'name': 'Precipitation', 'unit': 'mm', 'min': 0, 'max': 50},
    'wind_speed_10m': {'name': 'Wind Speed', 'unit': 'km/h', 'min': 0, 'max': 60},
    'wind_direction_10m': {'name': 'Wind Direction', 'unit': '°', 'min': 0, 'max': 360},
    'cloud_cover': {'name': 'Cloud Cover', 'unit': '%', 'min': 0, 'max': 100},
    'surface_pressure': {'name': 'Surface Pressure', 'unit': 'hPa', 'min': 990, 'max': 1030},
    'soil_temperature_0cm': {'name': 'Soil Temperature', 'unit': '°C', 'min': 20, 'max': 35},
    'uv_index': {'name': 'UV Index', 'unit': '', 'min': 0, 'max': 12},
    'apparent_temperature': {'name': 'Feels Like', 'unit': '°C', 'min': 15, 'max': 45},
    'dew_point_2m': {'name': 'Dew Point', 'unit': '°C', 'min': 15, 'max': 30},
    'visibility': {'name': 'Visibility', 'unit': 'm', 'min': 0, 'max': 50000},
}


def generate_global_grid(resolution=10.0):
    """Generate grid points covering the world.
    
    Args:
        resolution: Grid spacing in degrees (default 10.0)
    
    Returns:
        List of (lat, lon) tuples
    """
    points = []
    lat = -60.0  # Skip extreme polar regions
    while lat <= 70.0:
        lon = -180.0
        while lon <= 180.0:
            points.append((round(lat, 1), round(lon, 1)))
            lon += resolution
        lat += resolution
    
    return points


@app.route('/api/weather-data')
def api_weather_data():
    """Fetch weather data from Open-Meteo for global grid.
    
    Query Parameters:
        variable: Weather variable (default: temperature_2m)
        hour: Hour index for hourly forecast (default: 0 = current hour)
        day: Day index for daily forecast (0-6, overrides hour if provided)
        resolution: Grid resolution in degrees (default: 15)
    """
    import time as time_module
    
    variable = request.args.get('variable', 'temperature_2m')
    hour_index = int(request.args.get('hour', 0))
    day_index = request.args.get('day', None)
    resolution = float(request.args.get('resolution', 15))
    
    # Validate variable
    if variable not in WEATHER_VARIABLES:
        return jsonify({'error': f'Invalid variable: {variable}'}), 400
    
    # Generate grid points
    points = generate_global_grid(resolution)
    print(f"Generated {len(points)} grid points at resolution {resolution}°")
    
    # Check cache
    is_daily = day_index is not None
    cache_key = f"weather_{variable}_{resolution}_{is_daily}"
    if cache_key in weather_cache:
        cached_time, cached_data = weather_cache[cache_key]
        if time_module.time() - cached_time < WEATHER_CACHE_DURATION:
            print(f"Using cached weather data")
            # Return cached data with the right time slice
            return process_cached_weather(cached_data, variable, hour_index if not is_daily else int(day_index), is_daily)
    
    # Build API request - Open-Meteo supports comma-separated lat/lon for multiple points
    latitudes = ','.join(str(p[0]) for p in points)
    longitudes = ','.join(str(p[1]) for p in points)
    
    url = "https://api.open-meteo.com/v1/forecast"
    
    # Determine if using hourly or daily
    if is_daily:
        # Map hourly variables to daily equivalents
        daily_var = variable
        if variable == 'temperature_2m':
            daily_var = 'temperature_2m_mean'
        elif variable == 'wind_speed_10m':
            daily_var = 'wind_speed_10m_max'
        elif variable == 'relative_humidity_2m':
            daily_var = 'relative_humidity_2m_mean'
            
        params = {
            'latitude': latitudes,
            'longitude': longitudes,
            'daily': daily_var,
            'timezone': 'auto',
            'forecast_days': 7
        }
    else:
        params = {
            'latitude': latitudes,
            'longitude': longitudes,
            'hourly': variable,
            'timezone': 'auto',
            'forecast_days': 3
        }
    
    try:
        print(f"Fetching weather from Open-Meteo for {len(points)} points...")
        response = requests.get(url, params=params, timeout=120)
        
        if response.status_code != 200:
            print(f"Open-Meteo error: {response.status_code} - {response.text[:200]}")
            return jsonify({'error': f'Open-Meteo API error: {response.status_code}'}), 500
        
        raw_data = response.json()
        
        # Cache the raw response
        weather_cache[cache_key] = (time_module.time(), raw_data)
        print(f"✓ Weather data fetched and cached")
        
        return process_cached_weather(raw_data, variable, hour_index if not is_daily else int(day_index), is_daily)
        
    except Exception as e:
        print(f"Weather fetch error: {e}")
        return jsonify({'error': str(e)}), 500


def process_cached_weather(raw_data, variable, time_index, is_daily=False):
    """Process cached weather data and extract the relevant time slice."""
    heatmap_data = []
    times = []
    
    # Debug: Print raw data structure
    if isinstance(raw_data, list):
        print(f"DEBUG: Raw data is list with {len(raw_data)} items")
        if raw_data:
            sample = raw_data[0]
            print(f"DEBUG: First item keys: {list(sample.keys())}")
            if 'hourly' in sample:
                hourly_keys = list(sample['hourly'].keys())
                print(f"DEBUG: Hourly keys: {hourly_keys}")
                if variable in sample['hourly']:
                    print(f"DEBUG: Variable '{variable}' found! First 3 values: {sample['hourly'][variable][:3]}")
                else:
                    print(f"DEBUG: Variable '{variable}' NOT found in hourly!")
    else:
        print(f"DEBUG: Raw data is single object, keys: {list(raw_data.keys())}")
    
    # Open-Meteo returns an array when multiple locations are requested
    if isinstance(raw_data, list):
        for loc in raw_data:
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            
            if is_daily:
                daily = loc.get('daily', {})
                # Try different daily variable names
                values = daily.get(f'{variable}_mean') or daily.get(f'{variable}_max') or daily.get(variable, [])
                if not times and 'time' in daily:
                    times = daily['time']
            else:
                hourly = loc.get('hourly', {})
                values = hourly.get(variable, [])
                if not times and 'time' in hourly:
                    times = hourly['time']
            
            if values and time_index < len(values) and values[time_index] is not None:
                heatmap_data.append({
                    'lat': lat,
                    'lon': lon,
                    'value': values[time_index]
                })
    else:
        # Single location response
        lat = raw_data.get('latitude')
        lon = raw_data.get('longitude')
        
        if is_daily:
            daily = raw_data.get('daily', {})
            values = daily.get(f'{variable}_mean') or daily.get(f'{variable}_max') or daily.get(variable, [])
            times = daily.get('time', [])
        else:
            hourly = raw_data.get('hourly', {})
            values = hourly.get(variable, [])
            times = hourly.get('time', [])
        
        if values and time_index < len(values) and values[time_index] is not None:
            heatmap_data.append({
                'lat': lat,
                'lon': lon,
                'value': values[time_index]
            })
    
    # Get variable metadata
    var_meta = WEATHER_VARIABLES.get(variable, {'name': variable, 'unit': '', 'min': 0, 'max': 100})
    
    return jsonify({
        'success': True,
        'variable': variable,
        'variable_name': var_meta['name'],
        'unit': var_meta['unit'],
        'min_value': var_meta['min'],
        'max_value': var_meta['max'],
        'time_index': time_index,
        'is_daily': is_daily,
        'total_times': len(times),
        'times': times[:72] if not is_daily else times[:7],
        'data': heatmap_data,
        'point_count': len(heatmap_data)
    })


@app.route('/api/weather-variables')
def api_weather_variables():
    """Return list of available weather variables."""
    variables = []
    for key, meta in WEATHER_VARIABLES.items():
        variables.append({
            'id': key,
            'name': meta['name'],
            'unit': meta['unit']
        })
    return jsonify({'success': True, 'variables': variables})


@app.route('/api/weather-point')
def api_weather_point():
    """Fetch weather data for a specific point (for click popups).
    
    Query Parameters:
        lat: Latitude
        lon: Longitude
    """
    lat = float(request.args.get('lat', -6.2))
    lon = float(request.args.get('lon', 106.8))
    
    # Fetch all weather variables for this point
    variables = list(WEATHER_VARIABLES.keys())
    
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        'latitude': lat,
        'longitude': lon,
        'hourly': ','.join(variables),
        'current': ','.join(variables[:8]),  # Current weather for main vars
        'timezone': 'Asia/Jakarta',
        'forecast_days': 2
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            
            # Format current weather data
            current = {}
            if 'current' in data:
                for var in variables[:8]:
                    if var in data['current']:
                        meta = WEATHER_VARIABLES[var]
                        current[var] = {
                            'name': meta['name'],
                            'value': data['current'][var],
                            'unit': meta['unit']
                        }
            
            return jsonify({
                'success': True,
                'latitude': data.get('latitude'),
                'longitude': data.get('longitude'),
                'timezone': data.get('timezone'),
                'current': current,
                'hourly': data.get('hourly', {})
            })
        else:
            return jsonify({'error': 'Failed to fetch weather'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
