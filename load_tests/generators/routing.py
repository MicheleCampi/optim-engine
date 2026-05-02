"""
Random routing (CVRPTW) problem generator for load testing.

Three size classes calibrated for OptimEngine on Railway:
  - small:  ~1-2s solve time, mostly OPTIMAL
  - medium: ~5-10s solve time, mix OPTIMAL/FEASIBLE
  - large:  ~15-25s solve time, mostly FEASIBLE/TIMEOUT (intentional)

Geography: locations randomly placed in a bounding box covering northern
Italy (Parma–Milan corridor + surroundings). Coordinates are realistic
enough that total_distance values are interpretable.

Demand/capacity ratio fixed at ~0.7 — feasible by construction. INFEASIBLE
injection (capacity-saturated scenarios) deferred to a separate generator.
"""
import random
from typing import Literal

SizeClass = Literal["small", "medium", "large"]

# Bounding box: covers Parma, Milan, Bologna, Modena, Brescia, etc.
_LAT_RANGE = (44.5, 45.6)
_LON_RANGE = (9.5, 11.5)

_SIZE_CONFIG = {
    "small":  {"locations": (5, 10),  "vehicles": (1, 2),  "max_time": 5},
    "medium": {"locations": (15, 30), "vehicles": (3, 5),  "max_time": 10},
    "large":  {"locations": (40, 80), "vehicles": (5, 10), "max_time": 20},
}

_DEMAND_FILL_RATIO = 0.70  # total demand / total capacity


def random_routing(size_class: SizeClass = "small") -> dict:
    """
    Build a randomized but feasible CVRPTW problem.

    Returns a dict matching RoutingRequest schema. Always feasible by
    construction (demand_total ≈ 0.7 * capacity_total).
    """
    cfg = _SIZE_CONFIG[size_class]

    num_vehicles = random.randint(*cfg["vehicles"])
    num_locations = random.randint(*cfg["locations"])

    # Vehicles: random capacities in [50, 150]
    vehicle_capacities = [random.randint(50, 150) for _ in range(num_vehicles)]
    total_capacity = sum(vehicle_capacities)
    vehicles = [
        {
            "vehicle_id": f"V{i+1}",
            "capacity": cap,
            "start_location": "depot",
            "end_location": "depot",
        }
        for i, cap in enumerate(vehicle_capacities)
    ]

    # Locations: depot first, then customers
    target_demand = total_capacity * _DEMAND_FILL_RATIO
    avg_demand = max(1, int(target_demand / num_locations))

    locations = [
        {
            "location_id": "depot",
            "latitude": _rand_coord(_LAT_RANGE),
            "longitude": _rand_coord(_LON_RANGE),
            "demand": 0,
        }
    ]
    for i in range(num_locations):
        # Each customer demand uniform in [avg-50%, avg+50%]
        demand = max(1, random.randint(
            max(1, avg_demand // 2),
            max(2, avg_demand + avg_demand // 2),
        ))
        locations.append({
            "location_id": f"L{i+1}",
            "latitude": _rand_coord(_LAT_RANGE),
            "longitude": _rand_coord(_LON_RANGE),
            "demand": demand,
        })

    return {
        "depot_id": "depot",
        "vehicles": vehicles,
        "locations": locations,
        "max_solve_time_seconds": cfg["max_time"],
    }


def _rand_coord(range_tuple: tuple) -> float:
    """4 decimal places — realistic GPS precision (~11m)."""
    return round(random.uniform(*range_tuple), 4)
