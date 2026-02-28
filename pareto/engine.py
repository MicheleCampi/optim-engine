"""
OptimEngine — Multi-objective Pareto Optimization Engine

Approach: Weighted-sum scalarization.
1. For N objectives and K requested points, generate weight vectors
2. Always include extreme points (100% weight on each objective)
3. Fill remaining with evenly distributed weight combinations
4. Solve each weight combination as a single-objective problem
5. Filter dominated solutions to produce the Pareto frontier
6. Analyze trade-offs between objective pairs
"""

import copy
import itertools
import math
import time
from typing import Any

from .models import (
    ParetoRequest, ParetoResponse, ParetoSolverType,
    ObjectiveSpec, ParetoPoint, TradeOff, ParetoMetrics,
)

from solver.models import ScheduleRequest
from solver.engine import solve_schedule
from routing.models import RoutingRequest
from routing.engine import solve_routing
from packing.models import PackingRequest
from packing.engine import solve_packing


# ─── Objective extraction ───

SCHEDULING_OBJECTIVES = {
    "minimize_makespan": lambda r: r.metrics.makespan if r.metrics else 0,
    "minimize_total_tardiness": lambda r: r.metrics.total_tardiness if r.metrics and hasattr(r.metrics, "total_tardiness") else 0,
    "minimize_total_completion_time": lambda r: r.metrics.total_completion_time if r.metrics and hasattr(r.metrics, "total_completion_time") else 0,
    "maximize_machine_utilization": lambda r: -(r.metrics.avg_machine_utilization if r.metrics and hasattr(r.metrics, "avg_machine_utilization") else 0),
}

ROUTING_OBJECTIVES = {
    "minimize_total_distance": lambda r: r.metrics.total_distance if r.metrics else 0,
    "minimize_num_vehicles": lambda r: r.metrics.vehicles_used if r.metrics else 0,
    "minimize_longest_route": lambda r: r.metrics.longest_route_distance if r.metrics and hasattr(r.metrics, "longest_route_distance") else 0,
    "minimize_total_time": lambda r: r.metrics.total_time if r.metrics and hasattr(r.metrics, "total_time") else 0,
}

PACKING_OBJECTIVES = {
    "minimize_bins": lambda r: r.metrics.bins_used if r.metrics else 0,
    "maximize_items": lambda r: -(r.metrics.items_packed if r.metrics else 0),
    "maximize_value": lambda r: -(r.metrics.total_value if r.metrics and hasattr(r.metrics, "total_value") else 0),
    "minimize_waste": lambda r: r.metrics.total_waste_pct if r.metrics and hasattr(r.metrics, "total_waste_pct") else 0,
}


def _get_objective_map(solver_type: ParetoSolverType):
    if solver_type == ParetoSolverType.SCHEDULING:
        return SCHEDULING_OBJECTIVES
    elif solver_type == ParetoSolverType.ROUTING:
        return ROUTING_OBJECTIVES
    elif solver_type == ParetoSolverType.PACKING:
        return PACKING_OBJECTIVES
    return {}


def _extract_objectives(solver_type, objectives, response):
    """Extract all objective values from a solver response."""
    obj_map = _get_objective_map(solver_type)
    result = {}
    for obj in objectives:
        extractor = obj_map.get(obj.name)
        if extractor:
            val = extractor(response)
            # For maximization objectives stored as negative, flip sign for display
            if obj.name.startswith("maximize_"):
                result[obj.name] = -val
            else:
                result[obj.name] = float(val)
        else:
            result[obj.name] = 0.0
    return result


# ─── Weight generation ───

def _generate_weight_vectors(objectives: list[ObjectiveSpec], num_points: int) -> list[dict[str, float]]:
    """
    Generate weight vectors for weighted-sum scalarization.
    Always includes extreme points and balanced point.
    """
    n = len(objectives)
    vectors = []

    # Extreme points: 100% weight on each objective
    for i, obj in enumerate(objectives):
        w = {o.name: 0.0 for o in objectives}
        w[obj.name] = 1.0
        vectors.append(w)

    # Balanced point: equal weights (adjusted by user-specified weights)
    total_w = sum(o.weight for o in objectives)
    balanced = {o.name: o.weight / total_w for o in objectives}
    vectors.append(balanced)

    # Fill remaining with systematic weight combinations
    remaining = num_points - len(vectors)
    if remaining > 0 and n == 2:
        # For 2 objectives, evenly spaced weights
        for i in range(1, remaining + 1):
            alpha = i / (remaining + 1)
            w = {objectives[0].name: alpha, objectives[1].name: 1 - alpha}
            vectors.append(w)

    elif remaining > 0 and n >= 3:
        # For 3+ objectives, simplex grid
        steps = max(2, int(remaining ** (1 / (n - 1))))
        grid = []
        for combo in itertools.product(range(steps + 1), repeat=n):
            if sum(combo) == steps:
                w = {objectives[i].name: combo[i] / steps for i in range(n)}
                grid.append(w)

        # Remove duplicates of extreme/balanced
        for g in grid:
            is_dup = False
            for v in vectors:
                if all(abs(g[k] - v[k]) < 0.01 for k in g):
                    is_dup = True
                    break
            if not is_dup:
                vectors.append(g)
            if len(vectors) >= num_points:
                break

    return vectors[:num_points]


# ─── Solver dispatch ───

def _solve_with_objective(solver_type, request_data, objective_name, max_time):
    """Solve with a specific primary objective."""
    data = copy.deepcopy(request_data)
    data["objective"] = objective_name
    data["max_solve_time_seconds"] = max_time

    if solver_type == ParetoSolverType.SCHEDULING:
        req = ScheduleRequest(**data)
        resp = solve_schedule(req)
        return resp, resp.status.value

    elif solver_type == ParetoSolverType.ROUTING:
        req = RoutingRequest(**data)
        resp = solve_routing(req)
        return resp, resp.status.value

    elif solver_type == ParetoSolverType.PACKING:
        req = PackingRequest(**data)
        resp = solve_packing(req)
        return resp, resp.status.value

    raise ValueError(f"Unknown solver: {solver_type}")


# ─── Dominance filtering ───

def _is_dominated(point_a: dict[str, float], point_b: dict[str, float], minimize_keys: set) -> bool:
    """Check if point_a is dominated by point_b (b is at least as good in all, strictly better in one)."""
    at_least_as_good = True
    strictly_better = False

    for key in point_a:
        a_val = point_a[key]
        b_val = point_b[key]

        if key in minimize_keys:
            # Lower is better
            if b_val > a_val:
                at_least_as_good = False
            if b_val < a_val:
                strictly_better = True
        else:
            # Higher is better
            if b_val < a_val:
                at_least_as_good = False
            if b_val > a_val:
                strictly_better = True

    return at_least_as_good and strictly_better


def _filter_pareto_frontier(points: list[ParetoPoint], objectives: list[ObjectiveSpec]) -> list[ParetoPoint]:
    """Remove dominated points."""
    minimize_keys = {o.name for o in objectives if o.name.startswith("minimize_")}
    frontier = []

    for i, p in enumerate(points):
        if not p.feasible:
            continue
        dominated = False
        for j, q in enumerate(points):
            if i == j or not q.feasible:
                continue
            if _is_dominated(p.objectives, q.objectives, minimize_keys):
                dominated = True
                break
        if not dominated:
            frontier.append(p)

    return frontier


# ─── Trade-off analysis ───

def _analyze_trade_offs(frontier: list[ParetoPoint], objectives: list[ObjectiveSpec]) -> list[TradeOff]:
    """Compute pairwise trade-off analysis."""
    trade_offs = []
    obj_names = [o.name for o in objectives]

    for i in range(len(obj_names)):
        for j in range(i + 1, len(obj_names)):
            a_name = obj_names[i]
            b_name = obj_names[j]

            a_vals = [p.objectives.get(a_name, 0) for p in frontier]
            b_vals = [p.objectives.get(b_name, 0) for p in frontier]

            if len(a_vals) < 2:
                continue

            # Correlation
            n = len(a_vals)
            mean_a = sum(a_vals) / n
            mean_b = sum(b_vals) / n
            var_a = sum((x - mean_a) ** 2 for x in a_vals) / n
            var_b = sum((x - mean_b) ** 2 for x in b_vals) / n
            cov = sum((a_vals[k] - mean_a) * (b_vals[k] - mean_b) for k in range(n)) / n

            std_a = math.sqrt(var_a) if var_a > 0 else 0
            std_b = math.sqrt(var_b) if var_b > 0 else 0
            corr = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0

            # Trade-off ratio
            range_a = max(a_vals) - min(a_vals) if a_vals else 0
            range_b = max(b_vals) - min(b_vals) if b_vals else 0
            ratio = range_b / range_a if range_a > 0 else 0

            # Relationship
            if corr < -0.3:
                rel = "conflict"
            elif corr > 0.3:
                rel = "synergy"
            else:
                rel = "independent"

            trade_offs.append(TradeOff(
                objective_a=a_name,
                objective_b=b_name,
                correlation=round(corr, 3),
                trade_off_ratio=round(ratio, 3),
                relationship=rel,
            ))

    return trade_offs


# ─── Main engine ───

def optimize_pareto(request: ParetoRequest) -> ParetoResponse:
    """Run multi-objective Pareto optimization."""
    t0 = time.time()
    total_solves = 0

    try:
        # Validate objectives exist for solver type
        obj_map = _get_objective_map(request.solver_type)
        for obj in request.objectives:
            if obj.name not in obj_map:
                return ParetoResponse(
                    status="error",
                    message=f"Unknown objective '{obj.name}' for solver '{request.solver_type.value}'. Available: {list(obj_map.keys())}",
                )

        # Generate weight vectors
        weights = _generate_weight_vectors(request.objectives, request.num_points)

        # Solve for each weight vector
        # Strategy: use the objective with highest weight as the primary solver objective
        all_points = []

        for idx, w in enumerate(weights):
            # Pick primary objective (highest weight)
            primary = max(w, key=w.get)

            try:
                resp, status = _solve_with_objective(
                    request.solver_type, request.solver_request,
                    primary, request.max_solve_time_seconds,
                )
                total_solves += 1
            except Exception as e:
                all_points.append(ParetoPoint(
                    point_id=idx,
                    objectives={o.name: 0 for o in request.objectives},
                    weights_used=w,
                    feasible=False,
                    status="error",
                ))
                continue

            feasible = status in ("optimal", "feasible")
            obj_values = _extract_objectives(request.solver_type, request.objectives, resp) if feasible else {o.name: 0 for o in request.objectives}

            # Determine if extreme or balanced
            is_extreme = any(v >= 0.99 for v in w.values())
            total_w = sum(request.objectives[0].weight for _ in request.objectives)  # dummy
            is_balanced = all(abs(v - 1/len(request.objectives)) < 0.05 for v in w.values())

            all_points.append(ParetoPoint(
                point_id=idx,
                objectives=obj_values,
                weights_used=w,
                feasible=feasible,
                status=status,
                is_extreme=is_extreme,
                is_balanced=is_balanced,
            ))

        feasible_points = [p for p in all_points if p.feasible]

        if not feasible_points:
            return ParetoResponse(
                status="error",
                message="No feasible solution found for any weight combination.",
                frontier=all_points,
            )

        # Filter to Pareto frontier
        frontier = _filter_pareto_frontier(feasible_points, request.objectives)

        # Analyze trade-offs
        trade_offs = _analyze_trade_offs(frontier, request.objectives)

        # Compute spread
        spread = {}
        for obj in request.objectives:
            vals = [p.objectives.get(obj.name, 0) for p in frontier]
            spread[obj.name] = round(max(vals) - min(vals), 2) if vals else 0

        metrics = ParetoMetrics(
            points_generated=len(all_points),
            points_feasible=len(feasible_points),
            points_on_frontier=len(frontier),
            total_solves=total_solves,
            solve_time_seconds=round(time.time() - t0, 3),
            spread=spread,
        )

        # Build recommendation
        rec_parts = []
        for to in trade_offs:
            if to.relationship == "conflict":
                rec_parts.append(f"{to.objective_a} and {to.objective_b} are in conflict (correlation: {to.correlation:.2f}). Improving one degrades the other.")
            elif to.relationship == "synergy":
                rec_parts.append(f"{to.objective_a} and {to.objective_b} show synergy (correlation: {to.correlation:.2f}). They can be improved together.")
            else:
                rec_parts.append(f"{to.objective_a} and {to.objective_b} are largely independent.")

        if frontier:
            extreme_points = [p for p in frontier if p.is_extreme]
            for ep in extreme_points:
                primary_obj = max(ep.weights_used, key=ep.weights_used.get)
                rec_parts.append(f"Optimizing only {primary_obj}: {', '.join(f'{k}={v}' for k, v in ep.objectives.items())}.")

        recommendation = " ".join(rec_parts) if rec_parts else "Pareto frontier generated. Review the trade-off points to choose the best compromise."

        obj_names = [o.name for o in request.objectives]
        msg = (
            f"Pareto analysis completed in {metrics.solve_time_seconds:.1f}s. "
            f"{metrics.points_on_frontier} non-dominated solutions found from {total_solves} solves. "
            f"Objectives: {', '.join(obj_names)}. "
            f"Spread: {', '.join(f'{k}: {v}' for k, v in spread.items())}."
        )

        return ParetoResponse(
            status="completed",
            message=msg,
            frontier=frontier,
            trade_offs=trade_offs,
            metrics=metrics,
            recommendation=recommendation,
        )

    except Exception as e:
        return ParetoResponse(
            status="error",
            message=f"Pareto optimization error: {str(e)}",
        )
