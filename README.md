# Hive Kiosk (weather_kiosk v2)

A fully automated, self-updating information kiosk for **Hive Coliving, 1040 Folsom St, San Francisco**.
Runs on a Dell OptiPlex 7060 (Debian 13 "trixie") driving a portrait 1920×1080 display.

The kiosk is a local Flask server + Chromium in kiosk mode. Background fetchers pull
data on schedules and cache it to disk; the browser rotates through modules and never
needs the internet directly. A systemd timer keeps the code in sync with this repo,
so pushing to `main` updates the kiosk within ~15 minutes.

## Modules

| # | Module | Source |
|---|--------|--------|
| 1 | AI / LLM news + model leaderboard | Ars Technica, Engadget, The Register (RSS); leaderboard feed |
| 2 | US / World news + world & Bay Area sports | AP/Reuters via Google News RSS site-filters; ESPN scoreboard APIs |
| 3 | SF (94103) weather: 48-h forecast graph + 3-panel synchronized GOES-18 loops | api.weather.gov, cdn.star.nesdis.noaa.gov |
| 4 | Hive Discord feed + alert channel overlay | Discord **bot** REST API (see `docs/SECURITY_NOTES.md`) |
| 5 | Resident showcase (open contributions via auto-merged PRs) | `content/residents/` in this repo |
| 6 | Hidden admin panel (key sequence + password) | local |

## Layout

```
kiosk/            Flask server, fetchers, frontend
bin/              browser launcher, self-update script, system helper
systemd/          service + timer units
content/          resident showcase (open to PRs — see content/HOW_TO_POST.md)
docs/             GitHub workflow for contributors, security notes, admin guide
.github/          CI that validates + auto-merges showcase PRs
setup.sh          one-shot installer for a fresh Debian 13 box
```

## Quickstart (on the kiosk box)

```bash
sudo apt update && sudo apt install -y git
sudo git clone https://github.com/Snerk/weather_kiosk /opt/weather_kiosk
cd /opt/weather_kiosk
sudo ./setup.sh        # installs deps, systemd units, prompts for secrets
sudo reboot            # boots straight into the kiosk
```

Secrets (Discord bot token, admin password hash) live in `/etc/weather-kiosk/secrets.env`,
**outside the repo**. Cache/state lives in `/var/lib/weather-kiosk/`.

## Self-update

`kiosk-update.timer` runs every 15 min: `git fetch`; if `origin/main` moved, it hard-resets
the working tree, reinstalls Python deps if `requirements.txt` changed, and restarts the
server. The browser reconnects automatically. Local secrets and cache are never touched.

## Contributing

- Code changes: see `docs/GITHUB_WORKFLOW.md` (works from any device, including a phone).
- Residents posting to the showcase: see `content/HOW_TO_POST.md` — PRs that only touch
  `content/residents/` and pass validation are merged automatically, no human approval.
