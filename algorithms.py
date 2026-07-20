import heapq
import math
import json
import urllib.request
import urllib.error

# Kathmandu Valley Hubs Coordinates
HUBS = {
    'Kalanki': {'lat': 27.6946, 'lng': 85.2813},
    'New Baneshwor': {'lat': 27.6915, 'lng': 85.3331},
    'Koteshwor': {'lat': 27.6775, 'lng': 85.3486},
    'Chabahil': {'lat': 27.7172, 'lng': 85.3444},
    'Gongabu': {'lat': 27.7344, 'lng': 85.3112},
    'Thamel': {'lat': 27.7154, 'lng': 85.3123},
    'Lagankhel': {'lat': 27.6672, 'lng': 85.3218},
    'Bhaktapur': {'lat': 27.6722, 'lng': 85.4278}
}

# Hub connections & distances in km (Graph representation)
GRAPH = {
    'Kalanki': {'Gongabu': 4.8, 'Thamel': 5.2, 'Lagankhel': 6.5},
    'Thamel': {'Kalanki': 5.2, 'Gongabu': 3.0, 'Chabahil': 5.5, 'New Baneshwor': 4.2},
    'Gongabu': {'Kalanki': 4.8, 'Thamel': 3.0, 'Chabahil': 4.5},
    'Chabahil': {'Thamel': 5.5, 'Gongabu': 4.5, 'Koteshwor': 5.8, 'Bhaktapur': 11.0},
    'New Baneshwor': {'Thamel': 4.2, 'Koteshwor': 2.2, 'Lagankhel': 4.0},
    'Koteshwor': {'Chabahil': 5.8, 'New Baneshwor': 2.2, 'Lagankhel': 4.5, 'Bhaktapur': 8.5},
    'Lagankhel': {'Kalanki': 6.5, 'New Baneshwor': 4.0, 'Koteshwor': 4.5},
    'Bhaktapur': {'Chabahil': 11.0, 'Koteshwor': 8.5}
}

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians 
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

    # haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371 # Radius of earth in kilometers
    return r * c

# Physical road conditions and traffic congestion variables mapping (symmetrical lookup)
ROAD_CONDITIONS = {
    ('Gongabu', 'Kalanki'): {'condition': 'Under Construction (Ring Road Section)', 'traffic': 'Heavy', 'factor': 1.8, 'speed_limit': 30},
    ('Kalanki', 'Thamel'): {'condition': 'Potholes and active maintenance', 'traffic': 'Moderate', 'factor': 1.3, 'speed_limit': 40},
    ('Kalanki', 'Lagankhel'): {'condition': 'Smooth Asphalt (Standard)', 'traffic': 'Light', 'factor': 1.0, 'speed_limit': 50},
    ('Gongabu', 'Thamel'): {'condition': 'Narrow urban street lanes', 'traffic': 'Moderate', 'factor': 1.4, 'speed_limit': 35},
    ('Chabahil', 'Thamel'): {'condition': 'High commercial retail lane congestion', 'traffic': 'Heavy', 'factor': 1.9, 'speed_limit': 35},
    ('New Baneshwor', 'Thamel'): {'condition': 'Smooth arterial roads', 'traffic': 'Heavy', 'factor': 1.7, 'speed_limit': 45},
    ('Chabahil', 'Gongabu'): {'condition': 'Ring road section, minor dusty spots', 'traffic': 'Moderate', 'factor': 1.2, 'speed_limit': 45},
    ('Chabahil', 'Koteshwor'): {'condition': 'Ring road, peak hour heavy traffic', 'traffic': 'Heavy', 'factor': 1.6, 'speed_limit': 50},
    ('Bhaktapur', 'Chabahil'): {'condition': 'Araniko highway connection, smooth', 'traffic': 'Light', 'factor': 1.1, 'speed_limit': 55},
    ('Koteshwor', 'New Baneshwor'): {'condition': 'Smooth wide multi-lane highway', 'traffic': 'Heavy', 'factor': 1.8, 'speed_limit': 50},
    ('Lagankhel', 'New Baneshwor'): {'condition': 'Paved double-lane city street', 'traffic': 'Moderate', 'factor': 1.3, 'speed_limit': 40},
    ('Koteshwor', 'Lagankhel'): {'condition': 'Road damages near flyover underpass', 'traffic': 'Heavy', 'factor': 1.7, 'speed_limit': 40},
    ('Bhaktapur', 'Koteshwor'): {'condition': 'Six-lane Araniko Highway (Excellent)', 'traffic': 'Light', 'factor': 1.0, 'speed_limit': 60},
}

def get_road_data(u, v):
    """
    Finds the road conditions for the link between two hubs (undirected).
    """
    key = tuple(sorted([u, v]))
    fallback = {'condition': 'Normal road conditions', 'traffic': 'Moderate', 'factor': 1.2, 'speed_limit': 40}
    return ROAD_CONDITIONS.get(key, fallback)

def get_all_hubs_dict():
    """
    Combines the static HUBS dictionary with dynamic hubs registered in the database.
    """
    all_hubs = dict(HUBS)
    try:
        from models import Hub
        db_hubs = Hub.query.all()
        for h in db_hubs:
            all_hubs[h.name] = {'lat': h.latitude, 'lng': h.longitude}
    except Exception:
        pass
    return all_hubs

def get_dynamic_graph():
    """
    Builds a copy of GRAPH, linking dynamically registered hubs from the database
    to their closest neighbor in the existing network.
    """
    dynamic_graph = {node: dict(edges) for node, edges in GRAPH.items()}
    try:
        from models import Hub
        db_hubs = Hub.query.all()
        # Find hubs that are not in the static GRAPH
        dynamic_hub_records = [h for h in db_hubs if h.name not in GRAPH]
        
        if dynamic_hub_records:
            all_hubs = get_all_hubs_dict()
            for h in dynamic_hub_records:
                closest_neighbor = None
                min_dist = float('inf')
                for other_name, coords in all_hubs.items():
                    if other_name != h.name and other_name in GRAPH:
                        dist = haversine_distance(h.latitude, h.longitude, coords['lat'], coords['lng'])
                        if dist < min_dist:
                            min_dist = dist
                            closest_neighbor = other_name
                
                if closest_neighbor:
                    # Inject bidirectional edge
                    if h.name not in dynamic_graph:
                        dynamic_graph[h.name] = {}
                    dynamic_graph[h.name][closest_neighbor] = min_dist
                    
                    if closest_neighbor not in dynamic_graph:
                        dynamic_graph[closest_neighbor] = {}
                    dynamic_graph[closest_neighbor][h.name] = min_dist
    except Exception:
        pass
    return dynamic_graph

def dijkstra(start, end):
    """
    Dijkstra's Shortest Path Algorithm on Kathmandu Valley Hub Network,
    weighted by dynamic traffic and road conditions.
    Returns: (path_list, total_distance)
    """
    dynamic_graph = get_dynamic_graph()
    
    if start not in dynamic_graph or end not in dynamic_graph:
        return None, float('inf')
        
    queue = [(0, start, [start])]
    seen = set()
    
    while queue:
        (cost, current, path) = heapq.heappop(queue)
        if current in seen:
            continue
        seen.add(current)
        
        if current == end:
            # Return path and the actual physical distance in km
            real_dist = 0.0
            for i in range(len(path) - 1):
                real_dist += dynamic_graph[path[i]][path[i+1]]
            return path, real_dist
            
        for next_node, weight in dynamic_graph.get(current, {}).items():
            if next_node not in seen:
                road_data = get_road_data(current, next_node)
                # Weighted edge cost adjusted by traffic multiplier
                edge_cost = weight * road_data['factor']
                heapq.heappush(queue, (cost + edge_cost, next_node, path + [next_node]))
                
    return None, float('inf')

def fetch_osrm_route(lat1, lng1, lat2, lng2):
    """
    Fetch turn-by-turn road geometry from OSM Routing API (OSRM) 
    between two coordinates, falling back to straight lines on error.
    """
    url = f"http://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'ParcelFleet/1.0 (Logistics System Project)'}
        )
        # 3 seconds timeout to prevent blocking thread
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            if data.get('routes'):
                geojson_coords = data['routes'][0]['geometry']['coordinates']
                # geojson returns [lng, lat]
                return [{'lat': pt[1], 'lng': pt[0]} for pt in geojson_coords]
    except Exception as e:
        print(f"OSRM Routing API failed, falling back to straight line: {e}")
    # Fallback to straight line coordinate array
    return [{'lat': lat1, 'lng': lng1}, {'lat': lat2, 'lng': lng2}]

def get_route_segments(path, pickup_coords=None, delivery_coords=None):
    """
    Compiles detailed route segments with coordinates, traffic, and conditions.
    Connects [Home Pickup] -> [Hub Path] -> [Home Delivery].
    Uses real road geometry coordinates fetched from OSM Routing API.
    """
    segments = []
    all_hubs = get_all_hubs_dict()
    
    # 1. Home Pickup to Closest Hub leg
    if pickup_coords and len(path) > 0:
        hub_name = path[0]
        hub_info = all_hubs.get(hub_name)
        if hub_info:
            segments.append({
                'from': 'Home Pickup',
                'to': f"{hub_name} Hub",
                'coordinates': fetch_osrm_route(pickup_coords['lat'], pickup_coords['lng'], hub_info['lat'], hub_info['lng']),
                'traffic': 'Light',
                'condition': 'Local home access road (Clear)',
                'color': '#22C55E',  # Green
                'speed_limit': 30
            })
            
    # 2. Hub-to-Hub intermediate legs
    for i in range(len(path) - 1):
        u = path[i]
        v = path[i+1]
        u_info = all_hubs.get(u)
        v_info = all_hubs.get(v)
        
        if u_info and v_info:
            road_data = get_road_data(u, v)
            traffic = road_data['traffic']
            
            # Map traffic status to colors
            if traffic == 'Heavy':
                color = '#EF4444'  # Red
            elif traffic == 'Moderate':
                color = '#F59E0B'  # Orange/Yellow
            else:
                color = '#22C55E'  # Green
                
            segments.append({
                'from': f"{u} Hub",
                'to': f"{v} Hub",
                'coordinates': fetch_osrm_route(u_info['lat'], u_info['lng'], v_info['lat'], v_info['lng']),
                'traffic': traffic,
                'condition': road_data['condition'],
                'color': color,
                'speed_limit': road_data['speed_limit']
            })
            
    # 3. Closest Hub to Home Delivery leg
    if delivery_coords and len(path) > 0:
        hub_name = path[-1]
        hub_info = all_hubs.get(hub_name)
        if hub_info:
            segments.append({
                'from': f"{hub_name} Hub",
                'to': 'Home Delivery',
                'coordinates': fetch_osrm_route(hub_info['lat'], hub_info['lng'], delivery_coords['lat'], delivery_coords['lng']),
                'traffic': 'Light',
                'condition': 'Local home delivery lane (Clear)',
                'color': '#22C55E',  # Green
                'speed_limit': 30
            })
            
    return segments


def greedy_driver_assignment(parcel, available_drivers):
    """
    Greedy Driver Assignment: Finds the closest available driver
    to the parcel's pickup hub coordinate.
    Returns: (driver_object, distance) or (None, None)
    """
    all_hubs = get_all_hubs_dict()
    pickup_hub = all_hubs.get(parcel.pickup_hub)
    if not pickup_hub:
        pickup_lat = parcel.pickup_latitude
        pickup_lng = parcel.pickup_longitude
    else:
        pickup_lat = pickup_hub['lat']
        pickup_lng = pickup_hub['lng']
    
    closest_driver = None
    min_distance = float('inf')
    
    for driver in available_drivers:
        # Check if driver is available
        if driver.availability == 'Available':
            dist = haversine_distance(driver.latitude, driver.longitude, pickup_lat, pickup_lng)
            if dist < min_distance:
                min_distance = dist
                closest_driver = driver
                
    return closest_driver, min_distance

def get_route_coordinates(path):
    """
    Transforms a list of hub names into a list of lat/lng coordinate dicts
    for Leaflet map rendering.
    """
    all_hubs = get_all_hubs_dict()
    coords = []
    for hub_name in path:
        hub_info = all_hubs.get(hub_name)
        if hub_info:
            coords.append({'name': hub_name, 'lat': hub_info['lat'], 'lng': hub_info['lng']})
    return coords

def get_closest_hub(lat, lng):
    """
    Find the closest Kathmandu Valley hub name based on spatial distance.
    """
    all_hubs = get_all_hubs_dict()
    closest = None
    min_dist = float('inf')
    for name, coords in all_hubs.items():
        dist = haversine_distance(lat, lng, coords['lat'], coords['lng'])
        if dist < min_dist:
            min_dist = dist
            closest = name
    return closest

def fetch_osrm_routes_with_alternatives(lat1, lng1, lat2, lng2):
    """
    Fetch up to 3 driving routes (including alternatives) from OSRM API,
    returning coordinates, duration (minutes), and distance (km) for each.
    """
    import urllib.request
    import json
    url = f"http://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=full&geometries=geojson&alternatives=true"
    routes_list = []
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'ParcelFleet/1.0 (Logistics System Project)'}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            if data.get('routes'):
                for i, r in enumerate(data['routes']):
                    geojson_coords = r['geometry']['coordinates']
                    coords = [{'lat': pt[1], 'lng': pt[0]} for pt in geojson_coords]
                    duration_min = round(r['duration'] / 60.0, 1)
                    distance_km = round(r['distance'] / 1000.0, 2)
                    
                    name = "Recommended Route" if i == 0 else f"Alternative Route {i}"
                    routes_list.append({
                        'route_index': i,
                        'name': name,
                        'coordinates': coords,
                        'duration_min': duration_min,
                        'distance_km': distance_km
                    })
    except Exception as e:
        print(f"OSRM Alternatives API failed: {e}")
        
    if not routes_list:
        dist_km = round(haversine_distance(lat1, lng1, lat2, lng2), 2)
        duration_min = round((dist_km / 25.0) * 60.0, 1)
        routes_list.append({
            'route_index': 0,
            'name': 'Direct Route (Fallback)',
            'coordinates': [{'lat': lat1, 'lng': lng1}, {'lat': lat2, 'lng': lng2}],
            'duration_min': duration_min,
            'distance_km': dist_km
        })
    return routes_list
