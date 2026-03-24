import curses
import time
import requests
import re
from io import BytesIO
from PIL import Image
from datetime import datetime
import sys
import threading

# ==========================================
# PART 1: CONFIGURATION & CONSTANTS
# ==========================================

# NOAA CDN Endpoints
URL_GOES_EARTH = "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/09/"
URL_GOES_SUN = "https://cdn.star.nesdis.noaa.gov/GOES18/SUVI/FD/195/"

# Resolution Targets
TERM_W = 108
TERM_H = 78
HALF_H = 39  # Each panel gets half the height

# ASCII Ramp (Paul Bourke's Standard)
ASCII_CHARS = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
# Invert logic: In our code, 0=Dark, 1=Light. 
# Usually clouds/sun are light, space is dark. 
# So we want light pixels -> complex chars, dark pixels -> space.
# The ramp above: $ is dense (light), space is empty (dark). 
# We need to map 255 (white) -> $ and 0 (black) -> space.

# ==========================================
# PART 2: THE INGESTION ENGINE
# ==========================================

class FrameBuffer:
    def __init__(self):
        self.earth_frames = []
        self.sun_frames = []
        self.is_ready = False
        self.loading_status = "Initializing..."
        self.loading_progress = 0

    def fetch_file_list(self, url, ext=".jpg"):
        """
        Parses NOAA directory listing to find image files.
        Returns sorted list of full URLs.
        """
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                return []
            
            # Regex to find hrefs ending in .jpg
            # NOAA files often look like: 20233521200_GOES18-ABI-FD-GEOCOLOR-5424x5424.jpg
            # We want the smaller thumbnails if available to save bandwidth? 
            # NOAA usually provides varying resolutions. Let's look for standard ones.
            # "1808x1808" is a common medium res. "678x678" is better for terminal.
            # Let's try to match files ending in '678x678.jpg' or similar to be fast.
            # If not found, fall back to any jpg.
            
            links = re.findall(r'href="([^"]+\.jpg)"', r.text)
            
            # Filter for a reasonable resolution to save bandwidth
            # Band 09 often has '2169x2169' or '678x678'
            filtered = [x for x in links if '678x678' in x or '1280x1280' in x]
            
            # If filtered is empty, take whatever is there (maybe SUVI has different naming)
            if not filtered:
                filtered = links

            # Sort by filename (which usually contains timestamp)
            filtered.sort()
            
            # Return full URLs
            return [url + x for x in filtered]
        except Exception as e:
            self.loading_status = f"Error fetching list: {e}"
            return []

    def process_image(self, img_bytes):
        """
        Converts raw bytes -> PIL -> ASCII Block
        """
        try:
            img = Image.open(BytesIO(img_bytes))
            img = img.convert("L") # Grayscale

            # CROP LOGIC
            # We want to center crop to remove excess space.
            w, h = img.size
            min_dim = min(w, h)
            # Crop to a square in the center
            left = (w - min_dim) / 2
            top = (h - min_dim) / 2
            right = (w + min_dim) / 2
            bottom = (h + min_dim) / 2
            img = img.crop((left, top, right, bottom))

            # RESIZE LOGIC
            # Terminal pixels are not square. They are roughly 1:2 (W:H).
            # To preserve aspect ratio, we need to squash the height.
            # Target width: 108
            # Target height: 39
            img = img.resize((TERM_W, HALF_H), Image.Resampling.LANCZOS)
            
            # MAP TO ASCII
            pixels = img.getdata()
            ascii_str = ""
            range_width = len(ASCII_CHARS) - 1
            
            for pix in pixels:
                # pix is 0-255. 
                # We want 255 -> Index 0 ($)
                # We want 0 -> Index End ( )
                # Let's map normalized brightness
                val = pix / 255.0
                idx = int((1.0 - val) * range_width)
                ascii_str += ASCII_CHARS[idx]
                
            return ascii_str
        except Exception:
            return None

    def load_data(self):
        self.loading_status = "Scraping NOAA Manifests..."
        earth_urls = self.fetch_file_list(URL_GOES_EARTH)
        sun_urls = self.fetch_file_list(URL_GOES_SUN)
        
        # Limit to last ~24 frames (assuming 1 per hour roughly)
        # We take the last 24 items of the list.
        earth_urls = earth_urls[-24:]
        sun_urls = sun_urls[-24:]
        
        total_tasks = len(earth_urls) + len(sun_urls)
        completed = 0
        
        # Fetch Earth
        self.loading_status = "Downloading Earth Data (Water Vapor)..."
        for url in earth_urls:
            try:
                r = requests.get(url, timeout=5)
                frame = self.process_image(r.content)
                if frame: self.earth_frames.append(frame)
            except: pass
            completed += 1
            self.loading_progress = int((completed / total_tasks) * 100)

        # Fetch Sun
        self.loading_status = "Downloading Sun Data (SUVI 195)..."
        for url in sun_urls:
            try:
                r = requests.get(url, timeout=5)
                frame = self.process_image(r.content)
                if frame: self.sun_frames.append(frame)
            except: pass
            completed += 1
            self.loading_progress = int((completed / total_tasks) * 100)
            
        self.is_ready = True

# ==========================================
# PART 3: THE RENDER LOOP
# ==========================================

def draw_panel(stdscr, ascii_data, start_y, label):
    """
    Draws a single 108x39 panel
    """
    # Draw Label
    stdscr.addstr(start_y, 0, f" {label} ".center(TERM_W, "="))
    
    if not ascii_data:
        stdscr.addstr(start_y + 19, 40, "NO DATA AVAILABLE")
        return

    # Render characters
    # ascii_data is a single string length 108*39. We need to slice it.
    for i in range(HALF_H - 1): # -1 for label space
        row_str = ascii_data[i*TERM_W : (i+1)*TERM_W]
        try:
            stdscr.addstr(start_y + 1 + i, 0, row_str)
        except curses.error:
            pass

def main(stdscr):
    # Setup
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK) # Earth
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Sun
    
    # Init Loader
    buffer = FrameBuffer()
    loader_thread = threading.Thread(target=buffer.load_data)
    loader_thread.start()
    
    # Animation Indices
    idx_earth = 0
    idx_sun = 0
    
    while True:
        # Check input
        c = stdscr.getch()
        if c == ord('q'): break
        
        stdscr.erase()
        
        if not buffer.is_ready:
            # Loading Screen
            h, w = stdscr.getmaxyx()
            msg = f"{buffer.loading_status} [{buffer.loading_progress}%]"
            stdscr.addstr(h//2, (w - len(msg))//2, msg)
            stdscr.refresh()
            time.sleep(0.1)
            continue
            
        # RENDER FRAMES
        
        # Earth Panel (Top) - Cyan/Blue
        # Only try to draw if we have frames
        if buffer.earth_frames:
            current_earth = buffer.earth_frames[idx_earth]
            # Use color pair 1
            stdscr.attron(curses.color_pair(1))
            draw_panel(stdscr, current_earth, 0, "GOES-18 BAND 09 (MID-LEVEL WATER VAPOR)")
            stdscr.attroff(curses.color_pair(1))
            
            # Advance frame roughly every 100ms
            # But we are in a single loop. Let's rely on loop sleep.
            idx_earth = (idx_earth + 1) % len(buffer.earth_frames)

        # Sun Panel (Bottom) - Yellow
        if buffer.sun_frames:
            current_sun = buffer.sun_frames[idx_sun]
            stdscr.attron(curses.color_pair(2))
            draw_panel(stdscr, current_sun, HALF_H, "GOES-18 SUVI 195 (SOLAR CORONA)")
            stdscr.attroff(curses.color_pair(2))
            
            idx_sun = (idx_sun + 1) % len(buffer.sun_frames)

        # Footer
        try:
            stdscr.addstr(TERM_H - 1, 0, " LIVE FEED | 24H LOOP | PRESS 'q' TO EXIT ", curses.A_REVERSE)
        except: pass

        stdscr.refresh()
        time.sleep(0.15) # ~6.6 FPS

if __name__ == "__main__":
    try:
        # Enforce terminal size check?
        # For now, we assume the user has resized correctly: 108x78
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"CRITICAL FAILURE: {e}")
