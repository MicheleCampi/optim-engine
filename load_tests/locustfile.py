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
import random
from locust import HttpUser, task, between

from load_tests.generators.schedule import random_schedule
from load_tests.generators.routing import random_routing
from load_tests.generators.packing import random_packing


ENGINE_API_KEY = os.environ.get("ENGINE_API_KEY_PROD", "")


# ─── Size class distribution ───
# Each call picks a size class according to this mix:
#   60% small  → fast solves, mostly OPTIMAL
#   30% medium → real solves, mix OPTIMAL/FEASIBLE
#   10% large  → heavy solves, mostly FEASIBLE/TIMEOUT
# This produces a realistic dispersion across solver_duration_seconds buckets.
SIZE_WEIGHTS = [("small", 0.60), ("medium", 0.30), ("large", 0.10)]


def _pick_size() -> str:
    r = random.random()
    cumulative = 0.0
    for size, weight in SIZE_WEIGHTS:
        cumulative += weight
        if r <= cumulative:
            return size
    return "small"  # fallback


class OptimEngineSmokeUser(HttpUser):
    """
    Multi-solver load test user using parametric problem generators.

    Task weights reflect realistic domain mix:
      - schedule: 4 (most common in manufacturing)
      - routing:  2 (logistics use case)
      - packing:  1 (specialized bin-packing scenarios)

    Each task additionally rolls a size class (60/30/10 small/medium/large)
    so the load test produces a distribution of solver outcomes — not all
    OPTIMAL, not all TIMEOUT.
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
        self._post("/optimize_schedule", random_schedule(_pick_size()))

    @task(2)
    def routing(self):
        self._post("/optimize_routing", random_routing(_pick_size()))

    @task(1)
    def packing(self):
        self._post("/optimize_packing", random_packing(_pick_size()))
