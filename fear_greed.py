"""Market Fear & Greed + VIX Dial backed by CNN Fear & Greed and Yahoo Finance VIX."""

from datetime import datetime, timezone
import math
import time
import requests

CNN_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
YAHOO_VIX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL_SECONDS = 1800


def _fetch_vix() -> tuple[str, str]:
    try:
        r = requests.get(YAHOO_VIX_URL, params={"range": "5d", "interval": "1d"}, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose")
            if price is not None:
                p = float(price)
                delta_str = ""
                if prev is not None and float(prev) > 0:
                    d = p - float(prev)
                    sign = "+" if d >= 0 else ""
                    delta_str = f"{sign}{d:.2f}"
                return f"{p:.2f}", delta_str
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        pass
    return "--", ""


def fetch_fear_greed() -> dict:
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        return _CACHE["data"]

    try:
        resp = requests.get(CNN_FG_URL, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException:
        if _CACHE["data"] is not None:
            return _CACHE["data"]
        raise

    fg = raw.get("fear_and_greed", {})
    score = round(float(fg.get("score") or 50))
    score = max(0, min(100, score))
    rating = (fg.get("rating") or "neutral").upper()

    prev_close = round(float(fg.get("previous_close") or score))
    one_week = round(float(fg.get("previous_1_week") or score))
    one_month = round(float(fg.get("previous_1_month") or score))
    one_year = round(float(fg.get("previous_1_year") or score))

    # Semicircular needle endpoint on viewBox="0 0 220 128" (center 110, 108; r=72)
    # 0 -> 180° (left), 50 -> 90° (top), 100 -> 0° (right)
    angle_rad = math.radians(180.0 - (score / 100.0) * 180.0)
    nx = round(110 + 70 * math.cos(angle_rad), 1)
    ny = round(108 - 70 * math.sin(angle_rad), 1)

    # 30-day sparkline from fear_and_greed_historical.data
    hist_points = raw.get("fear_and_greed_historical", {}).get("data", [])
    recent = hist_points[-30:] if len(hist_points) > 30 else hist_points
    spark_pts = []
    if len(recent) >= 2:
        n = len(recent)
        for i, pt in enumerate(recent):
            y_val = max(0.0, min(100.0, float(pt.get("y") or 50)))
            sx = round((i / (n - 1)) * 236 + 2, 1)
            sy = round(56 - (y_val / 100.0) * 52, 1)
            spark_pts.append(f"{sx},{sy}")
    sparkline = " ".join(spark_pts)

    vix_val, vix_delta = _fetch_vix()

    result = {
        "title": "Fear & Greed + VIX",
        "score": score,
        "rating": rating,
        "prev_close": prev_close,
        "one_week": one_week,
        "one_month": one_month,
        "one_year": one_year,
        "delta_day": f"{score - prev_close:+d}",
        "vix": vix_val,
        "vix_delta": vix_delta,
        "nx": nx,
        "ny": ny,
        "sparkline": sparkline,
        "date": datetime.now(timezone.utc).strftime("%b %d, %Y").upper(),
    }
    _CACHE["ts"] = now
    _CACHE["data"] = result
    return result
