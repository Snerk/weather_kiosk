"""Module 3a: 48-hour forecast for 94103 from api.weather.gov raw gridpoint data.

The raw gridpoint endpoint gives every variable the spec asks for (including
gusts and RH, which the friendly /forecast/hourly endpoint often omits) in SI
units with ISO-8601 duration-encoded validity windows, which we expand to an
hourly series.
"""
import datetime as dt
import re
import requests

_ISO = re.compile(r"^(?P<t>[^/]+)/P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?)?$")


def _expand(prop, series, key):
    """Expand NWS {validTime, value} runs into series[iso_hour][key]."""
    for v in prop.get("values", []):
        m = _ISO.match(v["validTime"])
        if not m:
            continue
        start = dt.datetime.fromisoformat(m["t"])
        hours = int(m["d"] or 0) * 24 + int(m["h"] or 0) or 1
        for i in range(hours):
            t = (start + dt.timedelta(hours=i)).isoformat()
            series.setdefault(t, {})[key] = v["value"]


def fetch(cfg, cache_dir, secrets):
    c = cfg["weather"]
    hdrs = {"User-Agent": c["user_agent"]}
    pt = requests.get(f"https://api.weather.gov/points/{c['lat']},{c['lon']}",
                      headers=hdrs, timeout=30).json()
    grid_url = pt["properties"]["forecastGridData"]
    props = requests.get(grid_url, headers=hdrs, timeout=30).json()["properties"]

    series = {}
    for nws_key, key in [("temperature", "temp_c"), ("windSpeed", "wind_kph"),
                         ("windGust", "gust_kph"), ("windDirection", "wind_dir"),
                         ("relativeHumidity", "rh"),
                         ("probabilityOfPrecipitation", "pop")]:
        if nws_key in props:
            _expand(props[nws_key], series, key)

    now = dt.datetime.now(dt.timezone.utc)
    hours = []
    for t in sorted(series):
        ts = dt.datetime.fromisoformat(t)
        if now - dt.timedelta(hours=1) <= ts <= now + dt.timedelta(hours=c["hours"]):
            row = series[t]
            hours.append({
                "t": t,
                "temp_c": row.get("temp_c"),
                "temp_f": None if row.get("temp_c") is None
                          else round(row["temp_c"] * 9 / 5 + 32, 1),
                "wind_kph": row.get("wind_kph"),
                "wind_mph": _kph2mph(row.get("wind_kph")),
                "gust_kph": row.get("gust_kph"),
                "gust_mph": _kph2mph(row.get("gust_kph")),
                "wind_dir": row.get("wind_dir"),
                "rh": row.get("rh"),
                "pop": row.get("pop"),
            })
    return {"station": pt["properties"].get("radarStation"),
            "hours": hours[: c["hours"]]}


def _kph2mph(v):
    return None if v is None else round(v * 0.621371, 1)
