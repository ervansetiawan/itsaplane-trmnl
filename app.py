""" pytmrnl - A terminal for tracking aircraft """

import os
import time
from math import radians, sin, cos, sqrt, atan2

import requests
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "itsaplane-trmnl/1.0"})

_CACHE_TTL_SECONDS = 30
_FLIGHT_CACHE = {}

ADSB_PROVIDERS = [
    {
        "name": "adsb.fi",
        "url": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{radius}",
        "aircraft_key": "aircraft",
    },
    {
        "name": "adsb.lol",
        "url": "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius}",
        "aircraft_key": "ac",
    },
]

def get_aircraft_logo(aircraft_code):
    """
    Returns the logo filename for the given aircraft code.
    If no logo is found, returns a default logo filename.
    """
    if not aircraft_code:
        return None
        
    logos_dir = os.path.join(os.path.dirname(__file__), 'logos')
    if not os.path.exists(logos_dir):
        return None
        
    logo_filenames = [f for f in os.listdir(logos_dir)
                      if os.path.isfile(os.path.join(logos_dir, f))]

    # Check if the aircraft type has a corresponding logo
    for logo in logo_filenames:
        if aircraft_code.lower() in logo.lower():
            return logo

    return None

def get_aircraft_model(aircraft_type):
    """Reads aircrafts.csv and returns the model for the given aircraft type."""
    if not aircraft_type:
        return None
    
    if not os.path.exists('aircrafts.csv'):
        return None

    aircrafts = []
    with open('aircrafts.csv', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines[1:]:  # Skip the header
            parts = line.strip().split(',')
            if len(parts) == 2:
                aircrafts.append({"icao": parts[0].strip(), "model": parts[1].strip()})

    print(f"Searching for aircraft type: {aircraft_type} in {len(aircrafts)} entries")
    
    # Clean Pythonic lookup
    for aircraft in aircrafts:
        if aircraft['icao'] == aircraft_type:
            return aircraft['model']
            
    return None

def degrees_to_compass_direction(degrees):
    """
    Converts a heading in degrees (0-360) to a cardinal/intercardinal compass direction.
    """
    try:
        degrees = float(degrees) % 360
    except (ValueError, TypeError):
        return "\u2191"

    directions = ["\u2191", "\u2197", "\u2192", "\u2198", "\u2193", "\u2199", "\u2190", "\u2196"]
    index = int((degrees + 22.5) // 45) % 8
    return directions[index]


def degrees_to_cardinal(degrees):
    """Converts a bearing in degrees (0-360) to a 16-point cardinal direction."""
    try:
        degrees = float(degrees) % 360
    except (ValueError, TypeError):
        return ""

    cardinals = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    index = int((degrees + 11.25) // 22.5) % 16
    return cardinals[index]


CATEGORY_LABELS = {
    "A1": "Light",
    "A2": "Small",
    "A3": "Large",
    "A4": "High Vortex",
    "A5": "Heavy",
    "A6": "High Perf",
    "A7": "Rotorcraft",
    "B1": "Glider",
    "B2": "Lighter-than-air",
    "B4": "Ultralight",
    "B6": "UAV",
}

AIRLINE_NAMES = {
    "AAL": "American Airlines",
    "AAY": "Allegiant Air",
    "ACA": "Air Canada",
    "AFR": "Air France",
    "AMX": "Aeromexico",
    "ANA": "All Nippon Airways",
    "ASA": "Alaska Airlines",
    "ASH": "Mesa Airlines",
    "BAW": "British Airways",
    "CPA": "Cathay Pacific",
    "DAL": "Delta Air Lines",
    "DLH": "Lufthansa",
    "EDV": "Endeavor Air",
    "ENY": "Envoy Air",
    "FDX": "FedEx Express",
    "FFT": "Frontier Airlines",
    "GJS": "GoJet Airlines",
    "HAL": "Hawaiian Airlines",
    "JAL": "Japan Airlines",
    "JBU": "JetBlue",
    "JIA": "PSA Airlines",
    "KLM": "KLM",
    "MXY": "Breeze Airways",
    "NKS": "Spirit Airlines",
    "PDT": "Piedmont Airlines",
    "QFA": "Qantas",
    "QTR": "Qatar Airways",
    "QXE": "Horizon Air",
    "RPA": "Republic Airways",
    "SCX": "Sun Country Airlines",
    "SIA": "Singapore Airlines",
    "SKW": "SkyWest Airlines",
    "SWA": "Southwest Airlines",
    "UAE": "Emirates",
    "UAL": "United Airlines",
    "UPS": "UPS Airlines",
    "VOI": "Volaris",
}

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates the distance between two geographical coordinates using the Haversine formula."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    r = 3958.8  # Radius of Earth in miles
    return r * c

def rate_to_arrow(rate):
    """Converts a rate value to an arrow symbol."""
    try:
        val = int(rate)
        if val < 0:
            return '&#9660;'
        if val > 0:
            return '&#9650;'
    except (ValueError, TypeError):
        pass
    return ''

def fetch_flight_data_with_status(lat, lon, radius):
    """
    Fetches flight data from ADS-B APIs with short-lived caching and fallback.
    Returns (data_dict, None, 200) on success, or (None, error_msg, http_status) on failure.
    """
    cache_key = (str(lat), str(lon), str(radius))
    now = time.monotonic()
    cached = _FLIGHT_CACHE.get(cache_key)
    if cached and (now - cached["ts"]) < _CACHE_TTL_SECONDS:
        return cached["data"], None, 200

    last_error = "Upstream ADS-B request failed"
    last_status = 502

    for provider in ADSB_PROVIDERS:
        url = provider["url"].format(lat=lat, lon=lon, radius=radius)
        for attempt in range(2):
            try:
                resp = _SESSION.get(url, timeout=15)
                if resp.status_code == 200:
                    payload = resp.json()
                    aircraft = payload.get(provider["aircraft_key"], [])
                    normalized = {"ac": aircraft}
                    _FLIGHT_CACHE[cache_key] = {"ts": now, "data": normalized}
                    return normalized, None, 200

                print(
                    f"Error fetching flight data from {provider['name']}: "
                    f"{resp.status_code}. Response: {resp.text[:200]}"
                )
                last_error = f"{provider['name']} returned HTTP {resp.status_code}"
                last_status = 429 if resp.status_code == 429 else 502

                if resp.status_code == 429 and attempt == 0:
                    time.sleep(1.1)
                    continue
                break
            except (requests.RequestException, ValueError) as exc:
                print(f"Request to {provider['name']} failed: {exc}")
                last_error = f"{provider['name']} request failed: {exc}"
                last_status = 504 if isinstance(exc, requests.Timeout) else 502
                break

    return None, last_error, last_status


def fecth_flight_data_json(lat, lon, radius):
    """Fetches flight data from the ADS-B API."""
    data, _, _ = fetch_flight_data_with_status(lat, lon, radius)
    return data


def get_closest_flight(flight_data_json, prefer_airliners):
    """Finds the closest flight from the flight data JSON, preferring airborne aircraft."""
    aircraft_list = flight_data_json.get('ac', [])
    number_of_aircraft = len(aircraft_list)
    print(f"Number of aircraft found: {number_of_aircraft}")

    if number_of_aircraft == 0:
        return None

    airborne_index = None
    airborne_dist = float('inf')
    fallback_index = 0
    fallback_dist = float('inf')

    for index, ac in enumerate(aircraft_list):
        category = ac.get('category', '')
        if (prefer_airliners == 0) or (category in ('A3', 'A4', 'A5')):
            try:
                dist = float(ac.get('dst', 0))
            except (ValueError, TypeError):
                continue

            is_ground = str(ac.get('alt_baro', '')).strip().lower() == 'ground'
            if not is_ground and dist < airborne_dist:
                airborne_dist = dist
                airborne_index = index
            if dist < fallback_dist:
                fallback_dist = dist
                fallback_index = index

    chosen_index = airborne_index if airborne_index is not None else fallback_index
    chosen_dist = airborne_dist if airborne_index is not None else fallback_dist
    print(f"Closest flight found at index {chosen_index} with distance {chosen_dist} miles")
    return aircraft_list[chosen_index]

def is_route_plausible(origin_lat, origin_lon, dest_lat, dest_lon, ac_lat, ac_lon):
    """Checks whether the aircraft position is plausibly along the origin-destination corridor."""
    try:
        ac_lat = float(ac_lat)
        ac_lon = float(ac_lon)
    except (ValueError, TypeError):
        return True

    if ac_lat == 0 and ac_lon == 0:
        return True

    journey = calculate_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    if journey <= 0:
        return True

    dist_from_origin = calculate_distance(origin_lat, origin_lon, ac_lat, ac_lon)
    dist_to_dest = calculate_distance(ac_lat, ac_lon, dest_lat, dest_lon)

    if dist_to_dest > journey + 60:
        return False
    if dist_from_origin + dist_to_dest > journey * 1.35 + 60:
        return False
    return True


def get_route_info_json(callsign, lat=None, lon=None):
    """Fetches route information for a given flight callsign, using live position when available."""
    if not callsign or callsign.lower() == 'unknown':
        return None

    callsign_clean = callsign.strip().upper()
    if len(callsign_clean) < 2:
        return None

    if lat is not None and lon is not None:
        try:
            lat_f, lon_f = float(lat), float(lon)
            if lat_f != 0 or lon_f != 0:
                routeset_resp = _SESSION.post(
                    "https://api.adsb.lol/api/0/routeset",
                    json={"planes": [{"callsign": callsign_clean, "lat": lat_f, "lng": lon_f}]},
                    timeout=6,
                )
                if routeset_resp.status_code == 200:
                    payload = routeset_resp.json()
                    if isinstance(payload, list) and payload:
                        first = payload[0]
                        if isinstance(first, dict) and first.get('_airports'):
                            return first
        except (requests.RequestException, ValueError, TypeError) as e:
            print(f"Routeset lookup exception: {e}")

    prefix = callsign_clean[:2]
    # Fetch directly from the static server bypasses the redirect overhead
    url = f"https://vrs-standing-data.adsb.lol/routes/{prefix}/{callsign_clean}.json"

    try:
        route_response = _SESSION.get(url, timeout=10)
        if route_response.status_code == 200:
            return route_response.json()
        print(f"Route info not found for {callsign_clean} (Status: {route_response.status_code})")
    except requests.RequestException as e:
        print(f"Route fetching exception: {e}")

    return None

@app.route('/closest_flight', methods=['GET'])
def closest_flight():
    """ Fetches the closest flight data based on latitude, longitude, and radius."""
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    radius = request.args.get('radius')
    
    try:
        prefer_airliners = int(request.args.get('preferAirliners', '1'))
    except ValueError:
        prefer_airliners = 1

    print(f"Fetching closest flight data for lat: {lat}, lon: {lon}, radius: {radius} miles")

    if lat is None or lon is None or radius is None:
        return jsonify({"error": "Latitude, longitude, and radius are required parameters"}), 400

    flight_data_json, upstream_error, upstream_status = fetch_flight_data_with_status(lat, lon, radius)
    if flight_data_json is None:
        return jsonify({"error": upstream_error or "Upstream ADS-B error"}), upstream_status

    closest_flight_json = get_closest_flight(flight_data_json, prefer_airliners)
    if closest_flight_json is None:
        if request.args.get('allow_empty') == '1':
            return jsonify({"no_aircraft": True, "flight": "Clear Skies", "message": "No aircraft detected"})
        return jsonify({"error": "No aircraft detected"}), 404

    flight = (closest_flight_json.get('flight') or 'Unknown').strip()

    flight_data = {}
    flight_data['flight'] = flight
    flight_data['type'] = closest_flight_json.get('t', 'Unknown')
    flight_data['model'] = get_aircraft_model(flight_data['type'])

    # Field maps
    fields = [
        ('emergency', lambda v: v, False),
        ('category', str, ''),
        ('squawk', str, '0'),
        ('track', lambda v: v, 0),
        ('lat', lambda v: v, '0'),
        ('lon', lambda v: v, '0'),
        ('alt_baro', lambda v: v, '0'),
        ('alt_geo', lambda v: v, '0'),
        ('gs', lambda v: v, 0),
        ('baro_rate', lambda v: v, 0),
        ('geom_rate', lambda v: v, '0'),
        ('dir', lambda v: v, '0'),
        ('rsi', lambda v: v, '0'),
        ('dst', lambda v: v, 0),
        ('nav_modes', lambda v: v, 'Unknown'),
        ('nav_qnh', lambda v: v, '0'),
        ('nav_altitude_mcp', lambda v: v, '0'),
        ('nav_heading', lambda v: v, 0),
    ]

    for key, cast, default in fields:
        flight_data[key] = cast(closest_flight_json.get(key, default))

    flight_data['registration'] = str(
        closest_flight_json.get('r') or closest_flight_json.get('registration') or 'Unknown'
    )

    raw_track = flight_data['track']
    flight_data['baro_rate_symbol'] = rate_to_arrow(flight_data['baro_rate'])
    flight_data['geom_rate_symbol'] = rate_to_arrow(flight_data['geom_rate'])
    flight_data['dir_cardinal'] = degrees_to_cardinal(flight_data['dir'])
    flight_data['track_cardinal'] = degrees_to_cardinal(raw_track)
    flight_data['category_label'] = CATEGORY_LABELS.get(flight_data.get('category', ''), '')

    # Format Headings cleanly
    for k in ['track', 'dir', 'nav_heading']:
        flight_data[k] = f"{degrees_to_compass_direction(flight_data[k])} {flight_data[k]}°"

    # Fetch route data safely
    route_response_json = get_route_info_json(flight, flight_data.get('lat'), flight_data.get('lon'))
    flight_data['distance_journey'] = 0
    flight_data['distance_to_dest'] = 0
    flight_data['route_map'] = None

    if route_response_json:
        # Static file directly returns the object, not an array
        flight_data['route_iata'] = route_response_json.get('_airport_codes_iata', [])
        flight_data['airport_codes'] = route_response_json.get('airport_codes', [])
        flight_data['airline_code'] = route_response_json.get('airline_code', '')
        flight_data['airports'] = route_response_json.get('_airports', [])

        # Calculate coordinates if they are present
        if isinstance(flight_data['airports'], list) and len(flight_data['airports']) > 1:
            try:
                origin_lat = float(flight_data['airports'][0].get('lat', 0))
                origin_lon = float(flight_data['airports'][0].get('lon', 0))
                dest_lat = float(flight_data['airports'][1].get('lat', 0))
                dest_lon = float(flight_data['airports'][1].get('lon', 0))

                if is_route_plausible(origin_lat, origin_lon, dest_lat, dest_lon, flight_data['lat'], flight_data['lon']):
                    flight_data['distance_journey'] = int(calculate_distance(origin_lat, origin_lon, dest_lat, dest_lon))
                    flight_data['distance_to_dest'] = int(calculate_distance(float(flight_data['lat']), float(flight_data['lon']), dest_lat, dest_lon))
                    dj = flight_data['distance_journey']
                    prog = max(0.0, min(100.0, ((dj - flight_data['distance_to_dest']) / dj * 100.0) if dj > 0 else 0.0))
                    from route_map import build_route_map
                    flight_data['route_map'] = build_route_map(
                        origin_lat, origin_lon, dest_lat, dest_lon,
                        flight_data['lat'], flight_data['lon'],
                        track_deg=raw_track, progress_pct=prog,
                    )
                else:
                    print(f"Discarding implausible route {flight_data['route_iata']} for {flight}")
                    flight_data['route_iata'] = []
                    flight_data['airport_codes'] = 'unknown'
                    flight_data['airports'] = 'Unknown'
                    flight_data['distance_journey'] = 0
                    flight_data['distance_to_dest'] = 0
            except (ValueError, TypeError):
                flight_data['distance_journey'] = 0
                flight_data['distance_to_dest'] = 0
    else:
        # Defaults if database doesn't have route records for the plane
        flight_data['route_iata'] = []
        flight_data['airport_codes'] = []
        flight_data['airline_code'] = ''
        flight_data['airports'] = 'Unknown'
        flight_data['distance_journey'] = 0
        flight_data['distance_to_dest'] = 0

    flight_data['airline_name'] = (
        (route_response_json.get('airline_name') if isinstance(route_response_json, dict) else None)
        or AIRLINE_NAMES.get(flight_data['airline_code'], '')
    )
    if flight_data['distance_to_dest'] > 0 and float(flight_data.get('gs') or 0) > 0:
        flight_data['ete_minutes'] = int(
            round(flight_data['distance_to_dest'] / (float(flight_data['gs']) * 1.15078) * 60)
        )
    else:
        flight_data['ete_minutes'] = None

    flight_data['logo'] = get_aircraft_logo(flight_data['airline_code'])
    flight_data['logo_url'] = (
        f"{request.url_root.rstrip('/')}/logos/{flight_data['logo']}"
        if flight_data['logo']
        else None
    )
    print(f"Logo for airline code {flight_data['airline_code']}: {flight_data['logo']}")

    return jsonify(flight_data)


@app.route('/logos/<path:filename>')
def serve_logo(filename):
    logos_dir = os.path.join(os.path.dirname(__file__), 'logos')
    return send_from_directory(logos_dir, filename)

def _parse_optional_date():
    date_str = request.args.get('date')
    if not date_str:
        return None, None
    try:
        from datetime import date
        return date.fromisoformat(date_str), None
    except ValueError:
        return None, (jsonify({"error": "Invalid date format, expected YYYY-MM-DD"}), 400)


@app.route('/crossword/daily')
def crossword_daily():
    from crossword_generator import generate_daily_puzzle
    target_date, err = _parse_optional_date()
    if err:
        return err
    return jsonify(generate_daily_puzzle(target_date))


@app.route('/rebus/daily')
def rebus_daily():
    from rebus_generator import generate_daily_rebus
    target_date, err = _parse_optional_date()
    if err:
        return err
    return jsonify(generate_daily_rebus(target_date))


@app.route('/rce/daily')
def rce_daily():
    from rce_dashboard import fetch_rce_dashboard
    target_date, err = _parse_optional_date()
    if err:
        return err
    try:
        return jsonify(fetch_rce_dashboard(target_date))
    except requests.RequestException as exc:
        return jsonify({"error": f"CISA KEV feed unavailable: {exc}"}), 502


@app.route('/mitre/daily')
def mitre_daily():
    from mitre_attack import generate_daily_mitre
    target_date, err = _parse_optional_date()
    if err:
        return err
    return jsonify(generate_daily_mitre(target_date))


@app.route('/isc/daily')
def isc_daily():
    from sans_isc import fetch_sans_isc
    try:
        return jsonify(fetch_sans_isc())
    except requests.RequestException as exc:
        return jsonify({"error": f"SANS ISC feed unavailable: {exc}"}), 502


@app.route('/outages/daily')
def outages_daily():
    from outage_radar import fetch_outage_radar
    try:
        return jsonify(fetch_outage_radar())
    except requests.RequestException as exc:
        return jsonify({"error": f"IODA outage feed unavailable: {exc}"}), 502


@app.route('/solar/daily')
def solar_daily():
    from solar_orrery import generate_solar_orrery
    target_date, err = _parse_optional_date()
    if err:
        return err
    return jsonify(generate_solar_orrery(target_date))


@app.route('/museum/daily')
def museum_daily():
    from museum_daily import fetch_daily_masterpiece
    target_date, err = _parse_optional_date()
    if err:
        return err
    try:
        return jsonify(fetch_daily_masterpiece(target_date))
    except (requests.RequestException, ValueError) as exc:
        return jsonify({"error": f"Museum feed unavailable: {exc}"}), 502


@app.route('/kanji/daily')
def kanji_daily():
    from kanji_daily import generate_daily_kanji
    target_date, err = _parse_optional_date()
    if err:
        return err
    return jsonify(generate_daily_kanji(target_date))


@app.route('/plotter/daily')
def plotter_daily():
    from plotter_art import generate_daily_plotter
    target_date, err = _parse_optional_date()
    if err:
        return err
    return jsonify(generate_daily_plotter(target_date))


@app.route('/seismic/daily')
def seismic_daily():
    from seismic_pulse import fetch_seismic_pulse
    try:
        return jsonify(fetch_seismic_pulse())
    except requests.RequestException as exc:
        return jsonify({"error": f"USGS seismic feed unavailable: {exc}"}), 502


@app.route('/markets/fear-greed')
def markets_fear_greed():
    from fear_greed import fetch_fear_greed
    try:
        return jsonify(fetch_fear_greed())
    except requests.RequestException as exc:
        return jsonify({"error": f"Market sentiment feed unavailable: {exc}"}), 502


@app.route('/nba/story')
def nba_story():
    from nba_game_story import fetch_nba_game_story
    target_date, err = _parse_optional_date()
    if err:
        return err
    try:
        return jsonify(fetch_nba_game_story(target_date))
    except (requests.RequestException, ValueError) as exc:
        return jsonify({"error": f"NBA game story unavailable: {exc}"}), 502


@app.route('/nfl/story')
def nfl_story():
    from nfl_game_story import fetch_nfl_game_story
    target_date, err = _parse_optional_date()
    if err:
        return err
    try:
        return jsonify(fetch_nfl_game_story(target_date))
    except (requests.RequestException, ValueError) as exc:
        return jsonify({"error": f"NFL game story unavailable: {exc}"}), 502


@app.route('/stoic/daily')
def stoic_daily():
    from stoic_sundial import generate_stoic_sundial
    target_date, err = _parse_optional_date()
    if err:
        return err
    try:
        lat = float(request.args.get('lat') or 41.88)
        lon = float(request.args.get('lon') or -87.63)
    except ValueError:
        lat, lon = 41.88, -87.63
    return jsonify(generate_stoic_sundial(target_date, lat=lat, lon=lon))


@app.route('/retro/random')
def retro_random():
    from retro_games import fetch_random_retro_game
    seed_arg = request.args.get('seed')
    try:
        seed = int(seed_arg) if seed_arg is not None else None
    except ValueError:
        seed = None
    return jsonify(fetch_random_retro_game(seed=seed))


@app.route('/splatoon/schedule')
def splatoon_schedule():
    from splatoon_schedule import fetch_splatoon_schedule
    try:
        return jsonify(fetch_splatoon_schedule())
    except requests.RequestException as exc:
        return jsonify({"error": f"Splatoon schedule unavailable: {exc}"}), 502


@app.route('/iq/daily')
def iq_daily():
    from iq_puzzle import generate_daily_iq
    target_date, err = _parse_optional_date()
    if err:
        return err
    return jsonify(generate_daily_iq(target_date))


@app.route('/map/pixel')
def map_pixel():
    from pixel_map import generate_pixel_map
    return jsonify(generate_pixel_map())


if __name__ == '__main__':
    app.run(debug=True, port=5000)