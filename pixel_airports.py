"""Pixel Airports - TRMNL plugin backend rendering recognizable airport diagrams of random world airports."""

import math
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request

from airport_diagram import is_cached, render_airport_diagram

pixel_airports_bp = Blueprint("pixel_airports", __name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "pixel-airports-trmnl/1.0"})

# pylint: disable=line-too-long
# Iconic & diverse world airports (runways, island strips, mountain fields, mega-hubs)
LOCATIONS = [
    {"iata": "SFO", "icao": "KSFO", "name": "San Francisco Intl", "city": "San Francisco", "country": "United States", "region": "North America", "lat": 37.6213, "lon": -122.3790},
    {"iata": "KIX", "icao": "RJBB", "name": "Kansai Intl", "city": "Osaka", "country": "Japan", "region": "Asia", "lat": 34.4347, "lon": 135.2440},
    {"iata": "SXM", "icao": "TNCM", "name": "Princess Juliana Intl", "city": "Sint Maarten", "country": "Caribbean", "region": "North America", "lat": 18.0410, "lon": -63.1089},
    {"iata": "GIB", "icao": "LXGB", "name": "Gibraltar Intl", "city": "Gibraltar", "country": "Gibraltar", "region": "Europe", "lat": 36.1512, "lon": -5.3497},
    {"iata": "HKG", "icao": "VHHH", "name": "Hong Kong Intl", "city": "Hong Kong", "country": "China", "region": "Asia", "lat": 22.3080, "lon": 113.9185},
    {"iata": "LHR", "icao": "EGLL", "name": "London Heathrow", "city": "London", "country": "United Kingdom", "region": "Europe", "lat": 51.4700, "lon": -0.4543},
    {"iata": "JFK", "icao": "KJFK", "name": "John F. Kennedy Intl", "city": "New York", "country": "United States", "region": "North America", "lat": 40.6413, "lon": -73.7781},
    {"iata": "AMS", "icao": "EHAM", "name": "Amsterdam Schiphol", "city": "Amsterdam", "country": "Netherlands", "region": "Europe", "lat": 52.3105, "lon": 4.7683},
    {"iata": "DXB", "icao": "OMDB", "name": "Dubai Intl", "city": "Dubai", "country": "UAE", "region": "Asia", "lat": 25.2532, "lon": 55.3657},
    {"iata": "SIN", "icao": "WSSS", "name": "Singapore Changi", "city": "Singapore", "country": "Singapore", "region": "Asia", "lat": 1.3644, "lon": 103.9915},
    {"iata": "SYD", "icao": "YSSY", "name": "Sydney Kingsford Smith", "city": "Sydney", "country": "Australia", "region": "Oceania", "lat": -33.9399, "lon": 151.1753},
    {"iata": "FNC", "icao": "LPMA", "name": "Madeira Cristiano Ronaldo", "city": "Funchal", "country": "Portugal", "region": "Europe", "lat": 32.6979, "lon": -16.7745},
    {"iata": "DEN", "icao": "KDEN", "name": "Denver Intl", "city": "Denver", "country": "United States", "region": "North America", "lat": 39.8561, "lon": -104.6737},
    {"iata": "ORD", "icao": "KORD", "name": "Chicago O'Hare Intl", "city": "Chicago", "country": "United States", "region": "North America", "lat": 41.9742, "lon": -87.9073},
    {"iata": "CDG", "icao": "LFPG", "name": "Paris Charles de Gaulle", "city": "Paris", "country": "France", "region": "Europe", "lat": 49.0097, "lon": 2.5479},
    {"iata": "HND", "icao": "RJTT", "name": "Tokyo Haneda", "city": "Tokyo", "country": "Japan", "region": "Asia", "lat": 35.5494, "lon": 139.7798},
    {"iata": "ICN", "icao": "RKSI", "name": "Incheon Intl", "city": "Seoul", "country": "South Korea", "region": "Asia", "lat": 37.4602, "lon": 126.4407},
    {"iata": "MLE", "icao": "VRMM", "name": "Velana Intl", "city": "Malé", "country": "Maldives", "region": "Asia", "lat": 4.1918, "lon": 73.5291},
    {"iata": "KEF", "icao": "BIKF", "name": "Keflavík Intl", "city": "Reykjavik", "country": "Iceland", "region": "Europe", "lat": 63.9850, "lon": -22.6056},
    {"iata": "CPT", "icao": "FACT", "name": "Cape Town Intl", "city": "Cape Town", "country": "South Africa", "region": "Africa", "lat": -33.9715, "lon": 18.6021},
    {"iata": "GRU", "icao": "SBGR", "name": "São Paulo Guarulhos", "city": "São Paulo", "country": "Brazil", "region": "South America", "lat": -23.4356, "lon": -46.4731},
    {"iata": "BOG", "icao": "SKBO", "name": "El Dorado Intl", "city": "Bogotá", "country": "Colombia", "region": "South America", "lat": 4.7016, "lon": -74.1469},
    {"iata": "IST", "icao": "LTFM", "name": "Istanbul Airport", "city": "Istanbul", "country": "Turkey", "region": "Europe", "lat": 41.2753, "lon": 28.7519},
    {"iata": "LAX", "icao": "KLAX", "name": "Los Angeles Intl", "city": "Los Angeles", "country": "United States", "region": "North America", "lat": 33.9416, "lon": -118.4085},
    {"iata": "VCE", "icao": "LIPZ", "name": "Venice Marco Polo", "city": "Venice", "country": "Italy", "region": "Europe", "lat": 45.5053, "lon": 12.3519},
    {"iata": "ZQN", "icao": "NZQN", "name": "Queenstown Airport", "city": "Queenstown", "country": "New Zealand", "region": "Oceania", "lat": -45.0211, "lon": 168.7392},
    {"iata": "CAI", "icao": "HECA", "name": "Cairo Intl", "city": "Cairo", "country": "Egypt", "region": "Africa", "lat": 30.1219, "lon": 31.4056},
    {"iata": "LUA", "icao": "VNLK", "name": "Tenzing-Hillary (Lukla)", "city": "Lukla", "country": "Nepal", "region": "Asia", "lat": 27.6878, "lon": 86.7314},
    {"iata": "DFW", "icao": "KDFW", "name": "Dallas/Fort Worth Intl", "city": "Dallas", "country": "United States", "region": "North America", "lat": 32.8998, "lon": -97.0403},
    {"iata": "ATL", "icao": "KATL", "name": "Hartsfield-Jackson Atlanta", "city": "Atlanta", "country": "United States", "region": "North America", "lat": 33.6407, "lon": -84.4277},
    {"iata": "BOS", "icao": "KBOS", "name": "Boston Logan Intl", "city": "Boston", "country": "United States", "region": "North America", "lat": 42.3656, "lon": -71.0096},
    {"iata": "SAN", "icao": "KSAN", "name": "San Diego Intl", "city": "San Diego", "country": "United States", "region": "North America", "lat": 32.7338, "lon": -117.1933},
    {"iata": "SEA", "icao": "KSEA", "name": "Seattle-Tacoma Intl", "city": "Seattle", "country": "United States", "region": "North America", "lat": 47.4502, "lon": -122.3088},
    {"iata": "HNL", "icao": "PHNL", "name": "Daniel K. Inouye Intl", "city": "Honolulu", "country": "United States", "region": "Oceania", "lat": 21.3187, "lon": -157.9225},
    {"iata": "YVR", "icao": "CYVR", "name": "Vancouver Intl", "city": "Vancouver", "country": "Canada", "region": "North America", "lat": 49.1967, "lon": -123.1815},
    {"iata": "SDU", "icao": "SBRJ", "name": "Santos Dumont", "city": "Rio de Janeiro", "country": "Brazil", "region": "South America", "lat": -22.9105, "lon": -43.1631},
    {"iata": "GIG", "icao": "SBGL", "name": "Rio Galeão Intl", "city": "Rio de Janeiro", "country": "Brazil", "region": "South America", "lat": -22.8099, "lon": -43.2506},
    {"iata": "SCL", "icao": "SCEL", "name": "Arturo Merino Benítez", "city": "Santiago", "country": "Chile", "region": "South America", "lat": -33.3930, "lon": -70.7858},
    {"iata": "FRA", "icao": "EDDF", "name": "Frankfurt Airport", "city": "Frankfurt", "country": "Germany", "region": "Europe", "lat": 50.0379, "lon": 8.5622},
    {"iata": "MAD", "icao": "LEMD", "name": "Adolfo Suárez Madrid-Barajas", "city": "Madrid", "country": "Spain", "region": "Europe", "lat": 40.4983, "lon": -3.5676},
    {"iata": "ZRH", "icao": "LSZH", "name": "Zurich Airport", "city": "Zurich", "country": "Switzerland", "region": "Europe", "lat": 47.4582, "lon": 8.5555},
    {"iata": "BCN", "icao": "LEBL", "name": "Barcelona-El Prat", "city": "Barcelona", "country": "Spain", "region": "Europe", "lat": 41.2974, "lon": 2.0833},
    {"iata": "NCE", "icao": "LFMN", "name": "Nice Côte d'Azur", "city": "Nice", "country": "France", "region": "Europe", "lat": 43.6584, "lon": 7.2159},
    {"iata": "DOH", "icao": "OTHH", "name": "Hamad Intl", "city": "Doha", "country": "Qatar", "region": "Asia", "lat": 25.2731, "lon": 51.6081},
    {"iata": "JNB", "icao": "FAOR", "name": "O.R. Tambo Intl", "city": "Johannesburg", "country": "South Africa", "region": "Africa", "lat": -26.1367, "lon": 28.2411},
    {"iata": "BKK", "icao": "VTBS", "name": "Suvarnabhumi Airport", "city": "Bangkok", "country": "Thailand", "region": "Asia", "lat": 13.6900, "lon": 100.7501},
    {"iata": "TPE", "icao": "RCTP", "name": "Taiwan Taoyuan Intl", "city": "Taipei", "country": "Taiwan", "region": "Asia", "lat": 25.0797, "lon": 121.2342},
    {"iata": "BOM", "icao": "VABB", "name": "Chhatrapati Shivaji Maharaj", "city": "Mumbai", "country": "India", "region": "Asia", "lat": 19.0896, "lon": 72.8656},
    {"iata": "AKL", "icao": "NZAA", "name": "Auckland Airport", "city": "Auckland", "country": "New Zealand", "region": "Oceania", "lat": -37.0082, "lon": 174.7850},
    {"iata": "MEL", "icao": "YMML", "name": "Melbourne Airport", "city": "Melbourne", "country": "Australia", "region": "Oceania", "lat": -37.6690, "lon": 144.8410},
    {"iata": "MIA", "icao": "KMIA", "name": "Miami Intl", "city": "Miami", "country": "United States", "region": "North America", "lat": 25.7959, "lon": -80.2870},
    {"iata": "YYZ", "icao": "CYYZ", "name": "Toronto Pearson Intl", "city": "Toronto", "country": "Canada", "region": "North America", "lat": 43.6777, "lon": -79.6248},
    {"iata": "MEX", "icao": "MMMX", "name": "Mexico City Intl", "city": "Mexico City", "country": "Mexico", "region": "North America", "lat": 19.4361, "lon": -99.0719},
    {"iata": "ANC", "icao": "PANC", "name": "Ted Stevens Anchorage", "city": "Anchorage", "country": "United States", "region": "North America", "lat": 61.1743, "lon": -149.9962},
    {"iata": "LAS", "icao": "KLAS", "name": "Harry Reid Intl", "city": "Las Vegas", "country": "United States", "region": "North America", "lat": 36.0840, "lon": -115.1537},
    {"iata": "PHX", "icao": "KPHX", "name": "Phoenix Sky Harbor", "city": "Phoenix", "country": "United States", "region": "North America", "lat": 33.4373, "lon": -112.0078},
    {"iata": "DCA", "icao": "KDCA", "name": "Reagan National", "city": "Washington, D.C.", "country": "United States", "region": "North America", "lat": 38.8512, "lon": -77.0402},
    {"iata": "CUN", "icao": "MMUN", "name": "Cancún Intl", "city": "Cancún", "country": "Mexico", "region": "North America", "lat": 21.0365, "lon": -86.8771},
    {"iata": "EZE", "icao": "SAEZ", "name": "Ministro Pistarini (Ezeiza)", "city": "Buenos Aires", "country": "Argentina", "region": "South America", "lat": -34.8222, "lon": -58.5358},
    {"iata": "LIM", "icao": "SPJC", "name": "Jorge Chávez Intl", "city": "Lima", "country": "Peru", "region": "South America", "lat": -12.0219, "lon": -77.1143},
    {"iata": "UIO", "icao": "SEQM", "name": "Mariscal Sucre Intl", "city": "Quito", "country": "Ecuador", "region": "South America", "lat": -0.1292, "lon": -78.3575},
    {"iata": "MUC", "icao": "EDDM", "name": "Munich Airport", "city": "Munich", "country": "Germany", "region": "Europe", "lat": 48.3538, "lon": 11.7861},
    {"iata": "ATH", "icao": "LGAV", "name": "Athens Intl", "city": "Athens", "country": "Greece", "region": "Europe", "lat": 37.9364, "lon": 23.9445},
    {"iata": "LIS", "icao": "LPPT", "name": "Humberto Delgado", "city": "Lisbon", "country": "Portugal", "region": "Europe", "lat": 38.7742, "lon": -9.1342},
    {"iata": "DUB", "icao": "EIDW", "name": "Dublin Airport", "city": "Dublin", "country": "Ireland", "region": "Europe", "lat": 53.4213, "lon": -6.2701},
    {"iata": "ARN", "icao": "ESSA", "name": "Stockholm Arlanda", "city": "Stockholm", "country": "Sweden", "region": "Europe", "lat": 59.6519, "lon": 17.9186},
    {"iata": "PRG", "icao": "LKPR", "name": "Václav Havel Prague", "city": "Prague", "country": "Czechia", "region": "Europe", "lat": 50.1008, "lon": 14.2600},
    {"iata": "OSL", "icao": "ENGM", "name": "Oslo Gardermoen", "city": "Oslo", "country": "Norway", "region": "Europe", "lat": 60.1939, "lon": 11.1004},
    {"iata": "CMN", "icao": "GMMN", "name": "Mohammed V Intl", "city": "Casablanca", "country": "Morocco", "region": "Africa", "lat": 33.3675, "lon": -7.5899},
    {"iata": "ADD", "icao": "HAAB", "name": "Bole Intl", "city": "Addis Ababa", "country": "Ethiopia", "region": "Africa", "lat": 8.9779, "lon": 38.7993},
    {"iata": "NBO", "icao": "HKJK", "name": "Jomo Kenyatta Intl", "city": "Nairobi", "country": "Kenya", "region": "Africa", "lat": -1.3192, "lon": 36.9278},
    {"iata": "RUH", "icao": "OERK", "name": "King Khalid Intl", "city": "Riyadh", "country": "Saudi Arabia", "region": "Asia", "lat": 24.9576, "lon": 46.6988},
    {"iata": "KUL", "icao": "WMKK", "name": "Kuala Lumpur Intl", "city": "Kuala Lumpur", "country": "Malaysia", "region": "Asia", "lat": 2.7456, "lon": 101.7099},
    {"iata": "CGK", "icao": "WIII", "name": "Soekarno-Hatta Intl", "city": "Jakarta", "country": "Indonesia", "region": "Asia", "lat": -6.1256, "lon": 106.6559},
    {"iata": "DEL", "icao": "VIDP", "name": "Indira Gandhi Intl", "city": "New Delhi", "country": "India", "region": "Asia", "lat": 28.5562, "lon": 77.1000},
]

TAGLINES = {
    "SFO": "San Francisco Bay Parallel Runways",
    "KIX": "Man-Made Island in Osaka Bay",
    "SXM": "Maho Beach Low Approach",
    "GIB": "Public Road Crosses Runway",
    "HKG": "Reclaimed Chek Lap Kok Island",
    "LHR": "Dual Parallel Mega-Hub",
    "JFK": "Jamaica Bay Crossing Runways",
    "AMS": "Below Sea Level · 6 Runways",
    "DXB": "Desert Crossroads Mega-Hub",
    "SIN": "Coastal Changi Peninsula",
    "SYD": "Botany Bay Shoreline Runways",
    "FNC": "Cliffside Ocean Viaduct Runway",
    "DEN": "High Plains · 6 Runways",
    "ORD": "Intersecting Great Lakes Hub",
    "CDG": "Twin-Complex European Hub",
    "HND": "Tokyo Bay Reclaimed Runways",
    "ICN": "Yeongjong Island Tidal Flats",
    "MLE": "Coral Atoll Island Strip",
    "KEF": "North Atlantic Lava Fields",
    "CPT": "Table Mountain Foothills",
    "GRU": "São Paulo Basin Hub",
    "BOG": "High-Altitude Andean Plateau",
    "IST": "Black Sea Coast Mega-Hub",
    "LAX": "Pacific Coast Parallel Quad",
    "VCE": "Venetian Lagoon Shoreline",
    "ZQN": "Southern Alps Glacial Valley",
    "CAI": "Nile Delta Desert Edge",
    "LUA": "Himalayan Cliffside STOL Strip",
    "HNL": "Offshore Coral Reef Runway",
    "BOS": "Boston Harbor Peninsula",
    "SAN": "Downtown Harbor Single Strip",
    "SDU": "Guanabara Bay Waterside Strip",
    "NCE": "Mediterranean Seafront Runways",
    "DOH": "Reclaimed Persian Gulf Peninsula",
    "BOM": "Intersecting Urban Runways",
    "ANC": "Cook Inlet Subarctic Hub",
    "DCA": "Potomac River Approach",
}
WEATHER_CODES = {
    0: "Clear",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    80: "Showers",
    81: "Showers",
    82: "Heavy Showers",
    95: "Thunderstorm",
}


def degrees_to_compass(degrees):
    """Converts wind direction in degrees to an 8-point compass string."""
    if degrees is None:
        return ""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round((float(degrees) % 360) / 45) % 8]


def format_coords(lat, lon):
    """Formats coordinates as human-readable N/S, E/W strings."""
    lat_hem = "N" if lat >= 0 else "S"
    lon_hem = "E" if lon >= 0 else "W"
    return f"{abs(lat):.3f}° {lat_hem}, {abs(lon):.3f}° {lon_hem}"


def fetch_weather_and_elevation(lat, lon):
    """Fetches current weather, wind, local time, and elevation from Open-Meteo."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        "&current=temperature_2m,weather_code,wind_speed_10m,wind_direction_10m"
        "&wind_speed_unit=kn&timezone=auto"
    )
    try:
        resp = _SESSION.get(url, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            current = data.get("current", {})
            temp_c = current.get("temperature_2m")
            wind_kt = current.get("wind_speed_10m")
            wind_dir = current.get("wind_direction_10m")
            elev = data.get("elevation")
            local_iso = current.get("time", "")
            return {
                "elevation_m": int(round(elev)) if elev is not None else None,
                "temp_c": round(temp_c, 1) if temp_c is not None else None,
                "weather": WEATHER_CODES.get(current.get("weather_code"), "Clear"),
                "wind": (
                    f"{int(round(wind_kt))} kt {degrees_to_compass(wind_dir)}"
                    if wind_kt is not None
                    else "--"
                ),
                "wind_dir_deg": wind_dir,
                "wind_speed_kt": wind_kt,
                "local_time": local_iso.split("T")[1] if "T" in local_iso else "--:--",
            }
    except (requests.RequestException, ValueError):
        pass
    return {
        "elevation_m": None,
        "temp_c": None,
        "weather": "Unknown",
        "wind": "--",
        "wind_dir_deg": None,
        "wind_speed_kt": None,
        "local_time": "--:--",
    }


def fetch_metar(icao):
    """Fetches official aviation METAR from AviationWeather.gov."""
    url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json"
    try:
        resp = _SESSION.get(url, timeout=5)
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, list) and items:
                m = items[0]
                wspd = m.get("wspd")
                wgst = m.get("wgst")
                wdir = m.get("wdir")
                wind_str = None
                if wspd is not None and wdir is not None:
                    gust = f"G{int(round(wgst))}" if wgst else ""
                    wind_str = f"{int(round(wspd))}{gust} kt {degrees_to_compass(wdir)}"
                vis = m.get("visib")
                altim = m.get("altim")
                clouds = m.get("clouds") or []
                ceiling = next(
                    (f"{c.get('cover')} {c.get('base'):,} ft" for c in clouds if c.get("cover") in ("BKN", "OVC", "VV") and c.get("base")),
                    m.get("cover") or "CLR",
                )
                return {
                    "flt_cat": m.get("fltCat") or "",
                    "visibility": f"{vis} SM" if vis is not None else "--",
                    "altim": f"{int(round(altim))} hPa" if altim is not None else "--",
                    "ceiling": ceiling,
                    "wind": wind_str,
                    "wind_dir_deg": wdir if isinstance(wdir, (int, float)) else None,
                    "wind_speed_kt": wspd if isinstance(wspd, (int, float)) else None,
                    "raw_metar": m.get("rawOb") or "",
                }
    except (requests.RequestException, ValueError, TypeError):
        pass
    return {
        "flt_cat": "",
        "visibility": "--",
        "altim": "--",
        "ceiling": "--",
        "wind": None,
        "wind_dir_deg": None,
        "wind_speed_kt": None,
        "raw_metar": "",
    }


_TRAFFIC_CACHE = {}
_TRAFFIC_CACHE_TTL = 30
ADSB_PROVIDERS = [
    ("adsb.fi", "https://opendata.adsb.fi/api/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{radius}", "aircraft"),
    ("adsb.lol", "https://api.adsb.lol/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{radius}", "ac"),
]


def _format_ac_entry(ac):
    callsign = (ac.get("flight") or ac.get("r") or ac.get("hex") or "").strip().upper()
    ac_type = (ac.get("t") or "").strip().upper()
    alt_raw = ac.get("alt_baro")
    is_ground = alt_raw == "ground"
    if is_ground:
        alt_str = "GND"
    elif isinstance(alt_raw, (int, float)):
        alt_i = int(round(alt_raw))
        alt_str = f"FL{alt_i // 100:03d}" if alt_i >= 18000 else f"{alt_i:,} ft"
    else:
        alt_str = "--"

    rate = ac.get("baro_rate")
    arrow = ""
    if not is_ground and isinstance(rate, (int, float)):
        if rate > 250:
            arrow = "↑"
        elif rate < -250:
            arrow = "↓"

    gs = ac.get("gs")
    spd_str = f"{int(round(float(gs)))} kt" if isinstance(gs, (int, float)) else "--"
    dst = float(ac.get("dst", 99.0))
    return {
        "callsign": callsign[:8] or "UNKN",
        "type": ac_type[:4] or "ACFT",
        "alt": f"{alt_str}{arrow}",
        "speed": spd_str,
        "dist": f"{dst:.1f} nm",
        "is_ground": is_ground,
        "dst_num": dst,
        "has_flight": bool((ac.get("flight") or "").strip()),
    }


def fetch_nearby_traffic(lat, lon, radius_nm=10):
    """
    Fetches live aircraft count, airborne/ground breakdown, top nearby aircraft,
    and raw coordinates within radius_nm.
    Caches for 30s, retries once on 429, and falls back from adsb.fi to adsb.lol.
    """
    cache_key = (round(lat, 3), round(lon, 3), radius_nm)
    now = time.monotonic()
    cached = _TRAFFIC_CACHE.get(cache_key)
    if cached and (now - cached["ts"]) < _TRAFFIC_CACHE_TTL:
        return cached["data"]

    for _, url_tpl, ac_key in ADSB_PROVIDERS:
        url = url_tpl.format(lat=lat, lon=lon, radius=radius_nm)
        for attempt in range(2):
            try:
                resp = _SESSION.get(url, timeout=6)
                if resp.status_code == 200:
                    aircraft = resp.json().get(ac_key, [])
                    count = len(aircraft)
                    airborne_c = sum(1 for a in aircraft if a.get("alt_baro") != "ground")
                    ground_c = count - airborne_c

                    formatted = [
                        _format_ac_entry(a)
                        for a in aircraft
                        if (a.get("flight") or a.get("r") or "").strip()
                    ]
                    # Prioritize airborne + moving ground aircraft over stationary 0 kt gate traffic
                    formatted.sort(
                        key=lambda x: (
                            not x["has_flight"],
                            x["is_ground"] and x["speed"] == "0 kt",
                            x["dst_num"],
                        )
                    )

                    closest_str = "None"
                    if formatted:
                        c0 = formatted[0]
                        closest_str = f"{c0['callsign']} · {c0['type']}"

                    result = {
                        "traffic_count": count,
                        "airborne_count": airborne_c,
                        "ground_count": ground_c,
                        "closest_flight": closest_str,
                        "nearby_aircraft": formatted[:4],
                        "raw_aircraft": aircraft,
                    }
                    _TRAFFIC_CACHE[cache_key] = {"ts": now, "data": result}
                    return result
                if resp.status_code == 429 and attempt == 0:
                    time.sleep(1.1)
                    continue
                break
            except (requests.RequestException, ValueError, TypeError):
                break

    return {
        "traffic_count": None,
        "airborne_count": 0,
        "ground_count": 0,
        "closest_flight": "--",
        "nearby_aircraft": [],
        "raw_aircraft": [],
    }


def compute_wind_components(active_runway, wind_speed_kt, wind_dir_deg):
    """Computes headwind and crosswind components in knots for the active runway."""
    if not active_runway or wind_speed_kt is None or wind_dir_deg is None:
        return "--"
    match = re.match(r"(\d{1,2})", str(active_runway))
    if not match:
        return "--"
    rwy_deg = int(match.group(1)) * 10
    diff_rad = math.radians(float(wind_dir_deg) - rwy_deg)
    hw = int(round(float(wind_speed_kt) * math.cos(diff_rad)))
    xw = int(round(abs(float(wind_speed_kt) * math.sin(diff_rad))))
    hw_label = "HW" if hw >= 0 else "TW"
    return f"{abs(hw)} kt {hw_label} · {xw} kt XW"


def pick_airport():
    """Picks the requested airport (?iata= or ?index=) or a random cached one."""
    iata = (request.args.get("iata") or "").upper()
    if iata:
        for loc in LOCATIONS:
            if loc["iata"] == iata:
                return loc
    idx = request.args.get("index")
    if idx is not None and idx.isdigit():
        return LOCATIONS[int(idx) % len(LOCATIONS)]

    # Prefer airports whose OSM data is already cached so polls respond instantly
    cached = [loc for loc in LOCATIONS if is_cached(loc["iata"])]
    return random.choice(cached or LOCATIONS)


@pixel_airports_bp.route("/pixel_earth", methods=["GET"])
@pixel_airports_bp.route("/airport", methods=["GET"])
def airport():
    """Returns an airport diagram and metadata for a random world airport."""
    loc = pick_airport()
    meta = fetch_weather_and_elevation(loc["lat"], loc["lon"])
    metar = fetch_metar(loc["icao"])
    traffic = fetch_nearby_traffic(loc["lat"], loc["lon"])

    wind_dir_deg = metar["wind_dir_deg"] if metar["wind_dir_deg"] is not None else meta["wind_dir_deg"]
    wind_speed_kt = metar["wind_speed_kt"] if metar["wind_speed_kt"] is not None else meta["wind_speed_kt"]
    wind_display = metar["wind"] or meta["wind"]

    try:
        diagram_uri, info = render_airport_diagram(
            loc["iata"],
            loc["lat"],
            loc["lon"],
            wind_from_deg=wind_dir_deg,
            aircraft=traffic["raw_aircraft"],
        )
    except (requests.RequestException, RuntimeError, OSError) as exc:
        return jsonify({"error": f"Failed to build airport diagram: {exc}"}), 502

    longest = info["longest_runway_m"]
    longest_ft = int(round(longest * 3.28084, -1)) if longest else 0
    elev_m = meta["elevation_m"]
    elev_display = f"{elev_m:,} m / {int(round(elev_m * 3.28084)):,} ft" if elev_m is not None else "--"
    wind_components = compute_wind_components(info["active_runway"], wind_speed_kt, wind_dir_deg)
    tagline = TAGLINES.get(loc["iata"], f"{loc['region']} International Airport")
    traffic_count = traffic["traffic_count"]
    return jsonify(
        {
            "title": "Pixel Airports",
            "iata": loc["iata"],
            "icao": loc["icao"],
            "name": loc["name"],
            "city": loc["city"],
            "country": loc["country"],
            "region": loc["region"],
            "tagline": tagline,
            "coords": format_coords(loc["lat"], loc["lon"]),
            "elevation_m": elev_m,
            "elevation": elev_display,
            "temp_c": meta["temp_c"],
            "weather": meta["weather"],
            "wind": wind_display,
            "wind_components": wind_components,
            "local_time": meta["local_time"],
            "flt_cat": metar["flt_cat"],
            "visibility": metar["visibility"],
            "altim": metar["altim"],
            "ceiling": metar["ceiling"],
            "raw_metar": metar["raw_metar"],
            "traffic_count": f"{traffic_count} nearby" if traffic_count is not None else "--",
            "airborne_count": traffic["airborne_count"],
            "ground_count": traffic["ground_count"],
            "closest_flight": traffic["closest_flight"],
            "nearby_aircraft": traffic["nearby_aircraft"],
            "runways": " · ".join(info["runways"]) or "--",
            "runway_count": info["runway_count"],
            "longest_runway": f"{longest:,} m / {longest_ft:,} ft" if longest else "--",
            "active_runway": info["active_runway"] or "--",
            "date": datetime.now(timezone.utc).strftime("%b %d, %Y"),
            "diagram_data_uri": diagram_uri,
            # Backwards-compatible key for older templates
            "pixel_art_data_uri": diagram_uri,
        }
    )


def warm_cache(workers=2):
    """Pre-fetches OSM features and water masks for every airport (run once, cached on disk)."""

    def warm(loc):
        if is_cached(loc["iata"]):
            return f"{loc['iata']}: cached"
        start = time.time()
        try:
            render_airport_diagram(loc["iata"], loc["lat"], loc["lon"])
            return f"{loc['iata']}: ok ({time.time() - start:.0f}s)"
        except (requests.RequestException, RuntimeError, OSError) as exc:
            return f"{loc['iata']}: FAILED {exc}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for line in pool.map(warm, LOCATIONS):
            print(line, flush=True)


if __name__ == "__main__":
    if "--warm" in sys.argv:
        warm_cache()
