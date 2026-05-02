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


SMOKE_PAYLOAD = {
    "jobs": [
        {"job_id": "J1", "tasks": [{"task_id": "T1", "duration": 5,
                                     "eligible_machines": ["M1"]}]},
        {"job_id": "J2", "tasks": [{"task_id": "T2", "duration": 3,
                                     "eligible_machines": ["M1"]}]},
    ],
    "machines": [{"machine_id": "M1"}],
    "objective": "minimize_makespan",
    "time_limit_seconds": 5,
}


class OptimEngineSmokeUser(HttpUser):
    """Single-task smoke user. Calls /optimize_schedule with fixed payload."""

    wait_time = between(2, 5)  # seconds between tasks per user

    @task
    def schedule(self):
        if not ENGINE_API_KEY:
            raise RuntimeError("ENGINE_API_KEY_PROD env var not set")
        self.client.post(
            "/optimize_schedule",
            json=SMOKE_PAYLOAD,
            headers={"X-Engine-Key": ENGINE_API_KEY},
            name="/optimize_schedule",  # group all calls under one label in stats
        )
