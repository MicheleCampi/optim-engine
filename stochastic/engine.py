"""
OptimEngine — Stochastic Optimization Engine
Monte Carlo scenario sampling with probabilistic risk metrics.

Approach:
1. Sample N scenarios from specified probability distributions
2. Solve each scenario independently
3. Build objective distribution and compute risk metrics (CVaR, VaR)
4. Recommend solution based on chosen risk metric
"""

import copy
import math
import random
import time
from typing import Any

from .models import (
    StochasticRequest, StochasticResponse, StochasticSolverType,
    DistributionType, RiskMetric, StochasticParameter,
    ScenarioOutcome, DistributionSummary, RiskAnalysis, StochasticMetrics,
)

from solver.models import ScheduleRequest
from solver.engine import solve_schedule
from routing.models import RoutingRequest
from routing.engine import solve_routing
from packing.models import PackingRequest
from packing.engine import solve_packing


# ─── Path resolution ───

def _resolve_path(data: dict, path: str) -> Any:
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
                    for id_field in ["job_id", "task_id", "machine_id",
                                     "location_id", "vehicle_id",
                                     "item_id", "bin_id"]:
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
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        if "[" in part and "]" in part:
            field = part[:part.index("[")]
            key = part[part.index("[") + 1:part.index("]")]
            current = current[field]
            if isinstance(current, list):
                for item in current:
                    for id_field in ["job_id", "task_id", "machine_id",
                                     "location_id", "vehicle_id",
                                     "item_id", "bin_id"]:
                        if isinstance(item, dict) and item.get(id_field) == key:
                            current = item
                            break
        else:
            current = current[part]
    current[parts[-1]] = value


# ─── Sampling ───

def _sample_value(param: StochasticParameter, nominal: float, rng: random.Random) -> float:
    """Sample a single value from the parameter's distribution."""
    d = param.distribution
    mean = param.mean if param.mean is not None else nominal

    if d == DistributionType.NORMAL:
        val = rng.gauss(mean, param.std_dev)
        val = max(0, val)  # Non-negative

    elif d == DistributionType.UNIFORM:
        val = rng.uniform(param.min_value, param.max_value)

    elif d == DistributionType.TRIANGULAR:
        val = rng.triangular(param.min_value, param.max_value, param.mode_value)

    elif d == DistributionType.LOG_NORMAL:
        # Convert mean/std_dev to log-space parameters
        variance = param.std_dev ** 2
        mu = math.log(mean ** 2 / math.sqrt(variance + mean ** 2))
        sigma = math.sqrt(math.log(1 + variance / mean ** 2))
        val = rng.lognormvariate(mu, sigma)

    else:
        val = nominal

    # Preserve int type
    if isinstance(nominal, int):
        val = max(0, int(round(val)))
    else:
        val = max(0.0, round(val, 2))

    return val


def _generate_scenarios(
    params: list[StochasticParameter],
    nominal_values: dict[str, float],
    num_scenarios: int,
    seed: int,
) -> list[dict[str, float]]:
    """Generate Monte Carlo scenarios."""
    rng = random.Random(seed)
    scenarios = []

    for _ in range(num_scenarios):
        scenario = {}
        for p in params:
            nom = nominal_values[p.parameter_path]
            scenario[p.parameter_path] = _sample_value(p, nom, rng)
        scenarios.append(scenario)

    return scenarios


# ─── Solver dispatch ───

def _solve(solver_type: StochasticSolverType, request_data: dict, max_time: int) -> tuple[str, float, str]:
    request_data = copy.deepcopy(request_data)
    request_data["max_solve_time_seconds"] = max_time

    if solver_type == StochasticSolverType.SCHEDULING:
        req = ScheduleRequest(**request_data)
        resp = solve_schedule(req)
        obj = resp.metrics.makespan if resp.metrics else 0
        return resp.status.value, float(obj), "makespan"

    elif solver_type == StochasticSolverType.ROUTING:
        req = RoutingRequest(**request_data)
        resp = solve_routing(req)
        obj = resp.metrics.total_distance if resp.metrics else 0
        return resp.status.value, float(obj), "total_distance"

    elif solver_type == StochasticSolverType.PACKING:
        req = PackingRequest(**request_data)
        resp = solve_packing(req)
        obj = resp.metrics.bins_used if resp.metrics else 0
        return resp.status.value, float(obj), "bins_used"

    raise ValueError(f"Unknown solver type: {solver_type}")


# ─── Statistics ───

def _percentile(sorted_data: list[float], pct: float) -> float:
    if not sorted_data:
        return 0
    k = (len(sorted_data) - 1) * (pct / 100)
    f = int(math.floor(k))
    c = min(int(math.ceil(k)), len(sorted_data) - 1)
    if f == c:
        return sorted_data[f]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


def _cvar(sorted_data: list[float], confidence_pct: float) -> float:
    """
    Conditional Value at Risk.
    For a minimization problem, CVaR at 95% = average of the worst 5% outcomes (highest values).
    """
    if not sorted_data:
        return 0
    tail_size = max(1, int(math.ceil(len(sorted_data) * (1 - confidence_pct / 100))))
    tail = sorted_data[-tail_size:]
    return sum(tail) / len(tail)


def _skewness(data: list[float], mean: float, std_dev: float) -> float:
    if std_dev == 0 or len(data) < 3:
        return 0
    n = len(data)
    return (n / ((n - 1) * (n - 2))) * sum(((x - mean) / std_dev) ** 3 for x in data)


# ─── Main engine ───

def optimize_stochastic(request: StochasticRequest) -> StochasticResponse:
    """Run Monte Carlo stochastic optimization."""
    t0 = time.time()
    total_solves = 0

    try:
        data = request.solver_request

        # 1. Resolve nominal values
        nominal_values = {}
        for p in request.stochastic_parameters:
            try:
                val = _resolve_path(data, p.parameter_path)
                nominal_values[p.parameter_path] = val
            except (KeyError, ValueError) as e:
                return StochasticResponse(
                    status="error",
                    message=f"Cannot resolve parameter '{p.parameter_path}': {e}",
                )

        # 2. Generate scenarios
        scenarios = _generate_scenarios(
            request.stochastic_parameters,
            nominal_values,
            request.num_scenarios,
            request.seed,
        )

        # 3. Solve each scenario
        outcomes = []
        feasible_objectives = []

        obj_name = "objective"

        for i, scenario in enumerate(scenarios):
            scenario_data = copy.deepcopy(data)
            for path, val in scenario.items():
                try:
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
            except Exception:
                outcomes.append(ScenarioOutcome(
                    scenario_id=i,
                    parameter_values=scenario,
                    objective_value=0,
                    feasible=False,
                    status="error",
                ))
                continue

            feasible = status in ("optimal", "feasible")
            if feasible:
                feasible_objectives.append(obj)

            outcomes.append(ScenarioOutcome(
                scenario_id=i,
                parameter_values=scenario,
                objective_value=obj,
                feasible=feasible,
                status=status,
            ))

        if not feasible_objectives:
            return StochasticResponse(
                status="error",
                message="No feasible scenario found across all Monte Carlo samples.",
                scenarios=outcomes,
            )

        # 4. Compute distribution summary
        sorted_obj = sorted(feasible_objectives)
        n = len(sorted_obj)
        mean_obj = sum(sorted_obj) / n
        variance = sum((x - mean_obj) ** 2 for x in sorted_obj) / n
        std_dev = math.sqrt(variance)

        distribution = DistributionSummary(
            mean=round(mean_obj, 2),
            median=round(_percentile(sorted_obj, 50), 2),
            std_dev=round(std_dev, 2),
            min_value=round(sorted_obj[0], 2),
            max_value=round(sorted_obj[-1], 2),
            percentile_5=round(_percentile(sorted_obj, 5), 2),
            percentile_10=round(_percentile(sorted_obj, 10), 2),
            percentile_25=round(_percentile(sorted_obj, 25), 2),
            percentile_75=round(_percentile(sorted_obj, 75), 2),
            percentile_90=round(_percentile(sorted_obj, 90), 2),
            percentile_95=round(_percentile(sorted_obj, 95), 2),
            percentile_99=round(_percentile(sorted_obj, 99), 2),
            skewness=round(_skewness(sorted_obj, mean_obj, std_dev), 3) if std_dev > 0 else 0,
            coefficient_of_variation=round(std_dev / mean_obj * 100, 1) if mean_obj > 0 else 0,
        )

        # 5. Compute risk metrics
        risk = RiskAnalysis(
            expected_value=round(mean_obj, 2),
            var_90=round(_percentile(sorted_obj, 90), 2),
            var_95=round(_percentile(sorted_obj, 95), 2),
            var_99=round(_percentile(sorted_obj, 99), 2),
            cvar_90=round(_cvar(sorted_obj, 90), 2),
            cvar_95=round(_cvar(sorted_obj, 95), 2),
            cvar_99=round(_cvar(sorted_obj, 99), 2),
            worst_case=round(sorted_obj[-1], 2),
            best_case=round(sorted_obj[0], 2),
            probability_of_infeasibility=round(
                (len(outcomes) - n) / len(outcomes) * 100, 1
            ),
        )

        # 6. Select recommended scenario based on risk metric
        if request.optimize_for == RiskMetric.EXPECTED_VALUE:
            target = mean_obj
            label = "expected value"
        elif request.optimize_for == RiskMetric.CVAR_90:
            target = risk.cvar_90
            label = "CVaR 90%"
        elif request.optimize_for == RiskMetric.CVAR_95:
            target = risk.cvar_95
            label = "CVaR 95%"
        elif request.optimize_for == RiskMetric.CVAR_99:
            target = risk.cvar_99
            label = "CVaR 99%"
        elif request.optimize_for == RiskMetric.WORST_CASE:
            target = risk.worst_case
            label = "worst case"
        else:
            target = risk.cvar_95
            label = "CVaR 95%"

        # Find scenario closest to target
        best_match = None
        best_diff = float("inf")
        for o in outcomes:
            if o.feasible:
                diff = abs(o.objective_value - target)
                if diff < best_diff:
                    best_diff = diff
                    best_match = o

        # 7. Build recommendation
        rec_parts = []
        cv = distribution.coefficient_of_variation

        if cv < 5:
            rec_parts.append(f"Very stable: CV={cv:.1f}%. The {obj_name} varies minimally across scenarios. The deterministic solution is reliable.")
        elif cv < 15:
            rec_parts.append(f"Moderate variability: CV={cv:.1f}%. The {obj_name} ranges from {risk.best_case} to {risk.worst_case}. Consider using the {label} solution for safety.")
        elif cv < 30:
            rec_parts.append(f"High variability: CV={cv:.1f}%. The {obj_name} ranges from {risk.best_case} to {risk.worst_case}. Risk-aware planning strongly recommended.")
        else:
            rec_parts.append(f"Extreme variability: CV={cv:.1f}%. The {obj_name} ranges from {risk.best_case} to {risk.worst_case}. The system is highly sensitive to uncertain parameters.")

        if risk.probability_of_infeasibility > 0:
            rec_parts.append(f"⚠️ {risk.probability_of_infeasibility:.1f}% of scenarios are infeasible. Consider relaxing constraints or adding capacity buffer.")

        gap_pct = 0
        if risk.expected_value > 0:
            gap_pct = round((risk.cvar_95 - risk.expected_value) / risk.expected_value * 100, 1)
        rec_parts.append(f"The gap between expected value ({risk.expected_value}) and CVaR 95% ({risk.cvar_95}) is {gap_pct}%. This is the 'risk premium' — what you pay for 95% protection.")

        recommendation = " ".join(rec_parts)

        metrics = StochasticMetrics(
            scenarios_generated=len(outcomes),
            scenarios_feasible=n,
            scenarios_infeasible=len(outcomes) - n,
            total_solves=total_solves,
            solve_time_seconds=round(time.time() - t0, 3),
            optimized_for=label,
        )

        msg = (
            f"Stochastic analysis completed in {metrics.solve_time_seconds:.1f}s. "
            f"{len(outcomes)} Monte Carlo scenarios ({n} feasible, {len(outcomes) - n} infeasible). "
            f"Expected {obj_name}: {risk.expected_value}. "
            f"CVaR 95%: {risk.cvar_95}. "
            f"Range: [{risk.best_case}, {risk.worst_case}]."
        )

        return StochasticResponse(
            status="completed",
            message=msg,
            objective_name=obj_name,
            recommended_objective=round(target, 2),
            recommended_scenario=best_match,
            distribution=distribution,
            risk=risk,
            scenarios=outcomes,
            metrics=metrics,
            recommendation=recommendation,
        )

    except Exception as e:
        return StochasticResponse(
            status="error",
            message=f"Stochastic optimization error: {str(e)}",
        )
