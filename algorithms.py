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
    to the parcel's pickup coordinate whose assigned vehicle has 
    sufficient remaining weight and volume capacity.
    
    Parameters:
      - parcel: Parcel model or dict
      - available_drivers: list of Driver models
      
    Returns: (driver_object, distance_km) or (None, None)
    """
    if not available_drivers:
        return None, None

    parcel_weight = float(getattr(parcel, 'weight', 1.0) or 1.0)
    
    # Calculate parcel volume
    if hasattr(parcel, 'volume_m3'):
        parcel_volume = float(parcel.volume_m3 or 0.005)
    elif hasattr(parcel, 'length') and hasattr(parcel, 'width') and hasattr(parcel, 'height') and parcel.length and parcel.width and parcel.height:
        parcel_volume = float((parcel.length * parcel.width * parcel.height) / 1000000.0)
    else:
        parcel_volume = 0.005

    pickup_lat = getattr(parcel, 'pickup_latitude', 27.7172)
    pickup_lng = getattr(parcel, 'pickup_longitude', 85.3240)

    capable_drivers = []
    for d in available_drivers:
        if getattr(d, 'availability', 'Available') in ['Available', 'On Delivery']:
            # Determine vehicle capacity
            vehicle = getattr(d, 'assigned_vehicle', None)
            if vehicle:
                cap_w = float(vehicle.capacity_weight or 50.0)
                cap_v = float(vehicle.capacity_volume or 0.5)
            else:
                cap_w = 30.0  # Default bike capacity
                cap_v = 0.2

            # Calculate current load of driver's active parcels
            current_weight = 0.0
            current_volume = 0.0
            driver_parcels = getattr(d, 'parcels', getattr(d, 'assigned_parcels', [])) or []
            for p in driver_parcels:
                if getattr(p, 'status', None) not in ['Delivered', 'Cancelled'] and getattr(p, 'id', None) != getattr(parcel, 'id', None):
                    current_weight += float(getattr(p, 'weight', 0.0) or 0.0)
                    p_len = getattr(p, 'length', None)
                    p_wid = getattr(p, 'width', None)
                    p_hgt = getattr(p, 'height', None)
                    if p_len and p_wid and p_hgt:
                        current_volume += float((p_len * p_wid * p_hgt) / 1000000.0)
                    else:
                        current_volume += 0.005

            # Enforce capacity
            if (current_weight + parcel_weight <= cap_w + 1e-6) and (current_volume + parcel_volume <= cap_v + 1e-6):
                capable_drivers.append((d, cap_w - current_weight))

    if not capable_drivers:
        return None, None

    # Find closest capable driver based on live location distance to pickup point
    closest_driver = None
    min_distance = float('inf')

    for driver, rem_cap in capable_drivers:
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

# Distinct Color Palette for Multi-Courier Route Visualizations
COURIER_PALETTE = [
    '#4F46E5',  # Indigo
    '#059669',  # Emerald Green
    '#D97706',  # Amber / Warm Gold
    '#DC2626',  # Crimson Red
    '#7C3AED',  # Deep Violet
    '#0891B2',  # Cyan / Teal
    '#DB2777',  # Pink / Magenta
    '#2563EB',  # Royal Blue
    '#475569',  # Slate Gray
    '#CA8A04'   # Ochre
]

def calculate_location_distance(loc1, loc2):
    """
    Computes road/network shortest path distance between two locations.
    Leverages Dijkstra's algorithm for inter-hub transit and Haversine for local legs.
    """
    lat1 = loc1['lat']
    lng1 = loc1['lng']
    lat2 = loc2['lat']
    lng2 = loc2['lng']
    
    hub1 = loc1.get('hub_name') or get_closest_hub(lat1, lng1)
    hub2 = loc2.get('hub_name') or get_closest_hub(lat2, lng2)
    
    if hub1 and hub2 and hub1 != hub2:
        # Use Dijkstra on network graph between hubs
        path, hub_dist = dijkstra(hub1, hub2)
        if path and hub_dist != float('inf'):
            all_hubs = get_all_hubs_dict()
            h1_coords = all_hubs.get(hub1, {'lat': lat1, 'lng': lng1})
            h2_coords = all_hubs.get(hub2, {'lat': lat2, 'lng': lng2})
            d1 = haversine_distance(lat1, lng1, h1_coords['lat'], h1_coords['lng'])
            d2 = haversine_distance(h2_coords['lat'], h2_coords['lng'], lat2, lng2)
            return d1 + hub_dist + d2
            
    # Same hub or fallback direct road distance approximation (1.25x road factor)
    return haversine_distance(lat1, lng1, lat2, lng2) * 1.25

def solve_tsp(start_location, stops):
    """
    Solves the Traveling Salesperson Problem (TSP) to determine the optimal delivery sequence.
    Utilizes Dijkstra-backed distances between locations.
    Parameters:
      - start_location: dict {'lat': float, 'lng': float, 'name': str (optional)}
      - stops: list of dicts [{'id': ..., 'lat': float, 'lng': float, ...}]
    Returns:
      - ordered_stops: list of stop dicts in optimal delivery sequence with 'stop_number' and 'leg_distance_km'
      - total_distance_km: total route distance in km
      - legs: list of leg dicts with from, to, distance
    """
    if not stops:
        return [], 0.0, []
        
    if len(stops) == 1:
        dist = calculate_location_distance(start_location, stops[0])
        stop_with_num = dict(stops[0])
        stop_with_num['stop_number'] = 1
        stop_with_num['leg_distance_km'] = round(dist, 2)
        legs = [{
            'from_name': start_location.get('name', 'Courier Start'),
            'from_lat': start_location['lat'],
            'from_lng': start_location['lng'],
            'to_name': stops[0].get('receiver_name', 'Stop 1'),
            'to_lat': stops[0]['lat'],
            'to_lng': stops[0]['lng'],
            'distance_km': round(dist, 2)
        }]
        return [stop_with_num], round(dist, 2), legs

    # Precalculate distance matrix using Dijkstra / Road network distances
    n = len(stops)
    all_points = [start_location] + stops
    dist_matrix = [[0.0] * (n + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(i + 1, n + 1):
            d = calculate_location_distance(all_points[i], all_points[j])
            dist_matrix[i][j] = d
            dist_matrix[j][i] = d

    best_order = None
    best_dist = float('inf')

    # For small n (<= 9), evaluate all permutations for exact global optimum
    if n <= 9:
        import itertools
        for perm in itertools.permutations(range(1, n + 1)):
            current_dist = dist_matrix[0][perm[0]]
            for k in range(len(perm) - 1):
                current_dist += dist_matrix[perm[k]][perm[k+1]]
                if current_dist >= best_dist:  # Pruning
                    break
            if current_dist < best_dist:
                best_dist = current_dist
                best_order = list(perm)
    else:
        # Nearest neighbor initialization + 2-opt heuristic for larger n
        unvisited = set(range(1, n + 1))
        curr = 0
        tour = []
        while unvisited:
            next_node = min(unvisited, key=lambda node: dist_matrix[curr][node])
            tour.append(next_node)
            unvisited.remove(next_node)
            curr = next_node
            
        # 2-opt local search optimization
        improved = True
        while improved:
            improved = False
            for i in range(len(tour) - 1):
                for j in range(i + 1, len(tour)):
                    prev_i = 0 if i == 0 else tour[i - 1]
                    next_j = tour[j + 1] if j + 1 < len(tour) else None
                    
                    old_dist = dist_matrix[prev_i][tour[i]]
                    if next_j is not None:
                        old_dist += dist_matrix[tour[j]][next_j]
                        
                    new_dist = dist_matrix[prev_i][tour[j]]
                    if next_j is not None:
                        new_dist += dist_matrix[tour[i]][next_j]
                        
                    if new_dist < old_dist - 1e-6:
                        tour[i:j+1] = tour[i:j+1][::-1]
                        improved = True
                        break
                if improved:
                    break
                    
        best_dist = dist_matrix[0][tour[0]]
        for k in range(len(tour) - 1):
            best_dist += dist_matrix[tour[k]][tour[k+1]]
        best_order = tour

    # Build ordered output
    ordered_stops = []
    legs = []
    prev_idx = 0
    for rank, stop_idx in enumerate(best_order, 1):
        orig_stop = stops[stop_idx - 1]
        leg_dist = dist_matrix[prev_idx][stop_idx]
        stop_dict = dict(orig_stop)
        stop_dict['stop_number'] = rank
        stop_dict['leg_distance_km'] = round(leg_dist, 2)
        ordered_stops.append(stop_dict)
        
        legs.append({
            'from_name': all_points[prev_idx].get('name', f"Stop #{rank-1}" if rank > 1 else 'Courier Origin'),
            'from_lat': all_points[prev_idx]['lat'],
            'from_lng': all_points[prev_idx]['lng'],
            'to_name': orig_stop.get('receiver_name', f"Stop #{rank}"),
            'to_lat': orig_stop['lat'],
            'to_lng': orig_stop['lng'],
            'distance_km': round(leg_dist, 2)
        })
        prev_idx = stop_idx

    return ordered_stops, round(best_dist, 2), legs

def multi_courier_optimization(couriers, deliveries):
    """
    Multi-Courier Delivery Optimization:
    1. Assigns deliveries to multiple couriers based on vehicle capacity (weight & volume).
    2. Strictly enforces capacity constraints (never exceeds courier vehicle capacity).
    3. Identifies unassigned deliveries when total capacity is insufficient.
    4. Applies TSP to compute the optimal delivery order for each courier.
    5. Calculates total load, remaining capacity, ordered route, and distances for each courier.
    """
    if not couriers:
        return {
            'summary': {
                'total_deliveries': len(deliveries),
                'assigned_count': 0,
                'unassigned_count': len(deliveries),
                'total_couriers_used': 0,
                'total_distance_km': 0.0
            },
            'courier_routes': [],
            'unassigned_deliveries': [
                dict(d, reason="No available couriers in service.") for d in deliveries
            ]
        }

    # Normalize courier objects / dicts
    courier_state = []
    for i, c in enumerate(couriers):
        c_id = c.id if hasattr(c, 'id') else c.get('id', i + 1)
        c_name = c.name if hasattr(c, 'name') else c.get('name', f'Courier {i+1}')
        c_phone = c.phone if hasattr(c, 'phone') else c.get('phone', '')
        c_lat = float(c.latitude if hasattr(c, 'latitude') else c.get('lat', 27.7172))
        c_lng = float(c.longitude if hasattr(c, 'longitude') else c.get('lng', 85.3240))
        
        # Vehicle & Capacity
        if hasattr(c, 'effective_capacity_weight'):
            cap_w = float(c.effective_capacity_weight)
            cap_v = float(c.effective_capacity_volume)
            v_type = c.vehicle_type_name
            v_plate = c.assigned_vehicle.license_plate if c.assigned_vehicle else 'N/A'
            v_code = c.assigned_vehicle.vehicle_code if c.assigned_vehicle else 'N/A'
        else:
            cap_w = float(c.get('capacity_weight', 30.0))
            cap_v = float(c.get('capacity_volume', 0.2))
            v_type = c.get('vehicle_type', 'Bike')
            v_plate = c.get('license_plate', 'N/A')
            v_code = c.get('vehicle_code', 'N/A')
            
        color = COURIER_PALETTE[i % len(COURIER_PALETTE)]
        
        courier_state.append({
            'id': c_id,
            'name': c_name,
            'phone': c_phone,
            'lat': c_lat,
            'lng': c_lng,
            'capacity_weight': cap_w,
            'capacity_volume': cap_v,
            'current_weight': 0.0,
            'current_volume': 0.0,
            'vehicle_type': v_type,
            'license_plate': v_plate,
            'vehicle_code': v_code,
            'color': color,
            'assigned_items': []
        })

    # Normalize delivery objects / dicts
    unassigned = []
    normalized_deliveries = []
    for d in deliveries:
        d_id = d.id if hasattr(d, 'id') else d.get('id')
        t_id = d.tracking_id if hasattr(d, 'tracking_id') else d.get('tracking_id', f'PF-{d_id}')
        r_name = d.receiver_name if hasattr(d, 'receiver_name') else d.get('receiver_name', 'Customer')
        addr = d.delivery_address if hasattr(d, 'delivery_address') else d.get('delivery_address', '')
        d_lat = float(d.delivery_latitude if hasattr(d, 'delivery_latitude') else d.get('lat', 27.7000))
        d_lng = float(d.delivery_longitude if hasattr(d, 'delivery_longitude') else d.get('lng', 85.3300))
        weight = float(d.weight if hasattr(d, 'weight') else d.get('weight', 1.0))
        
        if hasattr(d, 'volume_m3'):
            vol = float(d.volume_m3)
        elif hasattr(d, 'length') and hasattr(d, 'width') and hasattr(d, 'height'):
            vol = float((d.length * d.width * d.height) / 1000000.0)
        else:
            vol = float(d.get('volume_m3', 0.005))
            
        normalized_deliveries.append({
            'parcel_id': d_id,
            'tracking_id': t_id,
            'receiver_name': r_name,
            'delivery_address': addr,
            'lat': d_lat,
            'lng': d_lng,
            'weight': weight,
            'volume_m3': vol,
            'raw_parcel': d
        })

    # Sort deliveries (Best-Fit Decreasing by weight and volume)
    normalized_deliveries.sort(key=lambda x: (x['weight'], x['volume_m3']), reverse=True)

    # Capacity-Constrained Greedy Geographic Bin Allocation
    for item in normalized_deliveries:
        best_courier = None
        min_marginal_cost = float('inf')
        
        for c in courier_state:
            # Check capacity constraints (both weight and volume)
            if (c['current_weight'] + item['weight'] <= c['capacity_weight'] + 1e-6) and \
               (c['current_volume'] + item['volume_m3'] <= c['capacity_volume'] + 1e-6):
                
                # Proximity metric: distance from courier origin or nearest assigned stop
                if not c['assigned_items']:
                    cost = calculate_location_distance({'lat': c['lat'], 'lng': c['lng']}, item)
                else:
                    cost = min(calculate_location_distance(stop, item) for stop in c['assigned_items'])
                    
                if cost < min_marginal_cost:
                    min_marginal_cost = cost
                    best_courier = c
                    
        if best_courier is not None:
            best_courier['assigned_items'].append(item)
            best_courier['current_weight'] += item['weight']
            best_courier['current_volume'] += item['volume_m3']
        else:
            unassigned.append({
                'parcel_id': item['parcel_id'],
                'tracking_id': item['tracking_id'],
                'receiver_name': item['receiver_name'],
                'delivery_address': item['delivery_address'],
                'lat': item['lat'],
                'lng': item['lng'],
                'weight': round(item['weight'], 2),
                'volume_m3': round(item['volume_m3'], 4),
                'reason': 'Exceeds available fleet weight or volume capacity'
            })

    # Build optimized TSP routes for each courier
    courier_routes = []
    total_fleet_dist = 0.0

    for c in courier_state:
        if not c['assigned_items']:
            continue
            
        start_loc = {
            'lat': c['lat'],
            'lng': c['lng'],
            'name': f"Courier Start ({c['name']})"
        }
        
        # Run TSP to get optimal order of stops
        ordered_stops, tsp_distance, legs = solve_tsp(start_loc, c['assigned_items'])
        total_fleet_dist += tsp_distance
        
        # Build full polyline road coordinates for map
        full_route_coords = []
        for leg in legs:
            sub_coords = fetch_osrm_route(leg['from_lat'], leg['from_lng'], leg['to_lat'], leg['to_lng'])
            if full_route_coords and sub_coords:
                full_route_coords.extend(sub_coords[1:])
            else:
                full_route_coords.extend(sub_coords)
                
        # Calculate load statistics
        assigned_w = round(c['current_weight'], 2)
        assigned_v = round(c['current_volume'], 4)
        rem_w = round(max(0.0, c['capacity_weight'] - c['current_weight']), 2)
        rem_v = round(max(0.0, c['capacity_volume'] - c['current_volume']), 4)
        util_w = round((assigned_w / c['capacity_weight']) * 100.0, 1) if c['capacity_weight'] > 0 else 0.0
        util_v = round((assigned_v / c['capacity_volume']) * 100.0, 1) if c['capacity_volume'] > 0 else 0.0
        
        # Estimated duration (average urban speed 25 km/h + 5 mins per drop)
        est_duration = round((tsp_distance / 25.0) * 60.0 + (len(ordered_stops) * 5), 1)

        courier_routes.append({
            'courier_id': c['id'],
            'courier_name': c['name'],
            'courier_phone': c['phone'],
            'courier_lat': c['lat'],
            'courier_lng': c['lng'],
            'vehicle_type': c['vehicle_type'],
            'license_plate': c['license_plate'],
            'vehicle_code': c['vehicle_code'],
            'color': c['color'],
            'capacity_weight': c['capacity_weight'],
            'capacity_volume': c['capacity_volume'],
            'assigned_weight': assigned_w,
            'assigned_volume': assigned_v,
            'remaining_weight': rem_w,
            'remaining_volume': rem_v,
            'utilization_weight_pct': util_w,
            'utilization_volume_pct': util_v,
            'total_stops': len(ordered_stops),
            'total_distance_km': tsp_distance,
            'estimated_duration_min': est_duration,
            'ordered_stops': ordered_stops,
            'legs': legs,
            'route_polyline': full_route_coords
        })

    assigned_count = sum(len(c['ordered_stops']) for c in courier_routes)

    return {
        'summary': {
            'total_deliveries': len(deliveries),
            'assigned_count': assigned_count,
            'unassigned_count': len(unassigned),
            'total_couriers_used': len(courier_routes),
            'total_distance_km': round(total_fleet_dist, 2)
        },
        'courier_routes': courier_routes,
        'unassigned_deliveries': unassigned
    }
