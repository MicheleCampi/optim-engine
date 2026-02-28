"""
OptimEngine — Sensitivity Analysis Engine
Parametric perturbation analysis: perturb parameters one at a time,
re-solve, and build a fragility map.

Supports all three solvers: scheduling, routing, packing.
Auto-detects critical parameters when none specified.
"""

import copy
import time
from typing import Any

from .models import (
    SensitivityRequest, SensitivityResponse, SolverType, PerturbationMode,
    ParameterSpec, ParameterSensitivity, PerturbationResult, SensitivityMetrics,
)

from solver.models import ScheduleRequest
from solver.engine import solve_schedule
from routing.models import RoutingRequest
from routing.engine import solve_routing
from packing.models import PackingRequest
from packing.engine import solve_packing


# ─── Parameter resolution ───

def _resolve_path(data: dict, path: str) -> tuple[Any, str]:
    """
    Resolve a dot-notation path like 'jobs[J1].tasks[cut].duration'
    into the actual value and a human-readable name.
    Returns (value, display_name).
    """
    parts = path.split(".")
    current = data
    name_parts = []

    for part in parts:
        if "[" in part and "]" in part:
            field = part[:part.index("[")]
            key = part[part.index("[") + 1:part.index("]")]
            current = current[field]
            # Find by ID in list
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
            name_parts.append(f"{field}[{key}]")
        else:
            if isinstance(current, dict):
                current = current[part]
            else:
                raise KeyError(f"Cannot navigate '{part}' in non-dict")
            name_parts.append(part)

    return current, ".".join(name_parts)


def _set_path(data: dict, path: str, value: Any):
    """Set a value at a dot-notation path."""
    parts = path.split(".")
    current = data

    for i, part in enumerate(parts[:-1]):
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
    if "[" in last:
        raise ValueError("Cannot set value on a list element directly")
    current[last] = value


def _apply_perturbation(
    base_value: Any, perturbation: float, mode: PerturbationMode
) -> Any:
    """Apply perturbation to a value."""
    if not isinstance(base_value, (int, float)):
        raise ValueError(f"Cannot perturb non-numeric value: {base_value}")

    if mode == PerturbationMode.PERCENTAGE:
        new_val = base_value * (1 + perturbation / 100)
    else:
        new_val = base_value + perturbation

    # Keep as int if original was int
    if isinstance(base_value, int):
        new_val = max(0, int(round(new_val)))
    else:
        new_val = max(0.0, round(new_val, 2))

    return new_val


# ─── Auto-detection of parameters ───

def _auto_detect_scheduling(data: dict) -> list[ParameterSpec]:
    """Auto-detect critical parameters for scheduling."""
    specs = []
    jobs = data.get("jobs", [])
    for job in jobs:
        job_id = job.get("job_id", "")
        for task in job.get("tasks", []):
            task_id = task.get("task_id", "")
            specs.append(ParameterSpec(
                parameter_path=f"jobs[{job_id}].tasks[{task_id}].duration",
            ))
        if job.get("due_date") is not None:
            specs.append(ParameterSpec(
                parameter_path=f"jobs[{job_id}].due_date",
            ))
    return specs[:12]  # Limit to avoid explosion


def _auto_detect_routing(data: dict) -> list[ParameterSpec]:
    """Auto-detect critical parameters for routing."""
    specs = []
    depot_id = data.get("depot_id", "")
    for loc in data.get("locations", []):
        loc_id = loc.get("location_id", "")
        if loc_id == depot_id:
            continue
        if loc.get("demand", 0) > 0:
            specs.append(ParameterSpec(
                parameter_path=f"locations[{loc_id}].demand",
            ))
    for veh in data.get("vehicles", []):
        veh_id = veh.get("vehicle_id", "")
        specs.append(ParameterSpec(
            parameter_path=f"vehicles[{veh_id}].capacity",
        ))
    return specs[:12]


def _auto_detect_packing(data: dict) -> list[ParameterSpec]:
    """Auto-detect critical parameters for packing."""
    specs = []
    for item in data.get("items", []):
        item_id = item.get("item_id", "")
        specs.append(ParameterSpec(
            parameter_path=f"items[{item_id}].weight",
        ))
    for b in data.get("bins", []):
        bin_id = b.get("bin_id", "")
        specs.append(ParameterSpec(
            parameter_path=f"bins[{bin_id}].weight_capacity",
        ))
    return specs[:12]


# ─── Solver dispatch ───

def _solve(solver_type: SolverType, request_data: dict, max_time: int) -> tuple[str, float, str]:
    """
    Solve and return (status, objective_value, objective_name).
    """
    request_data = copy.deepcopy(request_data)
    request_data["max_solve_time_seconds"] = max_time

    if solver_type == SolverType.SCHEDULING:
        req = ScheduleRequest(**request_data)
        resp = solve_schedule(req)
        obj = resp.metrics.makespan if resp.metrics else 0
        return resp.status.value, float(obj), "makespan"

    elif solver_type == SolverType.ROUTING:
        req = RoutingRequest(**request_data)
        resp = solve_routing(req)
        obj = resp.metrics.total_distance if resp.metrics else 0
        return resp.status.value, float(obj), "total_distance"

    elif solver_type == SolverType.PACKING:
        req = PackingRequest(**request_data)
        resp = solve_packing(req)
        obj = resp.metrics.bins_used if resp.metrics else 0
        return resp.status.value, float(obj), "bins_used"

    raise ValueError(f"Unknown solver type: {solver_type}")


# ─── Main engine ───

def analyze_sensitivity(request: SensitivityRequest) -> SensitivityResponse:
    """Run parametric sensitivity analysis."""
    t0 = time.time()
    total_solves = 0

    try:
        data = request.solver_request

        # 1. Solve baseline
        try:
            base_status, base_obj, obj_name = _solve(
                request.solver_type, data, request.max_solve_time_seconds
            )
            total_solves += 1
        except Exception as e:
            return SensitivityResponse(
                status="error",
                message=f"Baseline solve failed: {str(e)}",
            )

        if base_status not in ("optimal", "feasible"):
            return SensitivityResponse(
                status="error",
                message=f"Baseline problem is not feasible (status: {base_status}). Cannot analyze sensitivity of an infeasible problem.",
                baseline_objective=base_obj,
                baseline_objective_name=obj_name,
            )

        # 2. Determine parameters to analyze
        params = request.parameters
        if not params:
            if request.solver_type == SolverType.SCHEDULING:
                params = _auto_detect_scheduling(data)
            elif request.solver_type == SolverType.ROUTING:
                params = _auto_detect_routing(data)
            elif request.solver_type == SolverType.PACKING:
                params = _auto_detect_packing(data)

        if not params:
            return SensitivityResponse(
                status="error",
                message="No parameters to analyze. Specify parameters or ensure the request has perturbable fields.",
            )

        # 3. Perturb each parameter
        param_results = []

        for spec in params:
            try:
                base_value, display_name = _resolve_path(data, spec.parameter_path)
            except (KeyError, ValueError) as e:
                continue

            if not isinstance(base_value, (int, float)) or base_value == 0:
                continue

            perturbations = spec.perturbations[:request.max_perturbations_per_param]
            p_results = []
            max_delta = 0.0
            increases_hurt = 0
            decreases_hurt = 0

            for pert in perturbations:
                new_val = _apply_perturbation(base_value, pert, spec.mode)
                if new_val == base_value:
                    continue

                perturbed_data = copy.deepcopy(data)
                try:
                    _set_path(perturbed_data, spec.parameter_path, new_val)
                except Exception:
                    continue

                try:
                    p_status, p_obj, _ = _solve(
                        request.solver_type, perturbed_data,
                        request.max_solve_time_seconds,
                    )
                    total_solves += 1
                except Exception:
                    p_results.append(PerturbationResult(
                        perturbation_value=pert,
                        new_param_value=new_val,
                        objective_value=0,
                        objective_delta_pct=0,
                        feasible=False,
                        status="error",
                    ))
                    continue

                feasible = p_status in ("optimal", "feasible")
                if feasible and base_obj > 0:
                    delta_pct = round((p_obj - base_obj) / base_obj * 100, 2)
                elif not feasible:
                    delta_pct = 100.0  # Mark infeasible as max impact
                else:
                    delta_pct = 0.0

                p_results.append(PerturbationResult(
                    perturbation_value=pert,
                    new_param_value=new_val,
                    objective_value=p_obj,
                    objective_delta_pct=delta_pct,
                    feasible=feasible,
                    status=p_status,
                ))

                abs_delta = abs(delta_pct)
                if abs_delta > max_delta:
                    max_delta = abs_delta

                if pert > 0 and delta_pct > 0:
                    increases_hurt += 1
                elif pert < 0 and delta_pct > 0:
                    decreases_hurt += 1

            if not p_results:
                continue

            # Compute elasticity
            elasticities = []
            for pr in p_results:
                if pr.feasible and pr.perturbation_value != 0:
                    pct_param_change = abs(pr.perturbation_value) if spec.mode == PerturbationMode.PERCENTAGE else (abs(pr.perturbation_value) / abs(base_value) * 100 if base_value != 0 else 0)
                    if pct_param_change > 0:
                        elasticities.append(abs(pr.objective_delta_pct) / pct_param_change)

            avg_elasticity = round(sum(elasticities) / len(elasticities), 3) if elasticities else 0.0
            sensitivity_score = min(100.0, round(max_delta, 1))
            any_infeasible = any(not pr.feasible for pr in p_results)
            critical = any_infeasible or max_delta > 25

            if increases_hurt > decreases_hurt:
                direction = "increase_hurts"
            elif decreases_hurt > increases_hurt:
                direction = "decrease_hurts"
            else:
                direction = "symmetric"

            # Risk summary
            if critical and any_infeasible:
                risk_summary = f"CRITICAL: Perturbation of {display_name} causes infeasibility. This parameter must be tightly controlled."
            elif critical:
                risk_summary = f"HIGH RISK: {display_name} has >25% impact on objective. Direction: {direction}. Elasticity: {avg_elasticity:.2f}x."
            elif sensitivity_score > 10:
                risk_summary = f"MODERATE: {display_name} affects objective by up to {sensitivity_score:.0f}%. Monitor for changes."
            else:
                risk_summary = f"LOW RISK: {display_name} has minimal impact (<10%). Robust to variations."

            param_results.append(ParameterSensitivity(
                parameter_path=spec.parameter_path,
                parameter_name=display_name,
                baseline_value=base_value,
                sensitivity_score=sensitivity_score,
                elasticity=avg_elasticity,
                critical=critical,
                direction=direction,
                perturbation_results=p_results,
                risk_summary=risk_summary,
            ))

        # 4. Rank and aggregate
        param_results.sort(key=lambda x: x.sensitivity_score, reverse=True)
        risk_ranking = [p.parameter_name for p in param_results]

        n_critical = sum(1 for p in param_results if p.critical)
        avg_score = round(
            sum(p.sensitivity_score for p in param_results) / len(param_results), 1
        ) if param_results else 0

        metrics = SensitivityMetrics(
            parameters_analyzed=len(param_results),
            total_solves=total_solves,
            critical_parameters=n_critical,
            most_sensitive_parameter=risk_ranking[0] if risk_ranking else None,
            least_sensitive_parameter=risk_ranking[-1] if risk_ranking else None,
            baseline_objective=base_obj,
            baseline_status=base_status,
            avg_sensitivity_score=avg_score,
            solve_time_seconds=round(time.time() - t0, 3),
        )

        msg_parts = [
            f"Sensitivity analysis completed in {metrics.solve_time_seconds:.1f}s.",
            f"{len(param_results)} parameters analyzed across {total_solves} solves.",
        ]
        if n_critical > 0:
            msg_parts.append(f"⚠️ {n_critical} critical parameter(s) found.")
        msg_parts.append(f"Most sensitive: {risk_ranking[0]}." if risk_ranking else "")

        return SensitivityResponse(
            status="completed",
            message=" ".join(msg_parts),
            baseline_objective=base_obj,
            baseline_objective_name=obj_name,
            parameters=param_results,
            risk_ranking=risk_ranking,
            metrics=metrics,
        )

    except Exception as e:
        return SensitivityResponse(
            status="error",
            message=f"Sensitivity analysis error: {str(e)}",
        )
