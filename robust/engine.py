"""
OptimEngine — Robust Optimization Engine
Generates scenarios from uncertainty ranges, solves each,
and recommends a solution that protects against worst-case outcomes.

Approach: scenario-based robust optimization.
1. Generate scenarios by sampling from uncertainty ranges
2. Always include nominal, best-case, and worst-case corners
3. Solve each scenario independently
4. Select robust solution based on mode (worst-case, percentile, regret)
"""

import copy
import math
import random
import time
from typing import Any

from .models import (
    RobustRequest, RobustResponse, RobustSolverType, RobustMode,
    UncertainParameter, ScenarioResult, RobustSolution, RobustMetrics,
)

from solver.models import ScheduleRequest
from solver.engine import solve_schedule
from routing.models import RoutingRequest
from routing.engine import solve_routing
from packing.models import PackingRequest
from packing.engine import solve_packing


# ─── Path resolution (shared logic with sensitivity) ───

def _resolve_path(data: dict, path: str) -> Any:
    """Resolve a dot-notation path to its value."""
    parts = path.split(".")
    current = data
    for part in parts:
        if "[" in part and "]" in part:
            field = part[:part.index("[")]
            key = part[part.index("[") + 1:part.index("]")]
            current = current[field]
            if isinstance(current, list):
                found = False
                for item in current:
                    id_fields = [
                        "job_id", "task_id", "machine_id",
                        "location_id", "vehicle_id",
                        "item_id", "bin_id",
                    ]
                    for id_field in id_fields:
                        if isinstance(item, dict) and item.get(id_field) == key:
                            current = item
                            found = True
                            break
                    if found:
                        break
                if not found:
                    raise KeyError(f"ID '{key}' not found in '{field}'")
        else:
            current = current[part]
    return current


def _set_path(data: dict, path: str, value: Any):
    """Set a value at a dot-notation path."""
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        if "[" in part and "]" in part:
            field = part[:part.index("[")]
            key = part[part.index("[") + 1:part.index("]")]
            current = current[field]
            if isinstance(current, list):
                for item in current:
                    id_fields = [
                        "job_id", "task_id", "machine_id",
                        "location_id", "vehicle_id",
                        "item_id", "bin_id",
                    ]
                    for id_field in id_fields:
                        if isinstance(item, dict) and item.get(id_field) == key:
                            current = item
                            break
        else:
            current = current[part]
    last = parts[-1]
    current[last] = value


# ─── Scenario generation ───

def _generate_scenarios(
    params: list[UncertainParameter],
    nominal_values: dict[str, float],
    num_scenarios: int,
) -> list[dict[str, float]]:
    """
    Generate a set of scenarios.
    Always includes: nominal, all-worst, all-best.
    Fills remaining with Latin Hypercube-like sampling.
    """
    scenarios = []

    # Scenario 0: Nominal
    scenarios.append({p.parameter_path: nominal_values[p.parameter_path] for p in params})

    # Scenario 1: All worst-case (max for costs/durations, varies by context)
    # We use max values as worst case (conservative — longer durations, higher demand)
    worst = {p.parameter_path: p.max_value for p in params}
    scenarios.append(worst)

    # Scenario 2: All best-case
    best = {p.parameter_path: p.min_value for p in params}
    scenarios.append(best)

    # Remaining: random sampling within ranges
    remaining = max(0, num_scenarios - 3)
    random.seed(42)  # Reproducible

    for _ in range(remaining):
        scenario = {}
        for p in params:
            val = random.uniform(p.min_value, p.max_value)
            # Keep int if nominal was int
            nom = nominal_values[p.parameter_path]
            if isinstance(nom, int):
                val = int(round(val))
            else:
                val = round(val, 2)
            scenario[p.parameter_path] = val
        scenarios.append(scenario)

    return scenarios


# ─── Solver dispatch ───

def _solve(solver_type: RobustSolverType, request_data: dict, max_time: int) -> tuple[str, float, str]:
    """Solve and return (status, objective_value, objective_name)."""
    request_data = copy.deepcopy(request_data)
    request_data["max_solve_time_seconds"] = max_time

    if solver_type == RobustSolverType.SCHEDULING:
        req = ScheduleRequest(**request_data)
        resp = solve_schedule(req)
        obj = resp.metrics.makespan if resp.metrics else 0
        return resp.status.value, float(obj), "makespan"

    elif solver_type == RobustSolverType.ROUTING:
        req = RoutingRequest(**request_data)
        resp = solve_routing(req)
        obj = resp.metrics.total_distance if resp.metrics else 0
        return resp.status.value, float(obj), "total_distance"

    elif solver_type == RobustSolverType.PACKING:
        req = PackingRequest(**request_data)
        resp = solve_packing(req)
        obj = resp.metrics.bins_used if resp.metrics else 0
        return resp.status.value, float(obj), "bins_used"

    raise ValueError(f"Unknown solver type: {solver_type}")


# ─── Main engine ───

def optimize_robust(request: RobustRequest) -> RobustResponse:
    """Run scenario-based robust optimization."""
    t0 = time.time()
    total_solves = 0

    try:
        data = request.solver_request

        # 1. Resolve nominal values
        nominal_values = {}
        for p in request.uncertain_parameters:
            try:
                val = _resolve_path(data, p.parameter_path)
                if p.nominal_value is not None:
                    nominal_values[p.parameter_path] = p.nominal_value
                else:
                    nominal_values[p.parameter_path] = val
            except (KeyError, ValueError) as e:
                return RobustResponse(
                    status="error",
                    message=f"Cannot resolve parameter '{p.parameter_path}': {e}",
                )

        # 2. Generate scenarios
        scenarios = _generate_scenarios(
            request.uncertain_parameters,
            nominal_values,
            request.num_scenarios,
        )

        # 3. Solve each scenario
        results = []
        feasible_objectives = []

        for i, scenario in enumerate(scenarios):
            scenario_data = copy.deepcopy(data)
            for path, val in scenario.items():
                try:
                    # Preserve int type if original was int
                    orig = _resolve_path(data, path)
                    if isinstance(orig, int):
                        val = int(round(val))
                    _set_path(scenario_data, path, val)
                except Exception:
                    continue

            try:
                status, obj, obj_name = _solve(
                    request.solver_type, scenario_data, request.max_solve_time_seconds,
                )
                total_solves += 1
            except Exception as e:
                results.append(ScenarioResult(
                    scenario_id=i,
                    parameter_values=scenario,
                    objective_value=0,
                    feasible=False,
                    status="error",
                    is_nominal=(i == 0),
                ))
                continue

            feasible = status in ("optimal", "feasible")
            if feasible:
                feasible_objectives.append(obj)

            results.append(ScenarioResult(
                scenario_id=i,
                parameter_values=scenario,
                objective_value=obj,
                feasible=feasible,
                status=status,
                is_nominal=(i == 0),
            ))

        if not feasible_objectives:
            return RobustResponse(
                status="error",
                message="No feasible scenario found. The problem may be too constrained even under nominal conditions.",
                scenarios=results,
            )

        obj_name = "objective"
        if results:
            # Get obj_name from a successful solve
            try:
                _, _, obj_name = _solve(request.solver_type, data, request.max_solve_time_seconds)
            except Exception:
                pass

        # 4. Analyze results
        nominal_obj = results[0].objective_value if results[0].feasible else None
        sorted_feasible = sorted(feasible_objectives)

        best_obj = sorted_feasible[0]
        worst_obj = sorted_feasible[-1]

        # Percentiles
        def percentile(data_list, pct):
            if not data_list:
                return 0
            k = (len(data_list) - 1) * (pct / 100)
            f = int(math.floor(k))
            c = min(int(math.ceil(k)), len(data_list) - 1)
            if f == c:
                return data_list[f]
            return data_list[f] * (c - k) + data_list[c] * (k - f)

        p90 = percentile(sorted_feasible, 90)
        p95 = percentile(sorted_feasible, 95)

        # Standard deviation
        mean_obj = sum(feasible_objectives) / len(feasible_objectives)
        variance = sum((x - mean_obj) ** 2 for x in feasible_objectives) / len(feasible_objectives)
        std_dev = round(math.sqrt(variance), 2)

        # 5. Select robust solution based on mode
        if request.mode == RobustMode.WORST_CASE:
            # Find the scenario with worst feasible objective
            target_obj = worst_obj
            label = "worst-case scenario"
        elif request.mode == RobustMode.PERCENTILE_90:
            target_obj = p90
            label = "90th percentile scenario"
        elif request.mode == RobustMode.PERCENTILE_95:
            target_obj = p95
            label = "95th percentile scenario"
        elif request.mode == RobustMode.REGRET_MINIMIZATION:
            # Find scenario closest to mean (minimize expected regret)
            target_obj = min(feasible_objectives, key=lambda x: abs(x - mean_obj))
            label = "minimum-regret scenario"
        else:
            target_obj = worst_obj
            label = "worst-case scenario"

        # Find the scenario that matches target
        robust_scenario = None
        for r in results:
            if r.feasible and abs(r.objective_value - target_obj) < 0.01:
                robust_scenario = r
                r.is_worst_case = (r.objective_value == worst_obj)
                break

        if robust_scenario is None:
            robust_scenario = results[0]  # fallback to nominal

        robust_solution = RobustSolution(
            objective_value=robust_scenario.objective_value,
            scenario_used=label,
            parameter_values=robust_scenario.parameter_values,
        )

        # Mark worst case
        for r in results:
            if r.feasible and r.objective_value == worst_obj:
                r.is_worst_case = True

        # 6. Compute price of robustness
        if nominal_obj and nominal_obj > 0:
            price_pct = round((robust_scenario.objective_value - nominal_obj) / nominal_obj * 100, 2)
        else:
            price_pct = 0

        feasibility_rate = round(len(feasible_objectives) / len(results) * 100, 1)

        metrics = RobustMetrics(
            nominal_objective=nominal_obj or 0,
            worst_case_objective=worst_obj,
            best_case_objective=best_obj,
            robust_objective=robust_scenario.objective_value,
            price_of_robustness_pct=price_pct,
            feasibility_rate_pct=feasibility_rate,
            scenarios_evaluated=len(results),
            total_solves=total_solves,
            solve_time_seconds=round(time.time() - t0, 3),
            percentile_90_objective=round(p90, 2),
            percentile_95_objective=round(p95, 2),
            objective_std_dev=std_dev,
        )

        # 7. Build recommendation
        rec_parts = []
        if price_pct <= 5:
            rec_parts.append(f"The robust solution costs only {price_pct:.1f}% more than nominal — strongly recommended.")
        elif price_pct <= 15:
            rec_parts.append(f"The robust solution costs {price_pct:.1f}% more than nominal — a reasonable insurance premium.")
        else:
            rec_parts.append(f"The robust solution costs {price_pct:.1f}% more than nominal — significant premium. Consider tightening uncertainty ranges.")

        if feasibility_rate < 80:
            rec_parts.append(f"⚠️ Only {feasibility_rate:.0f}% of scenarios are feasible. The system is fragile under uncertainty.")
        elif feasibility_rate < 95:
            rec_parts.append(f"~{feasibility_rate:.0f}% of scenarios are feasible. Some edge cases cause infeasibility.")
        else:
            rec_parts.append(f"{feasibility_rate:.0f}% of scenarios are feasible. The system is robust.")

        if std_dev > 0 and mean_obj > 0:
            cv = std_dev / mean_obj * 100
            if cv > 20:
                rec_parts.append(f"High variability (CV={cv:.0f}%). Outcome depends heavily on uncertain parameters.")
            elif cv > 10:
                rec_parts.append(f"Moderate variability (CV={cv:.0f}%). Some sensitivity to parameter changes.")
            else:
                rec_parts.append(f"Low variability (CV={cv:.0f}%). Solution is stable across scenarios.")

        recommendation = " ".join(rec_parts)

        msg = (
            f"Robust analysis completed in {metrics.solve_time_seconds:.1f}s. "
            f"{len(results)} scenarios evaluated ({total_solves} solves). "
            f"Nominal {obj_name}: {nominal_obj or 'N/A'}. "
            f"Worst-case: {worst_obj}. "
            f"Robust ({label}): {robust_scenario.objective_value}. "
            f"Price of robustness: {price_pct:.1f}%."
        )

        return RobustResponse(
            status="completed",
            message=msg,
            objective_name=obj_name,
            robust_solution=robust_solution,
            scenarios=results,
            metrics=metrics,
            recommendation=recommendation,
        )

    except Exception as e:
        return RobustResponse(
            status="error",
            message=f"Robust optimization error: {str(e)}",
        )
