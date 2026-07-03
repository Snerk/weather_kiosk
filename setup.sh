#!/bin/bash
# Hive Kiosk installer — run once as root on a fresh Debian 13 box:
#   sudo git clone https://github.com/Snerk/weather_kiosk /opt/weather_kiosk
#   cd /opt/weather_kiosk && sudo ./setup.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
REPO=/opt/weather_kiosk

echo "== packages =="
apt-get update
apt-get install -y --no-install-recommends \
  git python3-venv python3-pip \
  xserver-xorg xinit openbox lightdm chromium unclutter x11-xserver-utils \
  fonts-jetbrains-mono

echo "== kiosk user =="
id kiosk &>/dev/null || useradd -m -s /bin/bash kiosk

echo "== python venv =="
python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install -r "$REPO/requirements.txt"

echo "== state + secrets =="
mkdir -p /var/lib/weather-kiosk/cache /etc/weather-kiosk
chown -R kiosk:kiosk /var/lib/weather-kiosk
if [ ! -f /etc/weather-kiosk/secrets.env ]; then
  read -rp "Discord BOT token (blank to skip): " DTOK
  read -rsp "Admin panel password: " APASS; echo
  HASH=$(python3 - "$APASS" <<'PY'
import hashlib, os, sys
salt = os.urandom(16)
dk = hashlib.pbkdf2_hmac("sha256", sys.argv[1].encode(), salt, 200_000)
print(f"pbkdf2$200000${salt.hex()}${dk.hex()}")
PY
)
  cat > /etc/weather-kiosk/secrets.env <<EOF
DISCORD_BOT_TOKEN=$DTOK
ADMIN_HASH=$HASH
EOF
  chmod 640 /etc/weather-kiosk/secrets.env
  chgrp kiosk /etc/weather-kiosk/secrets.env
fi

echo "== systemd =="
cp "$REPO"/systemd/*.service "$REPO"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now kiosk-server.service kiosk-update.timer

echo "== sudoers for admin-panel system actions =="
cat > /etc/sudoers.d/kiosk-syshelper <<'EOF'
kiosk ALL=(root) NOPASSWD: /opt/weather_kiosk/bin/kiosk-syshelper
EOF
chmod 440 /etc/sudoers.d/kiosk-syshelper

echo "== autologin to the browser =="
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-kiosk.conf <<'EOF'
[Seat:*]
autologin-user=kiosk
autologin-session=openbox
EOF
mkdir -p /home/kiosk/.config/openbox
cat > /home/kiosk/.config/openbox/autostart <<'EOF'
/opt/weather_kiosk/bin/kiosk-browser.sh &
EOF
chown -R kiosk:kiosk /home/kiosk/.config

echo
echo "Done. If the panel isn't on DP-1, edit KIOSK_OUTPUT in bin/kiosk-browser.sh"
echo "(run 'xrandr' as kiosk to list outputs). Then: sudo reboot"
