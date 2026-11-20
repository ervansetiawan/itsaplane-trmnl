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


def _moon_phase_name(d: date) -> str:
    dt = datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)
    known = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    cycle = ((dt - known).total_seconds() / 86400.0 % 29.53058867) / 29.53058867
    names = ["New Moon", "Waxing Cres.", "First Quarter", "Waxing Gib.", "Full Moon", "Waning Gib.", "Last Quarter", "Waning Cres."]
    return names[int((cycle * 8) + 0.5) % 8]


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
        lx = round(150 + (orbit_px + 10) * math.cos(lon_rad), 1)
        ly = round(150 - (orbit_px + 10) * math.sin(lon_rad) + 2.5, 1)

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

    return {
        "title": "Solar System Orrery",
        "date": d.strftime("%b %d, %Y").upper(),
        "day_of_year": d.timetuple().tm_yday,
        "moon_phase": _moon_phase_name(d),
        "earth_mars_au": f"{earth_mars_au:.2f} AU",
        "earth_mars_mkm": f"{earth_mars_au * 149.598:.0f}M km",
        "earth_venus_au": f"{earth_venus_au:.2f} AU",
        "earth_venus_mkm": f"{earth_venus_au * 149.598:.0f}M km",
        "planets": planets_out,
    }
