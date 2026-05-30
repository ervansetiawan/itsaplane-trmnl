""" pytmrnl - A terminal for tracking aircraft """

import os
import json
from math import radians, sin, cos, sqrt, atan2

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

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
    index = round((degrees + 22.5) / 45) % 8
    return directions[index]

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

def fecth_flight_data_json(lat, lon, radius):
    """Fetches flight data from the ADS-B API."""
    try:
        flight_data = requests.get(f'https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius}', timeout=10)
        if flight_data.status_code == 200:
            return flight_data.json()
        print(f"Error fetching flight data: {flight_data.status_code}. Response: {flight_data.text}")
    except requests.RequestException as e:
        print(f"Request failed: {e}")
    return None

def get_closest_flight(flight_data_json, prefer_airliners):
    """Finds the closest flight from the flight data JSON."""
    aircraft_list = flight_data_json.get('ac', [])
    number_of_aircraft = len(aircraft_list)
    print(f"Number of aircraft found: {number_of_aircraft}")

    if number_of_aircraft == 0:
        return None

    index_closest = 0
    closest_dist = 1000000 

    for index, ac in enumerate(aircraft_list):
        category = ac.get('category', '')
        if (prefer_airliners == 0) or (category in ('A3', 'A4', 'A5')):
            try:
                dist = int(ac.get('dst', 0))
                if dist < closest_dist:
                    closest_dist = dist
                    index_closest = index
            except (ValueError, TypeError):
                continue

    print(f"Closest flight found at index {index_closest} with distance {closest_dist} miles")
    return aircraft_list[index_closest]

def get_route_info_json(callsign):
    """Fetches route information for a given flight callsign directly from the asset server."""
    if not callsign or callsign.lower() == 'unknown':
        return None
        
    callsign_clean = callsign.strip().upper()
    if len(callsign_clean) < 2:
        return None
        
    prefix = callsign_clean[:2]
    # Fetch directly from the static server bypasses the redirect overhead
    url = f"https://vrs-standing-data.adsb.lol/routes/{prefix}/{callsign_clean}.json"
    
    try:
        route_response = requests.get(url, timeout=10)
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

    flight_data_json = fecth_flight_data_json(lat, lon, radius)
    if flight_data_json is None:
        return jsonify({"error": "No aircraft detected"}), 404

    closest_flight_json = get_closest_flight(flight_data_json, prefer_airliners)
    if closest_flight_json is None:
        return jsonify({"error": "No aircraft detected"}), 404
        
    flight = closest_flight_json.get('flight', 'Unknown').strip()

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
        ('registration', str, 'Unknown'),
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

    flight_data['baro_rate_symbol'] = rate_to_arrow(flight_data['baro_rate'])
    flight_data['geom_rate_symbol'] = rate_to_arrow(flight_data['geom_rate'])

    # Format Headings cleanly
    for k in ['track', 'dir', 'nav_heading']:
        flight_data[k] = f"{degrees_to_compass_direction(flight_data[k])} {flight_data[k]}°"

    # Fetch route data safely
    route_response_json = get_route_info_json(flight)
    
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

                flight_data['distance_journey'] = int(calculate_distance(origin_lat, origin_lon, dest_lat, dest_lon))
                flight_data['distance_to_dest'] = int(calculate_distance(float(flight_data['lat']), float(flight_data['lon']), dest_lat, dest_lon))
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

    flight_data['logo'] = get_aircraft_logo(flight_data['airline_code'])
    print(f"Logo for airline code {flight_data['airline_code']}: {flight_data['logo']}")

    return jsonify(flight_data)

if __name__ == '__main__':
    app.run(debug=True, port=5000)