"""Stoic Sundial & Year Matrix: Solar Horizon Arc, 52-Week Grid & Daily Reflection."""

from datetime import date, datetime, timezone
import math

REFLECTIONS = [
    {
        "quote": "You have power over your mind—not outside events. Realize this, and you will find strength.",
        "author": "Marcus Aurelius",
        "source": "Meditations",
        "challenge": "Write down one thing outside your control today and consciously release it.",
    },
    {
        "quote": "We suffer more often in imagination than in reality.",
        "author": "Seneca",
        "source": "Letters from a Stoic",
        "challenge": "Take one task you have been dreading and spend 5 minutes starting it.",
    },
    {
        "quote": "Wealth consists not in having great possessions, but in having few wants.",
        "author": "Epictetus",
        "source": "Discourses",
        "challenge": "Skip one impulse purchase or distraction today and note what you gained.",
    },
    {
        "quote": "Waste no more time arguing about what a good person should be. Be one.",
        "author": "Marcus Aurelius",
        "source": "Meditations",
        "challenge": "Do one small, unasked kindness before the sun sets.",
    },
    {
        "quote": "He who has a why to live can bear almost any how.",
        "author": "Viktor Frankl",
        "source": "Man's Search for Meaning",
        "challenge": "Name the single most meaningful outcome you want from today.",
    },
    {
        "quote": "How we spend our days is, of course, how we spend our lives.",
        "author": "Annie Dillard",
        "source": "The Writing Life",
        "challenge": "Protect one 45-minute block of uninterrupted deep work.",
    },
    {
        "quote": "First say to yourself what you would be; and then do what you have to do.",
        "author": "Epictetus",
        "source": "Discourses",
        "challenge": "Ship one small, tangible artifact before noon.",
    },
    {
        "quote": "No man is free who is not master of himself.",
        "author": "Epictetus",
        "source": "Fragments",
        "challenge": "Keep your phone in another room for the first hour of work.",
    },
    {
        "quote": "Begin at once to live, and count each separate day as a separate life.",
        "author": "Seneca",
        "source": "Letters from a Stoic",
        "challenge": "Step outside for 10 minutes without audio or screens.",
    },
    {
        "quote": "The impediment to action advances action. What stands in the way becomes the way.",
        "author": "Marcus Aurelius",
        "source": "Meditations",
        "challenge": "Pick the hardest bug or bottleneck on your list and tackle it first.",
    },
    {
        "quote": "Study hard what interests you the most in the most undisciplined, irreverent way possible.",
        "author": "Richard Feynman",
        "source": "Letters",
        "challenge": "Spend 20 minutes learning how something everyday actually works.",
    },
    {
        "quote": "Luck is what happens when preparation meets opportunity.",
        "author": "Seneca",
        "source": "Attributed",
        "challenge": "Leave your workspace cleaner tonight than you found it this morning.",
    },
    {
        "quote": "If it is not right, do not do it; if it is not true, do not say it.",
        "author": "Marcus Aurelius",
        "source": "Meditations",
        "challenge": "Give one direct, honest, and kind answer where you might have hedged.",
    },
    {
        "quote": "It is not that we have a short time to live, but that we waste a lot of it.",
        "author": "Seneca",
        "source": "On the Shortness of Life",
        "challenge": "Close every open browser tab you haven't touched in 24 hours.",
    },
    {
        "quote": "The soul becomes dyed with the color of its thoughts.",
        "author": "Marcus Aurelius",
        "source": "Meditations",
        "challenge": "Send a short message appreciating someone whose work you respect.",
    },
    {
        "quote": "Simplicity is about subtracting the obvious and adding the meaningful.",
        "author": "John Maeda",
        "source": "The Laws of Simplicity",
        "challenge": "Remove one unnecessary step from a workflow you repeat daily.",
    },
]


def _daylight_hours(day_of_year: int, lat_deg: float) -> float:
    lat_rad = math.radians(max(-65.0, min(65.0, lat_deg)))
    decl = math.radians(23.44) * math.sin(math.radians((360.0 / 365.0) * (day_of_year - 81)))
    cos_h = -math.tan(lat_rad) * math.tan(decl)
    cos_h = max(-0.99, min(0.99, cos_h))
    h_deg = math.degrees(math.acos(cos_h))
    return (2.0 * h_deg) / 15.0


def generate_stoic_sundial(
    target_date: date | None = None,
    lat: float = 41.88,
    lon: float = -87.63,
    now_utc: datetime | None = None,
) -> dict:
    d = target_date or date.today()
    now = now_utc or datetime.now(timezone.utc)
    day_of_year = d.timetuple().tm_yday
    is_leap = (d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0))
    total_days = 366 if is_leap else 365
    days_left = total_days - day_of_year
    year_pct = round(day_of_year / total_days * 100)

    # Approximate local solar time from longitude
    local_solar_hour = (now.hour + now.minute / 60.0 + lon / 15.0) % 24.0
    dl_hours = _daylight_hours(day_of_year, lat)
    sunrise_hr = 12.0 - dl_hours / 2.0
    sunset_hr = 12.0 + dl_hours / 2.0

    if local_solar_hour <= sunrise_hr:
        day_pct = 0
        phase = "Pre-Dawn"
    elif local_solar_hour >= sunset_hr:
        day_pct = 100
        phase = "After Dusk"
    else:
        day_pct = round((local_solar_hour - sunrise_hr) / dl_hours * 100)
        if day_pct < 25:
            phase = "Morning"
        elif day_pct < 60:
            phase = "Solar Noon"
        else:
            phase = "Afternoon"

    # Semicircle arc: cx=140, cy=104, r=90
    theta = math.pi * (1.0 - day_pct / 100.0)
    sun_x = round(140.0 + 90.0 * math.cos(theta), 1)
    sun_y = round(104.0 - 90.0 * math.sin(theta), 1)

    dl_h = int(dl_hours)
    dl_m = int(round((dl_hours - dl_h) * 60))
    if dl_m == 60:
        dl_h += 1
        dl_m = 0

    current_week = min(52, max(1, (day_of_year - 1) // 7 + 1))
    weeks = []
    for w in range(1, 53):
        idx = w - 1
        col = idx % 13
        row = idx // 13
        state = "past" if w < current_week else ("current" if w == current_week else "future")
        weeks.append(
            {
                "week": w,
                "x": col * 18 + 4,
                "y": row * 18 + 4,
                "state": state,
            }
        )

    ref = REFLECTIONS[d.toordinal() % len(REFLECTIONS)]

    return {
        "title": "Stoic Sundial",
        "date": d.strftime("%b %d, %Y").upper(),
        "year": d.year,
        "day_of_year": day_of_year,
        "total_days": total_days,
        "days_left": days_left,
        "year_pct": year_pct,
        "current_week": current_week,
        "weeks_left": 52 - current_week,
        "day_pct": day_pct,
        "phase": phase,
        "daylight": f"{dl_h}h {dl_m:02d}m",
        "sun_x": sun_x,
        "sun_y": sun_y,
        "weeks": weeks,
        "quote": ref["quote"],
        "author": ref["author"],
        "source": ref["source"],
        "challenge": ref["challenge"],
    }
