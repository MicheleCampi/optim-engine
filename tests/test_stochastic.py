"""Tests for OptimEngine Stochastic Optimization."""

import pytest
from stochastic.models import (
    StochasticRequest, StochasticSolverType, DistributionType,
    RiskMetric, StochasticParameter,
)
from stochastic.engine import optimize_stochastic


SCHEDULING_REQUEST = {
    "jobs": [
        {
            "job_id": "J1",
            "tasks": [
                {"task_id": "cut", "duration": 30, "eligible_machines": ["M1", "M2"]},
                {"task_id": "weld", "duration": 20, "eligible_machines": ["M2"]},
            ],
            "due_date": 80,
        },
        {
            "job_id": "J2",
            "tasks": [
                {"task_id": "cut", "duration": 40, "eligible_machines": ["M1"]},
                {"task_id": "weld", "duration": 25, "eligible_machines": ["M2"]},
            ],
            "due_date": 100,
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
        {"location_id": "c3", "demand": 20, "time_window_start": 0, "time_window_end": 5000},
    ],
    "vehicles": [
        {"vehicle_id": "v1", "capacity": 30},
        {"vehicle_id": "v2", "capacity": 30},
    ],
    "distance_matrix": [
        {"from_id": "depot", "to_id": "c1", "distance": 100, "travel_time": 100},
        {"from_id": "depot", "to_id": "c2", "distance": 200, "travel_time": 200},
        {"from_id": "depot", "to_id": "c3", "distance": 150, "travel_time": 150},
        {"from_id": "c1", "to_id": "depot", "distance": 100, "travel_time": 100},
        {"from_id": "c1", "to_id": "c2", "distance": 120, "travel_time": 120},
        {"from_id": "c1", "to_id": "c3", "distance": 180, "travel_time": 180},
        {"from_id": "c2", "to_id": "depot", "distance": 200, "travel_time": 200},
        {"from_id": "c2", "to_id": "c1", "distance": 120, "travel_time": 120},
        {"from_id": "c2", "to_id": "c3", "distance": 90, "travel_time": 90},
        {"from_id": "c3", "to_id": "depot", "distance": 150, "travel_time": 150},
        {"from_id": "c3", "to_id": "c1", "distance": 180, "travel_time": 180},
        {"from_id": "c3", "to_id": "c2", "distance": 90, "travel_time": 90},
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


class TestSchedulingStochastic:
    def test_normal_distribution(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=5,
                ),
            ],
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"
        assert resp.distribution is not None
        assert resp.risk is not None
        assert resp.metrics.scenarios_feasible > 0

    def test_uniform_distribution(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.UNIFORM,
                    min_value=20, max_value=50,
                ),
            ],
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"

    def test_triangular_distribution(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.TRIANGULAR,
                    min_value=20, max_value=50, mode_value=30,
                ),
            ],
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"

    def test_log_normal_distribution(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J2].tasks[weld].duration",
                    distribution=DistributionType.LOG_NORMAL,
                    mean=25, std_dev=8,
                ),
            ],
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"

    def test_multiple_uncertain_params(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=5,
                ),
                StochasticParameter(
                    parameter_path="jobs[J2].tasks[weld].duration",
                    distribution=DistributionType.UNIFORM,
                    min_value=15, max_value=40,
                ),
            ],
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"
        assert resp.metrics.scenarios_generated == 20


class TestRiskMetrics:
    def test_cvar_95(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=10,
                ),
            ],
            optimize_for=RiskMetric.CVAR_95,
            num_scenarios=30,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"
        assert resp.risk.cvar_95 >= resp.risk.expected_value
        assert resp.risk.cvar_95 <= resp.risk.worst_case

    def test_expected_value_mode(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=5,
                ),
            ],
            optimize_for=RiskMetric.EXPECTED_VALUE,
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"
        assert resp.recommended_objective == resp.risk.expected_value

    def test_worst_case_mode(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=10,
                ),
            ],
            optimize_for=RiskMetric.WORST_CASE,
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"
        assert resp.recommended_objective == resp.risk.worst_case

    def test_var_ordering(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=10,
                ),
            ],
            num_scenarios=50,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        r = resp.risk
        assert r.best_case <= r.expected_value
        assert r.var_90 <= r.var_95
        assert r.var_95 <= r.var_99
        assert r.var_99 <= r.worst_case


class TestRoutingStochastic:
    def test_demand_uncertainty(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="locations[c1].demand",
                    distribution=DistributionType.NORMAL,
                    mean=10, std_dev=3,
                ),
                StochasticParameter(
                    parameter_path="locations[c3].demand",
                    distribution=DistributionType.TRIANGULAR,
                    min_value=10, max_value=30, mode_value=20,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=10,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"


class TestPackingStochastic:
    def test_weight_uncertainty(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.PACKING,
            solver_request=PACKING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="items[a].weight",
                    distribution=DistributionType.NORMAL,
                    mean=10, std_dev=2,
                ),
                StochasticParameter(
                    parameter_path="items[c].weight",
                    distribution=DistributionType.UNIFORM,
                    min_value=15, max_value=28,
                ),
            ],
            num_scenarios=15,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "completed"


class TestDistributionSummary:
    def test_distribution_fields(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=8,
                ),
            ],
            num_scenarios=30,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        d = resp.distribution
        assert d.mean > 0
        assert d.median > 0
        assert d.std_dev >= 0
        assert d.min_value <= d.max_value
        assert d.percentile_5 <= d.percentile_95
        assert d.coefficient_of_variation >= 0

    def test_recommendation_generated(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=8,
                ),
            ],
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert len(resp.recommendation) > 0


class TestEdgeCases:
    def test_invalid_path(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[NONE].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=5,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.status == "error"

    def test_reproducibility(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=5,
                ),
            ],
            num_scenarios=10,
            seed=123,
            max_solve_time_seconds=5,
        )
        resp1 = optimize_stochastic(req)
        resp2 = optimize_stochastic(req)
        assert resp1.risk.expected_value == resp2.risk.expected_value

    def test_scenario_count(self):
        req = StochasticRequest(
            solver_type=StochasticSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            stochastic_parameters=[
                StochasticParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    distribution=DistributionType.NORMAL,
                    mean=30, std_dev=5,
                ),
            ],
            num_scenarios=15,
            max_solve_time_seconds=5,
        )
        resp = optimize_stochastic(req)
        assert resp.metrics.scenarios_generated == 15
