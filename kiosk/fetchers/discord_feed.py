"""Module 4: Hive Discord feed + alert channel, via a proper *bot* token.

Automating a normal user account ("self-botting") violates Discord's ToS and
gets accounts banned — do not do that. Create a bot at
https://discord.com/developers/applications, invite it to the Hive server with
View Channel + Read Message History, and put its token in
/etc/weather-kiosk/secrets.env as DISCORD_BOT_TOKEN.
"""
import json
import time
import requests

API = "https://discord.com/api/v10"


def _get(path, token):
    r = requests.get(API + path,
                     headers={"Authorization": f"Bot {token}",
                              "User-Agent": "HiveKiosk (weather_kiosk, v2)"},
                     timeout=30)
    r.raise_for_status()
    return r.json()


def fetch(cfg, cache_dir, secrets):
    c = cfg["discord"]
    token = secrets.get("DISCORD_BOT_TOKEN")
    if not token:
        return {"error": "DISCORD_BOT_TOKEN not set", "channels": [], "alert": None}

    channels = []
    for cid in dict.fromkeys(c["feed_channels"]):        # dedupe, keep order
        try:
            info = _get(f"/channels/{cid}", token)
            msgs = _get(f"/channels/{cid}/messages?limit={c['messages_per_channel']}",
                        token)
            channels.append({
                "id": cid, "name": info.get("name", cid),
                "messages": [{
                    "author": m["author"].get("global_name")
                              or m["author"].get("username", "?"),
                    "content": m.get("content", "")[:400],
                    "ts": m.get("timestamp", ""),
                    "id": m["id"],
                    "attachments": len(m.get("attachments", [])),
                } for m in msgs]})
        except Exception as e:
            channels.append({"id": cid, "name": cid, "error": str(e), "messages": []})

    # alert channel: any message newer than last-seen triggers an overlay
    alert = None
    state_f = cache_dir / "discord_alert_state.json"
    last_seen = 0
    if state_f.exists():
        last_seen = json.loads(state_f.read_text()).get("last_id", 0)
    try:
        msgs = _get(f"/channels/{c['alert_channel']}/messages?limit=1", token)
        if msgs:
            m = msgs[0]
            if int(m["id"]) > last_seen:
                state_f.write_text(json.dumps({"last_id": int(m["id"])}))
                alert = {
                    "author": m["author"].get("global_name")
                              or m["author"].get("username", "?"),
                    "content": m.get("content", "")[:600],
                    "ts": m.get("timestamp", ""),
                    "shown_since": time.time()}
    except Exception:
        pass
    # persist an active alert across refreshes until it expires
    active_f = cache_dir / "discord_alert_active.json"
    if alert:
        active_f.write_text(json.dumps(alert))
    elif active_f.exists():
        prev = json.loads(active_f.read_text())
        if time.time() - prev["shown_since"] < c["alert_display_minutes"] * 60:
            alert = prev
        else:
            active_f.unlink()
    return {"channels": channels, "alert": alert}
