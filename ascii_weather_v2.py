import curses
import math
import time
import json
import urllib.request
import argparse
import sys

# ==========================================
# PART 1: CLI & CONFIGURATION
# ==========================================

def parse_arguments():
    parser = argparse.ArgumentParser(description="ASCIIlite: The Atmospheric Rendering Engine")
    parser.add_argument('--lat', type=float, default=37.8715, help='Latitude (default: Berkeley)')
    parser.add_argument('--lon', type=float, default=-122.2730, help='Longitude (default: Berkeley)')
    parser.add_argument('--complex', action='store_true', help='Use the full 70-char density ramp')
    return parser.parse_args()

# ==========================================
# PART 2: THE NETWORK LAYER
# ==========================================

class NoaaClient:
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon
        self.headers = {'User-Agent': 'ASCIIlite/2.0'}
        self.station_url = None
        self.last_fetch = 0
        self.cache_duration = 900
        
        # Default State: "Null Sky"
        self.weather_data = {
            "wind_speed": 10.0,
            "wind_dir": 0,
            "temperature": 20.0,
            "description": "Connecting..."
        }

    def _get_json(self, url):
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())

    def resolve_station(self):
        try:
            point_url = f"https://api.weather.gov/points/{self.lat},{self.lon}"
            data = self._get_json(point_url)
            self.station_url = data['properties']['observationStations']
            
            # Resolve specific station URL
            stations_data = self._get_json(self.station_url)
            self.station_url = stations_data['features'][0]['id'] + "/observations/latest"
            return True
        except Exception:
            self.weather_data["description"] = "Loc Failure (Using Sim)"
            return False

    def update(self):
        now = time.time()
        if now - self.last_fetch < self.cache_duration:
            return

        if not self.station_url:
            if not self.resolve_station():
                return

        try:
            data = self._get_json(self.station_url)
            props = data['properties']
            
            w_speed = props.get('windSpeed', {}).get('value')
            w_dir = props.get('windDirection', {}).get('value')
            temp = props.get('temperature', {}).get('value')
            desc = props.get('textDescription', "Unknown")

            self.weather_data["wind_speed"] = w_speed if w_speed is not None else 10.0
            self.weather_data["wind_dir"] = w_dir if w_dir is not None else 0
            self.weather_data["temperature"] = temp if temp is not None else 20.0
            self.weather_data["description"] = desc
            self.last_fetch = now
        except Exception:
            pass # Keep existing data

# ==========================================
# PART 3: THE HIGH-FIDELITY RENDERER
# ==========================================

class AsciiRenderer:
    def __init__(self, use_complex=False):
        # The "Bourke" Ramp: sorted by pixel density
        if use_complex:
            self.ramp = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
        else:
            # A curated "Weather" Ramp (more aesthetic, less noisy)
            self.ramp = " @%#*+=-:. " 
            
        self.ramp_len = len(self.ramp)
        
    def noise(self, x, y, t):
        # 3-Octave Pseudo-Perlin
        v = math.sin(x*0.05 + t) + math.cos(y*0.05 + t*0.3) # Base
        v += 0.5 * math.sin(x*0.1 - t*2 + y*0.1)            # Contour
        v += 0.25 * math.cos(x*0.2 + y*0.2)                 # Grit
        return (v + 3.0) / 6.0 # Normalize 0-1

    def get_char(self, density, wind_speed, dx, dy):
        # 1. Calculate Density Index
        # We invert density because index 0 is usually the "heaviest" char in ramps
        idx = int((1.0 - density) * (self.ramp_len - 1))
        idx = max(0, min(self.ramp_len - 1, idx))
        base_char = self.ramp[idx]

        # 2. The "Flow" Override
        # If the wind is "fast" (simulated speed > 1.0) and the area is not too dense (cloud edge),
        # we override the character with a directional vector to show movement.
        speed_threshold = 0.8
        
        # Only modify the "lighter" parts of the cloud (edges), leave the core dense.
        is_cloud_edge = 0.3 < density < 0.7 
        
        if wind_speed > speed_threshold and is_cloud_edge:
            angle = math.degrees(math.atan2(dy, dx)) % 180
            if 0 <= angle < 30: return "-"
            elif 30 <= angle < 60: return "\\"
            elif 60 <= angle < 120: return "|"
            elif 120 <= angle < 150: return "/"
            else: return "-"
            
        return base_char

def main(stdscr):
    # Parse Args (Need to do this outside curses usually, but we hack it here)
    # We actually need to parse args BEFORE main is called by wrapper, 
    # but for a single script file, we pass the parsed args into main via global or closure.
    # We will use the args parsed in `if __name__` block.
    
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(30) # 30ms = ~30fps
    
    # Init colors if available
    if curses.has_colors():
        curses.start_color()
        # Pair 1: Blue on Black (Cold)
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        # Pair 2: White on Black (Neutral)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
        # Pair 3: Yellow on Black (Warm - if we implemented temp scaling)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    # Initialize
    noaa = NoaaClient(ARGS.lat, ARGS.lon)
    renderer = AsciiRenderer(use_complex=ARGS.complex)
    
    t = 0.0
    
    # Initial Connect Message
    h, w = stdscr.getmaxyx()
    stdscr.addstr(h//2, w//2 - 10, "A C Q U I R I N G   S I G N A L")
    stdscr.refresh()
    noaa.update()
    
    while True:
        c = stdscr.getch()
        if c == ord('q'): break
        
        noaa.update()
        
        # Physics Params
        real_speed = noaa.weather_data["wind_speed"]
        # Map speed: 0-60kmh to 0.0-3.0 simulation units
        sim_speed = (real_speed / 20.0) 
        
        # Direction Logic
        real_dir = noaa.weather_data["wind_dir"]
        sim_angle = math.radians((450 - real_dir) % 360)
        
        dx = math.cos(sim_angle) * sim_speed
        dy = -(math.sin(sim_angle) * sim_speed) # Flip Y for terminal
        
        rows, cols = stdscr.getmaxyx()
        t += 0.05
        
        # Render
        for y in range(rows - 2):
            for x in range(cols):
                # Parallax/Drift calculation
                nx = x * 0.4 - t * dx * 2
                ny = y * 0.8 - t * dy * 2 
                
                density = renderer.noise(nx, ny, t * 0.1)
                char = renderer.get_char(density, sim_speed, dx, dy)
                
                # Color Logic
                color = curses.color_pair(2)
                if density > 0.7: 
                    # Deep cloud - make it bold/white
                    attrs = color | curses.A_BOLD
                elif density < 0.3:
                    # Thin air - make it dim
                    attrs = color | curses.A_DIM
                else:
                    attrs = color
                    
                try:
                    stdscr.addch(y, x, char, attrs)
                except curses.error:
                    pass

        # HUD
        loc_str = f"LAT:{ARGS.lat:.2f} LON:{ARGS.lon:.2f}"
        hud = f" {loc_str} | TEMP: {noaa.weather_data['temperature']}C | WIND: {real_speed} km/h | {noaa.weather_data['description']} "
        try:
            stdscr.addstr(rows - 1, 0, hud[:cols-1], curses.A_REVERSE)
        except: pass
        
        stdscr.refresh()

if __name__ == "__main__":
    ARGS = parse_arguments()
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\n[ASCIIlite] Signal Lost.")
