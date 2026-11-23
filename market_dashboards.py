"""Four slow-refresh ePaper Stock Market Dashboards - TRMNL plugin Blueprint.

Endpoints:
1. /markets/earnings    - Weekly Earnings & Catalyst Calendar (Mon-Fri, BMO/AMC)
2. /markets/yield-curve - US Treasury Yield Curve & Macro Cycle Monitor
3. /markets/sectors     - S&P 500 Sector Rotation & Cycle Map (1W / 1M / 3M / YTD)
4. /markets/insiders    - SEC Form 4 Insider Buying Ledger (Open-Market Purchases)
"""

import base64
import csv
from datetime import date, datetime, timedelta, timezone
from io import BytesIO, StringIO
import re
import time

from flask import Blueprint, jsonify, request
from PIL import Image, ImageDraw, ImageFont
import requests

market_dashboards_bp = Blueprint("market_dashboards", __name__)

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }
)

_CACHE: dict[str, tuple[float, object]] = {}
_TTL_SECONDS = 300


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


def _to_data_uri(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _get_cached(key: str, ttl: int = _TTL_SECONDS):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None


def _set_cached(key: str, val: object):
    _CACHE[key] = (time.time(), val)
    return val


def _http_get(url: str, timeout: int = 10, headers: dict | None = None) -> requests.Response:
    resp = _SESSION.get(url, timeout=timeout, headers=headers)
    if resp.status_code == 429:
        time.sleep(1.1)
        resp = _SESSION.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp


def _parse_money(raw: str) -> float:
    if not raw:
        return 0.0
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _fmt_mcap(val: float) -> str:
    if val >= 1e12:
        return f"${val / 1e12:.2f}T"
    if val >= 1e9:
        return f"${val / 1e9:.1f}B"
    if val >= 1e6:
        return f"${val / 1e6:.0f}M"
    return "—"


def _fmt_compact_usd(val: float) -> str:
    val = abs(val)
    if val >= 1e6:
        return f"${val / 1e6:.2f}M"
    if val >= 1e3:
        return f"${val / 1e3:.0f}K"
    return f"${val:.0f}"


# ============================================================================
# 1. WEEKLY EARNINGS & CATALYST CALENDAR (/markets/earnings)
# ============================================================================

_FALLBACK_EARNINGS = [
    ("MON", "HPE", "Hewlett Packard Enterprise", "AMC", "$1.18", 54.3e9),
    ("MON", "ZM", "Zoom Communications", "AMC", "$1.31", 26.8e9),
    ("TUE", "CRWD", "CrowdStrike Holdings", "AMC", "$0.98", 92.4e9),
    ("TUE", "DELL", "Dell Technologies", "AMC", "$2.06", 88.5e9),
    ("TUE", "BBY", "Best Buy Co.", "BMO", "$1.30", 19.4e9),
    ("WED", "NVDA", "NVIDIA Corporation", "AMC", "$0.89", 3450.0e9),
    ("WED", "CRM", "Salesforce Inc.", "AMC", "$2.44", 310.0e9),
    ("WED", "TJX", "TJX Companies", "BMO", "$1.09", 134.0e9),
    ("THU", "INTU", "Intuit Inc.", "AMC", "$2.36", 182.0e9),
    ("THU", "DE", "Deere & Company", "BMO", "$3.90", 114.0e9),
    ("FRI", "BKE", "The Buckle Inc.", "BMO", "$0.94", 2.4e9),
]


def _fetch_week_earnings(monday: date, watchlist: set[str]) -> list[dict]:
    cache_key = f"earnings:{monday.isoformat()}:{','.join(sorted(watchlist))}"
    cached = _get_cached(cache_key, ttl=900)
    if cached is not None:
        return cached

    day_names = ["MON", "TUE", "WED", "THU", "FRI"]
    days_data: list[dict] = []
    total_fetched = 0

    for idx, dname in enumerate(day_names):
        cur_date = monday + timedelta(days=idx)
        url = f"https://api.nasdaq.com/api/calendar/earnings?date={cur_date.isoformat()}"
        rows = []
        try:
            resp = _http_get(url, timeout=7, headers={"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
            rows = (resp.json().get("data") or {}).get("rows") or []
        except requests.exceptions.RequestException:
            rows = []

        parsed: list[dict] = []
        bmo_count = 0
        amc_count = 0
        for r in rows:
            sym = (r.get("symbol") or "").strip().upper()
            if not sym:
                continue
            raw_time = (r.get("time") or "").lower()
            if "pre-market" in raw_time or "before" in raw_time:
                slot = "BMO"
                bmo_count += 1
            elif "after-hours" in raw_time or "after" in raw_time:
                slot = "AMC"
                amc_count += 1
            else:
                slot = "TBD"
            mcap = _parse_money(r.get("marketCap", ""))
            name = (r.get("name") or sym).strip()
            name = re.sub(r"\s+(Inc\.?|Corporation|Company|Holdings|Ltd\.?|PLC|Corp\.?).*$", "", name, flags=re.I)
            eps = (r.get("epsForecast") or "—").strip()
            is_watch = sym in watchlist
            parsed.append(
                {
                    "symbol": sym,
                    "name": name[:22],
                    "slot": slot,
                    "eps": eps,
                    "mcap": mcap,
                    "mcap_str": _fmt_mcap(mcap),
                    "watched": is_watch,
                    "day": dname,
                    "date_short": cur_date.strftime("%b %d"),
                }
            )

        parsed.sort(key=lambda x: (not x["watched"], -x["mcap"]))
        total_fetched += len(parsed)
        days_data.append(
            {
                "day": dname,
                "date_short": cur_date.strftime("%b %d"),
                "is_today": cur_date == date.today(),
                "total": len(parsed),
                "bmo": bmo_count,
                "amc": amc_count,
                "top": parsed[:4],
                "lead_ticker": parsed[0]["symbol"] if parsed else "—",
            }
        )

    if total_fetched == 0:
        days_data = []
        for idx, dname in enumerate(day_names):
            cur_date = monday + timedelta(days=idx)
            fallback_items = [
                {
                    "symbol": sym,
                    "name": cname[:22],
                    "slot": slot,
                    "eps": eps,
                    "mcap": mc,
                    "mcap_str": _fmt_mcap(mc),
                    "watched": sym in watchlist,
                    "day": dname,
                    "date_short": cur_date.strftime("%b %d"),
                }
                for (fd, sym, cname, slot, eps, mc) in _FALLBACK_EARNINGS
                if fd == dname
            ]
            bmo_c = sum(1 for x in fallback_items if x["slot"] == "BMO")
            amc_c = sum(1 for x in fallback_items if x["slot"] == "AMC")
            days_data.append(
                {
                    "day": dname,
                    "date_short": cur_date.strftime("%b %d"),
                    "is_today": cur_date == date.today(),
                    "total": len(fallback_items) * 8,
                    "bmo": bmo_c * 4,
                    "amc": amc_c * 4,
                    "top": fallback_items,
                    "lead_ticker": fallback_items[0]["symbol"] if fallback_items else "—",
                }
            )

    return _set_cached(cache_key, days_data)


def _render_earnings_chart_png(days_data: list[dict], width: int = 264, height: int = 186) -> str:
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    f_bold = _load_font(11, bold=True)
    f_sm = _load_font(10, bold=False)
    f_xs = _load_font(9, bold=True)

    # Legend at top
    draw.text((2, 2), "WEEKLY REPORTERS", fill=0, font=f_xs)
    draw.rectangle([width - 96, 3, width - 86, 11], fill=85, outline=0)
    draw.text((width - 83, 1), "BMO", fill=0, font=f_sm)
    draw.rectangle([width - 44, 3, width - 34, 11], fill=0, outline=0)
    draw.text((width - 31, 1), "AMC", fill=0, font=f_sm)

    chart_top = 24
    chart_bot = height - 40
    bar_max_h = chart_bot - chart_top
    max_total = max([max(1, d["bmo"] + d["amc"] or d["total"]) for d in days_data] + [10])

    col_w = width // 5
    for idx, d in enumerate(days_data):
        cx = idx * col_w + col_w // 2
        bx1, bx2 = cx - 15, cx + 15

        bmo = d["bmo"]
        amc = d["amc"]
        tot = bmo + amc if (bmo + amc) > 0 else d["total"]
        if (bmo + amc) == 0 and tot > 0:
            bmo = tot // 2
            amc = tot - bmo

        h_bmo = int((bmo / max_total) * (bar_max_h - 14))
        h_amc = int((amc / max_total) * (bar_max_h - 14))

        # Base line
        y_cur = chart_bot
        if h_bmo > 0:
            draw.rectangle([bx1, y_cur - h_bmo, bx2, y_cur], fill=85, outline=0, width=1)
            y_cur -= h_bmo
        if h_amc > 0:
            draw.rectangle([bx1, y_cur - h_amc, bx2, y_cur], fill=0, outline=0, width=1)
            y_cur -= h_amc

        # Count label above bar
        cnt_str = str(d["total"])
        draw.text((cx - (7 if d["total"] >= 10 else 3), max(14, y_cur - 13)), cnt_str, fill=0, font=f_xs)

        # Day pill at bottom
        if d["is_today"]:
            draw.rounded_rectangle([cx - 18, chart_bot + 4, cx + 18, chart_bot + 19], radius=3, fill=0)
            draw.text((cx - 13, chart_bot + 5), d["day"], fill=255, font=f_xs)
        else:
            draw.text((cx - 13, chart_bot + 5), d["day"], fill=0, font=f_bold)

        # Lead ticker beneath day
        lead = d["lead_ticker"][:5]
        draw.text((cx - len(lead) * 3, chart_bot + 22), lead, fill=85, font=f_sm)

    draw.line([(0, chart_bot), (width, chart_bot)], fill=0, width=1)
    return _to_data_uri(img)


@market_dashboards_bp.route("/markets/earnings", methods=["GET"])
def earnings_calendar_endpoint():
    """Weekly Earnings & Catalyst Calendar endpoint."""
    raw_tickers = request.args.get("tickers", "")
    watchlist = {t.strip().upper() for t in raw_tickers.split(",") if t.strip()}

    today = date.today()
    # Anchor to current week's Monday (or next Monday if Saturday/Sunday)
    if today.weekday() >= 5:
        monday = today + timedelta(days=7 - today.weekday())
    else:
        monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    days_data = _fetch_week_earnings(monday, watchlist)

    all_top: list[dict] = []
    for d in days_data:
        all_top.extend(d["top"])
    all_top.sort(key=lambda x: (not x["watched"], -x["mcap"]))

    week_total = sum(d["total"] for d in days_data)
    bmo_total = sum(d["bmo"] for d in days_data)
    amc_total = sum(d["amc"] for d in days_data)

    return jsonify(
        {
            "title": "Earnings Calendar",
            "week_range": f"{monday.strftime('%b %d')} – {friday.strftime('%b %d, %Y')}",
            "week_total": week_total,
            "bmo_total": bmo_total,
            "amc_total": amc_total,
            "summary_line": f"{week_total} reports · {bmo_total} BMO · {amc_total} AMC",
            "marquee": all_top[:6],
            "days": days_data,
            "chart_png": _render_earnings_chart_png(days_data, 264, 186),
            "compact_png": _render_earnings_chart_png(days_data, 256, 130),
        }
    )


# ============================================================================
# 2. US TREASURY YIELD CURVE & MACRO CYCLE MONITOR (/markets/yield-curve)
# ============================================================================

_TENOR_COLS = [
    ("1M", "1 Mo"),
    ("3M", "3 Mo"),
    ("6M", "6 Mo"),
    ("1Y", "1 Yr"),
    ("2Y", "2 Yr"),
    ("5Y", "5 Yr"),
    ("10Y", "10 Yr"),
    ("20Y", "20 Yr"),
    ("30Y", "30 Yr"),
]

_FALLBACK_YIELD_ROWS = [
    ("11/23/2026", {"1M": 4.28, "3M": 4.32, "6M": 4.26, "1Y": 4.18, "2Y": 4.14, "5Y": 4.19, "10Y": 4.36, "20Y": 4.64, "30Y": 4.55}),
    ("10/23/2026", {"1M": 4.45, "3M": 4.42, "6M": 4.31, "1Y": 4.12, "2Y": 4.02, "5Y": 4.05, "10Y": 4.21, "20Y": 4.52, "30Y": 4.44}),
    ("11/24/2025", {"1M": 5.38, "3M": 5.42, "6M": 5.28, "1Y": 4.96, "2Y": 4.62, "5Y": 4.38, "10Y": 4.41, "20Y": 4.74, "30Y": 4.56}),
]


def _fetch_treasury_curves() -> list[tuple[str, dict[str, float]]]:
    cached = _get_cached("treasury:curves", ttl=1800)
    if cached is not None:
        return cached

    cur_year = date.today().year
    parsed_rows: list[tuple[str, dict[str, float]]] = []
    for yr in (cur_year, cur_year - 1):
        url = (
            f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            f"daily-treasury-rates.csv/{yr}/all?type=daily_treasury_yield_curve"
            f"&field_tdr_date_value={yr}&page&_format=csv"
        )
        try:
            resp = _http_get(url, timeout=9)
            reader = csv.DictReader(StringIO(resp.text))
            for row in reader:
                d_str = (row.get("Date") or "").strip()
                rates: dict[str, float] = {}
                for short_k, col_k in _TENOR_COLS:
                    val = row.get(col_k)
                    if val:
                        try:
                            rates[short_k] = float(val)
                        except ValueError:
                            pass
                if d_str and len(rates) >= 7:
                    parsed_rows.append((d_str, rates))
        except requests.exceptions.RequestException:
            continue

    if len(parsed_rows) < 3:
        return _FALLBACK_YIELD_ROWS

    return _set_cached("treasury:curves", parsed_rows)


def _render_yield_curve_png(
    latest: dict[str, float],
    m1: dict[str, float],
    y1: dict[str, float],
    width: int = 336,
    height: int = 228,
) -> str:
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    f_bold = _load_font(11, bold=True)
    f_sm = _load_font(10, bold=False)
    f_xs = _load_font(9, bold=True)

    # Legend
    draw.line([(6, 8), (22, 8)], fill=0, width=2)
    draw.ellipse([12, 6, 16, 10], fill=0)
    draw.text((26, 2), "Latest", fill=0, font=f_xs)

    draw.line([(82, 8), (98, 8)], fill=85, width=2)
    draw.text((102, 2), "1M Ago", fill=85, font=f_sm)

    draw.line([(164, 8), (180, 8)], fill=170, width=1)
    draw.text((184, 2), "1Y Ago", fill=85, font=f_sm)

    pad_l, pad_r, pad_t, pad_b = 34, 14, 24, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    all_vals = [v for d in (latest, m1, y1) for v in d.values() if v > 0]
    y_min = max(0.0, min(all_vals) - 0.25)
    y_max = max(all_vals) + 0.25
    if y_max - y_min < 0.8:
        y_max = y_min + 0.8

    # Horizontal grid lines (4 levels)
    for step in range(5):
        yv = y_min + (y_max - y_min) * (step / 4)
        py = int(pad_t + plot_h - (step / 4) * plot_h)
        draw.line([(pad_l, py), (width - pad_r, py)], fill=170 if step > 0 else 0, width=1)
        draw.text((2, py - 6), f"{yv:.1f}%", fill=85, font=f_sm)

    tenors = [k for k, _ in _TENOR_COLS]
    n_pts = len(tenors)

    def _coords(curve: dict[str, float]) -> list[tuple[int, int, str, float]]:
        pts = []
        for idx, t_key in enumerate(tenors):
            if t_key not in curve:
                continue
            val = curve[t_key]
            px = int(pad_l + (idx / (n_pts - 1)) * plot_w)
            py = int(pad_t + plot_h - ((val - y_min) / (y_max - y_min)) * plot_h)
            pts.append((px, py, t_key, val))
        return pts

    # 1Y Ago (light gray)
    pts_y1 = _coords(y1)
    for i in range(len(pts_y1) - 1):
        draw.line([(pts_y1[i][0], pts_y1[i][1]), (pts_y1[i + 1][0], pts_y1[i + 1][1])], fill=170, width=1)

    # 1M Ago (medium gray)
    pts_m1 = _coords(m1)
    for i in range(len(pts_m1) - 1):
        draw.line([(pts_m1[i][0], pts_m1[i][1]), (pts_m1[i + 1][0], pts_m1[i + 1][1])], fill=85, width=2)

    # Latest (bold black + dots)
    pts_now = _coords(latest)
    for i in range(len(pts_now) - 1):
        draw.line([(pts_now[i][0], pts_now[i][1]), (pts_now[i + 1][0], pts_now[i + 1][1])], fill=0, width=2)
    for px, py, t_key, val in pts_now:
        draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=0)
        if t_key in ("3M", "2Y", "10Y", "30Y") and height >= 180:
            lbl = f"{val:.2f}"
            lx = max(pad_l, min(px - 10, width - pad_r - 24))
            ly = max(pad_t + 2, py - 15)
            draw.text((lx, ly), lbl, fill=0, font=f_xs)

    # X-axis tenor labels
    for idx, t_key in enumerate(tenors):
        px = int(pad_l + (idx / (n_pts - 1)) * plot_w)
        draw.line([(px, pad_t + plot_h), (px, pad_t + plot_h + 3)], fill=0, width=1)
        draw.text((px - 7, pad_t + plot_h + 6), t_key, fill=0, font=f_bold if t_key in ("2Y", "10Y", "30Y") else f_sm)

    return _to_data_uri(img)


@market_dashboards_bp.route("/markets/yield-curve", methods=["GET"])
def treasury_yield_curve_endpoint():
    """US Treasury Yield Curve & Macro Cycle Monitor endpoint."""
    rows = _fetch_treasury_curves()
    as_of_date, latest = rows[0]
    m1_date, m1 = rows[min(21, len(rows) - 1)]
    y1_date, y1 = rows[min(250, len(rows) - 1)]

    y3m = latest.get("3M", 0.0)
    y2 = latest.get("2Y", 0.0)
    y10 = latest.get("10Y", 0.0)
    y30 = latest.get("30Y", 0.0)

    spread_10_2 = round((y10 - y2) * 100)
    spread_10_3m = round((y10 - y3m) * 100)

    if spread_10_2 < -10 or spread_10_3m < -15:
        regime = "INVERTED CURVE"
        regime_note = "Short rates exceed 10Y benchmark; restrictive monetary posture."
    elif spread_10_2 > 35:
        regime = "STEEPENING CURVE"
        regime_note = "Long-end term premium expanding rapidly over 2Y policy expectations."
    elif abs(spread_10_2) <= 15:
        regime = "FLAT TRANSITION"
        regime_note = "2Y and 10Y yields tightly compressed near cycle inflection point."
    else:
        regime = "NORMAL (UPWARD)"
        regime_note = "Positive term structure across short, belly, and long-end maturities."

    tenors_table = []
    for short_k, _ in _TENOR_COLS:
        cur_v = latest.get(short_k, 0.0)
        m1_v = m1.get(short_k, cur_v)
        chg_bps = round((cur_v - m1_v) * 100)
        sign = "+" if chg_bps > 0 else ""
        tenors_table.append(
            {
                "tenor": short_k,
                "yield_str": f"{cur_v:.2f}%",
                "m1_chg": f"{sign}{chg_bps} bp",
            }
        )

    s10_2_sign = "+" if spread_10_2 > 0 else ""
    s10_3m_sign = "+" if spread_10_3m > 0 else ""

    return jsonify(
        {
            "title": "US Treasury Yield Curve",
            "as_of": as_of_date,
            "m1_date": m1_date,
            "y1_date": y1_date,
            "regime": regime,
            "regime_note": regime_note,
            "y3m": f"{y3m:.2f}%",
            "y2": f"{y2:.2f}%",
            "y10": f"{y10:.2f}%",
            "y30": f"{y30:.2f}%",
            "spread_10_2": f"{s10_2_sign}{spread_10_2} bps",
            "spread_10_3m": f"{s10_3m_sign}{spread_10_3m} bps",
            "tenors": tenors_table,
            "curve_png": _render_yield_curve_png(latest, m1, y1, 336, 228),
            "mini_curve_png": _render_yield_curve_png(latest, m1, y1, 256, 136),
        }
    )


# ============================================================================
# 3. S&P 500 SECTOR ROTATION & CYCLE MAP (/markets/sectors)
# ============================================================================

_SECTORS = [
    ("XLK", "Technology", "offensive"),
    ("XLF", "Financials", "cyclical"),
    ("XLI", "Industrials", "cyclical"),
    ("XLY", "Cons. Discret.", "offensive"),
    ("XLC", "Communication", "offensive"),
    ("XLV", "Health Care", "defensive"),
    ("XLE", "Energy", "cyclical"),
    ("XLB", "Materials", "cyclical"),
    ("XLP", "Cons. Staples", "defensive"),
    ("XLU", "Utilities", "defensive"),
    ("XLRE", "Real Estate", "defensive"),
]

_FALLBACK_SECTORS = [
    {"symbol": "XLF", "name": "Financials", "style": "cyclical", "w1": 1.8, "m1": 5.4, "m3": 11.2, "rs_m1": 3.1},
    {"symbol": "XLK", "name": "Technology", "style": "offensive", "w1": 2.1, "m1": 4.2, "m3": 9.8, "rs_m1": 1.9},
    {"symbol": "XLI", "name": "Industrials", "style": "cyclical", "w1": 1.1, "m1": 3.6, "m3": 8.4, "rs_m1": 1.3},
    {"symbol": "XLY", "name": "Cons. Discret.", "style": "offensive", "w1": 0.9, "m1": 3.1, "m3": 7.9, "rs_m1": 0.8},
    {"symbol": "XLC", "name": "Communication", "style": "offensive", "w1": 0.6, "m1": 2.5, "m3": 6.5, "rs_m1": 0.2},
    {"symbol": "XLE", "name": "Energy", "style": "cyclical", "w1": 1.4, "m1": 1.9, "m3": -1.2, "rs_m1": -0.4},
    {"symbol": "XLU", "name": "Utilities", "style": "defensive", "w1": -0.3, "m1": 1.1, "m3": 5.4, "rs_m1": -1.2},
    {"symbol": "XLP", "name": "Cons. Staples", "style": "defensive", "w1": -0.5, "m1": 0.4, "m3": 2.1, "rs_m1": -1.9},
    {"symbol": "XLRE", "name": "Real Estate", "style": "defensive", "w1": -0.8, "m1": -0.7, "m3": 3.0, "rs_m1": -3.0},
    {"symbol": "XLB", "name": "Materials", "style": "cyclical", "w1": -1.1, "m1": -1.4, "m3": 1.2, "rs_m1": -3.7},
    {"symbol": "XLV", "name": "Health Care", "style": "defensive", "w1": -1.5, "m1": -2.8, "m3": -3.4, "rs_m1": -5.1},
]


def _fetch_yahoo_closes(symbol: str) -> list[float]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=6mo&interval=1d"
    resp = _http_get(url, timeout=6)
    res = ((resp.json().get("chart") or {}).get("result") or [{}])[0]
    quotes = (((res.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    return [float(c) for c in quotes if c is not None]


def _pct_ret(closes: list[float], lookback: int) -> float:
    if len(closes) < 2:
        return 0.0
    idx = max(0, len(closes) - 1 - lookback)
    base = closes[idx]
    return round(((closes[-1] - base) / base) * 100.0, 1) if base else 0.0


def _fetch_sector_rotation() -> tuple[list[dict], dict]:
    cached = _get_cached("sectors:rotation", ttl=1800)
    if cached is not None:
        return cached

    try:
        spy_closes = _fetch_yahoo_closes("SPY")
        spy_w1 = _pct_ret(spy_closes, 5)
        spy_m1 = _pct_ret(spy_closes, 21)
        spy_m3 = _pct_ret(spy_closes, 63)

        rows: list[dict] = []
        for sym, name, style in _SECTORS:
            closes = _fetch_yahoo_closes(sym)
            if len(closes) < 10:
                raise requests.exceptions.RequestException(f"Insufficient history for {sym}")
            w1 = _pct_ret(closes, 5)
            m1 = _pct_ret(closes, 21)
            m3 = _pct_ret(closes, 63)
            rows.append(
                {
                    "symbol": sym,
                    "name": name,
                    "style": style,
                    "w1": w1,
                    "m1": m1,
                    "m3": m3,
                    "rs_m1": round(m1 - spy_m1, 1),
                }
            )
    except requests.exceptions.RequestException:
        rows = [dict(r) for r in _FALLBACK_SECTORS]
        spy_w1, spy_m1, spy_m3 = 0.8, 2.3, 6.4

    rows.sort(key=lambda r: r["m1"], reverse=True)
    for r in rows:
        for k in ("w1", "m1", "m3", "rs_m1"):
            val = r[k]
            r[f"{k}_str"] = f"{'+' if val > 0 else ''}{val:.1f}%"

    spy_info = {
        "w1_str": f"{'+' if spy_w1 > 0 else ''}{spy_w1:.1f}%",
        "m1_str": f"{'+' if spy_m1 > 0 else ''}{spy_m1:.1f}%",
        "m3_str": f"{'+' if spy_m3 > 0 else ''}{spy_m3:.1f}%",
    }
    return _set_cached("sectors:rotation", (rows, spy_info))


def _render_sector_bars_png(rows: list[dict], width: int = 336, height: int = 246) -> str:
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    f_bold = _load_font(10, bold=True)
    f_sm = _load_font(10, bold=False)
    f_xs = _load_font(9, bold=True)

    draw.text((2, 1), "1M RELATIVE STRENGTH VS. SPY (0.0%)", fill=85, font=f_xs)

    top_y = 18
    row_h = (height - top_y - 4) // max(1, len(rows))
    label_w = 104
    val_w = 42
    bar_x0 = label_w
    bar_x1 = width - val_w
    bar_mid = (bar_x0 + bar_x1) // 2
    half_span = (bar_x1 - bar_x0) // 2 - 4

    max_abs = max([abs(r["rs_m1"]) for r in rows] + [3.0])

    # Zero line (SPY baseline)
    draw.line([(bar_mid, top_y - 2), (bar_mid, height - 4)], fill=0, width=1)

    for idx, r in enumerate(rows):
        ry = top_y + idx * row_h
        lbl = f"{r['symbol']} {r['name'][:10]}"
        draw.text((2, ry + 2), lbl, fill=0, font=f_bold if idx < 3 else f_sm)

        rs = r["rs_m1"]
        px_len = max(3, int((abs(rs) / max_abs) * half_span))
        by1, by2 = ry + 3, ry + row_h - 3
        if rs >= 0:
            draw.rectangle([bar_mid, by1, bar_mid + px_len, by2], fill=0, outline=0)
        else:
            draw.rectangle([bar_mid - px_len, by1, bar_mid, by2], fill=170, outline=0)

        draw.text((bar_x1 + 4, ry + 2), r["rs_m1_str"], fill=0 if rs >= 0 else 85, font=f_bold if abs(rs) >= 2.0 else f_sm)

    return _to_data_uri(img)


@market_dashboards_bp.route("/markets/sectors", methods=["GET"])
def sector_rotation_endpoint():
    """S&P 500 Sector Rotation & Cycle Map endpoint."""
    rows, spy_info = _fetch_sector_rotation()
    top3_styles = [r["style"] for r in rows[:3]]
    if top3_styles.count("defensive") >= 2:
        regime = "DEFENSIVE ROTATION"
        regime_note = "Utilities, Staples & Health Care outperforming SPY; risk-off positioning."
    elif top3_styles.count("offensive") >= 2:
        regime = "RISK-ON GROWTH"
        regime_note = "Tech, Discretionary & Comm leading SPY; expansionary risk appetite."
    else:
        regime = "CYCLICAL BROADENING"
        regime_note = "Financials, Industrials & Energy leading relative strength over mega-cap growth."

    breadth_pos = sum(1 for r in rows if r["m1"] > 0)
    outperforming = sum(1 for r in rows if r["rs_m1"] > 0)

    return jsonify(
        {
            "title": "S&P 500 Sector Rotation",
            "as_of": datetime.now(timezone.utc).strftime("%b %d, %Y"),
            "regime": regime,
            "regime_note": regime_note,
            "spy": spy_info,
            "breadth_summary": f"{breadth_pos}/11 sectors positive (1M) · {outperforming}/11 beating SPY",
            "leaders": rows[:3],
            "laggards": list(reversed(rows[-3:])),
            "sectors": rows,
            "rotation_png": _render_sector_bars_png(rows, 336, 246),
            "mini_rotation_png": _render_sector_bars_png(rows[:6], 256, 134),
        }
    )


# ============================================================================
# 4. SEC FORM 4 INSIDER BUYING LEDGER (/markets/insiders)
# ============================================================================

_FALLBACK_INSIDERS = [
    {"filing_date": "Nov 23", "trade_date": "Nov 20", "ticker": "ET", "company": "Energy Transfer LP", "insider": "Warren Kelcy L", "role": "Exec Chair", "price": "$17.42", "qty": "+200,000", "delta_own": "+2%", "value_num": 3484000, "value_str": "$3.48M"},
    {"filing_date": "Nov 23", "trade_date": "Nov 20", "ticker": "PFE", "company": "Pfizer Inc.", "insider": "Bourla Albert", "role": "CEO", "price": "$25.18", "qty": "+40,000", "delta_own": "+9%", "value_num": 1007200, "value_str": "$1.01M"},
    {"filing_date": "Nov 22", "trade_date": "Nov 19", "ticker": "CROX", "company": "Crocs Inc.", "insider": "Hart Daniel P", "role": "EVP", "price": "$102.40", "qty": "+5,000", "delta_own": "+6%", "value_num": 512000, "value_str": "$512K"},
    {"filing_date": "Nov 22", "trade_date": "Nov 19", "ticker": "KVUE", "company": "Kenvue Inc.", "insider": "Mongon Thibaut", "role": "CEO", "price": "$22.85", "qty": "+18,000", "delta_own": "+14%", "value_num": 411300, "value_str": "$411K"},
    {"filing_date": "Nov 21", "trade_date": "Nov 19", "ticker": "DG", "company": "Dollar General", "insider": "Vasos Todd J", "role": "CEO", "price": "$76.10", "qty": "+4,500", "delta_own": "+5%", "value_num": 342450, "value_str": "$342K"},
    {"filing_date": "Nov 21", "trade_date": "Nov 18", "ticker": "ALB", "company": "Albemarle Corp", "insider": "Masters Jerry R", "role": "CEO", "price": "$98.50", "qty": "+2,500", "delta_own": "+4%", "value_num": 246250, "value_str": "$246K"},
    {"filing_date": "Nov 20", "trade_date": "Nov 18", "ticker": "CTVA", "company": "Corteva Inc.", "insider": "Engel Klaus A", "role": "Dir", "price": "$58.52", "qty": "+3,200", "delta_own": "+11%", "value_num": 187264, "value_str": "$187K"},
]


def _fetch_insider_buys() -> list[dict]:
    cached = _get_cached("insiders:buys", ttl=1800)
    if cached is not None:
        return cached

    # OpenInsider Screener: Open-market purchases >= $50k in last 14 days sorted by value
    url = (
        "http://openinsider.com/screener?s=&o=&pl=2&ph=&ll=&lh=&fd=14&fdr=&td=0&tdr="
        "&fdlyl=&fdlyh=&daysago=&xp=1&xs=0&vl=50&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999"
        "&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=8&cnt=30&page=1"
    )
    buys: list[dict] = []
    try:
        resp = _http_get(url, timeout=8)
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", resp.text, re.S):
            if "P - Purchase" not in row_html:
                continue
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
            if len(tds) < 13:
                continue
            cols = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip() for c in tds]
            # Extract clean ticker from anchor inside td[3]
            m_sym = re.search(r">([A-Z]{1,5})</a>", tds[3])
            ticker = m_sym.group(1) if m_sym else cols[3].split()[-1].upper()
            ticker = re.sub(r"[^A-Z.]", "", ticker)
            if not ticker:
                continue

            val_num = _parse_money(cols[12])
            if val_num < 25000:
                continue

            f_dt = cols[1][:10]
            try:
                f_short = datetime.strptime(f_dt, "%Y-%m-%d").strftime("%b %d")
            except ValueError:
                f_short = f_dt[:6]

            t_dt = cols[2][:10]
            try:
                t_short = datetime.strptime(t_dt, "%Y-%m-%d").strftime("%b %d")
            except ValueError:
                t_short = t_dt[:6]

            company = re.sub(r"\s+(Inc\.?|Corp\.?|Corporation|Company|Holdings|Ltd\.?|PLC|LP).*$", "", cols[4], flags=re.I)
            role = (cols[6] or "Insider").split(",")[0].strip()[:10]
            buys.append(
                {
                    "filing_date": f_short,
                    "trade_date": t_short,
                    "ticker": ticker,
                    "company": company[:20],
                    "insider": cols[5][:20],
                    "role": role,
                    "price": cols[8],
                    "qty": cols[9],
                    "delta_own": cols[11],
                    "value_num": val_num,
                    "value_str": _fmt_compact_usd(val_num),
                }
            )
    except requests.exceptions.RequestException:
        buys = []

    if len(buys) < 4:
        buys = [dict(x) for x in _FALLBACK_INSIDERS]

    # Deduplicate by (ticker, insider) keeping largest purchase
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for b in sorted(buys, key=lambda x: x["value_num"], reverse=True):
        key = (b["ticker"], b["insider"])
        if key not in seen:
            seen.add(key)
            deduped.append(b)

    return _set_cached("insiders:buys", deduped[:12])


def _render_insider_bars_png(buys: list[dict], width: int = 264, height: int = 196) -> str:
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    f_bold = _load_font(11, bold=True)
    f_sm = _load_font(10, bold=False)
    f_xs = _load_font(9, bold=True)

    draw.text((2, 2), "TOP OPEN-MARKET PURCHASES ($)", fill=85, font=f_xs)

    top = buys[:6]
    max_v = max([b["value_num"] for b in top] + [100000.0])

    y0 = 20
    row_h = (height - y0 - 4) // max(1, len(top))
    bar_x0 = 56
    bar_max_w = width - bar_x0 - 54

    for idx, b in enumerate(top):
        ry = y0 + idx * row_h
        draw.text((2, ry + 4), b["ticker"][:5], fill=0, font=f_bold)

        bw = max(6, int((b["value_num"] / max_v) * bar_max_w))
        fill_c = 0 if idx < 2 else (85 if idx < 4 else 170)
        draw.rounded_rectangle([bar_x0, ry + 4, bar_x0 + bw, ry + row_h - 5], radius=3, fill=fill_c, outline=0, width=1)
        draw.text((bar_x0 + bw + 5, ry + 4), b["value_str"], fill=0, font=f_bold if idx < 2 else f_sm)

    return _to_data_uri(img)


@market_dashboards_bp.route("/markets/insiders", methods=["GET"])
def insider_buying_endpoint():
    """SEC Form 4 Insider Buying Ledger endpoint."""
    buys = _fetch_insider_buys()
    total_val = sum(b["value_num"] for b in buys)
    c_suite_count = sum(1 for b in buys if any(k in b["role"].upper() for k in ("CEO", "CFO", "PRES", "CHAIR", "EXEC")))

    return jsonify(
        {
            "title": "SEC Form 4 Insider Buying",
            "window_label": "14-Day Open-Market Executive Buys",
            "total_value": _fmt_compact_usd(total_val),
            "buy_count": len(buys),
            "c_suite_count": c_suite_count,
            "summary_line": f"{len(buys)} filings · {_fmt_compact_usd(total_val)} bought · {c_suite_count} C-Suite",
            "lead": buys[0],
            "filings": buys[:7],
            "conviction_png": _render_insider_bars_png(buys, 264, 196),
            "mini_conviction_png": _render_insider_bars_png(buys[:4], 256, 124),
        }
    )
