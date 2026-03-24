import os
import time
import threading
import logging
from datetime import datetime, timedelta
import pytz

# Science & Rendering Stack
import nexradaws
import pyart
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# Web & Production Stack
from flask import Flask, send_from_directory, jsonify
from waitress import serve  # Peer-reviewed choice for kiosk stability

# --- CONFIGURATION ---
STATION = 'KMUX'
LAT, LON = 37.7749, -122.4194
DATA_DIR = './radar_raw'
FRAME_DIR = './static/frames'
MAX_AGE_HOURS = 24
PORT = 5000

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FRAME_DIR, exist_ok=True)

app = Flask(__name__)
conn = nexradaws.NexradAwsInterface()

def render_radar_frame(local_file):
    try:
        # Physics Check: Ignore MDM metadata files that lack volume data
        if "_MDM" in local_file.filepath:
            return False

        radar = pyart.io.read_nexrad_archive(local_file.filepath)
        projection = ccrs.LambertConformal(central_latitude=LAT, central_longitude=LON)
        
        fig = plt.figure(figsize=(10, 10), facecolor='black')
        ax = plt.axes(projection=projection)
        ax.set_extent([LON-1.8, LON+1.8, LAT-1.3, LAT+1.3], crs=ccrs.PlateCarree())

        ax.add_feature(cfeature.COASTLINE.with_scale('10m'), edgecolor='#444444', linewidth=1)
        
        display = pyart.graph.RadarMapDisplay(radar)
        
        # FIX: Changed 'embelish' to 'embellish'
        display.plot_ppi_map('reflectivity', 0, vmin=-8, vmax=64,
                             title_flag=False, colorbar_flag=False,
                             ax=ax, embellish=True) 

        plt.tight_layout(pad=0)
        timestamp = local_file.scan_time.strftime('%Y%m%d_%H%M%S')
        save_path = os.path.join(FRAME_DIR, f"frame_{timestamp}.png")
        
        plt.savefig(save_path, facecolor='black', bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        return True
    except Exception as e:
        # Silencing common compression errors for MDM files
        if "compression record" not in str(e):
            logging.error(f"Render Peer-Review Failure: {e}")
        return False

def background_worker():
    while True:
        try:
            logging.info("Syncing with NOAA NEXRAD S3...")
            end_time = datetime.utcnow().replace(tzinfo=pytz.utc)
            start_time = end_time - timedelta(hours=MAX_AGE_HOURS)
            scans = conn.get_avail_scans_in_range(start_time, end_time, STATION)
            
            # Peer-Review Optimization: Filter out metadata (MDM) files before downloading
            valid_scans = [s for s in scans if "_MDM" not in s.filename]
            
            existing_frames = [f for f in os.listdir(FRAME_DIR) if f.endswith('.png')]
            new_scans = [s for s in valid_scans if f"frame_{s.scan_time.strftime('%Y%m%d_%H%M%S')}.png" not in existing_frames]
            
            if new_scans:
                # Prioritize latest scans
                new_scans.sort(key=lambda x: x.scan_time)
                results = conn.download(new_scans[-15:], DATA_DIR) 
                for scan in results.iter_success():
                    render_radar_frame(scan)
                    if os.path.exists(scan.filepath):
                        os.remove(scan.filepath)

            # Garbage Collection
            cutoff = time.time() - (MAX_AGE_HOURS * 3600)
            for f in os.listdir(FRAME_DIR):
                f_path = os.path.join(FRAME_DIR, f)
                if os.path.getmtime(f_path) < cutoff:
                    os.remove(f_path)
            
            time.sleep(300)
        except Exception as e:
            logging.error(f"Worker heartbeat failed: {e}")
            time.sleep(60)

# --- WEB SERVER ---

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html style="background: black;">
    <head>
        <title>SF Bay Radar</title>
        <style>
            body { margin: 0; overflow: hidden; display: flex; justify-content: center; align-items: center; height: 100vh; }
            img { height: 100vh; width: auto; }
            #info { position: absolute; top: 10px; left: 10px; color: #00FF00; font-family: monospace; font-size: 1.2em; text-shadow: 1px 1px 2px black; }
        </style>
    </head>
    <body>
        <div id="info">KMUX | SF BAY AREA | <span id="ts">LOADING</span></div>
        <img id="radar" src="">
        <script>
            let frames = [];
            let i = 0;
            async function load() { 
                const r = await fetch('/api/manifest'); 
                frames = await r.json(); 
            }
            function play() {
                if(frames.length > 0) {
                    i = (i + 1) % frames.length;
                    document.getElementById('radar').src = '/static/frames/' + frames[i];
                    document.getElementById('ts').innerText = frames[i].split('_')[1] + " UTC";
                }
                setTimeout(play, 150);
            }
            setInterval(load, 60000);
            load().then(play);
        </script>
    </body>
    </html>
    """

@app.route('/api/manifest')
def manifest():
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.png')])
    return jsonify(files)

@app.route('/static/frames/<path:filename>')
def serve_frame(filename):
    return send_from_directory(FRAME_DIR, filename)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    threading.Thread(target=background_worker, daemon=True).start()
    
    # Using Waitress for robust multi-month operation
    print(f"Kiosk serving on http://0.0.0.0:{PORT}")
    serve(app, host='0.0.0.0', port=PORT)
