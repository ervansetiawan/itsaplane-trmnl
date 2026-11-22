"""Editorial Google Calendar Dashboard - TRMNL plugin Blueprint."""

import base64
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
import re
import time as time_mod
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, jsonify, request
from PIL import Image, ImageDraw, ImageFont
import requests

gcal_dashboard_bp = Blueprint("gcal_dashboard", __name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "itsaplane-trmnl/1.0 (+https://github.com/ervansetiawan/itsaplane-trmnl)"})

_ICS_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL_SECONDS = 60

_WEEKDAY_MAP = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_MEET_PATTERNS = [
    ("MEET", re.compile(r"meet\.google\.com", re.I)),
    ("ZOOM", re.compile(r"zoom\.us|zoomgov\.com", re.I)),
    ("TEAMS", re.compile(r"teams\.microsoft\.com|teams\.live\.com", re.I)),
    ("WEBEX", re.compile(r"webex\.com", re.I)),
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


_FALLBACK_OFFSETS = {
    "America/New_York": -5,
    "America/Chicago": -6,
    "America/Denver": -7,
    "America/Los_Angeles": -8,
    "Europe/London": 0,
    "Europe/Paris": 1,
    "Asia/Tokyo": 9,
    "UTC": 0,
}


def _resolve_tz(tz_name: str | None):
    key = (tz_name or "America/Chicago").strip()
    for candidate in (key, "America/Chicago"):
        try:
            return ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            if candidate in _FALLBACK_OFFSETS:
                return timezone(timedelta(hours=_FALLBACK_OFFSETS[candidate]))
    return datetime.now().astimezone().tzinfo or timezone.utc


def _fetch_ics_text(url: str) -> str:
    clean_url = url.strip()
    if clean_url.startswith("webcal://"):
        clean_url = "https://" + clean_url[len("webcal://") :]

    now_ts = time_mod.time()
    cached = _ICS_CACHE.get(clean_url)
    if cached and (now_ts - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    resp = _SESSION.get(clean_url, timeout=12)
    if resp.status_code == 429:
        time_mod.sleep(1.1)
        resp = _SESSION.get(clean_url, timeout=12)
    resp.raise_for_status()
    text = resp.text
    _ICS_CACHE[clean_url] = (now_ts, text)
    return text


def _unfold_ics(raw: str) -> list[str]:
    lines: list[str] = []
    for raw_line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] += raw_line[1:]
        else:
            lines.append(raw_line)
    return lines


def _unescape_ics(val: str) -> str:
    return (
        val.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _parse_ics_dt(val: str, params: dict[str, str], target_tz: ZoneInfo) -> tuple[datetime, bool]:
    val = val.strip()
    if len(val) == 8 and val.isdigit() or params.get("VALUE") == "DATE":
        d = datetime.strptime(val[:8], "%Y%m%d").date()
        return datetime.combine(d, time(0, 0), tzinfo=target_tz), True

    is_utc = val.endswith("Z")
    core = val[:-1] if is_utc else val
    dt_naive = datetime.strptime(core[:15], "%Y%m%dT%H%M%S")
    if is_utc:
        dt = dt_naive.replace(tzinfo=timezone.utc).astimezone(target_tz)
    elif "TZID" in params:
        src_tz = _resolve_tz(params["TZID"])
        dt = dt_naive.replace(tzinfo=src_tz).astimezone(target_tz)
    else:
        dt = dt_naive.replace(tzinfo=target_tz)
    return dt, False


def _parse_duration(dur_str: str) -> timedelta:
    match = re.match(r"^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", dur_str.strip())
    if not match:
        return timedelta(hours=1)
    weeks, days, hours, mins, secs = (int(g or 0) for g in match.groups())
    return timedelta(weeks=weeks, days=days, hours=hours, minutes=mins, seconds=secs)


def _parse_rrule(rule_str: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for item in rule_str.strip().split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.upper()] = v.upper()
    return parts


def _detect_meet_tag(location: str, description: str) -> str:
    combined = f"{location} {description}"
    for tag, pattern in _MEET_PATTERNS:
        if pattern.search(combined):
            return tag
    return ""


def _clean_location(location: str) -> str:
    if not location:
        return ""
    if re.match(r"^https?://", location.strip(), re.I):
        return ""
    loc = location.strip()
    return (loc[:28] + "...") if len(loc) > 30 else loc


def _expand_rrule(
    dtstart: datetime,
    duration: timedelta,
    rrule: dict[str, str],
    exdates: set[date],
    win_start: datetime,
    win_end: datetime,
    target_tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    freq = rrule.get("FREQ")
    if not freq:
        return [(dtstart, dtstart + duration)]

    interval = max(1, int(rrule.get("INTERVAL", "1")))
    max_count = int(rrule["COUNT"]) if "COUNT" in rrule else 500
    until_dt: datetime | None = None
    if "UNTIL" in rrule:
        u_raw = rrule["UNTIL"]
        if len(u_raw) == 8:
            until_dt = datetime.combine(datetime.strptime(u_raw, "%Y%m%d").date(), time(23, 59, 59), tzinfo=target_tz)
        else:
            until_dt, _ = _parse_ics_dt(u_raw, {}, target_tz)

    byday_tokens = [tok[-2:] for tok in rrule.get("BYDAY", "").split(",") if tok[-2:] in _WEEKDAY_MAP]
    byday_nums = [_WEEKDAY_MAP[tok] for tok in byday_tokens]

    results: list[tuple[datetime, datetime]] = []
    emitted = 0
    cur = dtstart

    if freq == "WEEKLY" and byday_nums:
        week_start = dtstart - timedelta(days=dtstart.weekday())
        while week_start <= win_end and emitted < max_count:
            for wd in sorted(byday_nums):
                cand = (week_start + timedelta(days=wd)).replace(
                    hour=dtstart.hour, minute=dtstart.minute, second=dtstart.second
                )
                if cand < dtstart:
                    continue
                if until_dt and cand > until_dt:
                    return results
                if cand > win_end:
                    return results
                emitted += 1
                if emitted > max_count:
                    return results
                if cand.date() not in exdates and cand + duration > win_start:
                    results.append((cand, cand + duration))
            week_start += timedelta(weeks=interval)
        return results

    step_limit = 730
    for _ in range(step_limit):
        if until_dt and cur > until_dt:
            break
        if cur > win_end or emitted >= max_count:
            break
        emitted += 1
        if cur.date() not in exdates and cur + duration > win_start:
            results.append((cur, cur + duration))

        if freq == "DAILY":
            cur += timedelta(days=interval)
        elif freq == "WEEKLY":
            cur += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            month_idx = cur.month - 1 + interval
            year = cur.year + month_idx // 12
            month = month_idx % 12 + 1
            day = min(cur.day, 28)
            cur = cur.replace(year=year, month=month, day=day)
        elif freq == "YEARLY":
            try:
                cur = cur.replace(year=cur.year + interval)
            except ValueError:
                cur = cur.replace(year=cur.year + interval, day=28)
        else:
            break

    return results


def parse_ics_events(
    raw_ics: str,
    cal_name: str,
    win_start: datetime,
    win_end: datetime,
    target_tz: ZoneInfo,
) -> list[dict]:
    """Parse VEVENTs from raw ICS text and expand recurrences inside [win_start, win_end]."""
    lines = _unfold_ics(raw_ics)
    events: list[dict] = []
    cur: dict | None = None

    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = {"exdates": set()}
            continue
        if line == "END:VEVENT":
            if cur and "dtstart" in cur and cur.get("status", "").upper() != "CANCELLED":
                dtstart, all_day = cur["dtstart"]
                if "dtend" in cur:
                    dtend, _ = cur["dtend"]
                elif "duration" in cur:
                    dtend = dtstart + cur["duration"]
                else:
                    dtend = dtstart + (timedelta(days=1) if all_day else timedelta(hours=1))
                dur = max(timedelta(minutes=5), dtend - dtstart)

                if "rrule" in cur:
                    occs = _expand_rrule(dtstart, dur, cur["rrule"], cur["exdates"], win_start, win_end, target_tz)
                elif dtend > win_start and dtstart < win_end:
                    occs = [(dtstart, dtend)]
                else:
                    occs = []

                summary = cur.get("summary") or "(Busy)"
                location = _clean_location(cur.get("location", ""))
                meet_tag = _detect_meet_tag(cur.get("location", ""), cur.get("description", ""))
                for s_dt, e_dt in occs:
                    events.append(
                        {
                            "title": summary,
                            "start": s_dt,
                            "end": e_dt,
                            "all_day": all_day,
                            "location": location,
                            "meet_tag": meet_tag,
                            "calendar": cal_name,
                        }
                    )
            cur = None
            continue

        if cur is None or ":" not in line:
            continue
        left, val = line.split(":", 1)
        parts = left.split(";")
        prop = parts[0].upper()
        params: dict[str, str] = {}
        for p in parts[1:]:
            if "=" in p:
                pk, pv = p.split("=", 1)
                params[pk.upper()] = pv

        if prop == "SUMMARY":
            cur["summary"] = _unescape_ics(val)
        elif prop == "LOCATION":
            cur["location"] = _unescape_ics(val)
        elif prop == "DESCRIPTION":
            cur["description"] = _unescape_ics(val)
        elif prop == "STATUS":
            cur["status"] = val.strip()
        elif prop == "DTSTART":
            cur["dtstart"] = _parse_ics_dt(val, params, target_tz)
        elif prop == "DTEND":
            cur["dtend"] = _parse_ics_dt(val, params, target_tz)
        elif prop == "DURATION":
            cur["duration"] = _parse_duration(val)
        elif prop == "RRULE":
            cur["rrule"] = _parse_rrule(val)
        elif prop == "EXDATE":
            for item in val.split(","):
                ex_dt, _ = _parse_ics_dt(item, params, target_tz)
                cur["exdates"].add(ex_dt.date())

    return events


def _demo_events(now_dt: datetime, target_tz: ZoneInfo) -> list[dict]:
    today = now_dt.date()
    d = lambda day_off, h, m=0: datetime.combine(today + timedelta(days=day_off), time(h, m), tzinfo=target_tz)

    events = [
        {
            "title": "Q4 Roadmap Freeze",
            "start": datetime.combine(today, time(0, 0), tzinfo=target_tz),
            "end": datetime.combine(today + timedelta(days=1), time(0, 0), tzinfo=target_tz),
            "all_day": True,
            "location": "",
            "meet_tag": "",
            "calendar": "Work",
        },
        {
            "title": "Morning Standup",
            "start": d(0, 9, 0),
            "end": d(0, 9, 30),
            "all_day": False,
            "location": "",
            "meet_tag": "MEET",
            "calendar": "Work",
        },
        {
            "title": "Architecture & Design Review",
            "start": d(0, 10, 30),
            "end": d(0, 11, 30),
            "all_day": False,
            "location": "Studio B / Meet",
            "meet_tag": "MEET",
            "calendar": "Work",
        },
        {
            "title": "Lunch w/ Maya",
            "start": d(0, 12, 15),
            "end": d(0, 13, 0),
            "all_day": False,
            "location": "Tartine Bakery",
            "meet_tag": "",
            "calendar": "Personal",
        },
        {
            "title": "Deep Work: ePaper Renderer",
            "start": d(0, 13, 30),
            "end": d(0, 15, 0),
            "all_day": False,
            "location": "Focus Block",
            "meet_tag": "",
            "calendar": "Work",
        },
        {
            "title": "1:1 Sync with Alex",
            "start": d(0, 15, 30),
            "end": d(0, 16, 15),
            "all_day": False,
            "location": "",
            "meet_tag": "ZOOM",
            "calendar": "Work",
        },
        {
            "title": "Evening Run / Gym",
            "start": d(0, 18, 0),
            "end": d(0, 19, 0),
            "all_day": False,
            "location": "Lakefront Trail",
            "meet_tag": "",
            "calendar": "Personal",
        },
        {
            "title": "Product Weekly",
            "start": d(1, 9, 30),
            "end": d(1, 10, 30),
            "all_day": False,
            "location": "",
            "meet_tag": "MEET",
            "calendar": "Work",
        },
        {
            "title": "API Latency Triage",
            "start": d(1, 11, 30),
            "end": d(1, 12, 15),
            "all_day": False,
            "location": "",
            "meet_tag": "ZOOM",
            "calendar": "Work",
        },
        {
            "title": "Dentist Appointment",
            "start": d(1, 16, 0),
            "end": d(1, 17, 0),
            "all_day": False,
            "location": "Downtown Dental",
            "meet_tag": "",
            "calendar": "Personal",
        },
    ]

    # Populate sample density dots across the rest of the current month
    month_start = today.replace(day=1)
    for offset in range(0, 31):
        cand = month_start + timedelta(days=offset)
        if cand.month != today.month or cand in (today, today + timedelta(days=1)):
            continue
        if cand.weekday() < 5:
            count = 1 + (cand.day % 3)
            for k in range(count):
                s_dt = datetime.combine(cand, time(9 + k * 2, 0), tzinfo=target_tz)
                events.append(
                    {
                        "title": "Demo Event",
                        "start": s_dt,
                        "end": s_dt + timedelta(hours=1),
                        "all_day": False,
                        "location": "",
                        "meet_tag": "",
                        "calendar": "Work",
                    }
                )
    return events


def _fmt_time_short(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _fmt_duration(delta: timedelta) -> str:
    mins = max(1, int(delta.total_seconds() // 60))
    hours, rem = divmod(mins, 60)
    if hours and rem:
        return f"{hours}h {rem}m"
    if hours:
        return f"{hours}h"
    return f"{rem}m"


def _compute_free_stats(timed_today: list[dict], now_dt: datetime, today: date, target_tz: ZoneInfo) -> tuple[int, str]:
    work_start = datetime.combine(today, time(8, 0), tzinfo=target_tz)
    work_end = datetime.combine(today, time(19, 0), tzinfo=target_tz)
    cursor = max(work_start, now_dt)

    busy_mins = 0
    intervals: list[tuple[datetime, datetime]] = []
    for ev in timed_today:
        s = max(ev["start"], work_start)
        e = min(ev["end"], work_end)
        if e > s:
            intervals.append((s, e))
    intervals.sort()

    merged: list[tuple[datetime, datetime]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    for s, e in merged:
        busy_mins += int((e - s).total_seconds() // 60)

    next_free = "Clear evening ahead"
    if cursor < work_end:
        probe = cursor
        for s, e in merged:
            if e <= probe:
                continue
            if s - probe >= timedelta(minutes=30):
                next_free = f"Free {_fmt_time_short(probe)}–{_fmt_time_short(s)} ({_fmt_duration(s - probe)})"
                break
            probe = max(probe, e)
        else:
            if work_end - probe >= timedelta(minutes=30):
                next_free = f"Free {_fmt_time_short(probe)}–{_fmt_time_short(work_end)} ({_fmt_duration(work_end - probe)})"

    return busy_mins, next_free


def _draw_day_bar(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    width: int,
    height: int,
    timed_today: list[dict],
    now_dt: datetime,
    today: date,
    target_tz: ZoneInfo,
) -> None:
    start_h, end_h = 7, 21
    total_mins = (end_h - start_h) * 60
    font_sm = _load_font(10, bold=False)
    font_xs = _load_font(9, bold=True)

    bar_y = y0 + 16
    bar_h = height - 28

    # Background track (lightest gray border, white fill)
    draw.rounded_rectangle([x0, bar_y, x0 + width, bar_y + bar_h], radius=4, fill=255, outline=170, width=1)

    # Hour grid ticks
    for hr in range(start_h, end_h + 1, 2):
        frac = (hr - start_h) / (end_h - start_h)
        tx = int(x0 + frac * width)
        draw.line([(tx, bar_y), (tx, bar_y + bar_h)], fill=170, width=1)
        label = f"{hr if hr <= 12 else hr - 12}{'a' if hr < 12 else 'p'}"
        anchor_x = max(x0 + 2, min(tx - 6, x0 + width - 18))
        draw.text((anchor_x, bar_y + bar_h + 3), label, fill=85, font=font_sm)

    # Event blocks
    win_start = datetime.combine(today, time(start_h, 0), tzinfo=target_tz)
    for ev in timed_today:
        s_min = max(0, (ev["start"] - win_start).total_seconds() / 60)
        e_min = min(total_mins, (ev["end"] - win_start).total_seconds() / 60)
        if e_min <= s_min:
            continue
        bx1 = int(x0 + (s_min / total_mins) * width)
        bx2 = max(bx1 + 4, int(x0 + (e_min / total_mins) * width))
        is_past = ev["end"] <= now_dt
        is_now = ev["start"] <= now_dt < ev["end"]
        fill_shade = 170 if is_past else (0 if is_now else 85)
        draw.rounded_rectangle([bx1, bar_y + 3, bx2, bar_y + bar_h - 3], radius=3, fill=fill_shade, outline=0, width=1)

    # NOW needle
    now_min = (now_dt - win_start).total_seconds() / 60
    if 0 <= now_min <= total_mins:
        nx = int(x0 + (now_min / total_mins) * width)
        draw.line([(nx, y0 + 10), (nx, bar_y + bar_h + 2)], fill=0, width=2)
        pill_x1 = max(x0, min(nx - 14, x0 + width - 28))
        draw.rounded_rectangle([pill_x1, y0, pill_x1 + 28, y0 + 12], radius=3, fill=0)
        draw.text((pill_x1 + 4, y0 + 1), "NOW", fill=255, font=font_xs)


def _render_overview_png(
    today: date,
    now_dt: datetime,
    target_tz: ZoneInfo,
    day_counts: dict[date, int],
    timed_today: list[dict],
) -> str:
    w, h = 264, 260
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)

    font_hdr = _load_font(11, bold=True)
    font_day = _load_font(11, bold=False)
    font_day_b = _load_font(11, bold=True)

    # Mini Month Grid (top)
    weekdays = ["M", "T", "W", "T", "F", "S", "S"]
    col_w = w // 7
    for idx, wd in enumerate(weekdays):
        cx = idx * col_w + col_w // 2
        draw.text((cx - 4, 2), wd, fill=85, font=font_hdr)

    draw.line([(0, 17), (w, 17)], fill=170, width=1)

    first_day = today.replace(day=1)
    start_pad = first_day.weekday()
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    days_in_month = (next_month - first_day).days

    row_h = 24
    grid_y = 22
    for day_num in range(1, days_in_month + 1):
        cell_idx = start_pad + day_num - 1
        row = cell_idx // 7
        col = cell_idx % 7
        cx = col * col_w + col_w // 2
        cy = grid_y + row * row_h

        cell_date = first_day.replace(day=day_num)
        is_today = cell_date == today
        is_weekend = col >= 5
        cnt = min(3, day_counts.get(cell_date, 0))

        if is_today:
            draw.rounded_rectangle([cx - 12, cy, cx + 12, cy + 16], radius=4, fill=0)
            txt_fill = 255
            fnt = font_day_b
        else:
            txt_fill = 85 if is_weekend else 0
            fnt = font_day

        num_str = str(day_num)
        tx = cx - (7 if day_num >= 10 else 3)
        draw.text((tx, cy + 1), num_str, fill=txt_fill, font=fnt)

        if cnt > 0:
            dot_y = cy + 18
            spacing = 5
            start_dx = cx - ((cnt - 1) * spacing) // 2
            for k in range(cnt):
                dx = start_dx + k * spacing
                draw.ellipse([dx - 1, dot_y - 1, dx + 1, dot_y + 1], fill=0)

    # Divider + Day Timeline Strip (bottom)
    num_rows = (start_pad + days_in_month + 6) // 7
    div_y = grid_y + num_rows * row_h + 6
    draw.line([(0, div_y), (w, div_y)], fill=170, width=1)
    draw.text((0, div_y + 5), "DAY TIMELINE (7A–9P)", fill=85, font=_load_font(10, bold=True))

    _draw_day_bar(draw, 2, div_y + 18, w - 4, 58, timed_today, now_dt, today, target_tz)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _render_daybar_png(
    today: date,
    now_dt: datetime,
    target_tz: ZoneInfo,
    timed_today: list[dict],
) -> str:
    w, h = 260, 58
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    _draw_day_bar(draw, 2, 2, w - 4, h - 4, timed_today, now_dt, today, target_tz)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_gcal_dashboard(
    ics_urls_raw: str = "",
    tz_name: str = "America/Chicago",
    cal_names_raw: str = "",
) -> dict:
    """Build the full Google Calendar dashboard payload for TRMNL."""
    target_tz = _resolve_tz(tz_name)
    now_dt = datetime.now(target_tz)
    today = now_dt.date()

    month_start = datetime.combine(today.replace(day=1), time(0, 0), tzinfo=target_tz)
    win_end = datetime.combine(today + timedelta(days=35), time(23, 59), tzinfo=target_tz)

    urls = [u.strip() for u in ics_urls_raw.split(",") if u.strip()]
    names = [n.strip() for n in cal_names_raw.split(",") if n.strip()]

    is_demo = len(urls) == 0
    if is_demo:
        all_events = _demo_events(now_dt, target_tz)
    else:
        all_events = []
        for idx, url in enumerate(urls):
            cal_label = names[idx] if idx < len(names) else (f"Cal {idx + 1}" if len(urls) > 1 else "Calendar")
            raw_ics = _fetch_ics_text(url)
            all_events.extend(parse_ics_events(raw_ics, cal_label, month_start, win_end, target_tz))

    day_counts: dict[date, int] = {}
    all_day_today: list[dict] = []
    timed_today: list[dict] = []
    tomorrow_date = today + timedelta(days=1)
    tomorrow_events: list[dict] = []

    for ev in all_events:
        ev_date = ev["start"].date()
        if ev["all_day"]:
            if ev["start"].date() <= today < ev["end"].date():
                all_day_today.append({"title": ev["title"], "calendar": ev["calendar"]})
            continue

        day_counts[ev_date] = day_counts.get(ev_date, 0) + 1
        if ev_date == today:
            timed_today.append(ev)
        elif ev_date == tomorrow_date:
            tomorrow_events.append(ev)

    timed_today.sort(key=lambda e: e["start"])
    tomorrow_events.sort(key=lambda e: e["start"])

    # Classify today's timed events & pick Hero (NOW or NEXT)
    hero: dict | None = None
    formatted_today: list[dict] = []
    for ev in timed_today:
        if ev["end"] <= now_dt:
            state = "past"
        elif ev["start"] <= now_dt < ev["end"]:
            state = "now"
        else:
            state = "next" if hero is None else "later"

        entry = {
            "title": ev["title"],
            "start_short": _fmt_time_short(ev["start"]),
            "end_short": _fmt_time_short(ev["end"]),
            "time_range": f"{_fmt_time_short(ev['start'])} – {_fmt_time_short(ev['end'])}",
            "duration": _fmt_duration(ev["end"] - ev["start"]),
            "location": ev["location"],
            "meet_tag": ev["meet_tag"],
            "calendar": ev["calendar"],
            "state": state,
        }
        if hero is None and state in ("now", "next"):
            delta = (ev["end"] - now_dt) if state == "now" else (ev["start"] - now_dt)
            countdown = f"{_fmt_duration(delta)} left" if state == "now" else f"in {_fmt_duration(delta)}"
            hero = {**entry, "status": state.upper(), "countdown": countdown}
        elif state != "past" or len(timed_today) <= 4:
            formatted_today.append(entry)

    busy_mins, free_window = _compute_free_stats(timed_today, now_dt, today, target_tz)
    busy_str = _fmt_duration(timedelta(minutes=busy_mins)) if busy_mins else "0m"

    formatted_tomorrow = [
        {
            "title": ev["title"],
            "start_short": _fmt_time_short(ev["start"]),
            "duration": _fmt_duration(ev["end"] - ev["start"]),
        }
        for ev in tomorrow_events[:3]
    ]

    return {
        "title": "Agenda",
        "is_demo": is_demo,
        "day_num": today.strftime("%d").lstrip("0"),
        "weekday": today.strftime("%A").upper(),
        "month_year": today.strftime("%b %Y").upper(),
        "date_label": today.strftime("%b %d, %Y"),
        "now_time": _fmt_time_short(now_dt),
        "event_count": len(timed_today),
        "summary_line": f"{len(timed_today)} events · {busy_str} booked",
        "free_window": free_window,
        "all_day": all_day_today[:2],
        "hero": hero,
        "today_events": formatted_today[:5],
        "tomorrow_label": tomorrow_date.strftime("%a, %b %d").upper(),
        "tomorrow_events": formatted_tomorrow,
        "overview_png": _render_overview_png(today, now_dt, target_tz, day_counts, timed_today),
        "daybar_png": _render_daybar_png(today, now_dt, target_tz, timed_today),
    }


@gcal_dashboard_bp.route("/gcal/dashboard", methods=["GET"])
def gcal_dashboard():
    """TRMNL polling endpoint for the Editorial Google Calendar Dashboard."""
    ics_url = request.args.get("ics_url", "")
    tz_name = request.args.get("tz", "America/Chicago")
    cal_names = request.args.get("calendar_names", "")
    try:
        payload = build_gcal_dashboard(ics_url, tz_name, cal_names)
        return jsonify(payload)
    except requests.exceptions.Timeout:
        return jsonify({"error": "Upstream calendar timed out"}), 504
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        return jsonify({"error": f"Calendar fetch failed ({status})"}), status if status in (401, 403, 404, 429) else 502
    except requests.exceptions.RequestException as exc:
        return jsonify({"error": f"Calendar connection error: {exc}"}), 502
