"""Tests for OptimEngine CVRPTW Routing Solver."""

import pytest
from routing.models import (
    RoutingRequest, Location, Vehicle, DistanceEntry,
    RoutingObjective, RoutingStatus,
)
from routing.engine import solve_routing


def make_simple_request(
    num_customers=3, num_vehicles=1, vehicle_capacity=100,
    use_coords=False, **kwargs,
) -> RoutingRequest:
    locations = [
        Location(location_id="depot", name="Depot", demand=0,
                 latitude=0.0 if use_coords else None,
                 longitude=0.0 if use_coords else None),
    ]
    for i in range(num_customers):
        locations.append(Location(
            location_id=f"cust_{i}", name=f"Customer {i}", demand=10,
            latitude=(i + 1) * 0.01 if use_coords else None,
            longitude=(i + 1) * 0.01 if use_coords else None,
        ))
    vehicles = [
        Vehicle(vehicle_id=f"v_{i}", name=f"Vehicle {i}", capacity=vehicle_capacity)
        for i in range(num_vehicles)
    ]
    n = len(locations)
    distances = []
    for i in range(n):
        for j in range(n):
            if i != j:
                d = abs(i - j) * 100
                distances.append(DistanceEntry(
                    from_id=locations[i].location_id,
                    to_id=locations[j].location_id,
                    distance=d, travel_time=d,
                ))
    return RoutingRequest(
        depot_id="depot", locations=locations, vehicles=vehicles,
        distance_matrix=distances, max_solve_time_seconds=10, **kwargs,
    )


class TestBasicRouting:
    def test_single_vehicle_3_customers(self):
        resp = solve_routing(make_simple_request(3, 1, 100))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.vehicles_used == 1
        assert resp.metrics.locations_served == 3

    def test_two_vehicles_6_customers(self):
        resp = solve_routing(make_simple_request(6, 2, 50))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.locations_served == 6

    def test_route_stops_have_times(self):
        resp = solve_routing(make_simple_request(3, 1, 100))
        for route in resp.routes:
            for stop in route.stops:
                assert stop.arrival_time >= 0
                assert stop.departure_time >= stop.arrival_time


class TestCapacity:
    def test_capacity_forces_multiple_vehicles(self):
        resp = solve_routing(make_simple_request(5, 3, 30))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.vehicles_used >= 2

    def test_capacity_not_exceeded(self):
        req = make_simple_request(4, 2, 25)
        resp = solve_routing(req)
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        for i, route in enumerate(resp.routes):
            if route.is_used:
                assert route.total_load <= req.vehicles[i].capacity


class TestTimeWindows:
    def test_time_windows_respected(self):
        locations = [
            Location(location_id="depot", demand=0, time_window_start=0, time_window_end=10000),
            Location(location_id="c1", demand=5, time_window_start=100, time_window_end=500, service_time=10),
            Location(location_id="c2", demand=5, time_window_start=200, time_window_end=600, service_time=10),
            Location(location_id="c3", demand=5, time_window_start=300, time_window_end=700, service_time=10),
        ]
        distances = []
        for li in locations:
            for lj in locations:
                if li.location_id != lj.location_id:
                    distances.append(DistanceEntry(
                        from_id=li.location_id, to_id=lj.location_id, distance=50, travel_time=50,
                    ))
        req = RoutingRequest(
            depot_id="depot", locations=locations,
            vehicles=[Vehicle(vehicle_id="v1", capacity=100)],
            distance_matrix=distances, max_solve_time_seconds=10,
        )
        resp = solve_routing(req)
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.locations_served == 3


class TestDropVisits:
    def test_drop_visits_enabled(self):
        resp = solve_routing(make_simple_request(5, 1, 20, allow_drop_visits=True, drop_penalty=10000))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)

    def test_high_penalty_prefers_serving(self):
        resp = solve_routing(make_simple_request(3, 2, 100, allow_drop_visits=True, drop_penalty=999999))
        assert resp.metrics.locations_served == 3


class TestObjectives:
    def test_minimize_distance(self):
        resp = solve_routing(make_simple_request(4, 2, 100, objective=RoutingObjective.MINIMIZE_TOTAL_DISTANCE))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.total_distance > 0

    def test_minimize_vehicles(self):
        resp = solve_routing(make_simple_request(3, 3, 100, objective=RoutingObjective.MINIMIZE_VEHICLES))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.vehicles_used <= 2

    def test_balance_routes(self):
        resp = solve_routing(make_simple_request(6, 3, 100, objective=RoutingObjective.BALANCE_ROUTES))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)


class TestEdgeCases:
    def test_single_customer(self):
        resp = solve_routing(make_simple_request(1, 1, 100))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.locations_served == 1

    def test_invalid_depot(self):
        req = make_simple_request(3, 1, 100)
        req.depot_id = "nonexistent"
        resp = solve_routing(req)
        assert resp.status == RoutingStatus.ERROR

    def test_many_vehicles_few_customers(self):
        resp = solve_routing(make_simple_request(2, 5, 100))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        unused = [r for r in resp.routes if not r.is_used]
        assert len(unused) >= 3

    def test_metrics_consistency(self):
        resp = solve_routing(make_simple_request(4, 2, 30))
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        m = resp.metrics
        assert m.locations_served + m.locations_dropped == 4
        assert m.solve_time_seconds > 0


class TestInputValidation:
    def test_duplicate_location_ids_rejected(self):
        with pytest.raises(Exception):
            RoutingRequest(
                depot_id="depot",
                locations=[Location(location_id="depot", demand=0), Location(location_id="depot", demand=5)],
                vehicles=[Vehicle(vehicle_id="v1", capacity=10)],
            )

    def test_duplicate_vehicle_ids_rejected(self):
        with pytest.raises(Exception):
            RoutingRequest(
                depot_id="depot",
                locations=[Location(location_id="depot", demand=0), Location(location_id="c1", demand=5)],
                vehicles=[Vehicle(vehicle_id="v1", capacity=10), Vehicle(vehicle_id="v1", capacity=20)],
            )


class TestRealisticScenario:
    def test_food_delivery(self):
        import random
        random.seed(42)
        locations = [
            Location(location_id="warehouse", name="Central Warehouse", demand=0, time_window_start=0, time_window_end=50000),
            Location(location_id="r1", name="Pizza Place", demand=15, service_time=5, time_window_start=0, time_window_end=3000),
            Location(location_id="r2", name="Sushi Bar", demand=10, service_time=5, time_window_start=500, time_window_end=4000),
            Location(location_id="r3", name="Burger Joint", demand=20, service_time=8, time_window_start=0, time_window_end=5000),
            Location(location_id="r4", name="Thai Kitchen", demand=12, service_time=5, time_window_start=1000, time_window_end=6000),
            Location(location_id="r5", name="Taco Truck", demand=8, service_time=3, time_window_start=0, time_window_end=4000),
            Location(location_id="r6", name="Chinese Wok", demand=18, service_time=6, time_window_start=500, time_window_end=5000),
            Location(location_id="r7", name="Indian Curry", demand=14, service_time=5, time_window_start=0, time_window_end=3500),
            Location(location_id="r8", name="Greek Gyros", demand=9, service_time=4, time_window_start=200, time_window_end=4500),
        ]
        distances = []
        for li in locations:
            for lj in locations:
                if li.location_id != lj.location_id:
                    distances.append(DistanceEntry(
                        from_id=li.location_id, to_id=lj.location_id,
                        distance=random.randint(200, 1500), travel_time=random.randint(200, 1500),
                    ))
        req = RoutingRequest(
            depot_id="warehouse", locations=locations,
            vehicles=[
                Vehicle(vehicle_id="d1", name="Driver A", capacity=50),
                Vehicle(vehicle_id="d2", name="Driver B", capacity=50),
                Vehicle(vehicle_id="d3", name="Driver C", capacity=40),
            ],
            distance_matrix=distances,
            objective=RoutingObjective.MINIMIZE_TOTAL_DISTANCE,
            max_solve_time_seconds=15,
        )
        resp = solve_routing(req)
        assert resp.status in (RoutingStatus.OPTIMAL, RoutingStatus.FEASIBLE)
        assert resp.metrics.locations_served == 8
        assert resp.metrics.vehicles_used >= 2
        for i, route in enumerate(resp.routes):
            if route.is_used:
                assert route.total_load <= req.vehicles[i].capacity
