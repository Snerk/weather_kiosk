#!/bin/bash

# ==============================================================================
# ASCIIlite.sh
# A modular Bash script to animate satellite imagery in ASCII.
#
# Usage: ./ASCIIlite.sh [-s GOES-18] [-f 10] [-r 100x50]
# ==============================================================================

# --- Configuration & Defaults ---
APP_NAME="ASCIIlite"
TEMP_DIR=$(mktemp -d -t ${APP_NAME}_XXXXXX)
USER_AGENT="Mozilla/5.0 (compatible; ASCIIlite/1.0; +https://github.com/example/asciilite)"

# Default Settings
SATELLITE="GOES-18"    # Default source
FRAMERATE=10           # Frames per second
WIDTH=$(tput cols)     # Default width (terminal width)
HEIGHT=$(tput lines)   # Default height (terminal height)
HOURS=24               # How many hours of history to fetch

# NOAA Source URLs (Modular lookup)
declare -A SOURCES
SOURCES["GOES-18"]="https://cdn.star.nesdis.noaa.gov/GOES18/ABI/FD/GEOCOLOR/"
SOURCES["GOES-16"]="https://cdn.star.nesdis.noaa.gov/GOES16/ABI/FD/GEOCOLOR/"
SOURCES["HIMAWARI"]="https://cdn.star.nesdis.noaa.gov/Himawari9/Kanagawa/FD/GEOCOLOR/"

# --- Helper Functions ---

cleanup() {
    # Remove temporary files on exit
    rm -rf "$TEMP_DIR"
    tput cnorm # Restore cursor
}
trap cleanup EXIT INT TERM

usage() {
    echo "Usage: $0 [options]"
    echo "  -s, --satellite [NAME]   Source (GOES-18, GOES-16). Default: GOES-18"
    echo "  -f, --framerate [FPS]    Animation speed. Default: 10"
    echo "  -r, --resolution [WxH]   Output resolution (e.g., 80x40). Default: Terminal size"
    echo "  -h, --help               Show this help message"
    exit 1
}

check_dependencies() {
    local deps=("curl" "jp2a")
    for cmd in "${deps[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            echo "Error: Required dependency '$cmd' is missing."
            echo "Please install it (e.g., 'sudo apt install $cmd' or 'brew install $cmd')."
            exit 1
        fi
    done
}

parse_resolution() {
    local res=$1
    if [[ "$res" =~ ([0-9]+)x([0-9]+) ]]; then
        WIDTH=${BASH_REMATCH[1]}
        HEIGHT=${BASH_REMATCH[2]}
    else
        echo "Error: Invalid resolution format. Use WxH (e.g., 80x40)."
        exit 1
    fi
}

# --- Core Modules ---

fetch_image_list() {
    local url=$1
    echo " -> Connecting to NOAA ($SATELLITE)..."
    
    # We target the 339x339 thumbnails to save bandwidth, as they are sufficient for ASCII.
    # Pattern usually: ..._GOES18-ABI-FD-GEOCOLOR-339x339.jpg
    
    local file_pattern="339x339.jpg"
    
    # Fetch index, filter for jpgs, sort, and take the amount needed for 24h
    # (Approx 1 image every 10 mins = 6/hr * 24 = 144 images)
    
    curl -s -A "$USER_AGENT" "$url" | \
    grep -o 'href="[^"]*"' | \
    sed 's/href="//;s/"//' | \
    grep "$file_pattern" | \
    sort | \
    tail -n 144 > "$TEMP_DIR/manifest.txt"
    
    local count=$(wc -l < "$TEMP_DIR/manifest.txt")
    echo " -> Found $count frames for the last $HOURS hours."
}

download_images() {
    local base_url=$1
    mkdir -p "$TEMP_DIR/images"
    
    echo " -> Downloading frames (this may take a moment)..."
    
    # Read manifest and download in parallel logic or loop
    local counter=0
    local total=$(wc -l < "$TEMP_DIR/manifest.txt")
    
    while read -r filename; do
        ((counter++))
        printf "\r    Downloading: [%3d/%3d] %s" "$counter" "$total" "$filename"
        # Download silently (-s) and retry on fail
        curl -s -A "$USER_AGENT" "${base_url}${filename}" -o "$TEMP_DIR/images/frame_$(printf "%03d" $counter).jpg" &
        
        # Limit background jobs to avoid network spam (batch of 10)
        if (( counter % 10 == 0 )); then wait; fi
    done < "$TEMP_DIR/manifest.txt"
    wait
    echo ""
}

render_ascii() {
    mkdir -p "$TEMP_DIR/frames"
    echo " -> Rendering ASCII frames..."
    
    local counter=0
    local total=$(ls "$TEMP_DIR/images"/*.jpg | wc -l)
    
    for img in "$TEMP_DIR/images"/*.jpg; do
        ((counter++))
        local basename=$(basename "$img" .jpg)
        
        # jp2a arguments:
        # --width/height: force size
        # --colors: use terminal colors
        # --background=dark: optimize for dark terminals
        
        jp2a --width="$WIDTH" --height="$HEIGHT" --colors --background=dark "$img" > "$TEMP_DIR/frames/$basename.txt"
    done
}

play_animation() {
    local delay=$(echo "scale=3; 1 / $FRAMERATE" | bc)
    
    tput civis # Hide cursor
    clear
    
    echo "Starting animation. Press CTRL+C to stop."
    sleep 1
    
    while true; do
        for frame in "$TEMP_DIR/frames"/*.txt; do
            # Move cursor to home (0,0) without clearing screen (prevents flicker)
            printf "\033[H"
            cat "$frame"
            sleep "$delay"
        done
    done
}

# --- Main Execution Flow ---

check_dependencies

# Argument Parsing
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--satellite)
            SATELLITE="$2"
            shift 2
            ;;
        -f|--framerate)
            FRAMERATE="$2"
            shift 2
            ;;
        -r|--resolution)
            parse_resolution "$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate Satellite Source
URL=${SOURCES[$SATELLITE]}
if [[ -z "$URL" ]]; then
    echo "Error: Unknown satellite source '$SATELLITE'."
    echo "Available: ${!SOURCES[@]}"
    exit 1
fi

# Execute Pipeline
echo "Initializing $APP_NAME..."
fetch_image_list "$URL"
download_images "$URL"
render_ascii
play_animation
