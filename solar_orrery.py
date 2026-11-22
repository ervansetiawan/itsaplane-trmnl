"""Live Solar System Orrery using JPL J2000 Keplerian orbital elements."""

from datetime import date, datetime, timezone
import math

ZODIAC = ["ARI", "TAU", "GEM", "CAN", "LEO", "VIR", "LIB", "SCO", "SAG", "CAP", "AQU", "PIS"]

# J2000 Keplerian elements: (name, abbr, orbit_px, dot_r, a, e, L0, L_rate, w_bar, node)
# Rates in degrees per Julian century (36525 days) from J2000.0 (2000-01-01 12:00 TT)
PLANETS = [
    ("Mercury", "MER", 22, 3.0, 0.387099, 0.205636, 252.2503, 149472.6741, 77.4578, 48.3308),
    ("Venus",   "VEN", 38, 4.2, 0.723332, 0.006777, 181.9791,  58517.8154, 131.6025, 76.6798),
    ("Earth",   "EAR", 56, 4.5, 1.000003, 0.016711, 100.4646,  35999.3724, 102.9377, 0.0),
    ("Mars",    "MAR", 76, 3.8, 1.523710, 0.093394, 355.4330,  19140.3027, 336.0408, 49.5595),
    ("Jupiter", "JUP", 104, 6.5, 5.202887, 0.048386, 34.3964,   3034.7461, 14.7285, 100.4739),
    ("Saturn",  "SAT", 130, 5.5, 9.536676, 0.053862, 49.9542,   1222.4936, 92.5989, 113.6624),
]


def _julian_centuries_j2000(d: date) -> float:
    dt = datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)
    j2000 = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    days = (dt - j2000).total_seconds() / 86400.0
    return days / 36525.0


def _solve_eccentric_anomaly(M_rad: float, e: float) -> float:
    E = M_rad
    for _ in range(6):
        E = E - (E - e * math.sin(E) - M_rad) / (1.0 - e * math.cos(E))
    return E


def _moon_phase_info(d: date) -> tuple[str, int, int]:
    dt = datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)
    known = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    cycle = ((dt - known).total_seconds() / 86400.0 % 29.53058867) / 29.53058867
    names = [
        "New Moon", "Waxing Cres.", "First Quarter", "Waxing Gib.",
        "Full Moon", "Waning Gib.", "Last Quarter", "Waning Cres.",
    ]
    illum = round((1.0 - math.cos(2.0 * math.pi * cycle)) / 2.0 * 100)
    days_to_full = round(((0.5 - cycle) % 1.0) * 29.53058867)
    return names[int((cycle * 8) + 0.5) % 8], illum, days_to_full


def _sky_visibility(ex: float, ey: float, px: float, py: float) -> tuple[str, float, str]:
    """Computes sky visibility, Earth distance (AU), and light-travel time from Earth."""
    dx, dy = px - ex, py - ey
    dist_au = math.hypot(dx, dy)
    light_min = dist_au * 8.3167
    light_str = f"{light_min:.1f}m" if light_min < 10 else f"{round(light_min)}m"

    sun_ang = math.atan2(-ey, -ex)
    pl_ang = math.atan2(dy, dx)
    elong = (math.degrees(pl_ang - sun_ang) + 180.0) % 360.0 - 180.0

    if abs(elong) < 15:
        vis = "Near Sun"
    elif abs(elong) >= 135:
        vis = "All Night"
    elif elong > 0:
        vis = "Evening"
    else:
        vis = "Morning"
    return vis, dist_au, light_str


def _build_bezel() -> tuple[list[dict], list[dict], list[dict]]:
    """Precomputes 36 astrolabe bezel ticks, 12 zodiac sector labels, and 8 sun rays."""
    ticks = []
    for deg in range(0, 360, 10):
        rad = math.radians(deg)
        major = deg % 30 == 0
        r_in = 136 if major else 140
        ticks.append({
            "x1": round(150 + r_in * math.cos(rad), 1),
            "y1": round(150 - r_in * math.sin(rad), 1),
            "x2": round(150 + 144 * math.cos(rad), 1),
            "y2": round(150 - 144 * math.sin(rad), 1),
            "major": major,
        })
    sectors = []
    for idx, z in enumerate(ZODIAC):
        rad = math.radians(idx * 30 + 15)
        sectors.append({
            "label": z,
            "x": round(150 + 153.5 * math.cos(rad), 1),
            "y": round(150 - 153.5 * math.sin(rad) + 2.5, 1),
        })
    rays = []
    for deg in range(0, 360, 45):
        rad = math.radians(deg)
        rays.append({
            "x1": round(150 + 8.5 * math.cos(rad), 1),
            "y1": round(150 - 8.5 * math.sin(rad), 1),
            "x2": round(150 + 13.5 * math.cos(rad), 1),
            "y2": round(150 - 13.5 * math.sin(rad), 1),
        })
    return ticks, sectors, rays


def generate_solar_orrery(target_date: date | None = None) -> dict:
    d = target_date or date.today()
    T = _julian_centuries_j2000(d)

    planets_out = []
    vectors_au: dict[str, tuple[float, float]] = {}

    for name, abbr, orbit_px, dot_r, a, e, L0, L_rate, w_bar, _node in PLANETS:
        L = (L0 + L_rate * T) % 360.0
        M_deg = (L - w_bar) % 360.0
        M_rad = math.radians(M_deg)
        E = _solve_eccentric_anomaly(M_rad, e)

        xv = a * (math.cos(E) - e)
        yv = a * math.sqrt(1.0 - e * e) * math.sin(E)
        v_rad = math.atan2(yv, xv)
        r_au = math.hypot(xv, yv)
        lon_deg = (math.degrees(v_rad) + w_bar) % 360.0
        lon_rad = math.radians(lon_deg)

        # True heliocentric (x, y) in AU for inter-planet distances
        vectors_au[abbr] = (r_au * math.cos(lon_rad), r_au * math.sin(lon_rad))

        # SVG coords on 300x300 canvas (center 150, 150; 0° at right, counter-clockwise)
        cx = round(150 + orbit_px * math.cos(lon_rad), 1)
        cy = round(150 - orbit_px * math.sin(lon_rad), 1)
        lx = cx
        ly = round(cy - dot_r - (6.5 if abbr == "SAT" else 4.5), 1)

        zodiac = ZODIAC[int(lon_deg // 30) % 12]
        planets_out.append({
            "name": name,
            "abbr": abbr,
            "orbit_r": orbit_px,
            "dot_r": dot_r,
            "cx": cx,
            "cy": cy,
            "lx": lx,
            "ly": ly,
            "lon": f"{lon_deg:.1f}°",
            "au": f"{r_au:.2f} AU",
            "zodiac": zodiac,
            "is_saturn": abbr == "SAT",
            "is_earth": abbr == "EAR",
        })

    ex, ey = vectors_au["EAR"]
    mx, my = vectors_au["MAR"]
    vx, vy = vectors_au["VEN"]
    earth_mars_au = math.hypot(mx - ex, my - ey)
    earth_venus_au = math.hypot(vx - ex, vy - ey)

    for p in planets_out:
        if p["abbr"] == "EAR":
            p["sky"] = "Home"
            p["earth_au"] = "0.00 AU"
            p["light_time"] = "0m"
        else:
            px, py = vectors_au[p["abbr"]]
            vis, edist, lstr = _sky_visibility(ex, ey, px, py)
            p["sky"] = vis
            p["earth_au"] = f"{edist:.2f} AU"
            p["light_time"] = lstr

    earth_p = next(p for p in planets_out if p["abbr"] == "EAR")
    mars_p = next(p for p in planets_out if p["abbr"] == "MAR")
    moon_phase, moon_illum, days_to_full = _moon_phase_info(d)
    ticks, sectors, rays = _build_bezel()
    full_moon_label = "Full Moon today" if days_to_full == 0 else f"Full Moon in {days_to_full}d"

    return {
        "title": "Solar System Orrery",
        "date": d.strftime("%b %d, %Y").upper(),
        "day_of_year": d.timetuple().tm_yday,
        "moon_phase": moon_phase,
        "moon_illum": moon_illum,
        "full_moon_label": full_moon_label,
        "earth_mars_au": f"{earth_mars_au:.2f} AU",
        "earth_mars_mkm": f"{earth_mars_au * 149.598:.0f}M km",
        "earth_venus_au": f"{earth_venus_au:.2f} AU",
        "earth_venus_mkm": f"{earth_venus_au * 149.598:.0f}M km",
        "earth_cx": earth_p["cx"],
        "earth_cy": earth_p["cy"],
        "mars_cx": mars_p["cx"],
        "mars_cy": mars_p["cy"],
        "bezel_ticks": ticks,
        "zodiac_sectors": sectors,
        "sun_rays": rays,
        "planets": planets_out,
    }
