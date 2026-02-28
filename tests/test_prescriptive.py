"""Tests for OptimEngine Prescriptive Intelligence."""

import pytest
from prescriptive.models import (
    PrescriptiveRequest, PrescriptiveSolverType, ForecastMethod,
    ForecastParameter, TimeSeriesPoint, RiskAppetite,
)
from prescriptive.engine import prescriptive_advise


# Increasing demand pattern
DEMAND_HISTORY = [
    TimeSeriesPoint(period=0, value=80),
    TimeSeriesPoint(period=1, value=85),
    TimeSeriesPoint(period=2, value=92),
    TimeSeriesPoint(period=3, value=88),
    TimeSeriesPoint(period=4, value=95),
    TimeSeriesPoint(period=5, value=100),
    TimeSeriesPoint(period=6, value=105),
]

# Volatile duration pattern
DURATION_HISTORY = [
    TimeSeriesPoint(period=0, value=30),
    TimeSeriesPoint(period=1, value=45),
    TimeSeriesPoint(period=2, value=25),
    TimeSeriesPoint(period=3, value=50),
    TimeSeriesPoint(period=4, value=28),
    TimeSeriesPoint(period=5, value=42),
]

# Stable pattern
STABLE_HISTORY = [
    TimeSeriesPoint(period=0, value=20),
    TimeSeriesPoint(period=1, value=21),
    TimeSeriesPoint(period=2, value=20),
    TimeSeriesPoint(period=3, value=19),
    TimeSeriesPoint(period=4, value=20),
]

SCHEDULING_REQUEST = {
    "jobs": [
        {
            "job_id": "J1",
            "tasks": [
                {"task_id": "cut", "duration": 30, "eligible_machines": ["M1", "M2"]},
                {"task_id": "weld", "duration": 20, "eligible_machines": ["M2"]},
            ],
            "due_date": 100,
        },
        {
            "job_id": "J2",
            "tasks": [
                {"task_id": "cut", "duration": 40, "eligible_machines": ["M1"]},
                {"task_id": "weld", "duration": 25, "eligible_machines": ["M2"]},
            ],
            "due_date": 120,
        },
    ],
    "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
    "objective": "minimize_makespan",
}

ROUTING_REQUEST = {
    "depot_id": "depot",
    "locations": [
        {"location_id": "depot", "demand": 0},
        {"location_id": "c1", "demand": 10, "time_window_start": 0, "time_window_end": 5000},
        {"location_id": "c2", "demand": 15, "time_window_start": 0, "time_window_end": 5000},
    ],
    "vehicles": [
        {"vehicle_id": "v1", "capacity": 40},
        {"vehicle_id": "v2", "capacity": 40},
    ],
    "distance_matrix": [
        {"from_id": "depot", "to_id": "c1", "distance": 100, "travel_time": 100},
        {"from_id": "depot", "to_id": "c2", "distance": 200, "travel_time": 200},
        {"from_id": "c1", "to_id": "depot", "distance": 100, "travel_time": 100},
        {"from_id": "c1", "to_id": "c2", "distance": 120, "travel_time": 120},
        {"from_id": "c2", "to_id": "depot", "distance": 200, "travel_time": 200},
        {"from_id": "c2", "to_id": "c1", "distance": 120, "travel_time": 120},
    ],
    "objective": "minimize_total_distance",
}

PACKING_REQUEST = {
    "items": [
        {"item_id": "a", "weight": 10, "value": 100},
        {"item_id": "b", "weight": 15, "value": 200},
        {"item_id": "c", "weight": 20, "value": 150},
    ],
    "bins": [
        {"bin_id": "box1", "weight_capacity": 30},
        {"bin_id": "box2", "weight_capacity": 30},
    ],
    "objective": "minimize_bins",
}


class TestForecastMethods:
    def test_exponential_smoothing(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                    forecast_method=ForecastMethod.EXPONENTIAL_SMOOTHING,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"
        assert len(resp.forecasts) == 1
        assert resp.forecasts[0].forecast_value > 0

    def test_moving_average(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=STABLE_HISTORY,
                    forecast_method=ForecastMethod.MOVING_AVERAGE,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"
        fc = resp.forecasts[0]
        assert fc.method_used == "moving_average"

    def test_linear_trend(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                    forecast_method=ForecastMethod.LINEAR_TREND,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"
        fc = resp.forecasts[0]
        assert fc.forecast_value > fc.historical_mean  # Increasing trend

    def test_seasonal_naive(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                    forecast_method=ForecastMethod.SEASONAL_NAIVE,
                    seasonal_period=4,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"


class TestRiskAppetite:
    def test_conservative(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                    forecast_method=ForecastMethod.EXPONENTIAL_SMOOTHING,
                ),
            ],
            risk_appetite=RiskAppetite.CONSERVATIVE,
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"
        assert resp.risk.conservative_objective >= resp.risk.aggressive_objective

    def test_aggressive(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                    forecast_method=ForecastMethod.EXPONENTIAL_SMOOTHING,
                ),
            ],
            risk_appetite=RiskAppetite.AGGRESSIVE,
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"

    def test_three_scenarios_computed(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                    forecast_method=ForecastMethod.EXPONENTIAL_SMOOTHING,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.risk.conservative_objective > 0
        assert resp.risk.moderate_objective > 0
        assert resp.risk.aggressive_objective > 0


class TestTrendDetection:
    def test_increasing_trend(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        fc = resp.forecasts[0]
        assert fc.trend in ("increasing", "stable")  # demand history has upward trend

    def test_volatile_detection(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DURATION_HISTORY,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        fc = resp.forecasts[0]
        assert fc.trend in ("volatile", "increasing", "decreasing")


class TestCrossSolver:
    def test_routing_prescriptive(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="locations[c1].demand",
                    historical_data=[
                        TimeSeriesPoint(period=0, value=8),
                        TimeSeriesPoint(period=1, value=10),
                        TimeSeriesPoint(period=2, value=12),
                        TimeSeriesPoint(period=3, value=11),
                        TimeSeriesPoint(period=4, value=14),
                    ],
                ),
            ],
            max_solve_time_seconds=10,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"

    def test_packing_prescriptive(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.PACKING,
            solver_request=PACKING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="items[a].weight",
                    historical_data=[
                        TimeSeriesPoint(period=0, value=9),
                        TimeSeriesPoint(period=1, value=10),
                        TimeSeriesPoint(period=2, value=11),
                        TimeSeriesPoint(period=3, value=10),
                    ],
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"


class TestActions:
    def test_actions_generated(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert len(resp.actions) >= 1
        assert resp.actions[0].action != ""
        assert resp.actions[0].reason != ""

    def test_recommendation_generated(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert len(resp.recommendation) > 0


class TestEdgeCases:
    def test_invalid_path(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[NOPE].tasks[cut].duration",
                    historical_data=STABLE_HISTORY,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "error"

    def test_multiple_forecast_params(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                ),
                ForecastParameter(
                    parameter_path="jobs[J2].tasks[weld].duration",
                    historical_data=STABLE_HISTORY,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        assert resp.status == "completed"
        assert len(resp.forecasts) == 2

    def test_prediction_interval(self):
        req = PrescriptiveRequest(
            solver_type=PrescriptiveSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            forecast_parameters=[
                ForecastParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    historical_data=DEMAND_HISTORY,
                    confidence_level=0.95,
                ),
            ],
            max_solve_time_seconds=5,
        )
        resp = prescriptive_advise(req)
        fc = resp.forecasts[0]
        assert fc.lower_bound <= fc.forecast_value
        assert fc.forecast_value <= fc.upper_bound
