"""
OptimEngine — Test Suite
Comprehensive tests for the scheduling solver and validator.

Tests cover:
  - Basic job shop scheduling (single machine per task)
  - Flexible job shop (multiple eligible machines)
  - Time windows and due dates
  - Machine availability constraints
  - Setup times
  - All objective types
  - Edge cases (single job, single machine, large instances)
  - Schedule validation (valid + invalid schedules)
  - API endpoints
"""

import sys
import os
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver.models import (
    ScheduleRequest, Job, Task, Machine, TimeWindow,
    ObjectiveType, SolverStatus,
    ValidateRequest, ScheduledTask,
)
from solver.engine import solve_schedule
from solver.validator import validate_schedule


# ═══════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════

def make_request(jobs_data, machines_data, objective="minimize_makespan", max_time=10):
    """Shorthand to build a ScheduleRequest from simplified data."""
    jobs = []
    for jd in jobs_data:
        tasks = []
        for td in jd["tasks"]:
            tasks.append(Task(
                task_id=td["id"],
                duration=td["dur"],
                eligible_machines=td["machines"],
                setup_time=td.get("setup", 0),
            ))
        jobs.append(Job(
            job_id=jd["id"],
            name=jd.get("name"),
            tasks=tasks,
            priority=jd.get("priority", 1),
            due_date=jd.get("due_date"),
            time_window=TimeWindow(**jd["tw"]) if "tw" in jd else None,
        ))
    
    machines = [Machine(
        machine_id=md["id"],
        name=md.get("name"),
        availability_start=md.get("avail_start", 0),
        availability_end=md.get("avail_end"),
    ) for md in machines_data]
    
    return ScheduleRequest(
        jobs=jobs,
        machines=machines,
        objective=ObjectiveType(objective),
        max_solve_time_seconds=max_time,
    )


passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


# ═══════════════════════════════════════════════
# 1. BASIC JOB SHOP
# ═══════════════════════════════════════════════

print("\n═══ 1. Basic Job Shop Scheduling ═══")

req = make_request(
    jobs_data=[
        {"id": "J1", "tasks": [
            {"id": "cut", "dur": 3, "machines": ["M1"]},
            {"id": "weld", "dur": 2, "machines": ["M2"]},
        ]},
        {"id": "J2", "tasks": [
            {"id": "cut", "dur": 2, "machines": ["M1"]},
            {"id": "weld", "dur": 4, "machines": ["M2"]},
        ]},
    ],
    machines_data=[{"id": "M1"}, {"id": "M2"}],
)

res = solve_schedule(req)

test("Status is optimal or feasible", res.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE), f"got {res.status}")
test("All 4 tasks scheduled", len(res.schedule) == 4, f"got {len(res.schedule)}")
test("Gantt has 4 entries", len(res.gantt) == 4, f"got {len(res.gantt)}")
test("Metrics computed", res.metrics is not None)
test("Makespan > 0", res.metrics.makespan > 0 if res.metrics else False)
test("2 job summaries", len(res.job_summaries) == 2, f"got {len(res.job_summaries)}")
test("2 machine utilizations", len(res.machine_utilization) == 2, f"got {len(res.machine_utilization)}")

# Verify no overlaps on each machine
for mid in ["M1", "M2"]:
    tasks_on_m = sorted([s for s in res.schedule if s.machine_id == mid], key=lambda t: t.start)
    no_overlap = all(tasks_on_m[i].end <= tasks_on_m[i+1].start for i in range(len(tasks_on_m)-1))
    test(f"No overlap on {mid}", no_overlap)

# Verify precedence
for jid in ["J1", "J2"]:
    cut = next(s for s in res.schedule if s.job_id == jid and s.task_id == "cut")
    weld = next(s for s in res.schedule if s.job_id == jid and s.task_id == "weld")
    test(f"Precedence {jid}: cut before weld", weld.start >= cut.end, f"cut.end={cut.end}, weld.start={weld.start}")


# ═══════════════════════════════════════════════
# 2. FLEXIBLE JOB SHOP (multiple eligible machines)
# ═══════════════════════════════════════════════

print("\n═══ 2. Flexible Job Shop ═══")

req_flex = make_request(
    jobs_data=[
        {"id": "J1", "tasks": [
            {"id": "op1", "dur": 3, "machines": ["M1", "M2"]},
            {"id": "op2", "dur": 2, "machines": ["M2", "M3"]},
        ]},
        {"id": "J2", "tasks": [
            {"id": "op1", "dur": 4, "machines": ["M1", "M2"]},
            {"id": "op2", "dur": 1, "machines": ["M3"]},
        ]},
        {"id": "J3", "tasks": [
            {"id": "op1", "dur": 2, "machines": ["M1", "M2", "M3"]},
        ]},
    ],
    machines_data=[{"id": "M1"}, {"id": "M2"}, {"id": "M3"}],
)

res_flex = solve_schedule(req_flex)
test("Flex: optimal/feasible", res_flex.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE))
test("Flex: 5 tasks scheduled", len(res_flex.schedule) == 5, f"got {len(res_flex.schedule)}")

# Verify each task is on an eligible machine
for st in res_flex.schedule:
    job = next(j for j in req_flex.jobs if j.job_id == st.job_id)
    task = next(t for t in job.tasks if t.task_id == st.task_id)
    test(f"Flex: {st.job_id}/{st.task_id} on eligible machine", st.machine_id in task.eligible_machines,
         f"assigned to {st.machine_id}, eligible: {task.eligible_machines}")


# ═══════════════════════════════════════════════
# 3. TIME WINDOWS
# ═══════════════════════════════════════════════

print("\n═══ 3. Time Windows ═══")

req_tw = make_request(
    jobs_data=[
        {"id": "J1", "tw": {"earliest_start": 5, "latest_end": 20}, "tasks": [
            {"id": "op1", "dur": 3, "machines": ["M1"]},
            {"id": "op2", "dur": 2, "machines": ["M1"]},
        ]},
        {"id": "J2", "tw": {"earliest_start": 0, "latest_end": 15}, "tasks": [
            {"id": "op1", "dur": 4, "machines": ["M1"]},
        ]},
    ],
    machines_data=[{"id": "M1"}],
)

res_tw = solve_schedule(req_tw)
test("TW: optimal/feasible", res_tw.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE))

j1_tasks = [s for s in res_tw.schedule if s.job_id == "J1"]
j2_tasks = [s for s in res_tw.schedule if s.job_id == "J2"]
if j1_tasks:
    j1_start = min(t.start for t in j1_tasks)
    j1_end = max(t.end for t in j1_tasks)
    test("TW: J1 starts >= 5", j1_start >= 5, f"starts at {j1_start}")
    test("TW: J1 ends <= 20", j1_end <= 20, f"ends at {j1_end}")
if j2_tasks:
    j2_end = max(t.end for t in j2_tasks)
    test("TW: J2 ends <= 15", j2_end <= 15, f"ends at {j2_end}")


# ═══════════════════════════════════════════════
# 4. DUE DATES + TARDINESS
# ═══════════════════════════════════════════════

print("\n═══ 4. Due Dates & Tardiness Objective ═══")

req_tard = make_request(
    jobs_data=[
        {"id": "J1", "due_date": 5, "priority": 5, "tasks": [
            {"id": "op1", "dur": 3, "machines": ["M1"]},
        ]},
        {"id": "J2", "due_date": 5, "priority": 1, "tasks": [
            {"id": "op1", "dur": 3, "machines": ["M1"]},
        ]},
        {"id": "J3", "due_date": 10, "tasks": [
            {"id": "op1", "dur": 3, "machines": ["M1"]},
        ]},
    ],
    machines_data=[{"id": "M1"}],
    objective="minimize_total_tardiness",
)

res_tard = solve_schedule(req_tard)
test("Tard: optimal/feasible", res_tard.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE))
test("Tard: metrics has tardiness", res_tard.metrics is not None and res_tard.metrics.total_tardiness >= 0)

# High-priority J1 should be scheduled first (lower tardiness for high-priority)
if res_tard.schedule:
    j1 = next((s for s in res_tard.schedule if s.job_id == "J1"), None)
    j2 = next((s for s in res_tard.schedule if s.job_id == "J2"), None)
    if j1 and j2:
        test("Tard: high-priority J1 starts before J2", j1.start <= j2.start,
             f"J1 starts at {j1.start}, J2 at {j2.start}")


# ═══════════════════════════════════════════════
# 5. MACHINE AVAILABILITY
# ═══════════════════════════════════════════════

print("\n═══ 5. Machine Availability ═══")

req_avail = make_request(
    jobs_data=[
        {"id": "J1", "tasks": [{"id": "op1", "dur": 3, "machines": ["M1"]}]},
    ],
    machines_data=[{"id": "M1", "avail_start": 10, "avail_end": 50}],
)

res_avail = solve_schedule(req_avail)
test("Avail: optimal/feasible", res_avail.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE))
if res_avail.schedule:
    st = res_avail.schedule[0]
    test("Avail: starts >= 10", st.start >= 10, f"starts at {st.start}")
    test("Avail: ends <= 50", st.end <= 50, f"ends at {st.end}")


# ═══════════════════════════════════════════════
# 6. SETUP TIMES
# ═══════════════════════════════════════════════

print("\n═══ 6. Setup Times ═══")

req_setup = make_request(
    jobs_data=[
        {"id": "J1", "tasks": [{"id": "op1", "dur": 3, "machines": ["M1"], "setup": 2}]},
        {"id": "J2", "tasks": [{"id": "op1", "dur": 3, "machines": ["M1"], "setup": 1}]},
    ],
    machines_data=[{"id": "M1"}],
)

res_setup = solve_schedule(req_setup)
test("Setup: optimal/feasible", res_setup.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE))
if res_setup.schedule:
    # Each task's scheduled duration should include setup
    for st in res_setup.schedule:
        test(f"Setup: {st.job_id} duration includes setup", st.duration > 3 or st.duration == 4 or st.duration == 5,
             f"duration={st.duration}")


# ═══════════════════════════════════════════════
# 7. EDGE CASES
# ═══════════════════════════════════════════════

print("\n═══ 7. Edge Cases ═══")

# Single job, single machine, single task
req_minimal = make_request(
    jobs_data=[{"id": "J1", "tasks": [{"id": "op1", "dur": 5, "machines": ["M1"]}]}],
    machines_data=[{"id": "M1"}],
)
res_min = solve_schedule(req_minimal)
test("Edge: minimal instance", res_min.status == SolverStatus.OPTIMAL)
test("Edge: minimal makespan = 5", res_min.metrics.makespan == 5 if res_min.metrics else False)

# Invalid machine reference
req_bad = make_request(
    jobs_data=[{"id": "J1", "tasks": [{"id": "op1", "dur": 3, "machines": ["NONEXISTENT"]}]}],
    machines_data=[{"id": "M1"}],
)
res_bad = solve_schedule(req_bad)
test("Edge: unknown machine → error", res_bad.status == SolverStatus.ERROR)


# ═══════════════════════════════════════════════
# 8. MEDIUM-SCALE INSTANCE
# ═══════════════════════════════════════════════

print("\n═══ 8. Medium-Scale Instance (20 jobs × 5 machines) ═══")

import random
random.seed(42)

machines_med = [{"id": f"M{i}"} for i in range(5)]
jobs_med = []
for j in range(20):
    num_tasks = random.randint(2, 4)
    tasks = []
    for t in range(num_tasks):
        num_eligible = random.randint(1, 3)
        eligible = random.sample([f"M{i}" for i in range(5)], num_eligible)
        tasks.append({"id": f"t{t}", "dur": random.randint(1, 10), "machines": eligible})
    jobs_med.append({"id": f"J{j}", "tasks": tasks, "due_date": random.randint(20, 60)})

req_med = make_request(jobs_med, machines_med, max_time=20)
t0 = time.time()
res_med = solve_schedule(req_med)
elapsed = time.time() - t0

test("Medium: optimal/feasible", res_med.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE), f"got {res_med.status}")
test("Medium: solved in < 25s", elapsed < 25, f"took {elapsed:.1f}s")
test("Medium: all tasks scheduled", len(res_med.schedule) == sum(len(j.tasks) for j in req_med.jobs),
     f"expected {sum(len(j.tasks) for j in req_med.jobs)}, got {len(res_med.schedule)}")
print(f"     → Makespan: {res_med.metrics.makespan if res_med.metrics else '?'}, Solve time: {res_med.metrics.solve_time_seconds if res_med.metrics else '?'}s")


# ═══════════════════════════════════════════════
# 9. SCHEDULE VALIDATOR — VALID SCHEDULE
# ═══════════════════════════════════════════════

print("\n═══ 9. Schedule Validator — Valid ═══")

# Use the solution from test 1 to validate
val_req = ValidateRequest(
    schedule=res.schedule,
    jobs=req.jobs,
    machines=req.machines,
)
val_res = validate_schedule(val_req)
test("Validator: solver output is valid", val_res.is_valid, f"violations: {val_res.num_violations}")
test("Validator: 0 error violations", val_res.num_violations == 0 or all(v.severity == "warning" for v in val_res.violations))
test("Validator: metrics computed", val_res.metrics is not None)


# ═══════════════════════════════════════════════
# 10. SCHEDULE VALIDATOR — INVALID SCHEDULES
# ═══════════════════════════════════════════════

print("\n═══ 10. Schedule Validator — Invalid ═══")

# Overlap violation
val_overlap = ValidateRequest(
    schedule=[
        ScheduledTask(job_id="J1", task_id="cut", machine_id="M1", start=0, end=3, duration=3),
        ScheduledTask(job_id="J1", task_id="weld", machine_id="M2", start=3, end=5, duration=2),
        ScheduledTask(job_id="J2", task_id="cut", machine_id="M1", start=2, end=4, duration=2),  # overlaps with J1/cut!
        ScheduledTask(job_id="J2", task_id="weld", machine_id="M2", start=4, end=8, duration=4),
    ],
    jobs=req.jobs,
    machines=req.machines,
)
val_ov_res = validate_schedule(val_overlap)
test("Validator: detects overlap", not val_ov_res.is_valid)
test("Validator: overlap violation type", any(v.violation_type == "overlap" for v in val_ov_res.violations))

# Precedence violation
val_prec = ValidateRequest(
    schedule=[
        ScheduledTask(job_id="J1", task_id="weld", machine_id="M2", start=0, end=2, duration=2),  # weld before cut!
        ScheduledTask(job_id="J1", task_id="cut", machine_id="M1", start=3, end=6, duration=3),
        ScheduledTask(job_id="J2", task_id="cut", machine_id="M1", start=0, end=2, duration=2),
        ScheduledTask(job_id="J2", task_id="weld", machine_id="M2", start=2, end=6, duration=4),
    ],
    jobs=req.jobs,
    machines=req.machines,
)
val_pr_res = validate_schedule(val_prec)
test("Validator: detects precedence violation", not val_pr_res.is_valid)
test("Validator: precedence violation type", any(v.violation_type == "precedence" for v in val_pr_res.violations))

# Machine eligibility violation
val_elig = ValidateRequest(
    schedule=[
        ScheduledTask(job_id="J1", task_id="cut", machine_id="M2", start=0, end=3, duration=3),  # cut should be on M1!
        ScheduledTask(job_id="J1", task_id="weld", machine_id="M2", start=3, end=5, duration=2),
        ScheduledTask(job_id="J2", task_id="cut", machine_id="M1", start=0, end=2, duration=2),
        ScheduledTask(job_id="J2", task_id="weld", machine_id="M2", start=5, end=9, duration=4),
    ],
    jobs=req.jobs,
    machines=req.machines,
)
val_el_res = validate_schedule(val_elig)
test("Validator: detects machine eligibility violation", not val_el_res.is_valid)
test("Validator: eligibility violation type", any(v.violation_type == "machine_eligibility" for v in val_el_res.violations))


# ═══════════════════════════════════════════════
# 11. ALL OBJECTIVES
# ═══════════════════════════════════════════════

print("\n═══ 11. All Objective Types ═══")

for obj in ObjectiveType:
    req_obj = make_request(
        jobs_data=[
            {"id": "J1", "due_date": 8, "tasks": [
                {"id": "t1", "dur": 3, "machines": ["M1"]},
                {"id": "t2", "dur": 2, "machines": ["M2"]},
            ]},
            {"id": "J2", "due_date": 10, "tasks": [
                {"id": "t1", "dur": 4, "machines": ["M1", "M2"]},
            ]},
        ],
        machines_data=[{"id": "M1"}, {"id": "M2"}],
        objective=obj.value,
    )
    res_obj = solve_schedule(req_obj)
    test(f"Objective {obj.value}: solved", res_obj.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE), f"got {res_obj.status}")


# ═══════════════════════════════════════════════
# 12. COSMETICS MANUFACTURING SCENARIO
# ═══════════════════════════════════════════════

print("\n═══ 12. Real-World: Cosmetics Manufacturing ═══")

req_cosm = make_request(
    jobs_data=[
        {"id": "CREAM-001", "name": "Moisturizing Cream Batch A", "due_date": 480, "priority": 8, "tasks": [
            {"id": "dosaggio", "dur": 45, "machines": ["DOSATORE-1", "DOSATORE-2"]},
            {"id": "lottatura", "dur": 120, "machines": ["TURBOEMUL-1"]},
            {"id": "astucciatura", "dur": 60, "machines": ["ASTUCCIATRICE-1", "ASTUCCIATRICE-2"]},
        ]},
        {"id": "SERUM-002", "name": "Anti-Age Serum", "due_date": 360, "priority": 10, "tasks": [
            {"id": "dosaggio", "dur": 30, "machines": ["DOSATORE-1"]},
            {"id": "lottatura", "dur": 90, "machines": ["TURBOEMUL-1", "TURBOEMUL-2"]},
            {"id": "riempimento", "dur": 45, "machines": ["RIEMPITRICE-1"]},
        ]},
        {"id": "SHAMPOO-003", "name": "Volumizing Shampoo", "due_date": 600, "priority": 5, "tasks": [
            {"id": "dosaggio", "dur": 60, "machines": ["DOSATORE-1", "DOSATORE-2"]},
            {"id": "lottatura", "dur": 150, "machines": ["TURBOEMUL-2"]},
            {"id": "riempimento", "dur": 30, "machines": ["RIEMPITRICE-1"]},
            {"id": "astucciatura", "dur": 40, "machines": ["ASTUCCIATRICE-1"]},
        ]},
        {"id": "LOTION-004", "name": "Body Lotion Premium", "due_date": 500, "priority": 7, "tasks": [
            {"id": "dosaggio", "dur": 50, "machines": ["DOSATORE-2"]},
            {"id": "lottatura", "dur": 100, "machines": ["TURBOEMUL-1", "TURBOEMUL-2"]},
            {"id": "riempimento", "dur": 55, "machines": ["RIEMPITRICE-1"]},
            {"id": "astucciatura", "dur": 35, "machines": ["ASTUCCIATRICE-1", "ASTUCCIATRICE-2"]},
        ]},
    ],
    machines_data=[
        {"id": "DOSATORE-1", "name": "Dosatore Polveri A"},
        {"id": "DOSATORE-2", "name": "Dosatore Polveri B"},
        {"id": "TURBOEMUL-1", "name": "Turboemulsore 500L"},
        {"id": "TURBOEMUL-2", "name": "Turboemulsore 1000L"},
        {"id": "RIEMPITRICE-1", "name": "Riempitrice Automatica"},
        {"id": "ASTUCCIATRICE-1", "name": "Astucciatrice Linea 1"},
        {"id": "ASTUCCIATRICE-2", "name": "Astucciatrice Linea 2"},
    ],
    objective="minimize_total_tardiness",
)

res_cosm = solve_schedule(req_cosm)
test("Cosmetics: optimal/feasible", res_cosm.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE))
test("Cosmetics: all 14 tasks scheduled", len(res_cosm.schedule) == 14, f"got {len(res_cosm.schedule)}")

if res_cosm.metrics:
    test("Cosmetics: solve time < 5s", res_cosm.metrics.solve_time_seconds < 5)
    print(f"     → Makespan: {res_cosm.metrics.makespan} min")
    print(f"     → Total tardiness: {res_cosm.metrics.total_tardiness} min")
    print(f"     → On-time: {res_cosm.metrics.num_on_time}/{len(req_cosm.jobs)}")
    print(f"     → Avg utilization: {res_cosm.metrics.avg_machine_utilization_pct}%")

# Print Gantt-style summary
if res_cosm.schedule:
    print("\n     Schedule summary:")
    for m in req_cosm.machines:
        tasks_on_m = sorted([s for s in res_cosm.schedule if s.machine_id == m.machine_id], key=lambda t: t.start)
        if tasks_on_m:
            task_str = " → ".join(f"{t.job_id}/{t.task_id}[{t.start}-{t.end}]" for t in tasks_on_m)
            print(f"     {m.name or m.machine_id}: {task_str}")


# ═══════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════

print(f"\n{'═'*50}")
print(f"  Results: {passed} passed, {failed} failed, {passed+failed} total")
print(f"{'═'*50}")

if failed > 0:
    sys.exit(1)
else:
    print("  🎉 All tests passed!")
