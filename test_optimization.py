"""
Test Suite for Multi-Courier Delivery Optimization & TSP Routing in ParcelFleet.
Tests:
1. Capacity Enforcement (Weight & Volume)
2. Multi-Courier Fair & Feasible Allocation
3. TSP Route Optimization (Minimizing Total Distance)
4. Dijkstra Shortest Path Integration with TSP Distance Matrix
5. Insufficient Capacity Handling (Unassigned Deliveries)
"""

import unittest
from algorithms import (
    dijkstra,
    haversine_distance,
    calculate_location_distance,
    solve_tsp,
    multi_courier_optimization,
    HUBS,
    GRAPH
)

class TestMultiCourierOptimization(unittest.TestCase):

    def setUp(self):
        # Sample Couriers with defined capacities
        self.couriers = [
            {
                'id': 1,
                'name': 'Ramesh Thapa',
                'phone': '9841111111',
                'lat': 27.7172,
                'lng': 85.3240,
                'capacity_weight': 25.0,   # 25 kg
                'capacity_volume': 0.15,   # 0.15 m3
                'vehicle_type': 'Bike',
                'license_plate': 'BA 2 PA 1234'
            },
            {
                'id': 2,
                'name': 'Suresh Shrestha',
                'phone': '9842222222',
                'lat': 27.6915,
                'lng': 85.3331,
                'capacity_weight': 30.0,   # 30 kg
                'capacity_volume': 0.20,   # 0.20 m3
                'vehicle_type': 'Bike',
                'license_plate': 'BA 3 PA 5678'
            }
        ]

        # Sample Deliveries within Kathmandu Valley
        self.deliveries = [
            {
                'id': 101,
                'tracking_id': 'PF-101',
                'receiver_name': 'Anita Adhikari',
                'delivery_address': 'Thamel, Kathmandu',
                'lat': 27.7154,
                'lng': 85.3123,
                'weight': 5.0,
                'volume_m3': 0.02
            },
            {
                'id': 102,
                'tracking_id': 'PF-102',
                'receiver_name': 'Bikash KC',
                'delivery_address': 'New Baneshwor, Kathmandu',
                'lat': 27.6915,
                'lng': 85.3331,
                'weight': 8.0,
                'volume_m3': 0.04
            },
            {
                'id': 103,
                'tracking_id': 'PF-103',
                'receiver_name': 'Chandra Gurung',
                'delivery_address': 'Koteshwor, Kathmandu',
                'lat': 27.6775,
                'lng': 85.3486,
                'weight': 7.0,
                'volume_m3': 0.03
            },
            {
                'id': 104,
                'tracking_id': 'PF-104',
                'receiver_name': 'Deepa Silwal',
                'delivery_address': 'Chabahil, Kathmandu',
                'lat': 27.7172,
                'lng': 85.3444,
                'weight': 6.0,
                'volume_m3': 0.03
            }
        ]

    # --- 1. CAPACITY CONSTRAINTS TEST ---
    def test_capacity_enforcement(self):
        """Test that no courier is assigned weight or volume exceeding vehicle limits."""
        result = multi_courier_optimization(self.couriers, self.deliveries)
        
        for route in result['courier_routes']:
            # Total weight must never exceed capacity
            self.assertLessEqual(
                route['assigned_weight'],
                route['capacity_weight'] + 1e-6,
                f"Courier {route['courier_name']} overloaded on weight!"
            )
            # Total volume must never exceed capacity
            self.assertLessEqual(
                route['assigned_volume'],
                route['capacity_volume'] + 1e-6,
                f"Courier {route['courier_name']} overloaded on volume!"
            )
            # Remaining capacity calculations must be accurate
            self.assertEqual(
                round(route['remaining_weight'], 2),
                round(route['capacity_weight'] - route['assigned_weight'], 2)
            )
            self.assertEqual(
                round(route['remaining_volume'], 4),
                round(route['capacity_volume'] - route['assigned_volume'], 4)
            )

    # --- 2. MULTI-COURIER ASSIGNMENT TEST ---
    def test_multi_courier_assignment(self):
        """Test that deliveries are distributed across multiple available couriers."""
        result = multi_courier_optimization(self.couriers, self.deliveries)
        
        self.assertEqual(result['summary']['total_deliveries'], 4)
        self.assertEqual(result['summary']['assigned_count'], 4)
        self.assertEqual(result['summary']['unassigned_count'], 0)
        # Should utilize both couriers
        self.assertGreaterEqual(result['summary']['total_couriers_used'], 1)
        
        assigned_parcels = []
        for r in result['courier_routes']:
            for s in r['ordered_stops']:
                assigned_parcels.append(s['parcel_id'])
                
        # All 4 unique deliveries must be present
        self.assertEqual(len(assigned_parcels), 4)
        self.assertEqual(set(assigned_parcels), {101, 102, 103, 104})

    # --- 3. TSP ROUTE ORDERING OPTIMIZATION TEST ---
    def test_tsp_route_optimization(self):
        """Test that TSP finds the shortest total distance for a sequence of stops."""
        start_loc = {'lat': 27.7172, 'lng': 85.3240, 'name': 'Center Point'}
        
        # Stops in collinear line to easily check optimal order
        collinear_stops = [
            {'id': 1, 'receiver_name': 'Stop A (Far East)', 'lat': 27.7172, 'lng': 85.3800},
            {'id': 2, 'receiver_name': 'Stop B (Near East)', 'lat': 27.7172, 'lng': 85.3400},
            {'id': 3, 'receiver_name': 'Stop C (Mid East)', 'lat': 27.7172, 'lng': 85.3600},
        ]
        
        ordered_stops, total_dist, legs = solve_tsp(start_loc, collinear_stops)
        
        # Expected optimal order from center (85.3240) going East: Stop B (85.3400) -> Stop C (85.3600) -> Stop A (85.3800)
        ordered_ids = [s['id'] for s in ordered_stops]
        self.assertEqual(ordered_ids, [2, 3, 1], "TSP did not find the linear optimal order!")
        
        # Verify total distance is strictly less than an inefficient zigzag order (e.g., 1 -> 2 -> 3)
        zigzag_dist = (
            calculate_location_distance(start_loc, collinear_stops[0]) +
            calculate_location_distance(collinear_stops[0], collinear_stops[1]) +
            calculate_location_distance(collinear_stops[1], collinear_stops[2])
        )
        self.assertLess(total_dist, zigzag_dist, "TSP total distance was not minimized!")

    # --- 4. DIJKSTRA INTEGRATION TEST ---
    def test_dijkstra_shortest_path_integration(self):
        """Test that Dijkstra is utilized for graph-based shortest path routing."""
        # Query known hub path: Kalanki to Bhaktapur
        path, dist = dijkstra('Kalanki', 'Bhaktapur')
        self.assertIsNotNone(path)
        self.assertEqual(path[0], 'Kalanki')
        self.assertEqual(path[-1], 'Bhaktapur')
        self.assertGreater(dist, 0.0)
        
        # Test location distance calculation uses Dijkstra for different hubs
        loc_kalanki = {'lat': 27.6946, 'lng': 85.2813, 'hub_name': 'Kalanki'}
        loc_bhaktapur = {'lat': 27.6722, 'lng': 85.4278, 'hub_name': 'Bhaktapur'}
        computed_dist = calculate_location_distance(loc_kalanki, loc_bhaktapur)
        self.assertAlmostEqual(computed_dist, dist, delta=0.5)

    # --- 5. INSUFFICIENT CAPACITY TEST ---
    def test_insufficient_capacity_handling(self):
        """Test that unassigned deliveries are identified when fleet capacity is exceeded."""
        # Single courier with limited capacity (10 kg, 0.05 m3)
        tiny_courier = [
            {
                'id': 99,
                'name': 'Small Bike',
                'lat': 27.7172,
                'lng': 85.3240,
                'capacity_weight': 10.0,
                'capacity_volume': 0.05,
                'vehicle_type': 'Bike'
            }
        ]
        
        # Total weight = 5 + 8 + 7 = 20 kg (> 10 kg capacity)
        oversized_deliveries = [
            {'id': 201, 'tracking_id': 'PF-201', 'receiver_name': 'User 1', 'delivery_address': 'A', 'lat': 27.7154, 'lng': 85.3123, 'weight': 5.0, 'volume_m3': 0.02},
            {'id': 202, 'tracking_id': 'PF-202', 'receiver_name': 'User 2', 'delivery_address': 'B', 'lat': 27.6915, 'lng': 85.3331, 'weight': 8.0, 'volume_m3': 0.03},
            {'id': 203, 'tracking_id': 'PF-203', 'receiver_name': 'User 3', 'delivery_address': 'C', 'lat': 27.6775, 'lng': 85.3486, 'weight': 7.0, 'volume_m3': 0.03}
        ]
        
        result = multi_courier_optimization(tiny_courier, oversized_deliveries)
        
        # Must report unassigned deliveries accurately
        self.assertGreater(result['summary']['unassigned_count'], 0)
        self.assertGreater(len(result['unassigned_deliveries']), 0)
        
        # Verify that assigned weight did NOT exceed 10.0 kg
        for r in result['courier_routes']:
            self.assertLessEqual(r['assigned_weight'], 10.0)
            
        # Verify unassigned reason is populated
        for un in result['unassigned_deliveries']:
            self.assertIn('Exceeds', un['reason'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
