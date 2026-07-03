"""Module 2a: US/World/geopolitical headlines (AP + Reuters via site-filtered RSS)."""
from . import _rss


def fetch(cfg, cache_dir, secrets):
    c = cfg["world_news"]
    return {"news": _rss.pull(c["feeds"], c["max_items"])}
