"""Shared RSS helpers."""
import calendar
import feedparser


def pull(feed_urls, max_items, keyword_filter=None):
    items = []
    for url in feed_urls:
        parsed = feedparser.parse(url)
        src = parsed.feed.get("title", url)
        for e in parsed.entries:
            title = e.get("title", "")
            if keyword_filter and not any(k in title.lower() for k in keyword_filter):
                continue
            ts = 0
            for key in ("published_parsed", "updated_parsed"):
                if e.get(key):
                    ts = calendar.timegm(e[key])
                    break
            items.append({"title": title, "source": src,
                          "summary": e.get("summary", "")[:280],
                          "link": e.get("link", ""), "ts": ts})
    items.sort(key=lambda i: i["ts"], reverse=True)
    # dedupe near-identical headlines (Google News often mirrors)
    seen, out = set(), []
    for i in items:
        key = i["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out[:max_items]
