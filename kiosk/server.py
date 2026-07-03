#!/usr/bin/env python3
"""Hive Kiosk server.

Serves the kiosk single-page app, exposes cached module data as JSON, and runs
background fetchers on schedules. All external I/O happens here; the browser
only ever talks to localhost.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets as pysecrets
import subprocess
import threading
import time
from pathlib import Path

import yaml
from flask import (Flask, abort, jsonify, request, send_from_directory)

from fetchers import ai_news, world_news, sports, weather, goes, discord_feed

REPO_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("KIOSK_STATE_DIR", "/var/lib/weather-kiosk"))
CACHE_DIR = STATE_DIR / "cache"
OVERRIDES = STATE_DIR / "overrides.json"
SECRETS_ENV = Path("/etc/weather-kiosk/secrets.env")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("kiosk")

app = Flask(__name__, static_folder="static", template_folder="templates")
_sessions: dict[str, float] = {}          # token -> expiry epoch
SESSION_TTL = 3600


# ---------------------------------------------------------------- config ----
def load_secrets() -> dict:
    env = {}
    if SECRETS_ENV.exists():
        for line in SECRETS_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def load_config() -> dict:
    cfg = yaml.safe_load((REPO_DIR / "kiosk" / "config.yaml").read_text())
    if OVERRIDES.exists():
        try:
            deep_merge(cfg, json.loads(OVERRIDES.read_text()))
        except Exception:
            log.exception("bad overrides.json — ignoring")
    return cfg


def deep_merge(base: dict, extra: dict) -> None:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


def save_overrides(patch: dict) -> None:
    cur = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    deep_merge(cur, patch)
    OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES.write_text(json.dumps(cur, indent=2))


# ------------------------------------------------------------- scheduler ----
FETCHERS = {
    "ai_news":    (ai_news.fetch,    lambda c: c["ai_news"]["refresh_minutes"] * 60),
    "world_news": (world_news.fetch, lambda c: c["world_news"]["refresh_minutes"] * 60),
    "sports":     (sports.fetch,     lambda c: c["sports"]["refresh_minutes"] * 60),
    "weather":    (weather.fetch,    lambda c: c["weather"]["refresh_minutes"] * 60),
    "goes":       (goes.fetch,       lambda c: c["goes"]["refresh_minutes"] * 60),
    "discord":    (discord_feed.fetch, lambda c: c["discord"]["feed_refresh_minutes"] * 60),
}


def scheduler_loop(name: str) -> None:
    fetch_fn, interval_fn = FETCHERS[name]
    while True:
        cfg = load_config()
        try:
            data = fetch_fn(cfg, CACHE_DIR, load_secrets())
            out = CACHE_DIR / f"{name}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            tmp.write_text(json.dumps({"updated": time.time(), "data": data}))
            tmp.replace(out)
            log.info("%s refreshed", name)
        except Exception:
            log.exception("%s fetch failed", name)
        time.sleep(max(60, interval_fn(cfg)))


def start_schedulers() -> None:
    for name in FETCHERS:
        threading.Thread(target=scheduler_loop, args=(name,), daemon=True,
                         name=f"fetch-{name}").start()


# ------------------------------------------------------------------ auth ----
def check_password(candidate: str) -> bool:
    """ADMIN_HASH format: pbkdf2$<iterations>$<salt_hex>$<hash_hex>"""
    stored = load_secrets().get("ADMIN_HASH", "")
    try:
        _, iters, salt, ref = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", candidate.encode(),
                                 bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), ref)
    except Exception:
        return False


def require_session() -> None:
    tok = request.headers.get("X-Kiosk-Session", "")
    exp = _sessions.get(tok, 0)
    if exp < time.time():
        abort(401)
    _sessions[tok] = time.time() + SESSION_TTL


# ---------------------------------------------------------------- routes ----
@app.get("/")
def index():
    return send_from_directory("templates", "index.html")


@app.get("/api/config")
def api_config():
    cfg = load_config()
    return jsonify({"display": cfg["display"],
                    "admin_key_sequence": cfg["admin"]["key_sequence"],
                    "alert_display_minutes": cfg["discord"]["alert_display_minutes"]})


@app.get("/api/module/<name>")
def api_module(name):
    if name not in FETCHERS:
        abort(404)
    f = CACHE_DIR / f"{name}.json"
    if not f.exists():
        return jsonify({"updated": 0, "data": None})
    return app.response_class(f.read_text(), mimetype="application/json")


@app.get("/goes-frames/<path:fname>")
def goes_frames(fname):
    return send_from_directory(CACHE_DIR / "goes", fname)


# Showcase: list resident directories and serve their files. Rendering happens
# in a fully sandboxed iframe on the client — see SECURITY_NOTES.md.
@app.get("/api/showcase")
def api_showcase():
    root = REPO_DIR / "content" / "residents"
    entries = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        card = d / "card.html"
        meta = d / "card.json"
        if card.exists():
            info = {"id": d.name, "url": f"/showcase/{d.name}/card.html"}
            if meta.exists():
                try:
                    info.update(json.loads(meta.read_text()))
                except Exception:
                    pass
            entries.append(info)
    return jsonify(entries)


@app.get("/showcase/<resident>/<path:fname>")
def showcase_file(resident, fname):
    root = (REPO_DIR / "content" / "residents" / resident).resolve()
    if not str(root).startswith(str(REPO_DIR / "content" / "residents")):
        abort(403)
    return send_from_directory(root, fname)


# ----------------------------------------------------------- admin routes ---
@app.post("/api/admin/login")
def admin_login():
    if not check_password(request.json.get("password", "")):
        time.sleep(1.0)                     # slow brute force
        abort(401)
    tok = pysecrets.token_urlsafe(32)
    _sessions[tok] = time.time() + SESSION_TTL
    return jsonify({"token": tok})


@app.get("/api/admin/settings")
def admin_settings():
    require_session()
    return jsonify(load_config()["display"])


@app.post("/api/admin/settings")
def admin_save():
    require_session()
    patch = request.json
    if not isinstance(patch, dict):
        abort(400)
    save_overrides({"display": patch})
    return jsonify({"ok": True})


ALLOWED_SYS = {"restart-server", "restart-browser", "reboot", "update-now"}


@app.post("/api/admin/system/<action>")
def admin_system(action):
    require_session()
    if action not in ALLOWED_SYS:
        abort(400)
    subprocess.Popen(["sudo", "/opt/weather_kiosk/bin/kiosk-syshelper", action])
    return jsonify({"ok": True})


@app.get("/admin")
def admin_page():
    return send_from_directory("templates", "admin.html")


if __name__ == "__main__":
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    start_schedulers()
    app.run(host="127.0.0.1", port=8080)
