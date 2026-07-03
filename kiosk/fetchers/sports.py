"""Module 2b: world + Bay Area sports via ESPN public scoreboard APIs."""
import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"


def fetch(cfg, cache_dir, secrets):
    out = []
    for lg in cfg["sports"]["leagues"]:
        try:
            r = requests.get(BASE.format(path=lg["path"]), timeout=20)
            r.raise_for_status()
            for ev in r.json().get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                teams = [t.get("team", {}).get("displayName", "")
                         for t in comp.get("competitors", [])]
                if lg["teams"] and not any(t in teams for t in lg["teams"]):
                    continue
                score = " – ".join(
                    f"{t.get('team', {}).get('abbreviation', '?')} "
                    f"{t.get('score', '')}"
                    for t in comp.get("competitors", []))
                out.append({
                    "league": lg["path"].split("/")[-1].upper(),
                    "name": ev.get("shortName", ""),
                    "status": ev.get("status", {}).get("type", {})
                                .get("shortDetail", ""),
                    "score": score,
                    "date": ev.get("date", "")})
        except Exception:
            continue
    return {"events": out}
