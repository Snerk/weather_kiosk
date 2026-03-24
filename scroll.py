#!/usr/bin/env python3
import sys
import gi
import requests
import time
import threading
import logging
from collections import deque

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk, Pango, PangoCairo

# --- CONFIGURATION (SF Design System) ---
COLOR_BG = "#1c3f5e"   # Slate L3 (Deep/Dark Blue)
COLOR_TXT = "#ffffff"  # White
FONT_FAMILY = "Sans"   # System default

# NWS API Configuration
USER_AGENT = "(sf-kiosk-display, admin@example.com)" 
SF_COORDS = "37.7749,-122.4194"
SCROLL_SPEED = 2  # Pixels per tick
TICK_RATE = 16    # ms (~60fps)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WeatherMarquee(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="gov.sf.weather.kiosk")
        self.forecast_text = "Loading San Francisco Forecast..."
        self.scroll_x = 0
        self.text_width = 0
        self.view_width = 1000 # Initial fallback

    def do_activate(self):
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("SF Weather Kiosk")
        
        # CHANGED: Removed fullscreen(), added default window size
        window.set_default_size(1000, 200)
        
        # CSS Styling
        css_provider = Gtk.CssProvider()
        css = f"""
            window {{ background-color: {COLOR_BG}; }}
            label {{ color: {COLOR_TXT}; font-family: '{FONT_FAMILY}'; font-weight: 300; }}
        """
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Main Layout
        self.drawing_area = Gtk.DrawingArea()
        # connecting the draw function is what enables the dynamic resizing
        self.drawing_area.set_draw_func(self.on_draw)
        window.set_child(self.drawing_area)
        
        window.present()
        
        # Start background threads
        threading.Thread(target=self.weather_worker, daemon=True).start()
        GLib.timeout_add(TICK_RATE, self.scroll_tick)

    def scroll_tick(self):
        # Move text left
        self.scroll_x -= SCROLL_SPEED
        
        # Reset if text has fully scrolled off screen
        # Uses current view_width to know when to wrap
        if self.scroll_x < -self.text_width:
            self.scroll_x = self.view_width
        
        self.drawing_area.queue_draw()
        return True

    def on_draw(self, area, cr, width, height):
        # CHANGED: Update view width immediately on every frame/resize
        self.view_width = width

        # Create Pango Layout
        layout = self.drawing_area.create_pango_layout(self.forecast_text)
        
        # CHANGED: Calculate dynamic font size based on current window height
        # We ensure a minimum size of 12 to prevent errors if window is tiny
        dynamic_size = max(12, int(height / 2.5)) 
        
        font_desc = Pango.FontDescription(f"{FONT_FAMILY} {dynamic_size}")
        layout.set_font_description(font_desc)
        
        # Calculate text dimensions
        ink, logical = layout.get_extents()
        self.text_width = logical.width / Pango.SCALE
        text_height = logical.height / Pango.SCALE
        
        # Center Vertically
        y_pos = (height - text_height) / 2
        
        # Draw Text
        cr.set_source_rgb(1, 1, 1) 
        cr.move_to(self.scroll_x, y_pos)
        PangoCairo.show_layout(cr, layout)

    def weather_worker(self):
        """Fetches NWS data robustly in a background thread."""
        while True:
            try:
                # 1. Get Gridpoint 
                pt_url = f"https://api.weather.gov/points/{SF_COORDS}"
                r = requests.get(pt_url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
                grid_url = r.json()['properties']['forecast']

                # 2. Get Forecast
                f_r = requests.get(grid_url, headers={"User-Agent": USER_AGENT})
                f_r.raise_for_status()
                data = f_r.json()
                
                # 3. Parse
                periods = data['properties']['periods'][:2] 
                new_text = "   ///   ".join([f"{p['name'].upper()}: {p['detailedForecast']}" for p in periods])
                new_text = f"SAN FRANCISCO WEATHER   ///   {new_text}   ///   "
                
                GLib.idle_add(self.update_text, new_text)
                time.sleep(900) 

            except Exception as e:
                logging.error(f"Weather Fetch Error: {e}")
                time.sleep(60) 

    def update_text(self, text):
        self.forecast_text = text

if __name__ == "__main__":
    app = WeatherMarquee()
    exit_status = app.run(sys.argv)
    sys.exit(exit_status)
