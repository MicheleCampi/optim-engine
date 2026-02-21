"""
OptimEngine — Schedule Validator
Validates an existing schedule against the original constraints.

This is the second MCP tool: agents can verify schedules (manual or generated)
and get detailed violation reports + improvement suggestions.
"""

import collections
from .models import (
    ValidateRequest, ValidateResponse, ValidationViolation,
    ScheduledTask, Job, Machine, ScheduleMetrics,
    JobSummary, MachineUtilization,
)
from .engine import _compute_job_summaries, _compute_machine_utilization, _compute_metrics


def validate_schedule(request: ValidateRequest) -> ValidateResponse:
    """
    Validate a schedule against jobs/machines constraints.
    
    Checks:
      1. Machine eligibility (task assigned to an eligible machine)
      2. No overlaps (no two tasks overlap on the same machine)
      3. Precedence (tasks within a job respect order)
      4. Time windows (job starts/ends within allowed windows)
      5. Machine availability (tasks within machine availability windows)
      6. Consistency (start + duration == end)
    """
    violations: list[ValidationViolation] = []
    suggestions: list[str] = []
    
    # Build lookup maps
    job_map = {j.job_id: j for j in request.jobs}
    machine_map = {m.machine_id: m for m in request.machines}
    machine_ids = set(machine_map.keys())
    
    task_lookup: dict[tuple[str, str], ScheduledTask] = {}
    for st in request.schedule:
        task_lookup[(st.job_id, st.task_id)] = st
    
    # ── 1. Consistency check ──
    for st in request.schedule:
        if st.start + st.duration != st.end:
            violations.append(ValidationViolation(
                violation_type="consistency",
                severity="error",
                description=f"Task {st.job_id}/{st.task_id}: start({st.start}) + duration({st.duration}) != end({st.end})",
                affected_tasks=[f"{st.job_id}/{st.task_id}"],
            ))
    
    # ── 2. Machine existence ──
    for st in request.schedule:
        if st.machine_id not in machine_ids:
            violations.append(ValidationViolation(
                violation_type="unknown_machine",
                severity="error",
                description=f"Task {st.job_id}/{st.task_id} assigned to unknown machine '{st.machine_id}'",
                affected_tasks=[f"{st.job_id}/{st.task_id}"],
            ))
    
    # ── 3. Machine eligibility ──
    for st in request.schedule:
        job = job_map.get(st.job_id)
        if not job:
            violations.append(ValidationViolation(
                violation_type="unknown_job",
                severity="error",
                description=f"Scheduled task references unknown job '{st.job_id}'",
                affected_tasks=[f"{st.job_id}/{st.task_id}"],
            ))
            continue
        
        task_def = next((t for t in job.tasks if t.task_id == st.task_id), None)
        if not task_def:
            violations.append(ValidationViolation(
                violation_type="unknown_task",
                severity="error",
                description=f"Job '{st.job_id}' has no task '{st.task_id}'",
                affected_tasks=[f"{st.job_id}/{st.task_id}"],
            ))
            continue
        
        if st.machine_id not in task_def.eligible_machines:
            violations.append(ValidationViolation(
                violation_type="machine_eligibility",
                severity="error",
                description=f"Task {st.job_id}/{st.task_id} assigned to machine '{st.machine_id}' but eligible machines are {task_def.eligible_machines}",
                affected_tasks=[f"{st.job_id}/{st.task_id}"],
            ))
    
    # ── 4. No-overlap per machine ──
    tasks_by_machine: dict[str, list[ScheduledTask]] = collections.defaultdict(list)
    for st in request.schedule:
        tasks_by_machine[st.machine_id].append(st)
    
    for mid, tasks in tasks_by_machine.items():
        sorted_tasks = sorted(tasks, key=lambda t: t.start)
        for i in range(len(sorted_tasks) - 1):
            a = sorted_tasks[i]
            b = sorted_tasks[i + 1]
            if a.end > b.start:
                violations.append(ValidationViolation(
                    violation_type="overlap",
                    severity="error",
                    description=f"Machine '{mid}': task {a.job_id}/{a.task_id} ends at {a.end} but {b.job_id}/{b.task_id} starts at {b.start}",
                    affected_tasks=[f"{a.job_id}/{a.task_id}", f"{b.job_id}/{b.task_id}"],
                ))
    
    # ── 5. Precedence within jobs ──
    for job in request.jobs:
        for i in range(len(job.tasks) - 1):
            t1_id = job.tasks[i].task_id
            t2_id = job.tasks[i + 1].task_id
            st1 = task_lookup.get((job.job_id, t1_id))
            st2 = task_lookup.get((job.job_id, t2_id))
            if st1 and st2 and st2.start < st1.end:
                violations.append(ValidationViolation(
                    violation_type="precedence",
                    severity="error",
                    description=f"Job '{job.job_id}': task '{t2_id}' starts at {st2.start} before predecessor '{t1_id}' ends at {st1.end}",
                    affected_tasks=[f"{job.job_id}/{t1_id}", f"{job.job_id}/{t2_id}"],
                ))
    
    # ── 6. Time windows ──
    for job in request.jobs:
        if not job.time_window:
            continue
        first_st = task_lookup.get((job.job_id, job.tasks[0].task_id))
        last_st = task_lookup.get((job.job_id, job.tasks[-1].task_id))
        
        if first_st and job.time_window.earliest_start > 0 and first_st.start < job.time_window.earliest_start:
            violations.append(ValidationViolation(
                violation_type="time_window",
                severity="error",
                description=f"Job '{job.job_id}' starts at {first_st.start} before earliest_start {job.time_window.earliest_start}",
                affected_tasks=[f"{job.job_id}/{job.tasks[0].task_id}"],
            ))
        if last_st and job.time_window.latest_end is not None and last_st.end > job.time_window.latest_end:
            violations.append(ValidationViolation(
                violation_type="time_window",
                severity="error",
                description=f"Job '{job.job_id}' ends at {last_st.end} after latest_end {job.time_window.latest_end}",
                affected_tasks=[f"{job.job_id}/{job.tasks[-1].task_id}"],
            ))
    
    # ── 7. Machine availability ──
    for st in request.schedule:
        m = machine_map.get(st.machine_id)
        if not m:
            continue
        if st.start < m.availability_start:
            violations.append(ValidationViolation(
                violation_type="machine_availability",
                severity="error",
                description=f"Task {st.job_id}/{st.task_id} starts at {st.start} before machine '{m.machine_id}' is available at {m.availability_start}",
                affected_tasks=[f"{st.job_id}/{st.task_id}"],
            ))
        if m.availability_end is not None and st.end > m.availability_end:
            violations.append(ValidationViolation(
                violation_type="machine_availability",
                severity="error",
                description=f"Task {st.job_id}/{st.task_id} ends at {st.end} after machine '{m.machine_id}' availability ends at {m.availability_end}",
                affected_tasks=[f"{st.job_id}/{st.task_id}"],
            ))
    
    # ── 8. Missing tasks (warnings) ──
    for job in request.jobs:
        for task in job.tasks:
            if (job.job_id, task.task_id) not in task_lookup:
                violations.append(ValidationViolation(
                    violation_type="missing_task",
                    severity="warning",
                    description=f"Task {job.job_id}/{task.task_id} is not in the schedule",
                    affected_tasks=[f"{job.job_id}/{task.task_id}"],
                ))
    
    # ── Compute metrics on the provided schedule ──
    metrics = None
    if not any(v.severity == "error" for v in violations):
        try:
            job_summaries = _compute_job_summaries(request.jobs, request.schedule)
            total_span = max((st.end for st in request.schedule), default=0)
            machine_utils = _compute_machine_utilization(request.machines, request.schedule, total_span)
            metrics = _compute_metrics(job_summaries, machine_utils, 0.0)
        except Exception:
            pass
    
    # ── Generate improvement suggestions ──
    if not violations:
        # Check for idle gaps
        for mid, tasks in tasks_by_machine.items():
            sorted_tasks = sorted(tasks, key=lambda t: t.start)
            total_idle = 0
            for i in range(len(sorted_tasks) - 1):
                gap = sorted_tasks[i + 1].start - sorted_tasks[i].end
                if gap > 0:
                    total_idle += gap
            if total_idle > 0 and len(sorted_tasks) > 1:
                suggestions.append(
                    f"Machine '{mid}' has {total_idle} time units of idle gaps between tasks. Consider compacting."
                )
        
        # Check utilization imbalance
        if tasks_by_machine:
            loads = {mid: sum(t.duration for t in tasks) for mid, tasks in tasks_by_machine.items()}
            if loads:
                max_load = max(loads.values())
                min_load = min(loads.values()) if len(loads) > 1 else max_load
                if max_load > 0 and min_load / max_load < 0.5:
                    suggestions.append(
                        f"Load imbalance detected: busiest machine has {max_load} time units, lightest has {min_load}. Consider rebalancing."
                    )
        
        # Check tardiness
        for job in request.jobs:
            if job.due_date is not None:
                last_st = task_lookup.get((job.job_id, job.tasks[-1].task_id))
                if last_st and last_st.end > job.due_date:
                    suggestions.append(
                        f"Job '{job.job_id}' is {last_st.end - job.due_date} time units late (due: {job.due_date}, ends: {last_st.end})."
                    )
    
    errors = [v for v in violations if v.severity == "error"]
    
    return ValidateResponse(
        is_valid=len(errors) == 0,
        num_violations=len(violations),
        violations=violations,
        metrics=metrics,
        improvement_suggestions=suggestions,
    )
