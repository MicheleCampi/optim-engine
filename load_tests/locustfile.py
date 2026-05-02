"""
OptimEngine — minimal load test (smoke).

Usage:
    export ENGINE_API_KEY_PROD="..."
    locust -f load_tests/locustfile.py \\
        --host=https://optim-engine-production.up.railway.app \\
        --users=1 --spawn-rate=1 --run-time=30s --headless

Smoke scope: hits /optimize_schedule with a small fixed payload.
Real workload generators (size mix, multi-solver, INFEASIBLE injection)
are out of scope — see Phase B in the May 23 plan.
"""
import os
from locust import HttpUser, task, between


ENGINE_API_KEY = os.environ.get("ENGINE_API_KEY_PROD", "")


# ─── Fixed smoke payloads ───
# Real workload generators (size mix, INFEASIBLE injection) deferred to Phase B.

SCHEDULE_PAYLOAD = {
    "jobs": [
        {"job_id": "J1", "tasks": [{"task_id": "T1", "duration": 5,
                                     "eligible_machines": ["M1"]}]},
        {"job_id": "J2", "tasks": [{"task_id": "T2", "duration": 3,
                                     "eligible_machines": ["M1"]}]},
    ],
    "machines": [{"machine_id": "M1"}],
    "objective": "minimize_makespan",
    "max_solve_time_seconds": 5,
}

ROUTING_PAYLOAD = {
    "depot_id": "depot",
    "vehicles": [
        {"vehicle_id": "V1", "capacity": 100,
         "start_location": "depot", "end_location": "depot"},
    ],
    "locations": [
        {"location_id": "depot", "latitude": 44.80, "longitude": 10.30, "demand": 0},
        {"location_id": "L1",    "latitude": 44.81, "longitude": 10.31, "demand": 20},
        {"location_id": "L2",    "latitude": 44.82, "longitude": 10.32, "demand": 30},
    ],
    "max_solve_time_seconds": 5,
}

PACKING_PAYLOAD = {
    "items": [
        {"item_id": "I1", "weight": 5, "value": 10},
        {"item_id": "I2", "weight": 8, "value": 15},
        {"item_id": "I3", "weight": 3, "value": 7},
    ],
    "bins": [
        {"bin_id": "B1", "weight_capacity": 10},
        {"bin_id": "B2", "weight_capacity": 15},
    ],
    "max_solve_time_seconds": 5,
}


class OptimEngineSmokeUser(HttpUser):
    """
    Multi-solver smoke user. Calls L1 endpoints with fixed payloads.

    Task weights reflect a rough realistic mix:
      - schedule: 4 (most common in manufacturing)
      - routing:  2 (logistics use case)
      - packing:  1 (specialized bin-packing scenarios)
    """

    wait_time = between(2, 5)  # seconds between tasks per user

    def _post(self, path: str, payload: dict) -> None:
        if not ENGINE_API_KEY:
            raise RuntimeError("ENGINE_API_KEY_PROD env var not set")
        self.client.post(
            path,
            json=payload,
            headers={"X-Engine-Key": ENGINE_API_KEY},
            name=path,  # group calls per endpoint in Locust stats
        )

    @task(4)
    def schedule(self):
        self._post("/optimize_schedule", SCHEDULE_PAYLOAD)

    @task(2)
    def routing(self):
        self._post("/optimize_routing", ROUTING_PAYLOAD)

    @task(1)
    def packing(self):
        self._post("/optimize_packing", PACKING_PAYLOAD)
