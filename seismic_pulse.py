"""Global Seismic Pulse backed by USGS live M4.5+ 24h GeoJSON feed."""

from datetime import datetime, timezone
import time
import requests

USGS_M45_DAY_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL_SECONDS = 1800


def _format_quake(feat: dict) -> dict:
    props = feat.get("properties") or {}
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") or [0.0, 0.0, 0.0]

    mag = float(props.get("mag") or 0.0)
    place = (props.get("place") or "Unknown location").strip()
    if len(place) > 42:
        place = place[:39].rstrip() + "..."

    ts_ms = props.get("time") or 0
    ts_sec = ts_ms / 1000.0
    time_str = datetime.fromtimestamp(ts_sec, tz=timezone.utc).strftime("%H:%M UTC") if ts_sec else ""
    depth_km = round(float(coords[2])) if len(coords) > 2 and coords[2] is not None else 0
    lat = round(float(coords[1]), 2) if len(coords) > 1 else 0.0
    lon = round(float(coords[0]), 2) if len(coords) > 0 else 0.0

    # Magnitude bar percentage (4.5 -> 25%, 7.5+ -> 100%)
    mag_pct = max(15, min(100, round(((mag - 4.0) / 3.5) * 100)))

    # Map (lat, lon) onto 360x144 equirectangular dot-matrix viewBox (lon -180..180, lat 80..-64)
    map_x = round(max(4.0, min(356.0, lon + 180.0)), 1)
    map_y = round(max(4.0, min(140.0, 80.0 - lat)), 1)

    return {
        "mag": f"{mag:.1f}",
        "mag_num": mag,
        "mag_pct": mag_pct,
        "place": place,
        "depth_km": depth_km,
        "coords": f"{lat}°, {lon}°",
        "map_x": map_x,
        "map_y": map_y,
        "time": time_str,
        "ts": ts_sec,
        "tsunami": bool(props.get("tsunami")),
    }


def fetch_seismic_pulse() -> dict:
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        features = _CACHE["data"]
    else:
        try:
            resp = requests.get(USGS_M45_DAY_URL, timeout=10)
            resp.raise_for_status()
            features = resp.json().get("features", [])
            _CACHE["ts"] = now
            _CACHE["data"] = features
        except requests.RequestException:
            if _CACHE["data"] is not None:
                features = _CACHE["data"]
            else:
                raise

    quakes = [_format_quake(f) for f in features]
    by_mag = sorted(quakes, key=lambda q: (q["mag_num"], q["ts"]), reverse=True)

    m5_plus = sum(1 for q in quakes if q["mag_num"] >= 5.0)
    m6_plus = sum(1 for q in quakes if q["mag_num"] >= 6.0)
    tsunami_count = sum(1 for q in quakes if q["tsunami"])

    # 24 hourly bars (oldest -> newest) showing max magnitude & count
    until_ts = int(now)
    start_ts = until_ts - 86400
    hour_counts = [0] * 24
    hour_max_mag = [0.0] * 24
    for q in quakes:
        ts = q["ts"]
        if start_ts <= ts <= until_ts:
            idx = min(23, max(0, int((ts - start_ts) // 3600)))
            hour_counts[idx] += 1
            if q["mag_num"] > hour_max_mag[idx]:
                hour_max_mag[idx] = q["mag_num"]

    hourly_bars = []
    for i in range(24):
        if hour_counts[i] == 0:
            h = 2
            solid = False
        else:
            # Scale M4.5..M7.5 -> 16..60px height
            h = max(14, min(60, round(((hour_max_mag[i] - 4.0) / 3.5) * 56) + 4))
            solid = hour_max_mag[i] >= 5.0
        hourly_bars.append({
            "x": i * 10 + 1,
            "y": 64 - h,
            "h": h,
            "solid": solid,
        })

    featured = by_mag[0] if by_mag else None
    ring_radii = []
    if featured:
        num_rings = 5 if featured["mag_num"] >= 5.5 else 4
        ring_radii = [18 + i * 11 for i in range(num_rings)]

    return {
        "title": "Global Seismic Pulse",
        "date": datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC").upper(),
        "total_quakes": len(quakes),
        "m5_plus": m5_plus,
        "m6_plus": m6_plus,
        "tsunami_count": tsunami_count,
        "featured": featured,
        "ring_radii": ring_radii,
        "items": by_mag[1:6],
        "map_pins": by_mag[:16],
        "hourly_bars": hourly_bars,
    }
