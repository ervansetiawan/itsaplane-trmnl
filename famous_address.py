"""Daily Famous Address - TRMNL plugin Blueprint."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import re
import sys
import time

import requests
from flask import Blueprint, jsonify, request

from address_map import is_cached, render_address_map

famous_address_bp = Blueprint("famous_address", __name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "daily-famous-address-trmnl/1.0"})

_WIKI_CACHE = {}
_WIKI_TTL_SECONDS = 86400

# pylint: disable=line-too-long
ADDRESSES = [
    {"slug": "abbey-road", "address": "3 Abbey Road", "name": "Abbey Road Studios", "city": "London", "country": "United Kingdom", "year": "1969", "category": "Music", "lat": 51.5319, "lon": -0.1783, "wiki": "Abbey_Road_Studios", "fallback": "EMI recording studio where The Beatles recorded almost all of their albums and photographed the iconic 1969 Abbey Road crosswalk cover."},
    {"slug": "baker-street", "address": "221B Baker Street", "name": "Sherlock Holmes Museum", "city": "London", "country": "United Kingdom", "year": "1887", "category": "Literature", "lat": 51.5238, "lon": -0.1586, "wiki": "221B_Baker_Street", "fallback": "The famous London residence of Arthur Conan Doyle's fictional detective Sherlock Holmes, first introduced in A Study in Scarlet in 1887."},
    {"slug": "downing-street", "address": "10 Downing Street", "name": "Number 10", "city": "London", "country": "United Kingdom", "year": "1735", "category": "Politics", "lat": 51.5034, "lon": -0.1276, "wiki": "10_Downing_Street", "fallback": "Official residence and office of the Prime Minister of the United Kingdom since Sir Robert Walpole moved in during 1735."},
    {"slug": "stonewall-inn", "address": "53 Christopher Street", "name": "The Stonewall Inn", "city": "New York", "country": "United States", "year": "1969", "category": "History", "lat": 40.7338, "lon": -74.0021, "wiki": "Stonewall_Inn", "fallback": "Site of the June 1969 Stonewall riots in Greenwich Village, widely considered the catalyst for the modern LGBTQ+ rights movement."},
    {"slug": "wall-street", "address": "11 Wall Street", "name": "New York Stock Exchange", "city": "New York", "country": "United States", "year": "1792", "category": "Finance", "lat": 40.7069, "lon": -74.0113, "wiki": "New_York_Stock_Exchange", "fallback": "The world's largest stock exchange, founded under the Buttonwood Agreement in 1792 and site of the 1929 Wall Street Crash."},
    {"slug": "independence-hall", "address": "520 Chestnut Street", "name": "Independence Hall", "city": "Philadelphia", "country": "United States", "year": "1776", "category": "History", "lat": 39.9489, "lon": -75.1500, "wiki": "Independence_Hall", "fallback": "Where both the United States Declaration of Independence (1776) and the U.S. Constitution (1787) were debated and adopted."},
    {"slug": "white-house", "address": "1600 Pennsylvania Ave NW", "name": "The White House", "city": "Washington, D.C.", "country": "United States", "year": "1800", "category": "Politics", "lat": 38.8977, "lon": -77.0365, "wiki": "White_House", "fallback": "Official residence and workplace of every U.S. president since John Adams in 1800; burned by British troops in 1814 and rebuilt."},
    {"slug": "dealey-plaza", "address": "411 Elm Street", "name": "Texas School Book Depository", "city": "Dallas", "country": "United States", "year": "1963", "category": "History", "lat": 32.7798, "lon": -96.8085, "wiki": "Texas_School_Book_Depository", "fallback": "Sixth-floor window overlooking Dealey Plaza from which President John F. Kennedy was assassinated on November 22, 1963."},
    {"slug": "lorraine-motel", "address": "450 Mulberry Street", "name": "Lorraine Motel", "city": "Memphis", "country": "United States", "year": "1968", "category": "History", "lat": 35.1345, "lon": -90.0576, "wiki": "Lorraine_Motel", "fallback": "Site of the assassination of civil rights leader Martin Luther King Jr. on April 4, 1968; now home to the National Civil Rights Museum."},
    {"slug": "watergate", "address": "2600 Virginia Ave NW", "name": "Watergate Complex", "city": "Washington, D.C.", "country": "United States", "year": "1972", "category": "Politics", "lat": 38.8989, "lon": -77.0548, "wiki": "Watergate_complex", "fallback": "Site of the 1972 Democratic National Committee headquarters break-in that sparked the Watergate scandal and President Nixon's resignation."},
    {"slug": "bletchley-park", "address": "Sherwood Drive", "name": "Bletchley Park", "city": "Milton Keynes", "country": "United Kingdom", "year": "1941", "category": "Science", "lat": 51.9977, "lon": -0.7407, "wiki": "Bletchley_Park", "fallback": "World War II British codebreaking headquarters where Alan Turing and colleagues cracked the German Enigma cipher."},
    {"slug": "hp-garage", "address": "367 Addison Avenue", "name": "HP Garage", "city": "Palo Alto", "country": "United States", "year": "1939", "category": "Tech", "lat": 37.4430, "lon": -122.1547, "wiki": "HP_Garage", "fallback": "Birthplace of Silicon Valley, where Bill Hewlett and David Packard built their first audio oscillator in 1939."},
    {"slug": "wright-brothers", "address": "1000 N Croatan Hwy", "name": "Kill Devil Hills", "city": "Kitty Hawk", "country": "United States", "year": "1903", "category": "Aviation", "lat": 36.0178, "lon": -75.6699, "wiki": "Wright_Brothers_National_Memorial", "fallback": "Where Orville and Wilbur Wright achieved the first powered, controlled, sustained airplane flight on December 17, 1903."},
    {"slug": "empire-state", "address": "350 Fifth Avenue", "name": "Empire State Building", "city": "New York", "country": "United States", "year": "1931", "category": "Architecture", "lat": 40.7484, "lon": -73.9857, "wiki": "Empire_State_Building", "fallback": "102-story Art Deco skyscraper completed in just 410 days in 1931, holding the world's tallest building title for nearly 40 years."},
    {"slug": "wrigley-field", "address": "1060 W Addison Street", "name": "Wrigley Field", "city": "Chicago", "country": "United States", "year": "1914", "category": "Sports", "lat": 41.9484, "lon": -87.6553, "wiki": "Wrigley_Field", "fallback": "Opened in 1914, famous for its ivy-covered brick outfield walls, hand-turned scoreboard, and Babe Ruth's 1932 'Called Shot'."},
    {"slug": "checkpoint-charlie", "address": "Friedrichstraße 43", "name": "Checkpoint Charlie", "city": "Berlin", "country": "Germany", "year": "1961", "category": "History", "lat": 52.5074, "lon": 13.3904, "wiki": "Checkpoint_Charlie", "fallback": "Best-known Berlin Wall crossing point between the American and Soviet sectors, site of a 1961 tank standoff during the Cold War."},
    {"slug": "anne-frank-house", "address": "Prinsengracht 263", "name": "Anne Frank House", "city": "Amsterdam", "country": "Netherlands", "year": "1942", "category": "History", "lat": 52.3752, "lon": 4.8840, "wiki": "Anne_Frank_House", "fallback": "Canal-side building where Anne Frank and her family hid in a secret annex for two years during WWII while she wrote her diary."},
    {"slug": "eiffel-tower", "address": "5 Av. Anatole France", "name": "Eiffel Tower", "city": "Paris", "country": "France", "year": "1889", "category": "Architecture", "lat": 48.8584, "lon": 2.2945, "wiki": "Eiffel_Tower", "fallback": "Built by Gustave Eiffel as the entrance arch for the 1889 World's Fair, initially meant to stand for 20 years before radio saved it."},
    {"slug": "colosseum", "address": "Piazza del Colosseo 1", "name": "The Colosseum", "city": "Rome", "country": "Italy", "year": "80 AD", "category": "History", "lat": 41.8902, "lon": 12.4922, "wiki": "Colosseum", "fallback": "Largest ancient amphitheatre ever built, completed in 80 AD under Emperor Titus for gladiatorial contests and public spectacles."},
    {"slug": "cern", "address": "Espl. des Particules 1", "name": "CERN", "city": "Meyrin", "country": "Switzerland", "year": "1989", "category": "Science", "lat": 46.2330, "lon": 6.0557, "wiki": "CERN", "fallback": "European particle physics lab where Tim Berners-Lee invented the World Wide Web in 1989 and the Higgs boson was discovered in 2012."},
    {"slug": "sydney-opera", "address": "Bennelong Point", "name": "Sydney Opera House", "city": "Sydney", "country": "Australia", "year": "1973", "category": "Architecture", "lat": -33.8568, "lon": 151.2153, "wiki": "Sydney_Opera_House", "fallback": "Jørn Utzon's expressionist harbor landmark with interlocking concrete shells, opened in 1973 after 14 years of construction."},
    {"slug": "apple-park", "address": "One Apple Park Way", "name": "Apple Park", "city": "Cupertino", "country": "United States", "year": "2017", "category": "Tech", "lat": 37.3346, "lon": -122.0090, "wiki": "Apple_Park", "fallback": "Ring-shaped corporate headquarters designed by Norman Foster and envisioned by Steve Jobs, opened in 2017."},
    {"slug": "fenway-park", "address": "4 Jersey Street", "name": "Fenway Park", "city": "Boston", "country": "United States", "year": "1912", "category": "Sports", "lat": 42.3467, "lon": -71.0972, "wiki": "Fenway_Park", "fallback": "Major League Baseball's oldest active ballpark (opened 1912), home to the iconic 37-foot Green Monster left-field wall."},
    {"slug": "sun-studio", "address": "706 Union Avenue", "name": "Sun Studio", "city": "Memphis", "country": "United States", "year": "1954", "category": "Music", "lat": 35.1392, "lon": -90.0376, "wiki": "Sun_Studio", "fallback": "Sam Phillips' recording studio where Elvis Presley, Johnny Cash, Jerry Lee Lewis, and Carl Perkins launched rock and roll."},
    {"slug": "rosa-parks", "address": "251 Montgomery Street", "name": "Rosa Parks Arrest Site", "city": "Montgomery", "country": "United States", "year": "1955", "category": "History", "lat": 32.3752, "lon": -86.3069, "wiki": "Montgomery_bus_boycott", "fallback": "Corner outside the Empire Theater where Rosa Parks refused to give up her bus seat on December 1, 1955, sparking the Montgomery bus boycott."},
]


def format_coords(lat, lon):
    """Formats coordinates as human-readable N/S, E/W strings."""
    lat_hem = "N" if lat >= 0 else "S"
    lon_hem = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}° {lat_hem}, {abs(lon):.4f}° {lon_hem}"


def _trim_story(text, max_chars=280):
    """Trims text cleanly at a sentence boundary within max_chars."""
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= max_chars:
        return clean
    cut = clean[:max_chars]
    last_dot = cut.rfind(". ")
    if last_dot > 80:
        return cut[: last_dot + 1]
    return cut.rsplit(" ", 1)[0] + "..."


def fetch_wiki_story(wiki_slug, fallback):
    """Fetches a concise summary from Wikipedia REST API with 24h caching."""
    now = time.monotonic()
    cached = _WIKI_CACHE.get(wiki_slug)
    if cached and (now - cached["ts"]) < _WIKI_TTL_SECONDS:
        return cached["story"]

    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{wiki_slug}"
    try:
        resp = _SESSION.get(url, timeout=5)
        if resp.status_code == 200:
            extract = resp.json().get("extract") or ""
            if extract:
                story = _trim_story(extract)
                _WIKI_CACHE[wiki_slug] = {"ts": now, "story": story}
                return story
    except (requests.RequestException, ValueError):
        pass
    return fallback


def pick_address():
    """Picks the requested address (?slug= or ?index=) or today's daily address."""
    slug = (request.args.get("slug") or "").strip().lower()
    if slug:
        for item in ADDRESSES:
            if item["slug"] == slug:
                return item
    idx = request.args.get("index")
    if idx is not None and idx.isdigit():
        return ADDRESSES[int(idx) % len(ADDRESSES)]

    cached = [a for a in ADDRESSES if is_cached(a["slug"])]
    pool = cached or ADDRESSES
    return pool[date.today().toordinal() % len(pool)]


@famous_address_bp.route("/famous_address", methods=["GET"])
def famous_address():
    """Returns a street-level map and historical story for the daily famous address."""
    item = pick_address()
    try:
        map_uri = render_address_map(item["slug"], item["lat"], item["lon"])
    except (requests.RequestException, RuntimeError, OSError) as exc:
        return jsonify({"error": f"Failed to build address map: {exc}"}), 502

    story = fetch_wiki_story(item["wiki"], item["fallback"])
    return jsonify(
        {
            "title": "Famous Address",
            "slug": item["slug"],
            "address": item["address"],
            "name": item["name"],
            "city": item["city"],
            "country": item["country"],
            "year": item["year"],
            "category": item["category"],
            "coords": format_coords(item["lat"], item["lon"]),
            "story": story,
            "date": datetime.now(timezone.utc).strftime("%b %d, %Y"),
            "map_data_uri": map_uri,
        }
    )


def warm_cache(workers=2):
    """Pre-fetches OSM features and water masks for all addresses."""

    def warm(item):
        if is_cached(item["slug"]):
            return f"{item['slug']}: cached"
        start = time.time()
        try:
            render_address_map(item["slug"], item["lat"], item["lon"])
            return f"{item['slug']}: ok ({time.time() - start:.0f}s)"
        except (requests.RequestException, RuntimeError, OSError) as exc:
            return f"{item['slug']}: FAILED {exc}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for line in pool.map(warm, ADDRESSES):
            print(line, flush=True)


if __name__ == "__main__":
    if "--warm" in sys.argv:
        warm_cache()
