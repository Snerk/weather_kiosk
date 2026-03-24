import sys
import requests
import json
import traceback  # Added for debugging crashes
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, 
                             QFrame, QHBoxLayout, QGridLayout)
from PyQt6.QtGui import QPixmap, QColor, QImage
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

# --- Configuration ---
USER_AGENT = "Heliosphere_Kiosk/2.2 (github.com/gemini-user)"

# --- Data Endpoints ---
KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
WIND_URL = "https://services.swpc.noaa.gov/products/solar-wind/plasma-5-minute.json"
XRAY_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json"
SUVI_BASE = "https://services.swpc.noaa.gov/products/animations"
SUVI_BANDS = ['195', '284', '303', '094', '131', '171']

# --- Styling ---
BG_COLOR = "#0f111a"      
PANEL_COLOR = "#1a1c29"   
ACCENT_COLOR = "#ff9e64"  
TEXT_COLOR = "#a9b1d6"    
ALERT_COLOR = "#f7768e"   

STYLE_SHEET = f"""
    QWidget {{
        background-color: {BG_COLOR};
        color: {TEXT_COLOR};
        font-family: "Segoe UI", "Consolas", sans-serif;
    }}
    QFrame.panel {{
        background-color: {PANEL_COLOR};
        border-radius: 8px;
        border: 1px solid #292e42;
    }}
    QLabel.header {{
        color: {ACCENT_COLOR};
        font-weight: 900;
        letter-spacing: 3px;
        font-size: 14px;
    }}
    QLabel.metric-val {{
        font-size: 28px;
        font-weight: bold;
        color: #e0af68;
    }}
    QLabel.metric-label {{
        font-size: 11px;
        text-transform: uppercase;
        color: #565f89;
        letter-spacing: 1px;
    }}
    QToolTip {{
        border: 1px solid {ACCENT_COLOR};
        background-color: {PANEL_COLOR};
        color: {TEXT_COLOR};
    }}
"""

TOOLTIPS = {
    'kp': "Planetary K-index\n\n0-9 scale of geomagnetic storm magnitude.",
    'wind': "Solar Wind Speed\n\nSpeed of particles from the Sun (>500 km/s is fast).",
    'dens': "Proton Density\n\nConcentration of charged particles.",
    'xray': "X-Ray Flux\n\nSolar flare intensity (A, B, C, M, X scale)."
}

class TelemetryWorker(QThread):
    data_ready = pyqtSignal(dict)
    
    def run(self):
        headers = {'User-Agent': USER_AGENT}
        data_pkg = {}
        try:
            def get_json(url):
                try:
                    r = requests.get(url, headers=headers, timeout=5)
                    r.raise_for_status()
                    return r.json()
                except:
                    return [] # Return empty list on fail

            kp_data = get_json(KP_URL)
            if kp_data and len(kp_data) > 1:
                data_pkg['kp'] = kp_data[-1][1]

            wind_data = get_json(WIND_URL)
            if wind_data and len(wind_data) > 1:
                data_pkg['wind_speed'] = wind_data[-1][2]
                data_pkg['wind_density'] = wind_data[-1][1]

            xray_data = get_json(XRAY_URL)
            if xray_data and len(xray_data) > 0:
                data_pkg['xray_class'] = self.flux_to_class(xray_data[-1].get('flux', 0))

            self.data_ready.emit(data_pkg)
        except Exception as e:
            # Silently fail in thread, just don't crash app
            print(f"Telemetry Error: {e}")

    def flux_to_class(self, flux):
        import math
        try:
            if flux <= 0: return "A0.0"
            log_flux = math.log10(flux)
            if log_flux < -7.0: return f"A{10**(log_flux+8):.1f}"
            elif -7.0 <= log_flux < -6.0: return f"B{10**(log_flux+7):.1f}"
            elif -6.0 <= log_flux < -5.0: return f"C{10**(log_flux+6):.1f}"
            elif -5.0 <= log_flux < -4.0: return f"M{10**(log_flux+5):.1f}"
            else: return f"X{10**(log_flux+4):.1f}"
        except:
            return "--"

class AnimationLoader(QThread):
    sequence_ready = pyqtSignal(str, list) 

    def __init__(self, band, target_size):
        super().__init__()
        self.band = band
        self.target_size = target_size 

    def run(self):
        headers = {'User-Agent': USER_AGENT}
        frames = [] 
        try:
            manifest_url = f"{SUVI_BASE}/suvi-primary-{self.band}.json"
            resp = requests.get(manifest_url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                return # Skip if manifest fails

            data = resp.json()
            
            # Limit to last 40 frames to prevent memory overload on Kiosk
            step = max(1, len(data) // 40) 
            selection = data[::step]

            for item in selection:
                img_url = "https://services.swpc.noaa.gov" + item['url']
                try:
                    r_img = requests.get(img_url, headers=headers, timeout=5)
                    if r_img.status_code == 200:
                        img = QImage.fromData(r_img.content)
                        if not img.isNull():
                            # Resize in thread to save main thread CPU
                            scaled = img.scaled(
                                self.target_size[0], self.target_size[1],
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation
                            )
                            frames.append(scaled)
                except:
                    continue 

            if frames:
                self.sequence_ready.emit(self.band, frames)
            
        except Exception as e:
            print(f"Loader Error ({self.band}): {e}")

class MetricBox(QFrame):
    def __init__(self, title, unit, tooltip_key):
        super().__init__()
        self.setProperty("class", "panel")
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(2)
        self.setLayout(self.layout)
        self.setToolTip(TOOLTIPS.get(tooltip_key, ""))

        self.lbl_title = QLabel(title)
        self.lbl_title.setProperty("class", "metric-label")
        
        self.lbl_val = QLabel("--")
        self.lbl_val.setProperty("class", "metric-val")
        
        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setStyleSheet("color: #565f89; font-size: 10px;")

        self.layout.addWidget(self.lbl_title)
        self.layout.addWidget(self.lbl_val)
        self.layout.addWidget(self.lbl_unit)

    def set_value(self, value):
        self.lbl_val.setText(str(value))

class HeliosphereApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heliosphere SWPC Kiosk")
        self.resize(480, 800)
        self.setStyleSheet(STYLE_SHEET)

        self.bands = SUVI_BANDS
        self.current_band_idx = 0
        self.pixmap_frames = [] 
        self.frame_idx = 0
        self.next_pixmaps_cache = None 
        self.next_band_name = ""

        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(15)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(self.main_layout)

        self.setup_ui()

        # Timers
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.play_frame)
        
        self.cycle_timer = QTimer()
        self.cycle_timer.setInterval(10 * 60 * 1000) 
        self.cycle_timer.timeout.connect(self.trigger_band_switch)

        self.telemetry_timer = QTimer()
        self.telemetry_timer.setInterval(5 * 60 * 1000)
        self.telemetry_timer.timeout.connect(self.refresh_telemetry)

        # --- KEY FIX: Use singleShot to start threads AFTER the event loop starts ---
        # This prevents the "thread still has a frame" crash on startup
        QTimer.singleShot(100, self.startup_sequence)

    def setup_ui(self):
        self.header = QLabel("SWPC // HELIOSPHERE")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header.setProperty("class", "header")
        self.main_layout.addWidget(self.header)

        self.vis_panel = QFrame()
        self.vis_panel.setProperty("class", "panel")
        self.vis_layout = QVBoxLayout(self.vis_panel)
        self.vis_layout.setContentsMargins(5, 5, 5, 5)

        self.sun_img = QLabel()
        self.sun_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sun_img.setMinimumHeight(400) 
        self.sun_img.setStyleSheet("background-color: #000; border-radius: 4px;")
        
        self.vis_label = QLabel("SYSTEM INITIALIZING...")
        self.vis_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vis_label.setStyleSheet("color: #e0af68; font-size: 10px; margin-top: 5px;")
        
        self.vis_layout.addWidget(self.sun_img)
        self.vis_layout.addWidget(self.vis_label)
        self.main_layout.addWidget(self.vis_panel)

        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)

        self.kp_box = MetricBox("PLANETARY K-INDEX", "0-9 SCALE", 'kp')
        self.wind_box = MetricBox("SOLAR WIND", "KM/SEC", 'wind')
        self.dens_box = MetricBox("PROTON DENSITY", "P/CM³", 'dens')
        self.xray_box = MetricBox("X-RAY FLUX", "GOES-16", 'xray')

        self.grid_layout.addWidget(self.kp_box, 0, 0)
        self.grid_layout.addWidget(self.wind_box, 0, 1)
        self.grid_layout.addWidget(self.dens_box, 1, 0)
        self.grid_layout.addWidget(self.xray_box, 1, 1)

        self.main_layout.addLayout(self.grid_layout)
        self.main_layout.addStretch()

        self.status_lbl = QLabel("System Ready")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet("color: #414868; font-size: 11px;")
        self.main_layout.addWidget(self.status_lbl)

    def startup_sequence(self):
        """Called safely after the window is shown."""
        self.status_lbl.setText("Connecting to SWPC...")
        self.refresh_telemetry()
        self.load_band(self.bands[0]) 
        self.cycle_timer.start()
        self.telemetry_timer.start()

    def load_band(self, band):
        self.status_lbl.setText(f"Buffering Band {band}...")
        self.loader = AnimationLoader(band, target_size=(400, 400))
        self.loader.sequence_ready.connect(self.on_band_ready)
        # Add finished signal to ensure thread cleanup
        self.loader.finished.connect(self.loader.deleteLater)
        self.loader.start()

    def on_band_ready(self, band, qimages):
        try:
            # Convert QImages to QPixmaps on the main thread
            converted_frames = [QPixmap.fromImage(img) for img in qimages]

            if not self.pixmap_frames:
                self.pixmap_frames = converted_frames
                self.update_vis_label(band)
                self.anim_timer.start(100)
                self.status_lbl.setText("System Active")
                self.prepare_next_band()
            else:
                self.next_pixmaps_cache = converted_frames
                self.next_band_name = band
                self.status_lbl.setText(f"Next Band ({band}) Ready")
        except Exception as e:
            print(f"Error processing band: {e}")

    def prepare_next_band(self):
        next_idx = (self.current_band_idx + 1) % len(self.bands)
        self.load_band(self.bands[next_idx])

    def trigger_band_switch(self):
        if self.next_pixmaps_cache:
            self.pixmap_frames = self.next_pixmaps_cache
            self.current_band_idx = (self.current_band_idx + 1) % len(self.bands)
            self.update_vis_label(self.next_band_name)
            self.next_pixmaps_cache = None
            self.next_band_name = ""
            self.prepare_next_band()
        else:
            self.status_lbl.setText("Buffering next sequence...")

    def play_frame(self):
        if not self.pixmap_frames: return
        self.frame_idx = (self.frame_idx + 1) % len(self.pixmap_frames)
        self.sun_img.setPixmap(self.pixmap_frames[self.frame_idx])

    def update_vis_label(self, band):
        desc = {
            '195': '195Å • CORONAL HOLES',
            '284': '284Å • ACTIVE REGIONS',
            '303': '303Å • CHROMOSPHERE',
            '094': '094Å • SOLAR FLARES',
            '131': '131Å • HOT PLASMA',
            '171': '171Å • CORONAL LOOPS'
        }
        self.vis_label.setText(f"SUVI {desc.get(band, band)} • PAST 24H")

    def refresh_telemetry(self):
        self.telemetry_worker = TelemetryWorker()
        self.telemetry_worker.data_ready.connect(self.update_metrics)
        self.telemetry_worker.finished.connect(self.telemetry_worker.deleteLater)
        self.telemetry_worker.start()

    def update_metrics(self, data):
        self.kp_box.set_value(data.get('kp', '--'))
        self.wind_box.set_value(int(float(data.get('wind_speed', 0))))
        self.dens_box.set_value(data.get('wind_density', '--'))
        self.xray_box.set_value(data.get('xray_class', '--'))
        try:
            kp = float(data.get('kp', 0))
            if kp >= 5: 
                self.kp_box.lbl_val.setStyleSheet(f"color: {ALERT_COLOR};")
        except: pass

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = HeliosphereApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        # Catch errors to prevent silent crashes
        traceback.print_exc()
