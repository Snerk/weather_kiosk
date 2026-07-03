#!/bin/bash
# Self-update: run by kiosk-update.timer every 15 min.
set -euo pipefail
REPO=/opt/weather_kiosk
cd "$REPO"
git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0

echo "updating $LOCAL -> $REMOTE"
REQ_BEFORE=$(sha256sum requirements.txt)
git reset --hard origin/main
git clean -fd --exclude=.venv
if [ "$REQ_BEFORE" != "$(sha256sum requirements.txt)" ]; then
  "$REPO/.venv/bin/pip" install -r requirements.txt
fi
systemctl restart kiosk-server.service
