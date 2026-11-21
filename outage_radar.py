"""Live BGP & Internet Outage Radar backed by Georgia Tech IODA v2."""

from datetime import datetime, timezone
import time
import requests

IODA_ALERTS_URL = "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts"
_CACHE: dict = {"ts": 0.0, "data": None}
_RESPONSE_CACHE: dict = {"data": None}
_CACHE_TTL_SECONDS = 1800

# ISO-2 country centroids (lat, lon) for equirectangular map projection
COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "US": (39.8, -98.6), "CA": (56.1, -106.3), "MX": (23.6, -102.5), "GT": (15.8, -90.2),
    "HN": (15.2, -86.2), "NI": (12.9, -85.2), "CR": (9.7, -83.8), "PA": (8.5, -80.8),
    "CU": (21.5, -77.8), "DO": (18.7, -70.2), "HT": (19.0, -72.3), "JM": (18.1, -77.3),
    "CO": (4.6, -74.3), "VE": (6.4, -66.6), "EC": (-1.8, -78.2), "PE": (-9.2, -75.0),
    "BR": (-14.2, -51.9), "BO": (-16.3, -63.6), "PY": (-23.4, -58.4), "CL": (-35.7, -71.5),
    "AR": (-38.4, -63.6), "UY": (-32.5, -55.8),
    "GB": (55.4, -3.4), "IE": (53.4, -8.2), "PT": (39.4, -8.2), "ES": (40.5, -3.7),
    "FR": (46.2, 2.2), "BE": (50.5, 4.5), "NL": (52.1, 5.3), "DE": (51.2, 10.5),
    "CH": (46.8, 8.2), "IT": (41.9, 12.6), "AT": (47.5, 14.6), "PL": (51.9, 19.1),
    "CZ": (49.8, 15.5), "SK": (48.7, 19.7), "HU": (47.2, 19.5), "RO": (45.9, 24.9),
    "BG": (42.7, 25.5), "GR": (39.1, 21.8), "UA": (48.4, 31.2), "BY": (53.7, 27.9),
    "RU": (61.5, 105.3), "SE": (60.1, 18.6), "NO": (60.5, 8.5), "FI": (61.9, 25.7),
    "DK": (56.3, 9.5), "IS": (64.9, -19.0), "TR": (38.9, 35.2),
    "MA": (31.8, -7.1), "DZ": (28.0, 1.7), "TN": (33.9, 9.5), "LY": (26.3, 17.2),
    "EG": (26.8, 30.8), "SD": (12.9, 30.2), "ET": (9.1, 40.5), "KE": (-0.0, 37.9),
    "UG": (1.4, 32.3), "TZ": (-6.4, 34.9), "NG": (9.1, 8.7), "GH": (7.9, -1.0),
    "CI": (7.5, -5.5), "SN": (14.5, -14.5), "CM": (7.4, 12.4), "CD": (-4.0, 21.8),
    "AO": (-11.2, 17.9), "ZM": (-13.1, 27.8), "ZW": (-19.0, 29.2), "ZA": (-30.6, 22.9),
    "SA": (23.9, 45.1), "AE": (23.4, 53.8), "QA": (25.4, 51.2), "OM": (21.5, 55.9),
    "YE": (15.6, 48.5), "IQ": (33.2, 43.7), "IR": (32.4, 53.7), "SY": (34.8, 38.9),
    "JO": (30.6, 36.2), "IL": (31.0, 34.9), "LB": (33.9, 35.9), "AF": (33.9, 67.7),
    "PK": (30.4, 69.3), "IN": (20.6, 78.9), "BD": (23.7, 90.4), "NP": (28.4, 84.1),
    "LK": (7.9, 80.8), "MM": (21.9, 95.9), "TH": (15.9, 100.9), "VN": (14.1, 108.3),
    "KH": (12.6, 104.9), "MY": (4.2, 101.9), "SG": (1.4, 103.8), "ID": (-0.8, 113.9),
    "PH": (12.9, 121.8), "CN": (35.9, 104.2), "TW": (23.7, 120.9), "KR": (35.9, 127.8),
    "JP": (36.2, 138.3), "KZ": (48.0, 66.9), "UZ": (41.4, 64.6), "MN": (46.9, 103.8),
    "AU": (-25.3, 133.8), "NZ": (-40.9, 174.9),
}


def _extract_coords(alert: dict) -> tuple[float, float] | None:
    entity = alert.get("entity") or {}
    attrs = entity.get("attrs") or {}
    cc = (attrs.get("country_code") or "").upper()
    if not cc and entity.get("type") == "country":
        cc = (entity.get("code") or "").upper()
    if cc in COUNTRY_COORDS:
        return COUNTRY_COORDS[cc]
    name = (entity.get("name") or "").upper()
    for code in COUNTRY_COORDS:
        if f"-{code}" in name or f"({code})" in name:
            return COUNTRY_COORDS[code]
    return None


def _format_alert(alert: dict) -> dict:
    entity = alert.get("entity") or {}
    attrs = entity.get("attrs") or {}
    val = alert.get("value")
    hist = alert.get("historyValue")

    drop_pct = 0
    if isinstance(val, (int, float)) and isinstance(hist, (int, float)) and hist > 0:
        drop_pct = max(0, min(100, round((1.0 - (val / hist)) * 100)))

    ts = alert.get("time") or 0
    time_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M UTC") if ts else ""

    name = (entity.get("name") or entity.get("code") or "Unknown").strip()
    cc = (attrs.get("country_code") or "").upper()
    if entity.get("type") == "region" and cc and f", {cc}" not in name:
        name = f"{name}, {cc}"
    if len(name) > 42:
        name = name[:39].rstrip() + "..."

    org = (attrs.get("org") or "").strip()
    if len(org) > 40:
        org = org[:37].rstrip() + "..."

    coords = _extract_coords(alert)
    map_x = round(coords[1] + 180, 1) if coords else None
    map_y = round(90 - coords[0], 1) if coords else None

    return {
        "code": entity.get("code", ""),
        "name": name,
        "org": org,
        "entity_type": (entity.get("type") or "").upper(),
        "datasource": (alert.get("datasource") or "").upper(),
        "level": (alert.get("level") or "normal").upper(),
        "drop_pct": drop_pct,
        "value": val,
        "history_value": hist,
        "time": time_str,
        "ts": ts,
        "map_x": map_x,
        "map_y": map_y,
    }


def _fetch_alert_window(start: int, until: int) -> list[dict]:
    for attempt in range(2):
        try:
            resp = requests.get(
                IODA_ALERTS_URL,
                params={"from": start, "until": until, "limit": 500},
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; TRMNL-Outage-Radar/1.0)",
                    "Accept": "application/json",
                },
                timeout=10,
            )
            if resp.status_code == 429 and attempt == 0:
                time.sleep(1.0)
                continue
            resp.raise_for_status()
            return resp.json().get("data", [])
        except requests.RequestException:
            if attempt == 0:
                continue
            return []
    return []


def fetch_outage_radar() -> dict:
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        alerts = _CACHE["data"]
    else:
        until = int(now)
        # Fetch 2 sequential 12h windows (no parallel burst) to cover the full 24h timeline gently
        windows = [(until - 86400, until - 43200), (until - 43200, until)]
        alerts = []
        for idx, (w_start, w_end) in enumerate(windows):
            if idx > 0:
                time.sleep(0.25)
            alerts.extend(_fetch_alert_window(w_start, w_end))
        if alerts:
            _CACHE["ts"] = now
            _CACHE["data"] = alerts
        elif _RESPONSE_CACHE["data"] is not None:
            return _RESPONSE_CACHE["data"]
        elif _CACHE["data"] is not None:
            alerts = _CACHE["data"]

    formatted = [_format_alert(a) for a in alerts]
    critical_list = [a for a in formatted if a["level"] == "CRITICAL"]
    bgp_count = sum(1 for a in formatted if a["datasource"] == "BGP")
    unique_nets = len({a["code"] for a in formatted if a["code"]})

    # Deduplicate by entity code, keeping highest drop_pct then newest timestamp
    by_code: dict[str, dict] = {}
    pool = critical_list if critical_list else formatted
    for item in pool:
        key = item["code"] or item["name"]
        prev = by_code.get(key)
        if prev is None or (item["drop_pct"], item["ts"]) > (prev["drop_pct"], prev["ts"]):
            by_code[key] = item

    ranked = sorted(
        by_code.values(),
        key=lambda x: (1 if x["entity_type"] in ("COUNTRY", "REGION") else 0, x["drop_pct"], x["ts"]),
        reverse=True,
    )

    # Bucket 24h alerts into 24 hourly bars (oldest -> newest)
    until_ts = int(now)
    start_ts = until_ts - 86400
    hour_total = [0] * 24
    hour_crit = [0] * 24
    for a in formatted:
        ts = a["ts"]
        if start_ts <= ts <= until_ts:
            idx = min(23, max(0, int((ts - start_ts) // 3600)))
            hour_total[idx] += 1
            if a["level"] == "CRITICAL":
                hour_crit[idx] += 1

    max_hr = max(hour_total) if any(hour_total) else 1
    hourly_bars = []
    for i in range(24):
        h_tot = round((hour_total[i] / max_hr) * 60) if hour_total[i] > 0 else 2
        h_crit = round((hour_crit[i] / max_hr) * 60) if hour_crit[i] > 0 else 0
        hourly_bars.append({
            "x": i * 10 + 1,
            "y": 64 - h_tot,
            "h": h_tot,
            "cy": 64 - h_crit,
            "ch": h_crit,
        })

    ping_count = sum(1 for a in formatted if "PING" in a["datasource"])
    tele_count = sum(1 for a in formatted if "MERIT" in a["datasource"])
    tot_safe = max(1, len(formatted))

    result = {
        "title": "BGP & Outage Radar",
        "date": datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC").upper(),
        "total_alerts": len(formatted),
        "critical_count": len(critical_list),
        "bgp_count": bgp_count,
        "ping_count": ping_count,
        "tele_count": tele_count,
        "bgp_pct": round((bgp_count / tot_safe) * 100),
        "ping_pct": round((ping_count / tot_safe) * 100),
        "tele_pct": round((tele_count / tot_safe) * 100),
        "affected_nets": unique_nets,
        "featured": ranked[0] if ranked else None,
        "items": ranked[1:6],
        "hourly_bars": hourly_bars,
    }
    if formatted:
        _RESPONSE_CACHE["data"] = result
    return result
