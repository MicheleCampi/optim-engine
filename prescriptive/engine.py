"""
OptimEngine — Prescriptive Intelligence Engine
Forecast + Optimize + Risk-Aware Recommendations.

Pipeline:
1. Forecast each uncertain parameter from historical data
2. Inject forecasted values into solver request
3. Solve with point forecast (moderate), upper bound (conservative), lower bound (aggressive)
4. Run sensitivity on forecasted parameters
5. Generate actionable recommendations
"""

import copy
import math
import time
from typing import Any

from .models import (
    PrescriptiveRequest, PrescriptiveResponse, PrescriptiveSolverType,
    ForecastMethod, ForecastParameter, ForecastResult, RiskAppetite,
    OptimizationResult, RiskAssessment, Action, TimeSeriesPoint,
)

from solver.models import ScheduleRequest
from solver.engine import solve_schedule
from routing.models import RoutingRequest
from routing.engine import solve_routing
from packing.models import PackingRequest
from packing.engine import solve_packing


# ─── Path helpers ───

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


# ─── Forecasting methods ───

def _moving_average(values: list[float], horizon: int = 1) -> float:
    """Simple moving average of last N values."""
    window = min(len(values), 5)
    return sum(values[-window:]) / window


def _exponential_smoothing(values: list[float], alpha: float = None, horizon: int = 1) -> float:
    """Single exponential smoothing (SES)."""
    if alpha is None:
        # Auto-detect: minimize SSE over grid search
        best_alpha = 0.3
        best_sse = float("inf")
        for a in [i / 20 for i in range(1, 20)]:
            sse = 0
            s = values[0]
            for v in values[1:]:
                sse += (v - s) ** 2
                s = a * v + (1 - a) * s
            if sse < best_sse:
                best_sse = sse
                best_alpha = a
        alpha = best_alpha

    s = values[0]
    for v in values[1:]:
        s = alpha * v + (1 - alpha) * s
    return s


def _linear_trend(values: list[float], horizon: int = 1) -> float:
    """Linear regression trend extrapolation."""
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den > 0 else 0
    intercept = y_mean - slope * x_mean
    return intercept + slope * (n - 1 + horizon)


def _seasonal_naive(values: list[float], period: int, horizon: int = 1) -> float:
    """Seasonal naive: repeat value from same season last cycle."""
    if period and period <= len(values):
        idx = len(values) - period + ((horizon - 1) % period)
        if 0 <= idx < len(values):
            return values[idx]
    return values[-1]


def _forecast_parameter(param: ForecastParameter) -> ForecastResult:
    """Run forecast for a single parameter."""
    # Sort by period, extract values
    sorted_data = sorted(param.historical_data, key=lambda p: p.period)
    values = [p.value for p in sorted_data]
    n = len(values)

    mean_val = sum(values) / n
    variance = sum((v - mean_val) ** 2 for v in values) / n
    std_val = math.sqrt(variance) if variance > 0 else 0

    # Forecast
    method = param.forecast_method
    horizon = param.forecast_horizon

    if method == ForecastMethod.MOVING_AVERAGE:
        forecast = _moving_average(values, horizon)
    elif method == ForecastMethod.EXPONENTIAL_SMOOTHING:
        forecast = _exponential_smoothing(values, param.smoothing_alpha, horizon)
    elif method == ForecastMethod.LINEAR_TREND:
        forecast = _linear_trend(values, horizon)
    elif method == ForecastMethod.SEASONAL_NAIVE:
        forecast = _seasonal_naive(values, param.seasonal_period or 4, horizon)
    else:
        forecast = values[-1]

    # Prediction interval
    # Use residual-based interval
    if method == ForecastMethod.EXPONENTIAL_SMOOTHING:
        alpha = param.smoothing_alpha or 0.3
        s = values[0]
        residuals = []
        for v in values[1:]:
            residuals.append(v - s)
            s = alpha * v + (1 - alpha) * s
    else:
        # Simple residual from mean
        residuals = [v - mean_val for v in values]

    if residuals:
        res_std = math.sqrt(sum(r ** 2 for r in residuals) / len(residuals))
    else:
        res_std = std_val

    # Z-score for confidence
    z_map = {0.50: 0.674, 0.80: 1.282, 0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_map.get(param.confidence_level, 1.96)
    margin = z * res_std * math.sqrt(1 + horizon * 0.1)  # widen with horizon

    lower = forecast - margin
    upper = forecast + margin

    # Trend analysis
    if n >= 3:
        x_mean = (n - 1) / 2
        y_mean = mean_val
        num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0
        normalized_slope = abs(slope) / mean_val if mean_val > 0 else 0

        if normalized_slope < 0.02:
            trend = "stable"
        elif slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        # Check volatility
        cv = std_val / mean_val if mean_val > 0 else 0
        if cv > 0.3:
            trend = "volatile"
            normalized_slope = cv
    else:
        trend = "stable"
        normalized_slope = 0

    return ForecastResult(
        parameter_path=param.parameter_path,
        method_used=method.value,
        historical_mean=round(mean_val, 2),
        historical_std=round(std_val, 2),
        forecast_value=round(forecast, 2),
        lower_bound=round(max(0, lower), 2),
        upper_bound=round(upper, 2),
        confidence_level=param.confidence_level,
        trend=trend,
        trend_strength=round(normalized_slope, 4),
        forecast_horizon=horizon,
    )


# ─── Solver dispatch ───

def _solve(solver_type: PrescriptiveSolverType, request_data: dict, max_time: int):
    data = copy.deepcopy(request_data)
    data["max_solve_time_seconds"] = max_time

    if solver_type == PrescriptiveSolverType.SCHEDULING:
        req = ScheduleRequest(**data)
        resp = solve_schedule(req)
        obj = resp.metrics.makespan if resp.metrics else 0
        return resp.status.value, float(obj), "makespan"
    elif solver_type == PrescriptiveSolverType.ROUTING:
        req = RoutingRequest(**data)
        resp = solve_routing(req)
        obj = resp.metrics.total_distance if resp.metrics else 0
        return resp.status.value, float(obj), "total_distance"
    elif solver_type == PrescriptiveSolverType.PACKING:
        req = PackingRequest(**data)
        resp = solve_packing(req)
        obj = resp.metrics.bins_used if resp.metrics else 0
        return resp.status.value, float(obj), "bins_used"
    raise ValueError(f"Unknown solver: {solver_type}")


# ─── Main engine ───

def prescriptive_advise(request: PrescriptiveRequest) -> PrescriptiveResponse:
    """Run the full prescriptive pipeline: Forecast → Optimize → Risk → Advise."""
    t0 = time.time()

    try:
        data = request.solver_request

        # ── Step 1: Forecast ──
        forecasts = []
        for fp in request.forecast_parameters:
            try:
                _resolve_path(data, fp.parameter_path)
            except (KeyError, ValueError) as e:
                return PrescriptiveResponse(
                    status="error",
                    message=f"Cannot resolve parameter '{fp.parameter_path}': {e}",
                )
            fc = _forecast_parameter(fp)
            forecasts.append(fc)

        # ── Step 2: Inject and Optimize ──
        # Prepare three scenarios: conservative, moderate, aggressive
        scenarios = {}
        for label, appetite in [("conservative", "upper"), ("moderate", "point"), ("aggressive", "lower")]:
            scenario_data = copy.deepcopy(data)
            params_used = {}
            for fc in forecasts:
                if appetite == "upper":
                    val = fc.upper_bound
                elif appetite == "lower":
                    val = fc.lower_bound
                else:
                    val = fc.forecast_value

                orig = _resolve_path(data, fc.parameter_path)
                if isinstance(orig, int):
                    val = max(0, int(round(val)))
                else:
                    val = max(0.0, round(val, 2))
                _set_path(scenario_data, fc.parameter_path, val)
                params_used[fc.parameter_path] = val

            try:
                status, obj, obj_name = _solve(
                    request.solver_type, scenario_data, request.max_solve_time_seconds,
                )
            except Exception as e:
                status, obj, obj_name = "error", 0, "unknown"

            scenarios[label] = {
                "status": status,
                "objective": obj,
                "obj_name": obj_name,
                "params": params_used,
                "feasible": status in ("optimal", "feasible"),
            }

        # Primary result based on risk appetite
        primary = scenarios[request.risk_appetite.value]

        optimization = OptimizationResult(
            objective_name=primary["obj_name"],
            objective_value=primary["objective"],
            status=primary["status"],
            parameters_used=primary["params"],
        )

        # ── Step 3: Risk Assessment ──
        feasible_count = sum(1 for s in scenarios.values() if s["feasible"])
        if feasible_count == 3:
            feas_risk = "low"
        elif feasible_count >= 2:
            feas_risk = "medium"
        else:
            feas_risk = "high"

        # Find most sensitive forecasted parameter
        max_impact = 0
        critical_param = ""
        for fc in forecasts:
            spread = fc.upper_bound - fc.lower_bound
            if fc.historical_mean > 0:
                rel_spread = spread / fc.historical_mean
            else:
                rel_spread = spread
            if rel_spread > max_impact:
                max_impact = rel_spread
                critical_param = fc.parameter_path

        sensitivity_summary = f"Most critical: {critical_param} (prediction spread: {max_impact:.0%} of mean)." if critical_param else ""

        risk = RiskAssessment(
            conservative_objective=scenarios["conservative"]["objective"],
            moderate_objective=scenarios["moderate"]["objective"],
            aggressive_objective=scenarios["aggressive"]["objective"],
            sensitivity_summary=sensitivity_summary,
            feasibility_risk=feas_risk,
        )

        # ── Step 4: Generate Actions ──
        actions = []
        priority = 1

        # Trend-based actions
        for fc in forecasts:
            if fc.trend == "increasing":
                actions.append(Action(
                    priority=priority,
                    action=f"Plan for increasing {fc.parameter_path} (trend: +{fc.trend_strength:.1%}/period).",
                    reason=f"Historical data shows consistent upward trend. Forecast: {fc.forecast_value} (was {fc.historical_mean} avg).",
                    impact=f"May need {((fc.forecast_value - fc.historical_mean) / fc.historical_mean * 100):.0f}% more capacity." if fc.historical_mean > 0 else "",
                ))
                priority += 1
            elif fc.trend == "volatile":
                actions.append(Action(
                    priority=priority,
                    action=f"Add safety buffer for {fc.parameter_path} (volatile: CV={fc.trend_strength:.0%}).",
                    reason=f"High variability in historical data. Prediction interval: [{fc.lower_bound}, {fc.upper_bound}].",
                    impact="Consider robust or conservative planning.",
                ))
                priority += 1
            elif fc.trend == "decreasing":
                actions.append(Action(
                    priority=priority,
                    action=f"Monitor declining {fc.parameter_path} (trend: -{fc.trend_strength:.1%}/period).",
                    reason=f"Downward trend detected. Forecast: {fc.forecast_value} (was {fc.historical_mean} avg).",
                    impact="Potential to reduce allocated resources.",
                ))
                priority += 1

        # Feasibility-based actions
        if feas_risk == "high":
            actions.insert(0, Action(
                priority=1,
                action="Increase capacity or relax constraints immediately.",
                reason=f"Most scenarios are infeasible. System cannot handle forecasted demand.",
                impact="Without action, plan failure is likely.",
            ))
            for a in actions[1:]:
                a.priority += 1

        elif feas_risk == "medium":
            actions.append(Action(
                priority=priority,
                action="Consider switching to conservative planning mode.",
                reason="Some scenarios are infeasible at the boundaries of prediction intervals.",
                impact="Prevents plan failure in pessimistic conditions.",
            ))
            priority += 1

        # Risk appetite alignment
        if request.risk_appetite == RiskAppetite.AGGRESSIVE and feas_risk != "low":
            actions.append(Action(
                priority=priority,
                action="Warning: aggressive risk appetite with non-trivial uncertainty. Consider moderate.",
                reason=f"Feasibility risk is {feas_risk}. Aggressive planning uses lower bounds which may underestimate.",
                impact="Risk of plan failure if actual values exceed forecast.",
            ))

        # ── Step 5: Executive Recommendation ──
        obj_name = primary["obj_name"]
        mod_obj = scenarios["moderate"]["objective"]
        con_obj = scenarios["conservative"]["objective"]
        agg_obj = scenarios["aggressive"]["objective"]

        rec_parts = []
        rec_parts.append(f"Based on {len(forecasts)} forecasted parameter(s) using {request.risk_appetite.value} risk appetite:")
        rec_parts.append(f"Recommended {obj_name}: {primary['objective']}.")

        if con_obj > 0 and agg_obj > 0 and con_obj != agg_obj:
            spread_pct = abs(con_obj - agg_obj) / mod_obj * 100 if mod_obj > 0 else 0
            rec_parts.append(f"Outcome range: {agg_obj} (optimistic) to {con_obj} (pessimistic), spread {spread_pct:.0f}%.")

        for fc in forecasts:
            if fc.trend != "stable":
                rec_parts.append(f"{fc.parameter_path} is {fc.trend} (forecast: {fc.forecast_value}).")

        if feas_risk != "low":
            rec_parts.append(f"Feasibility risk: {feas_risk}. Monitor closely.")

        recommendation = " ".join(rec_parts)

        msg = (
            f"Prescriptive analysis completed in {time.time() - t0:.1f}s. "
            f"{len(forecasts)} parameter(s) forecasted. "
            f"Risk appetite: {request.risk_appetite.value}. "
            f"Recommended {obj_name}: {primary['objective']}. "
            f"Feasibility risk: {feas_risk}."
        )

        return PrescriptiveResponse(
            status="completed",
            message=msg,
            forecasts=forecasts,
            optimization=optimization,
            risk=risk,
            actions=actions,
            recommendation=recommendation,
            solve_time_seconds=round(time.time() - t0, 3),
        )

    except Exception as e:
        return PrescriptiveResponse(
            status="error",
            message=f"Prescriptive analysis error: {str(e)}",
        )
