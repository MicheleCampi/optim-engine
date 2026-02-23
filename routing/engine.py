"""
OptimEngine — CVRPTW Routing Solver
Capacitated Vehicle Routing Problem with Time Windows via Google OR-Tools.
"""

import math
import time
from typing import Optional

from ortools.constraint_solver import routing_enums_pb2, pywrapcp

from .models import (
    RoutingRequest, RoutingResponse, RoutingStatus, RoutingObjective,
    VehicleRoute, RouteStop, RoutingMetrics,
)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return int(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _build_distance_matrix(request: RoutingRequest) -> tuple[list[list[int]], list[list[int]]]:
    loc_ids = [loc.location_id for loc in request.locations]
    loc_index = {lid: i for i, lid in enumerate(loc_ids)}
    n = len(loc_ids)

    dist = [[0] * n for _ in range(n)]
    travel_time = [[0] * n for _ in range(n)]

    if request.distance_matrix:
        custom = {}
        for entry in request.distance_matrix:
            if entry.from_id in loc_index and entry.to_id in loc_index:
                fi, ti = loc_index[entry.from_id], loc_index[entry.to_id]
                custom[(fi, ti)] = (entry.distance, entry.travel_time)

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if (i, j) in custom:
                    d, t = custom[(i, j)]
                    dist[i][j] = d
                    travel_time[i][j] = t if t is not None else d
                else:
                    li, lj = request.locations[i], request.locations[j]
                    if all(v is not None for v in [li.latitude, li.longitude, lj.latitude, lj.longitude]):
                        d = _haversine(li.latitude, li.longitude, lj.latitude, lj.longitude)
                        dist[i][j] = d
                        travel_time[i][j] = d
                    else:
                        dist[i][j] = 0
                        travel_time[i][j] = 0
    else:
        has_coords = all(
            loc.latitude is not None and loc.longitude is not None
            for loc in request.locations
        )
        if has_coords:
            for i in range(n):
                for j in range(n):
                    if i != j:
                        li, lj = request.locations[i], request.locations[j]
                        d = _haversine(li.latitude, li.longitude, lj.latitude, lj.longitude)
                        dist[i][j] = d
                        travel_time[i][j] = d

    return dist, travel_time


def solve_routing(request: RoutingRequest) -> RoutingResponse:
    t0 = time.time()

    try:
        loc_ids = [loc.location_id for loc in request.locations]
        loc_index = {lid: i for i, lid in enumerate(loc_ids)}

        if request.depot_id not in loc_index:
            return RoutingResponse(
                status=RoutingStatus.ERROR,
                message=f"Depot '{request.depot_id}' not found in locations list."
            )

        depot_idx = loc_index[request.depot_id]
        num_vehicles = len(request.vehicles)
        num_locations = len(request.locations)

        dist_matrix, time_matrix = _build_distance_matrix(request)

        manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot_idx)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return dist_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel = time_matrix[from_node][to_node]
            service = request.locations[from_node].service_time
            return travel + service

        time_callback_index = routing.RegisterTransitCallback(time_callback)

        max_time = 0
        for loc in request.locations:
            if loc.time_window_end is not None:
                max_time = max(max_time, loc.time_window_end)
        if max_time == 0:
            max_time = sum(
                max(row) for row in time_matrix
            ) + sum(loc.service_time for loc in request.locations)
        max_time = max(max_time, 100000)

        routing.AddDimension(
            time_callback_index,
            max_time,
            max_time,
            False,
            "Time"
        )
        time_dimension = routing.GetDimensionOrDie("Time")

        for i, loc in enumerate(request.locations):
            index = manager.NodeToIndex(i)
            tw_start = loc.time_window_start
            tw_end = loc.time_window_end if loc.time_window_end is not None else max_time
            time_dimension.CumulVar(index).SetRange(tw_start, tw_end)

        for v in range(num_vehicles):
            start_index = routing.Start(v)
            end_index = routing.End(v)
            depot_loc = request.locations[depot_idx]
            tw_start = depot_loc.time_window_start
            tw_end = depot_loc.time_window_end if depot_loc.time_window_end is not None else max_time
            time_dimension.CumulVar(start_index).SetRange(tw_start, tw_end)
            time_dimension.CumulVar(end_index).SetRange(tw_start, tw_end)

        for v in range(num_vehicles):
            routing.AddVariableMinimizedByFinalizer(
                time_dimension.CumulVar(routing.Start(v))
            )
            routing.AddVariableMinimizedByFinalizer(
                time_dimension.CumulVar(routing.End(v))
            )

        for v_idx, veh in enumerate(request.vehicles):
            if veh.max_travel_time is not None:
                end_index = routing.End(v_idx)
                time_dimension.CumulVar(end_index).SetMax(veh.max_travel_time)

        demands = [loc.demand for loc in request.locations]

        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return demands[from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        vehicle_capacities = [veh.capacity for veh in request.vehicles]

        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,
            vehicle_capacities,
            True,
            "Capacity"
        )

        has_max_dist = any(veh.max_travel_distance is not None for veh in request.vehicles)
        if has_max_dist:
            routing.AddDimension(
                transit_callback_index,
                0,
                max(veh.max_travel_distance or 999999999 for veh in request.vehicles),
                True,
                "Distance"
            )
            dist_dimension = routing.GetDimensionOrDie("Distance")
            for v_idx, veh in enumerate(request.vehicles):
                if veh.max_travel_distance is not None:
                    end_index = routing.End(v_idx)
                    dist_dimension.CumulVar(end_index).SetMax(veh.max_travel_distance)

        for v_idx, veh in enumerate(request.vehicles):
            if veh.fixed_cost > 0:
                routing.SetFixedCostOfVehicle(veh.fixed_cost, v_idx)

        if request.allow_drop_visits:
            for i in range(num_locations):
                if i == depot_idx:
                    continue
                index = manager.NodeToIndex(i)
                routing.AddDisjunction([index], request.drop_penalty)

        if request.objective == RoutingObjective.MINIMIZE_VEHICLES:
            for v_idx in range(num_vehicles):
                routing.SetFixedCostOfVehicle(100000, v_idx)
        elif request.objective == RoutingObjective.BALANCE_ROUTES:
            if not has_max_dist:
                routing.AddDimension(
                    transit_callback_index, 0, 999999999, True, "Distance"
                )
            dist_dim = routing.GetDimensionOrDie("Distance")
            dist_dim.SetGlobalSpanCostCoefficient(100)

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_params.time_limit.FromSeconds(request.max_solve_time_seconds)
        search_params.log_search = False

        solution = routing.SolveWithParameters(search_params)
        solve_time = time.time() - t0

        if not solution:
            if routing.status() == 3:
                return RoutingResponse(
                    status=RoutingStatus.TIMEOUT,
                    message=f"Solver timed out after {request.max_solve_time_seconds}s. Try increasing time limit, adding vehicles, or enabling allow_drop_visits."
                )
            return RoutingResponse(
                status=RoutingStatus.NO_SOLUTION,
                message="No feasible solution found. Check: vehicle capacities vs demands, time windows compatibility, and number of vehicles. Try enabling allow_drop_visits=True."
            )

        routes = []
        all_served_locations = set()
        total_distance = 0
        total_time_all = 0
        total_demand = 0

        for v_idx in range(num_vehicles):
            veh = request.vehicles[v_idx]
            route_stops = []
            route_distance = 0
            route_load = 0
            index = routing.Start(v_idx)
            previous_index = index

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                loc = request.locations[node]
                time_var = time_dimension.CumulVar(index)
                arrival = solution.Value(time_var)

                cap_dim = routing.GetDimensionOrDie("Capacity")
                load_after = solution.Value(cap_dim.CumulVar(index))

                if node != depot_idx:
                    all_served_locations.add(loc.location_id)
                    wait = max(0, loc.time_window_start - arrival) if arrival < loc.time_window_start else 0
                    route_stops.append(RouteStop(
                        location_id=loc.location_id,
                        name=loc.name,
                        arrival_time=arrival,
                        departure_time=arrival + wait + loc.service_time,
                        load_after=load_after,
                        demand_served=loc.demand,
                        wait_time=wait,
                    ))
                    route_load += loc.demand

                previous_index = index
                index = solution.Value(routing.NextVar(index))

                from_node = manager.IndexToNode(previous_index)
                to_node = manager.IndexToNode(index)
                route_distance += dist_matrix[from_node][to_node]

            end_time_var = time_dimension.CumulVar(index)
            route_time = solution.Value(end_time_var)

            is_used = len(route_stops) > 0
            route = VehicleRoute(
                vehicle_id=veh.vehicle_id,
                name=veh.name,
                stops=route_stops,
                total_distance=route_distance,
                total_time=route_time,
                total_load=route_load,
                num_stops=len(route_stops),
                is_used=is_used,
            )
            routes.append(route)

            if is_used:
                total_distance += route_distance
                total_time_all += route_time
                total_demand += route_load

        non_depot_locs = [loc for loc in request.locations if loc.location_id != request.depot_id]
        dropped = [loc.location_id for loc in non_depot_locs if loc.location_id not in all_served_locations]

        used_routes = [r for r in routes if r.is_used]
        num_used = len(used_routes)
        avg_dist = total_distance / num_used if num_used > 0 else 0
        avg_load_pct = (
            sum(r.total_load / request.vehicles[i].capacity * 100
                for i, r in enumerate(routes) if r.is_used) / num_used
        ) if num_used > 0 else 0
        max_dist = max((r.total_distance for r in used_routes), default=0)
        max_rt = max((r.total_time for r in used_routes), default=0)

        metrics = RoutingMetrics(
            total_distance=total_distance,
            total_time=total_time_all,
            total_demand_served=total_demand,
            vehicles_used=num_used,
            vehicles_available=num_vehicles,
            locations_served=len(all_served_locations),
            locations_dropped=len(dropped),
            dropped_location_ids=dropped,
            avg_route_distance=round(avg_dist, 1),
            avg_route_load_pct=round(avg_load_pct, 1),
            max_route_distance=max_dist,
            max_route_time=max_rt,
            solve_time_seconds=round(solve_time, 3),
        )

        status = RoutingStatus.OPTIMAL if len(dropped) == 0 else RoutingStatus.FEASIBLE
        msg_parts = [
            f"{'Optimal' if status == RoutingStatus.OPTIMAL else 'Feasible'} solution found in {solve_time:.2f}s.",
            f"{num_used}/{num_vehicles} vehicles used.",
            f"{len(all_served_locations)} locations served.",
            f"Total distance: {total_distance}.",
        ]
        if dropped:
            msg_parts.append(f"{len(dropped)} locations dropped.")

        return RoutingResponse(
            status=status,
            message=" ".join(msg_parts),
            routes=routes,
            metrics=metrics,
            dropped_locations=dropped,
        )

    except Exception as e:
        return RoutingResponse(
            status=RoutingStatus.ERROR,
            message=f"Routing solver error: {str(e)}"
        )
