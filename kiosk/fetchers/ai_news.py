"""Module 1: AI/LLM headlines + model leaderboard."""
import json
from pathlib import Path
import requests
from . import _rss


def fetch(cfg, cache_dir, secrets):
    c = cfg["ai_news"]
    news = _rss.pull(c["feeds"], c["max_items"], c.get("keyword_filter"))
    board = _leaderboard(cfg, cache_dir)
    return {"news": news, "leaderboard": board}


def _leaderboard(cfg, cache_dir):
    """Best-effort. Leaderboard sites change often and rarely offer stable APIs;
    on any failure we fall back to the committed snapshot, which contributors
    should refresh periodically (kiosk/fetchers/leaderboard_fallback.json)."""
    try:
        # LMArena publishes leaderboard JSON consumed by its frontend; treat as
        # unstable and guard everything.
        r = requests.get(
            "https://storage.googleapis.com/arena-elo/leaderboard.json",
            timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = sorted(data, key=lambda x: -x.get("score", 0))[:10]
        return {"source": "LMArena", "rows": [
            {"model": x.get("model", "?"), "score": x.get("score"),
             "open": bool(x.get("open_weights"))} for x in rows]}
    except Exception:
        fb = Path(__file__).parent / cfg["ai_news"]["leaderboard"]["fallback_file"]
        return json.loads(fb.read_text())
