"""Tests for OptimEngine Sensitivity Analysis."""

import pytest
from sensitivity.models import (
    SensitivityRequest, SolverType, ParameterSpec, PerturbationMode,
)
from sensitivity.engine import analyze_sensitivity


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
        {
            "job_id": "J3",
            "tasks": [
                {"task_id": "cut", "duration": 20, "eligible_machines": ["M1", "M2"]},
                {"task_id": "weld", "duration": 35, "eligible_machines": ["M2"]},
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
        {"item_id": "d", "weight": 8, "value": 80},
    ],
    "bins": [
        {"bin_id": "box1", "weight_capacity": 30},
        {"bin_id": "box2", "weight_capacity": 30},
    ],
    "objective": "minimize_bins",
}


class TestSchedulingSensitivity:
    def test_auto_detect_parameters(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        assert resp.metrics.parameters_analyzed > 0
        assert resp.baseline_objective > 0

    def test_specific_parameter(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="jobs[J1].tasks[cut].duration",
                perturbations=[-50, -20, 20, 50, 100],
            )],
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        assert len(resp.parameters) == 1
        assert resp.parameters[0].parameter_name == "jobs[J1].tasks[cut].duration"
        assert resp.parameters[0].baseline_value == 30
        assert len(resp.parameters[0].perturbation_results) >= 4

    def test_sensitivity_score_computed(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="jobs[J2].tasks[cut].duration",
            )],
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        p = resp.parameters[0]
        assert p.sensitivity_score >= 0
        assert p.elasticity >= 0
        assert p.direction in ("increase_hurts", "decrease_hurts", "symmetric")

    def test_risk_ranking(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert len(resp.risk_ranking) > 0
        # Ranking should be sorted by sensitivity (descending)
        scores = [p.sensitivity_score for p in resp.parameters]
        assert scores == sorted(scores, reverse=True)

    def test_due_date_sensitivity(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="jobs[J1].due_date",
                perturbations=[-30, -20, -10, 10, 20, 30],
            )],
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"


class TestRoutingSensitivity:
    def test_auto_detect(self):
        req = SensitivityRequest(
            solver_type=SolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            max_solve_time_seconds=10,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        assert resp.metrics.parameters_analyzed > 0
        assert resp.baseline_objective_name == "total_distance"

    def test_demand_perturbation(self):
        req = SensitivityRequest(
            solver_type=SolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="locations[c3].demand",
                perturbations=[-50, 50, 100],
            )],
            max_solve_time_seconds=10,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        assert len(resp.parameters) == 1

    def test_capacity_perturbation(self):
        req = SensitivityRequest(
            solver_type=SolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="vehicles[v1].capacity",
                perturbations=[-30, -20, 20, 30],
            )],
            max_solve_time_seconds=10,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"


class TestPackingSensitivity:
    def test_auto_detect(self):
        req = SensitivityRequest(
            solver_type=SolverType.PACKING,
            solver_request=PACKING_REQUEST,
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        assert resp.metrics.parameters_analyzed > 0

    def test_weight_perturbation(self):
        req = SensitivityRequest(
            solver_type=SolverType.PACKING,
            solver_request=PACKING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="items[c].weight",
                perturbations=[-50, -25, 25, 50, 100],
            )],
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        assert len(resp.parameters) == 1

    def test_bin_capacity_perturbation(self):
        req = SensitivityRequest(
            solver_type=SolverType.PACKING,
            solver_request=PACKING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="bins[box1].weight_capacity",
                perturbations=[-30, -15, 15, 30],
            )],
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"


class TestMetrics:
    def test_metrics_populated(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        m = resp.metrics
        assert m.parameters_analyzed > 0
        assert m.total_solves > 1
        assert m.baseline_objective > 0
        assert m.solve_time_seconds > 0
        assert m.most_sensitive_parameter is not None

    def test_critical_count(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        actual_critical = sum(1 for p in resp.parameters if p.critical)
        assert resp.metrics.critical_parameters == actual_critical


class TestEdgeCases:
    def test_invalid_parameter_path(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="jobs[NONEXISTENT].tasks[cut].duration",
            )],
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        # Should complete but with 0 parameters analyzed
        assert resp.status in ("completed", "error")

    def test_absolute_perturbation_mode(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            parameters=[ParameterSpec(
                parameter_path="jobs[J1].tasks[cut].duration",
                perturbations=[-10, -5, 5, 10, 20],
                mode=PerturbationMode.ABSOLUTE,
            )],
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        assert resp.status == "completed"
        # Check absolute perturbation applied correctly
        for pr in resp.parameters[0].perturbation_results:
            if pr.perturbation_value == 10:
                assert pr.new_param_value == 40  # 30 + 10

    def test_risk_summary_generated(self):
        req = SensitivityRequest(
            solver_type=SolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            max_solve_time_seconds=5,
        )
        resp = analyze_sensitivity(req)
        for p in resp.parameters:
            assert len(p.risk_summary) > 0
