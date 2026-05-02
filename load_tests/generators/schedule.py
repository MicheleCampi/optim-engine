"""
Random schedule problem generator for load testing.

Three size classes calibrated empirically against OptimEngine on Railway:
  - small:  ~50-200ms solve time, mostly OPTIMAL
  - medium: ~1-5s solve time, mix OPTIMAL/FEASIBLE
  - large:  ~5-15s solve time, mostly FEASIBLE/TIMEOUT (intentional)

Parametrization is intentional: load test must produce a *distribution* of
solver outcomes across the histogram buckets, not all-OPTIMAL or all-TIMEOUT.
"""
import random
from typing import Literal

SizeClass = Literal["small", "medium", "large"]

_SIZE_CONFIG = {
    "small":  {"jobs": (3, 6),   "tasks_per_job": (1, 2), "machines": (2, 3),
               "duration": (2, 8),   "time_limit": 5},
    "medium": {"jobs": (10, 20), "tasks_per_job": (2, 4), "machines": (3, 5),
               "duration": (3, 15),  "time_limit": 10},
    "large":  {"jobs": (30, 50), "tasks_per_job": (3, 6), "machines": (4, 7),
               "duration": (5, 25),  "time_limit": 15},
}

_OBJECTIVES = ["minimize_makespan", "minimize_total_tardiness"]


def random_schedule(size_class: SizeClass = "small") -> dict:
    """
    Build a randomized but feasible scheduling problem.

    Returns a dict matching ScheduleRequest schema. Always feasible by
    construction — we control infeasibility via separate generator if needed.
    """
    cfg = _SIZE_CONFIG[size_class]

    num_machines = random.randint(*cfg["machines"])
    machine_ids = [f"M{i+1}" for i in range(num_machines)]
    machines = [{"machine_id": mid} for mid in machine_ids]

    num_jobs = random.randint(*cfg["jobs"])
    jobs = []
    for j in range(num_jobs):
        num_tasks = random.randint(*cfg["tasks_per_job"])
        tasks = []
        for t in range(num_tasks):
            # Each task is eligible on a random non-empty subset of machines
            k = random.randint(1, num_machines)
            eligible = random.sample(machine_ids, k)
            tasks.append({
                "task_id":  f"T{j+1}_{t+1}",
                "duration": random.randint(*cfg["duration"]),
                "eligible_machines": eligible,
            })
        job = {"job_id": f"J{j+1}", "tasks": tasks}
        # 30% of jobs have a due_date — drives tardiness objective variance
        if random.random() < 0.30:
            # Loose due date (not too tight to force INFEASIBLE)
            job["due_date"] = sum(t["duration"] for t in tasks) * random.randint(2, 4)
            job["priority"] = random.randint(1, 10)
        jobs.append(job)

    return {
        "jobs": jobs,
        "machines": machines,
        "objective": random.choice(_OBJECTIVES),
        "max_solve_time_seconds": cfg["time_limit"],
    }
