import sys
import os
import time
import requests
import threading
import logging
from bs4 import BeautifulSoup

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QComboBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap

# --- CONFIGURATION ---
# Explicit target resolutions prevent the app from mixing image sizes and breaking the time-series
SOURCES = {
    "CONUS": {"url": "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/CONUS/GEOCOLOR/", "res": "1250x750"},
    "Full Disk": {"url": "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/GEOCOLOR/", "res": "1808x1808"},
    "Pacific SW": {"url": "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/SECTOR/psw/GEOCOLOR/", "res": "1200x1200"},
    "FD Band 10": {"url": "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/10/", "res": "1808x1808"}
}

CACHE_ROOT = "./goes_time_series_cache"
MAX_FRAMES = 280  # Approx 24 hours of imagery
SYNC_INTERVAL = 600 # 10 minutes

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WeatherSync")

class DataSynchronizer(threading.Thread):
    def __init__(self, source_key):
        super().__init__(daemon=True)
        self.source_key = source_key
        self.base_url = SOURCES[source_key]["url"]
        self.target_res = SOURCES[source_key]["res"]
        self.cache_dir = os.path.join(CACHE_ROOT, source_key.replace(" ", "_"))
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Implement Connection Pooling to speed up massive frame downloads
        self.session = requests.Session()
        self.running = True

    def run(self):
        while self.running:
            try:
                self.sync_directory()
                self.cleanup_old_files()
            except Exception as e:
                logger.error(f"Sync error for {self.source_key}: {e}")
            time.sleep(SYNC_INTERVAL)

    def sync_directory(self):
        resp = self.session.get(self.base_url, timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Filter specifically by resolution to prevent time/size skipping
        res_suffix = f"{self.target_res}.jpg"
        links = [a['href'] for a in soup.find_all('a', href=True) 
                 if 'GOES18' in a['href'] and a['href'].endswith(res_suffix)]
        
        latest_links = sorted(links)[-MAX_FRAMES:]

        for link in latest_links:
            local_path = os.path.join(self.cache_dir, link)
            if not os.path.exists(local_path):
                try:
                    logger.info(f"[{self.source_key}] Downloading {link}")
                    img_data = self.session.get(self.base_url + link, timeout=15).content
                    
                    # Write to a temporary file first to prevent UI reading partial files
                    temp_path = local_path + ".tmp"
                    with open(temp_path, 'wb') as f:
                        f.write(img_data)
                    os.rename(temp_path, local_path)
                except Exception as e:
                    logger.warning(f"Failed to download {link}: {e}")

    def cleanup_old_files(self):
        files = sorted([os.path.join(self.cache_dir, f) for f in os.listdir(self.cache_dir) if not f.endswith('.tmp')])
        if len(files) > MAX_FRAMES:
            for f in files[:-MAX_FRAMES]:
                try:
                    os.remove(f)
                except OSError:
                    pass

class AnimationDashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.current_source = "CONUS"
        self.frames = []
        self.frame_idx = 0
        
        # Memory caching to prevent CPU bottlenecking during animation
        self.pixmap_cache = {} 

        # Start the background sync threads
        self.syncers = {k: DataSynchronizer(k) for k in SOURCES.keys()}
        for s in self.syncers.values(): 
            s.start()

        self.init_ui()

        # Animation loop
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.next_frame)
        self.anim_timer.start(100) # 10 FPS

        # Refresh the local file list
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_local_frames)
        self.refresh_timer.start(10000) # Check local disk every 10s
        self.load_local_frames()

    def init_ui(self):
        self.setWindowTitle("GOES-18 24hr Time-Series Animator")
        self.setStyleSheet("background-color: #0f111a; color: #a9b1d6; font-size: 14px;")
        layout = QVBoxLayout(self)

        self.selector = QComboBox()
        self.selector.addItems(SOURCES.keys())
        self.selector.currentIndexChanged.connect(self.change_source)
        self.selector.setStyleSheet("""
            QComboBox { background-color: #1a1b26; border: 1px solid #292e42; padding: 5px; }
            QComboBox QAbstractItemView { background-color: #1a1b26; selection-background-color: #0db9d7; }
        """)
        layout.addWidget(self.selector)

        self.display = QLabel("Initializing Cache...\nCheck terminal for download progress.")
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display.setMinimumSize(800, 600)
        layout.addWidget(self.display, stretch=1)

    def change_source(self):
        self.current_source = self.selector.currentText()
        self.pixmap_cache.clear() # Clear cache on source switch to save RAM
        self.load_local_frames()
        self.frame_idx = 0

    def load_local_frames(self):
        path = os.path.join(CACHE_ROOT, self.current_source.replace(" ", "_"))
        # Ensure we only read fully written files
        if os.path.exists(path):
            self.frames = sorted([os.path.join(path, f) for f in os.listdir(path) if f.endswith('.jpg')])

    def get_cached_pixmap(self, path):
        """Returns a pre-scaled pixmap from RAM, avoiding disk I/O and CPU scaling."""
        if path in self.pixmap_cache:
            return self.pixmap_cache[path]
            
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None # Handle corrupt files safely
            
        scaled = pixmap.scaled(
            self.display.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.pixmap_cache[path] = scaled
        
        # Housekeeping: Keep cache roughly the size of max frames
        if len(self.pixmap_cache) > MAX_FRAMES + 10:
            # Remove oldest items (dictionaries maintain insertion order in Python 3.7+)
            oldest_key = next(iter(self.pixmap_cache))
            del self.pixmap_cache[oldest_key]
            
        return scaled

    def resizeEvent(self, event):
        """If the user resizes the window, we must dump the cache to recalculate scaling."""
        self.pixmap_cache.clear()
        super().resizeEvent(event)

    def next_frame(self):
        if not self.frames: 
            self.display.setText(f"Waiting for {self.current_source} imagery to download...\n(Check your terminal log)")
            return
            
        # Ensure idx is within bounds if files were deleted
        self.frame_idx = self.frame_idx % len(self.frames) 
        
        frame_path = self.frames[self.frame_idx]
        scaled_pixmap = self.get_cached_pixmap(frame_path)
        
        if scaled_pixmap:
            self.display.setPixmap(scaled_pixmap)
            
        self.frame_idx += 1


# --- THE MISSING EXECUTION BLOCK ---
if __name__ == "__main__":
    # Ensure High DPI scaling is supported for modern displays
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = AnimationDashboard()
    window.resize(1024, 768)
    window.show()
    
    sys.exit(app.exec())
