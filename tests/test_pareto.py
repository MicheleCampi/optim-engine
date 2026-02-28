"""Tests for OptimEngine Multi-objective Pareto Optimization."""

import pytest
from pareto.models import (
    ParetoRequest, ParetoSolverType, ObjectiveSpec,
)
from pareto.engine import optimize_pareto


SCHEDULING_REQUEST = {
    "jobs": [
        {
            "job_id": "J1",
            "tasks": [
                {"task_id": "cut", "duration": 30, "eligible_machines": ["M1", "M2"]},
                {"task_id": "weld", "duration": 20, "eligible_machines": ["M2"]},
            ],
            "due_date": 60,
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
                {"task_id": "cut", "duration": 15, "eligible_machines": ["M1", "M2"]},
                {"task_id": "weld", "duration": 35, "eligible_machines": ["M2"]},
            ],
            "due_date": 90,
        },
    ],
    "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
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
        {"vehicle_id": "v1", "capacity": 50},
        {"vehicle_id": "v2", "capacity": 50},
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
}

PACKING_REQUEST = {
    "items": [
        {"item_id": "a", "weight": 10, "value": 100},
        {"item_id": "b", "weight": 15, "value": 200},
        {"item_id": "c", "weight": 20, "value": 150},
        {"item_id": "d", "weight": 8, "value": 90},
    ],
    "bins": [
        {"bin_id": "box1", "weight_capacity": 30},
        {"bin_id": "box2", "weight_capacity": 30},
        {"bin_id": "box3", "weight_capacity": 30},
    ],
}


class TestSchedulingPareto:
    def test_two_objectives(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"
        assert len(resp.frontier) >= 1
        assert resp.metrics.points_on_frontier >= 1

    def test_extreme_points_included(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=6,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"
        extreme = [p for p in resp.frontier if p.is_extreme]
        assert len(extreme) >= 1

    def test_trade_off_analysis(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=8,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"
        assert len(resp.trade_offs) >= 1
        to = resp.trade_offs[0]
        assert to.relationship in ("conflict", "synergy", "independent")

    def test_weighted_objectives(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan", weight=3.0),
                ObjectiveSpec(name="minimize_total_tardiness", weight=1.0),
            ],
            num_points=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"

    def test_three_objectives(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
                ObjectiveSpec(name="minimize_total_completion_time"),
            ],
            num_points=6,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"
        assert len(resp.trade_offs) >= 3  # 3 pairs


class TestRoutingPareto:
    def test_distance_vs_vehicles(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.ROUTING,
            solver_request=ROUTING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_total_distance"),
                ObjectiveSpec(name="minimize_num_vehicles"),
            ],
            num_points=5,
            max_solve_time_seconds=10,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"
        assert resp.metrics.total_solves >= 3


class TestPackingPareto:
    def test_bins_vs_value(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.PACKING,
            solver_request=PACKING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_bins"),
                ObjectiveSpec(name="maximize_value"),
            ],
            num_points=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"


class TestMetrics:
    def test_spread_computed(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=6,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert "minimize_makespan" in resp.metrics.spread
        assert "minimize_total_tardiness" in resp.metrics.spread

    def test_recommendation_generated(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert len(resp.recommendation) > 0

    def test_frontier_not_larger_than_generated(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=10,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.metrics.points_on_frontier <= resp.metrics.points_feasible


class TestEdgeCases:
    def test_invalid_objective(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="nonexistent_objective"),
            ],
            num_points=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "error"

    def test_min_points(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=3,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.status == "completed"
        assert resp.metrics.points_generated == 3

    def test_solve_count(self):
        req = ParetoRequest(
            solver_type=ParetoSolverType.SCHEDULING,
            solver_request=SCHEDULING_REQUEST,
            objectives=[
                ObjectiveSpec(name="minimize_makespan"),
                ObjectiveSpec(name="minimize_total_tardiness"),
            ],
            num_points=5,
            max_solve_time_seconds=5,
        )
        resp = optimize_pareto(req)
        assert resp.metrics.total_solves == 5
