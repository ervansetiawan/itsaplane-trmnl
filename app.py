import os
from flask import Flask, jsonify, request 
from io import BytesIO 

import markdown2
 
import requests
import json

app = Flask(__name__)

# read aircrafts.csv and return a list of dictionaries
def get_aircraft_model(aircraft_type):  
    aircrafts = []
    with open('aircrafts.csv', 'r') as file:
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
    from math import radians, sin, cos, sqrt, atan2

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
    if int(rate) < 0:
        return '&#9660;'
    elif int(rate) > 0:
        return '&#9650;'
    else:
        return ''
    
@app.route('/closest_flight', methods=['GET'])
def closest_flight():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    radius = request.args.get('radius')
  
    preferAirliners = int(request.args.get('preferAirliners', '0'))

    print(f"Fetching closest flight data for lat: {lat}, lon: {lon}, radius: {radius} miles")

    if lat is None or lon is None or radius is None:
        return jsonify({"error": "Latitude, longitude, and radius are required parameters"}), 400   

    closest_response = requests.get(f'https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius}')

    if closest_response.status_code == 200:
        closest_response_json = closest_response.json()

        index = 0
        index_closest = 0
        flight = None
        closest_dist = 1000000  # Initialize with a large number

        number_of_aircraft = len(closest_response_json.get('ac', []))
        print(f"Number of aircraft found: {number_of_aircraft}")

        if number_of_aircraft == 0:
            return jsonify({"error": "No aircraft found within the specified radius"}), 404

        while index < number_of_aircraft:

            category = closest_response_json['ac'][index].get('category', '') 
            print(preferAirliners==0)
            if((preferAirliners == 0) or (category == 'A3' or category == 'A4' or category == 'A5')):
                dist = int(closest_response_json.get('ac', [{}])[index].get('dst', '0'))
                print(f"Checking flight at index {index}: {closest_response_json.get('ac', [{}])[index].get('flight', 'Unknown')} with distance {dist} miles")
                if dist < closest_dist:
                    flight = closest_response_json.get('ac', [{}])[index].get('flight')
                    closest_dist = dist
                    index_closest = index

            index += 1
   
        print(f"Closest flight found: {flight} at index {index_closest} with distance {closest_dist} miles")
      
        # call https://api.adsb.lol/0/routeset to get the route data using POST method
        # pass in the request body as JSON
        planes = {
            "planes": [
                {
                    "callsign": flight.strip(),
                    "lat": lat,
                    "lng": lon
                }
            ]
        }

        route_response = requests.post('https://api.adsb.lol/api/0/routeset', data=json.dumps(planes), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})

        print(f"Route response status code: {route_response.status_code}")
        if route_response.status_code == 200:
            route_response_json = route_response.json()

            flight_data= {}

            flight_data['flight'] = flight
            flight_data['type'] = closest_response_json.get('ac', [{}])[index_closest].get('t', 'Unknown')
            
            flight_data['model'] = get_aircraft_model(flight_data['type'])         
                     
            # Define the fields to extract: (key, type, default)
            fields = [
                ('emergency', lambda v: v, False),
                ('category', str, ''),
                ('squawk', str, '0'),
                ('track', int, 0),
                ('lat', lambda v: v, '0'),
                ('lon', lambda v: v, '0'),
                ('alt_baro', lambda v: v, '0'),
                ('alt_geo', lambda v: v, '0'),
                ('registration', lambda v: v, 'Unknown'),
                ('gs', int, 0),
                ('baro_rate', int, 0),
                ('geom_rate', lambda v: v, '0'),
                ('dir', lambda v: v, '0'),
                ('rsi', lambda v: v, '0'),
                ('dst', int, 0),
                ('nav_modes', lambda v: v, 'Unknown'),
                ('nav_qnh', lambda v: v, '0'),
                ('nav_altitude_mcp', lambda v: v, '0'),
                ('nav_heading', int, 0),
            ]
            ac = closest_response_json.get('ac', [{}])[index_closest]
            for key, cast, default in fields:
                flight_data[key] = cast(ac.get(key, default))

            flight_data['baro_rate_symbol'] = rate_to_arrow(flight_data['baro_rate'])
            flight_data['geom_rate_symbol'] = rate_to_arrow(flight_data['geom_rate'])

            # Determine the heading symbol based on the track value
            # Initialize heading_symbol
            
            flight_data['track'] = degrees_to_compass_direction(flight_data['track']) + " " + str(flight_data['track']) + "°"

            flight_data['dir'] = degrees_to_compass_direction(flight_data['dir']) + " " + str(flight_data['dir']) + "°"

            flight_data['nav_heading'] = degrees_to_compass_direction(flight_data['nav_heading']) + " " + str(flight_data['nav_heading']) + "°"

            # assign _airport_codes_iata to flight_data['route_iata']
            # if _airport_codes_iata is not present, assign an empty list       
            flight_data['route_iata'] = route_response_json[0].get(('_airport_codes_iata'), [])

            flight_data['airport_codes'] = route_response_json[0].get(('airport_codes'), [])

            if flight_data['airport_codes']:  
                code = flight_data['airport_codes'].split('-')
                if len(code) == 3:
                    # Keep only the first two segments
                    # flight_data['airport_codes'] = code[0] + '-' + code[1]
                    flight_data['airport_codes'] = code[0] + '-' + code[1] 
                
            flight_data['airline_code'] = route_response_json[0].get(('airline_code'), [])
            flight_data['airports'] = route_response_json[0].get('_airports', 'Unknown')

            if (flight_data['airports'] and len(flight_data['airports']) > 1):
                origin_lat = route_response_json[0].get('_airports')[0].get('lat', '0')
                origin_lon = route_response_json[0].get('_airports')[0].get('lon', '0')

                dest_lat = route_response_json[0].get('_airports')[1].get('lat', '0')
                dest_lon = route_response_json[0].get('_airports')[1].get('lon', '0')

                flight_data['distance_journey'] = int(calculate_distance(float(origin_lat), float(origin_lon), float(dest_lat), float(dest_lon)))
                flight_data['distance_to_dest'] = int(calculate_distance(float(flight_data['lat']), float(flight_data['lon']), float(dest_lat), float(dest_lon)))

            return jsonify(flight_data)
        else:
            return jsonify({"error": "Route data not found"}), 404
    else:
        return jsonify({"error": "Closest flight data not found"}), 500




