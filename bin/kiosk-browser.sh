#!/bin/bash
# Launched by the kiosk user's openbox autostart. Rotates the display to
# portrait, hides the cursor, and keeps Chromium alive forever.
OUTPUT=${KIOSK_OUTPUT:-DP-1}      # `xrandr` lists names; DP-1 on the OptiPlex
xrandr --output "$OUTPUT" --rotate left || true
xset s off -dpms s noblank
unclutter -idle 1 -root &
until chromium --kiosk --noerrdialogs --disable-session-crashed-bubble \
      --disable-infobars --check-for-update-interval=31536000 \
      --autoplay-policy=no-user-gesture-required \
      http://127.0.0.1:8080/ ; do
  sleep 2
done
