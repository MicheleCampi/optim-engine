"""Tests for OptimEngine Robust Optimization."""

import pytest
from robust.models import (
    RobustRequest, RobustSolverType, RobustMode, UncertainParameter,
)
from robust.engine import optimize_robust


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


class TestSchedulingRobust:
    def test_basic_robust(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=50,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"
        assert resp.robust_solution is not None
        assert resp.metrics.scenarios_evaluated == 10
        assert resp.metrics.nominal_objective > 0

    def test_multiple_uncertain_params(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=50,
                ),
                UncertainParameter(
                    parameter_path="jobs[J2].tasks[weld].duration",
                    min_value=15, max_value=40,
                ),
            ],
            num_scenarios=15,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"
        assert resp.metrics.scenarios_evaluated == 15

    def test_worst_case_mode(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=60,
                ),
            ],
            mode=RobustMode.WORST_CASE,
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"
        assert resp.robust_solution.objective_value >= resp.metrics.nominal_objective

    def test_percentile_90_mode(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=60,
                ),
            ],
            mode=RobustMode.PERCENTILE_90,
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"
        # P90 should be <= worst case
        assert resp.robust_solution.objective_value <= resp.metrics.worst_case_objective

    def test_regret_minimization_mode(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=50,
                ),
            ],
            mode=RobustMode.REGRET_MINIMIZATION,
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"


class TestRoutingRobust:
    def test_demand_uncertainty(self):
        req = RobustRequest(
            solver_type=RobustSolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="locations[c1].demand",
                    min_value=5, max_value=25,
                ),
                UncertainParameter(
                    parameter_path="locations[c3].demand",
                    min_value=10, max_value=30,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=10,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"
        assert resp.metrics.feasibility_rate_pct > 0

    def test_capacity_uncertainty(self):
        req = RobustRequest(
            solver_type=RobustSolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="vehicles[v1].capacity",
                    min_value=20, max_value=40,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=10,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"


class TestPackingRobust:
    def test_weight_uncertainty(self):
        req = RobustRequest(
            solver_type=RobustSolverType.PACKING,
            solver_request=PACKING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="items[a].weight",
                    min_value=5, max_value=18,
                ),
                UncertainParameter(
                    parameter_path="items[c].weight",
                    min_value=15, max_value=28,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"

    def test_capacity_uncertainty(self):
        req = RobustRequest(
            solver_type=RobustSolverType.PACKING,
            solver_request=PACKING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="bins[box1].weight_capacity",
                    min_value=20, max_value=40,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"


class TestMetricsAndRecommendation:
    def test_price_of_robustness(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=60,
                ),
            ],
            num_scenarios=15,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.metrics.price_of_robustness_pct >= 0
        assert resp.metrics.worst_case_objective >= resp.metrics.best_case_objective

    def test_feasibility_rate(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=50,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert 0 <= resp.metrics.feasibility_rate_pct <= 100

    def test_recommendation_generated(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=50,
                ),
            ],
            num_scenarios=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert len(resp.recommendation) > 0

    def test_std_dev_and_percentiles(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=10, max_value=60,
                ),
            ],
            num_scenarios=20,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.metrics.objective_std_dev >= 0
        assert resp.metrics.percentile_90_objective >= resp.metrics.best_case_objective
        assert resp.metrics.percentile_95_objective >= resp.metrics.percentile_90_objective


class TestEdgeCases:
    def test_invalid_parameter_path(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[NONEXISTENT].tasks[cut].duration",
                    min_value=20, max_value=50,
                ),
            ],
            num_scenarios=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "error"

    def test_min_equals_max(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=30, max_value=30,
                ),
            ],
            num_scenarios=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.status == "completed"
        # All scenarios should give same result
        assert resp.metrics.objective_std_dev == 0

    def test_scenario_count_respected(self):
        req = RobustRequest(
            solver_type=RobustSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            uncertain_parameters=[
                UncertainParameter(
                    parameter_path="jobs[J1].tasks[cut].duration",
                    min_value=20, max_value=50,
                ),
            ],
            num_scenarios=7,
            max_solve_time_seconds=5,
        )
        resp = optimize_robust(req)
        assert resp.metrics.scenarios_evaluated == 7
