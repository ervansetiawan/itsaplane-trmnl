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
    logos_dir = os.path.join(os.path.dirname(__file__), 'logos')
    logo_filenames = [f for f in os.listdir(logos_dir)
                      if os.path.isfile(os.path.join(logos_dir, f))]

    # Check if the aircraft type has a corresponding logo
    for logo in logo_filenames:
        if aircraft_code.lower() in logo.lower():
            return logo

    # Return None if no specific logo is found
    return None

# read aircrafts.csv and return a list of dictionaries
def get_aircraft_model(aircraft_type):
    """Reads aircrafts.csv and returns the model for the given aircraft type."""
    if not aircraft_type:
        return None
    aircrafts = []
    with open('aircrafts.csv', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines[1:]:  # Skip the header
            parts = line.strip().split(',')
            if len(parts) == 2:
                aircrafts.append({"icao": parts[0].strip(), "model": parts[1].strip()})

    i=0

    print(f"Searching for aircraft type: {aircraft_type} in {len(aircrafts)} entries")
    # Find the aircraft model based on the type

    model = None
    while i < len(aircrafts):
        if aircrafts[i]['icao'] == aircraft_type:
            model = aircrafts[i]['model']
            break
        i += 1
    return model

def degrees_to_compass_direction(degrees):
    """
    Converts a heading in degrees (0-360) to a cardinal/intercardinal compass direction.
    """

    directions = ["\u2191", "\u2197", "\u2192", "\u2198", "\u2193", "\u2199", "\u2190", "\u2196"]
    # Adjust degrees to handle values outside 0-360 range
    degrees = degrees % 360

    # Each direction covers 45 degrees (360 / 8)
    # Shift the range so N is centered around 0 (i.e., -22.5 to +22.5)
    index = round((degrees + 22.5) / 45) % 8

    return directions[index]

# calculate distance between two coordinates and return the distance in miles
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates the distance between two geographical coordinates using the Haversine formula."""
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    # Radius of Earth in miles (mean radius)
    r = 3958.8
    return r * c

def rate_to_arrow(rate):
    """Converts a rate value to an arrow symbol."""

    if int(rate) < 0:
        return '&#9660;'
    if int(rate) > 0:
        return '&#9650;'
    return ''


def fecth_flight_data_json(lat, lon, radius):
    """Fetches flight data from the ADS-B API."""
    flight_data = requests.get(f'https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius}',
                                    timeout=10)
    if flight_data.status_code == 200:
        return flight_data.json()
    return None

def get_closest_flight(flight_data_json, prefer_airliners):
    """Finds the closest flight from the flight data JSON."""
    index = 0
    index_closest = 0
    closest_dist = 1000000  # Initialize with a large number

    number_of_aircraft = len(flight_data_json.get('ac', []))
    print(f"Number of aircraft found: {number_of_aircraft}")

    if number_of_aircraft == 0:
        return None

    while index < number_of_aircraft:
        category = flight_data_json['ac'][index].get('category', '')
        if((prefer_airliners == 0) or
           (category in ('A3', 'A4', 'A5'))):
            dist = int(flight_data_json.get('ac', [{}])[index].get('dst', '0'))
            if dist < closest_dist:
                closest_dist = dist
                index_closest = index
        index += 1

    print(
        f"Closest flight found at index {index_closest} "
        f"with distance {closest_dist} miles"
    )
    return flight_data_json.get('ac', [{}])[index_closest]

def get_route_info_json(callsign, lat, lon):
    """Fetches route information for a given flight callsign."""
    planes = {
        "planes": [
            {
                "callsign": callsign.strip(),
                "lat": lat,
                "lng": lon
            }
        ]
    }

    route_response = requests.post('https://api.adsb.lol/api/0/routeset',
                                   data=json.dumps(planes),
                                   timeout=10,
                                   headers={'Content-Type': 'application/json',
                                            'Accept': 'application/json'})

    if route_response.status_code == 200:
        return route_response.json()
    return None

@app.route('/closest_flight', methods=['GET'])
def closest_flight():
    """ Fetches the closest flight data based on latitude, longitude, and radius."""
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    radius = request.args.get('radius')
    prefer_airliners = int(request.args.get('preferAirliners', '1'))

    print(f"Fetching closest flight data for lat: {lat}, lon: {lon}, radius: {radius} miles")

    if lat is None or lon is None or radius is None:
        return jsonify({"error": "Latitude, longitude, and radius are required parameters"}), 400

    flight_data_json = fecth_flight_data_json(lat, lon, radius)
    if flight_data_json is None:
        return jsonify({"error": "No flights found within the specified radius"}), 404

    closest_flight_json = get_closest_flight(flight_data_json, prefer_airliners)

    flight = closest_flight_json.get('flight', 'Unknown')

    if closest_flight_json:
        flight_data= {}
        flight_data['flight'] = flight
        flight_data['type'] = closest_flight_json.get('t', 'Unknown')
        flight_data['model'] = get_aircraft_model(flight_data['type'])

        # Define the fields to extract: (key, type, default)
        fields = [
            ('emergency', lambda v: v, False),
            ('category', str, ''),
            ('squawk', lambda v: v, '0'),
            ('track', lambda v: v, 0),
            ('lat', lambda v: v, '0'),
            ('lon', lambda v: v, '0'),
            ('alt_baro', lambda v: v, '0'),
            ('alt_geo', lambda v: v, '0'),
            ('registration', lambda v: v, 'Unknown'),
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

        # Determine the heading symbol based on the track value
        # Initialize heading_symbol
        for k in ['track', 'dir', 'nav_heading']:
            flight_data[k] = f"{degrees_to_compass_direction(flight_data[k])} {flight_data[k]}°"

        # Fetch route information using the flight callsign
        route_response_json = get_route_info_json(flight, flight_data['lat'], flight_data['lon'])
        if route_response_json and len(route_response_json) > 0:
            # assign _airport_codes_iata to flight_data['route_iata']
            # if _airport_codes_iata is not present, assign an empty list
            flight_data['route_iata'] = route_response_json[0].get(('_airport_codes_iata'), [])
            flight_data['airport_codes'] = route_response_json[0].get(('airport_codes'), [])

        flight_data['airline_code'] = route_response_json[0].get(('airline_code'), [])

        flight_data['logo'] = get_aircraft_logo(flight_data['airline_code'])
        print(f"Logo for airline code {flight_data['airline_code']}: {flight_data['logo']}")

        flight_data['airports'] = route_response_json[0].get('_airports', 'Unknown')

        if (flight_data['airports'] and len(flight_data['airports']) > 1):
            origin_lat = route_response_json[0].get('_airports')[0].get('lat', '0')
            origin_lon = route_response_json[0].get('_airports')[0].get('lon', '0')

            dest_lat = route_response_json[0].get('_airports')[1].get('lat', '0')
            dest_lon = route_response_json[0].get('_airports')[1].get('lon', '0')

            flight_data['distance_journey'] = int(calculate_distance(float(origin_lat),
                                                                        float(origin_lon),
                                                                        float(dest_lat),
                                                                        float(dest_lon)))
            flight_data['distance_to_dest'] = int(calculate_distance(float(flight_data['lat']),
                                                                        float(flight_data['lon']),
                                                                        float(dest_lat),
                                                                        float(dest_lon)))

            return jsonify(flight_data)
        return jsonify({"error": "Route data not found"}), 404
    return jsonify({"error": "Closest flight data not found"}), 500
