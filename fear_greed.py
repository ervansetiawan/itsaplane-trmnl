"""Market Fear & Greed + VIX Term Structure & 7-Pillar Equalizer."""

import base64
from datetime import datetime, timezone
from io import BytesIO
import math
import time

from PIL import Image, ImageDraw, ImageFont
import requests

CNN_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)

_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL_SECONDS = 1800

_PILLAR_KEYS = [
    ("S&P Momentum", "MOM", "market_momentum_sp500"),
    ("Price Strength", "STR", "stock_price_strength"),
    ("Volume Breadth", "BRD", "stock_price_breadth"),
    ("Put/Call Options", "P/C", "put_call_options"),
    ("VIX Volatility", "VIX", "market_volatility_vix"),
    ("Junk Bond Demand", "HYB", "junk_bond_demand"),
    ("Safe Haven Flow", "SHV", "safe_haven_demand"),
]


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold
        else ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rating_short(rating_raw: str) -> str:
    r = (rating_raw or "").strip().lower()
    if "extreme fear" in r:
        return "EXT FEAR"
    if "fear" in r:
        return "FEAR"
    if "extreme greed" in r:
        return "EXT GREED"
    if "greed" in r:
        return "GREED"
    return "NEUTRAL"


def _arc_point(score_val: float, cx: float, cy: float, radius: float) -> tuple[float, float]:
    clamped = max(0.0, min(100.0, float(score_val)))
    angle_rad = math.radians(180.0 - (clamped / 100.0) * 180.0)
    return (
        round(cx + radius * math.cos(angle_rad), 1),
        round(cy - radius * math.sin(angle_rad), 1),
    )


def _build_dial_ticks(cx: float = 110.0, cy: float = 108.0) -> list[dict]:
    ticks = []
    major_vals = {0, 25, 45, 50, 55, 75, 100}
    for val in range(0, 105, 5):
        is_major = val in major_vals
        r_outer = 92.0
        r_inner = 78.0 if is_major else 85.0
        x1, y1 = _arc_point(val, cx, cy, r_inner)
        x2, y2 = _arc_point(val, cx, cy, r_outer)
        ticks.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "major": is_major})
    return ticks


def _fetch_quote(symbol: str) -> tuple[float | None, float | None]:
    try:
        r = _SESSION.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            params={"range": "5d", "interval": "1d"},
            timeout=6,
        )
        if r.status_code == 429:
            time.sleep(1.1)
            r = _SESSION.get(
                YAHOO_CHART_URL.format(symbol=symbol),
                params={"range": "5d", "interval": "1d"},
                timeout=6,
            )
        if r.status_code == 200:
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose")
            p_val = float(price) if price is not None else None
            prev_val = float(prev) if prev is not None else None
            return p_val, prev_val
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        pass
    return None, None


def _fetch_vix_suite() -> dict:
    vix_p, vix_prev = _fetch_quote("%5EVIX")
    vix9d_p, _ = _fetch_quote("%5EVIX9D")
    vix3m_p, _ = _fetch_quote("%5EVIX3M")

    vix_str = f"{vix_p:.2f}" if vix_p is not None else "--"
    vix_delta = ""
    if vix_p is not None and vix_prev is not None and vix_prev > 0:
        d = vix_p - vix_prev
        vix_delta = f"{'+' if d >= 0 else ''}{d:.2f}"

    vix9d_str = f"{vix9d_p:.1f}" if vix9d_p is not None else vix_str
    vix3m_str = f"{vix3m_p:.1f}" if vix3m_p is not None else vix_str

    if vix9d_p is not None and vix3m_p is not None:
        if vix9d_p > vix3m_p + 0.35:
            term_regime = "BACKWARDATION"
        elif vix3m_p > vix9d_p + 0.35:
            term_regime = "CONTANGO"
        else:
            term_regime = "FLAT TERM"
    else:
        term_regime = "SPOT VIX"

    return {
        "vix": vix_str,
        "vix_delta": vix_delta,
        "vix9d": vix9d_str,
        "vix3m": vix3m_str,
        "vix_term_regime": term_regime,
    }


def _render_pillars_png(pillars: list[dict], width: int = 340, height: int = 160) -> str:
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    f_bold = _load_font(10, bold=True)
    f_sm = _load_font(10, bold=False)
    f_xs = _load_font(9, bold=True)

    label_w = 104
    badge_w = 78
    bar_x0 = label_w
    bar_x1 = width - badge_w
    bar_w = bar_x1 - bar_x0

    # Header & threshold ticks (0, 25, 50, 75, 100)
    draw.text((2, 1), "7 SENTIMENT PILLARS", fill=85, font=f_xs)
    for mark in (25, 50, 75):
        mx = int(bar_x0 + (mark / 100.0) * bar_w)
        draw.line([(mx, 14), (mx, height - 4)], fill=170, width=1)
        draw.text((mx - 5, 1), str(mark), fill=85, font=f_xs)

    top_y = 16
    row_h = (height - top_y - 2) // max(1, len(pillars))

    for idx, p in enumerate(pillars):
        ry = top_y + idx * row_h
        draw.text((2, ry + 3), p["label"], fill=0, font=f_sm)

        # Track
        by1, by2 = ry + 4, ry + row_h - 4
        draw.rounded_rectangle([bar_x0, by1, bar_x1, by2], radius=2, fill=255, outline=170, width=1)

        # Filled bar
        sc = max(2, min(100, p["score"]))
        fill_w = max(4, int((sc / 100.0) * bar_w))
        shade = 0 if sc <= 25 else (85 if sc < 55 else 170)
        draw.rounded_rectangle([bar_x0, by1, bar_x0 + fill_w, by2], radius=2, fill=shade, outline=0, width=1)

        # Score + short rating on right
        right_txt = f"{p['score']:2d} {p['short_rating']}"
        draw.text((bar_x1 + 6, ry + 3), right_txt, fill=0, font=f_bold if sc <= 25 or sc >= 75 else f_sm)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def fetch_fear_greed() -> dict:
    """Fetch CNN Fear & Greed Index, 7 sub-indicators, 30D history, and CBOE VIX term structure."""
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        return _CACHE["data"]

    try:
        resp = _SESSION.get(CNN_FG_URL, timeout=8)
        if resp.status_code == 429:
            time.sleep(1.1)
            resp = _SESSION.get(CNN_FG_URL, timeout=8)
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

    # Semicircular needle endpoint on viewBox="0 0 220 128" (center 110, 108)
    nx, ny = _arc_point(score, 110.0, 108.0, 70.0)
    w1_x, w1_y = _arc_point(one_week, 110.0, 108.0, 86.0)
    m1_x, m1_y = _arc_point(one_month, 110.0, 108.0, 86.0)

    # 30-day sparkline from fear_and_greed_historical.data
    hist_points = raw.get("fear_and_greed_historical", {}).get("data", [])
    recent = hist_points[-30:] if len(hist_points) > 30 else hist_points
    spark_pts = []
    y_vals = []
    if len(recent) >= 2:
        n = len(recent)
        for i, pt in enumerate(recent):
            y_val = max(0.0, min(100.0, float(pt.get("y") or 50)))
            y_vals.append(round(y_val))
            sx = round((i / (n - 1)) * 236 + 2, 1)
            sy = round(56 - (y_val / 100.0) * 52, 1)
            spark_pts.append(f"{sx},{sy}")
    sparkline = " ".join(spark_pts)
    spark_area = f"2,58 {sparkline} 238,58" if spark_pts else ""
    min_30d = min(y_vals) if y_vals else score
    max_30d = max(y_vals) if y_vals else score

    # Parse 7 CNN sub-indicators
    pillars: list[dict] = []
    fear_pillars = 0
    greed_pillars = 0
    for label, abbr, key in _PILLAR_KEYS:
        obj = raw.get(key) or {}
        p_score = max(0, min(100, round(float(obj.get("score") or 50))))
        p_rating = _rating_short(obj.get("rating") or "neutral")
        if p_score < 45:
            fear_pillars += 1
        elif p_score > 55:
            greed_pillars += 1
        pillars.append(
            {
                "label": label,
                "abbr": abbr,
                "score": p_score,
                "short_rating": p_rating,
            }
        )

    pc_data = (raw.get("put_call_options") or {}).get("data") or []
    put_call_ratio = f"{float(pc_data[-1]['y']):.2f}" if pc_data and pc_data[-1].get("y") is not None else "--"

    hy_data = (raw.get("junk_bond_demand") or {}).get("data") or []
    hy_spread = f"{float(hy_data[-1]['y']):.2f}%" if hy_data and hy_data[-1].get("y") is not None else "--"

    vix_suite = _fetch_vix_suite()

    result = {
        "title": "Fear & Greed + VIX",
        "score": score,
        "rating": rating,
        "prev_close": prev_close,
        "one_week": one_week,
        "one_month": one_month,
        "one_year": one_year,
        "delta_day": f"{score - prev_close:+d}",
        "vix": vix_suite["vix"],
        "vix_delta": vix_suite["vix_delta"],
        "vix9d": vix_suite["vix9d"],
        "vix3m": vix_suite["vix3m"],
        "vix_term_regime": vix_suite["vix_term_regime"],
        "put_call_ratio": put_call_ratio,
        "hy_spread": hy_spread,
        "fear_pillars": fear_pillars,
        "greed_pillars": greed_pillars,
        "pillars": pillars,
        "pillars_png": _render_pillars_png(pillars, 340, 160),
        "nx": nx,
        "ny": ny,
        "w1_x": w1_x,
        "w1_y": w1_y,
        "m1_x": m1_x,
        "m1_y": m1_y,
        "dial_ticks": _build_dial_ticks(110.0, 108.0),
        "sparkline": sparkline,
        "spark_area": spark_area,
        "min_30d": min_30d,
        "max_30d": max_30d,
        "date": datetime.now(timezone.utc).strftime("%b %d, %Y").upper(),
    }
    _CACHE["ts"] = now
    _CACHE["data"] = result
    return result
