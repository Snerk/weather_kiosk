"""Module 3b: download + prune GOES-18 GEOCOLOR frames for three panels and
emit synchronized frame manifests keyed by timestamp.

CDN filenames look like 20261841200_GOES18-ABI-FD-GEOCOLOR-1808x1808.jpg
(YYYY JJJ HHMM). We keep one frame per `frame_stride_minutes` over the last
`hours` hours, per panel, then align the three panels on nearest timestamps.
"""
import datetime as dt
import re
import requests

LINK = re.compile(r'href="((\d{11})_[^"]+?-(\d+x\d+)\.jpg)"')


def _parse_ts(s):
    year, jday, hh, mm = int(s[:4]), int(s[4:7]), int(s[7:9]), int(s[9:11])
    return (dt.datetime(year, 1, 1, hh, mm, tzinfo=dt.timezone.utc)
            + dt.timedelta(days=jday - 1))


def fetch(cfg, cache_dir, secrets):
    c = cfg["goes"]
    goes_dir = cache_dir / "goes"
    goes_dir.mkdir(parents=True, exist_ok=True)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=c["hours"])
    stride = dt.timedelta(minutes=c["frame_stride_minutes"])
    panels = {}

    for p in c["panels"]:
        idx = requests.get(p["url"], timeout=60).text
        frames, last_kept = [], None
        for fname, tss, size in sorted(LINK.findall(idx)):
            if size != p["size"]:
                continue
            ts = _parse_ts(tss)
            if ts < cutoff:
                continue
            if last_kept and ts - last_kept < stride:
                continue
            last_kept = ts
            local = goes_dir / f"{p['id']}_{fname}"
            if not local.exists():
                try:
                    r = requests.get(p["url"] + fname, timeout=120)
                    r.raise_for_status()
                    local.write_bytes(r.content)
                except Exception:
                    continue
            frames.append({"ts": ts.isoformat(),
                           "url": f"/goes-frames/{local.name}"})
        panels[p["id"]] = frames

    # prune anything on disk older than the cutoff
    for f in goes_dir.iterdir():
        m = re.search(r"_(\d{11})_", "_" + f.name)
        if m and _parse_ts(m.group(1)) < cutoff:
            f.unlink(missing_ok=True)

    # synchronized timeline: master = panel with most frames; others matched
    # to nearest ts within one stride
    if not any(panels.values()):
        return {"panels": panels, "timeline": []}
    master_id = max(panels, key=lambda k: len(panels[k]))
    timeline = []
    for mf in panels[master_id]:
        mts = dt.datetime.fromisoformat(mf["ts"])
        step = {"ts": mf["ts"], "frames": {}}
        for pid, frames in panels.items():
            best, bd = None, stride
            for fr in frames:
                d = abs(dt.datetime.fromisoformat(fr["ts"]) - mts)
                if d <= bd:
                    best, bd = fr["url"], d
            if best:
                step["frames"][pid] = best
        timeline.append(step)
    return {"panels": {k: len(v) for k, v in panels.items()},
            "timeline": timeline}
