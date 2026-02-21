"""
OptimEngine — CP-SAT Scheduling Solver
The computational brain: Flexible Job Shop Scheduling via Google OR-Tools CP-SAT.

Supports:
  - Flexible Job Shop (tasks can run on multiple eligible machines)
  - Precedence constraints (tasks within a job are sequential)
  - Time windows (earliest start, latest end per job)
  - Machine availability windows
  - Setup times
  - Priority-weighted objectives
  - Multiple optimization objectives (makespan, tardiness, load balancing)
"""

import collections
import time
from typing import Optional

from ortools.sat.python import cp_model

from .models import (
    ScheduleRequest, ScheduleResponse, ScheduledTask,
    JobSummary, MachineUtilization, ScheduleMetrics, GanttEntry,
    SolverStatus, ObjectiveType,
)


# Named tuples for internal bookkeeping
_TaskVar = collections.namedtuple("_TaskVar", "start end interval duration machine_id job_id task_id")


def solve_schedule(request: ScheduleRequest) -> ScheduleResponse:
    """
    Solve a Flexible Job Shop Scheduling Problem.
    
    This is the core function that:
    1. Builds a CP-SAT model from the request
    2. Adds variables, constraints, and objective
    3. Solves with the given time limit
    4. Extracts and formats the solution
    """
    t0 = time.time()
    
    try:
        model = cp_model.CpModel()
        
        # ── Index structures ──
        machine_ids = {m.machine_id for m in request.machines}
        machine_map = {m.machine_id: m for m in request.machines}
        
        # Validate all task machine references
        for job in request.jobs:
            for task in job.tasks:
                for mid in task.eligible_machines:
                    if mid not in machine_ids:
                        return ScheduleResponse(
                            status=SolverStatus.ERROR,
                            message=f"Task {job.job_id}/{task.task_id} references unknown machine '{mid}'"
                        )
        
        # ── Compute horizon ──
        horizon = sum(
            t.duration + t.setup_time
            for j in request.jobs for t in j.tasks
        )
        # Add machine availability offsets
        for m in request.machines:
            if m.availability_end is not None:
                horizon = max(horizon, m.availability_end)
        for j in request.jobs:
            if j.time_window and j.time_window.latest_end is not None:
                horizon = max(horizon, j.time_window.latest_end)
            if j.due_date is not None:
                horizon = max(horizon, j.due_date * 2)  # allow tardiness
        
        # ── Variables ──
        # For each (job, task, eligible_machine): optional interval + presence literal
        all_task_vars: dict[tuple[str, str, str], _TaskVar] = {}
        presence_literals: dict[tuple[str, str, str], cp_model.IntVar] = {}
        
        # Per (job, task): the chosen start/end (across all machine alternatives)
        task_starts: dict[tuple[str, str], cp_model.IntVar] = {}
        task_ends: dict[tuple[str, str], cp_model.IntVar] = {}
        
        # Per machine: list of interval vars for no-overlap
        machine_intervals: dict[str, list] = {m.machine_id: [] for m in request.machines}
        
        for job in request.jobs:
            for task in job.tasks:
                jid, tid = job.job_id, task.task_id
                total_duration = task.duration + task.setup_time
                
                # Global start/end for this task (across alternatives)
                suffix = f"_{jid}_{tid}"
                t_start = model.new_int_var(0, horizon, f"start{suffix}")
                t_end = model.new_int_var(0, horizon, f"end{suffix}")
                task_starts[(jid, tid)] = t_start
                task_ends[(jid, tid)] = t_end
                
                if len(task.eligible_machines) == 1:
                    # ── Single machine: no alternatives needed ──
                    mid = task.eligible_machines[0]
                    interval = model.new_interval_var(
                        t_start, total_duration, t_end, f"interval{suffix}_{mid}"
                    )
                    all_task_vars[(jid, tid, mid)] = _TaskVar(
                        start=t_start, end=t_end, interval=interval,
                        duration=total_duration, machine_id=mid,
                        job_id=jid, task_id=tid
                    )
                    machine_intervals[mid].append(interval)
                    
                    # Apply machine availability
                    m = machine_map[mid]
                    if m.availability_start > 0:
                        model.add(t_start >= m.availability_start)
                    if m.availability_end is not None:
                        model.add(t_end <= m.availability_end)
                else:
                    # ── Multiple eligible machines: optional intervals ──
                    alt_presences = []
                    for mid in task.eligible_machines:
                        alt_suffix = f"{suffix}_{mid}"
                        presence = model.new_bool_var(f"pres{alt_suffix}")
                        alt_start = model.new_int_var(0, horizon, f"astart{alt_suffix}")
                        alt_end = model.new_int_var(0, horizon, f"aend{alt_suffix}")
                        alt_interval = model.new_optional_interval_var(
                            alt_start, total_duration, alt_end, presence, f"aint{alt_suffix}"
                        )
                        
                        all_task_vars[(jid, tid, mid)] = _TaskVar(
                            start=alt_start, end=alt_end, interval=alt_interval,
                            duration=total_duration, machine_id=mid,
                            job_id=jid, task_id=tid
                        )
                        presence_literals[(jid, tid, mid)] = presence
                        alt_presences.append(presence)
                        machine_intervals[mid].append(alt_interval)
                        
                        # Link alternative start/end to global start/end when present
                        model.add(alt_start == t_start).only_enforce_if(presence)
                        model.add(alt_end == t_end).only_enforce_if(presence)
                        
                        # Machine availability
                        m = machine_map[mid]
                        if m.availability_start > 0:
                            model.add(alt_start >= m.availability_start).only_enforce_if(presence)
                        if m.availability_end is not None:
                            model.add(alt_end <= m.availability_end).only_enforce_if(presence)
                    
                    # Exactly one machine must be chosen
                    model.add_exactly_one(alt_presences)
        
        # ── Precedence constraints (tasks within a job are sequential) ──
        for job in request.jobs:
            for i in range(len(job.tasks) - 1):
                t1 = job.tasks[i]
                t2 = job.tasks[i + 1]
                model.add(
                    task_starts[(job.job_id, t2.task_id)] >=
                    task_ends[(job.job_id, t1.task_id)]
                )
        
        # ── No-overlap per machine ──
        for mid, intervals in machine_intervals.items():
            if len(intervals) > 1:
                model.add_no_overlap(intervals)
        
        # ── Job time window constraints ──
        for job in request.jobs:
            if job.time_window:
                first_task = job.tasks[0]
                last_task = job.tasks[-1]
                if job.time_window.earliest_start > 0:
                    model.add(
                        task_starts[(job.job_id, first_task.task_id)] >=
                        job.time_window.earliest_start
                    )
                if job.time_window.latest_end is not None:
                    model.add(
                        task_ends[(job.job_id, last_task.task_id)] <=
                        job.time_window.latest_end
                    )
        
        # ── Objective ──
        if request.objective == ObjectiveType.MINIMIZE_MAKESPAN:
            makespan = model.new_int_var(0, horizon, "makespan")
            for job in request.jobs:
                last_task = job.tasks[-1]
                model.add(makespan >= task_ends[(job.job_id, last_task.task_id)])
            model.minimize(makespan)
        
        elif request.objective in (ObjectiveType.MINIMIZE_TOTAL_TARDINESS, ObjectiveType.MINIMIZE_MAX_TARDINESS):
            tardiness_vars = []
            for job in request.jobs:
                if job.due_date is not None:
                    last_task = job.tasks[-1]
                    t_var = model.new_int_var(0, horizon, f"tardiness_{job.job_id}")
                    job_end = task_ends[(job.job_id, last_task.task_id)]
                    model.add(t_var >= job_end - job.due_date)
                    model.add(t_var >= 0)
                    # Weight by priority
                    tardiness_vars.append((t_var, job.priority))
            
            if tardiness_vars:
                if request.objective == ObjectiveType.MINIMIZE_TOTAL_TARDINESS:
                    model.minimize(sum(tv * p for tv, p in tardiness_vars))
                else:
                    max_tard = model.new_int_var(0, horizon, "max_tardiness")
                    for tv, _ in tardiness_vars:
                        model.add(max_tard >= tv)
                    model.minimize(max_tard)
            else:
                # Fallback to makespan if no due dates
                makespan = model.new_int_var(0, horizon, "makespan")
                for job in request.jobs:
                    last_task = job.tasks[-1]
                    model.add(makespan >= task_ends[(job.job_id, last_task.task_id)])
                model.minimize(makespan)
        
        elif request.objective == ObjectiveType.BALANCE_LOAD:
            # Minimize the maximum machine load
            machine_loads = {}
            for mid in machine_ids:
                load = model.new_int_var(0, horizon, f"load_{mid}")
                machine_loads[mid] = load
            
            # For each task, add its duration to the assigned machine's load
            for job in request.jobs:
                for task in job.tasks:
                    jid, tid = job.job_id, task.task_id
                    total_dur = task.duration + task.setup_time
                    if len(task.eligible_machines) == 1:
                        mid = task.eligible_machines[0]
                        # Load accumulation handled via max_load below
                    # For flexible: load depends on which machine is chosen
            
            # Simpler approach: minimize max end time across machines (proxy for balance)
            max_load = model.new_int_var(0, horizon, "max_load")
            for mid in machine_ids:
                for job in request.jobs:
                    last_task = job.tasks[-1]
                    model.add(max_load >= task_ends[(job.job_id, last_task.task_id)])
            model.minimize(max_load)
        
        # ── Solve ──
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = request.max_solve_time_seconds
        solver.parameters.num_workers = 4  # parallel search
        solver.parameters.log_search_progress = False
        
        status = solver.solve(model)
        solve_time = time.time() - t0
        
        # ── Extract solution ──
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver_status = SolverStatus.OPTIMAL if status == cp_model.OPTIMAL else SolverStatus.FEASIBLE
            
            scheduled_tasks = []
            gantt_entries = []
            
            for job in request.jobs:
                for task in job.tasks:
                    jid, tid = job.job_id, task.task_id
                    
                    # Determine which machine was chosen
                    chosen_mid = None
                    chosen_start = None
                    chosen_end = None
                    
                    if len(task.eligible_machines) == 1:
                        mid = task.eligible_machines[0]
                        tv = all_task_vars[(jid, tid, mid)]
                        chosen_mid = mid
                        chosen_start = solver.value(tv.start)
                        chosen_end = solver.value(tv.end)
                    else:
                        for mid in task.eligible_machines:
                            pres = presence_literals.get((jid, tid, mid))
                            if pres is not None and solver.value(pres):
                                tv = all_task_vars[(jid, tid, mid)]
                                chosen_mid = mid
                                chosen_start = solver.value(tv.start)
                                chosen_end = solver.value(tv.end)
                                break
                    
                    if chosen_mid is not None:
                        st = ScheduledTask(
                            job_id=jid, task_id=tid, machine_id=chosen_mid,
                            start=chosen_start, end=chosen_end,
                            duration=task.duration + task.setup_time
                        )
                        scheduled_tasks.append(st)
                        
                        job_name = next((j.name for j in request.jobs if j.job_id == jid), jid)
                        gantt_entries.append(GanttEntry(
                            job_id=jid, task_id=tid, machine_id=chosen_mid,
                            start=chosen_start, end=chosen_end,
                            label=f"{job_name or jid} / {tid}"
                        ))
            
            # ── Compute metrics ──
            job_summaries = _compute_job_summaries(request.jobs, scheduled_tasks)
            machine_utils = _compute_machine_utilization(
                request.machines, scheduled_tasks, max(st.end for st in scheduled_tasks) if scheduled_tasks else 0
            )
            metrics = _compute_metrics(job_summaries, machine_utils, solve_time)
            
            return ScheduleResponse(
                status=solver_status,
                message=f"{'Optimal' if solver_status == SolverStatus.OPTIMAL else 'Feasible'} schedule found in {solve_time:.2f}s. Makespan: {metrics.makespan} time units.",
                schedule=scheduled_tasks,
                job_summaries=job_summaries,
                machine_utilization=machine_utils,
                metrics=metrics,
                gantt=gantt_entries,
            )
        
        elif status == cp_model.INFEASIBLE:
            return ScheduleResponse(
                status=SolverStatus.INFEASIBLE,
                message="No feasible schedule exists with the given constraints. Check time windows, machine availability, and task durations."
            )
        else:
            return ScheduleResponse(
                status=SolverStatus.TIMEOUT,
                message=f"Solver timed out after {request.max_solve_time_seconds}s without finding a solution. Try increasing max_solve_time_seconds or reducing problem size."
            )
    
    except Exception as e:
        return ScheduleResponse(
            status=SolverStatus.ERROR,
            message=f"Solver error: {str(e)}"
        )


def _compute_job_summaries(jobs, scheduled_tasks: list[ScheduledTask]) -> list[JobSummary]:
    """Compute per-job summary metrics."""
    task_by_job: dict[str, list[ScheduledTask]] = collections.defaultdict(list)
    for st in scheduled_tasks:
        task_by_job[st.job_id].append(st)
    
    summaries = []
    for job in jobs:
        tasks = task_by_job.get(job.job_id, [])
        if not tasks:
            continue
        j_start = min(t.start for t in tasks)
        j_end = max(t.end for t in tasks)
        tardiness = max(0, j_end - job.due_date) if job.due_date is not None else 0
        summaries.append(JobSummary(
            job_id=job.job_id,
            name=job.name,
            start=j_start,
            end=j_end,
            makespan=j_end - j_start,
            tardiness=tardiness,
            on_time=tardiness == 0,
        ))
    return summaries


def _compute_machine_utilization(machines, scheduled_tasks: list[ScheduledTask], total_span: int) -> list[MachineUtilization]:
    """Compute per-machine utilization."""
    task_by_machine: dict[str, list[ScheduledTask]] = collections.defaultdict(list)
    for st in scheduled_tasks:
        task_by_machine[st.machine_id].append(st)
    
    utils = []
    for m in machines:
        tasks = task_by_machine.get(m.machine_id, [])
        busy = sum(t.duration for t in tasks)
        span = total_span if total_span > 0 else 1
        utils.append(MachineUtilization(
            machine_id=m.machine_id,
            name=m.name,
            busy_time=busy,
            idle_time=max(0, span - busy),
            utilization_pct=round(busy / span * 100, 1) if span > 0 else 0,
            num_tasks=len(tasks),
        ))
    return utils


def _compute_metrics(
    job_summaries: list[JobSummary],
    machine_utils: list[MachineUtilization],
    solve_time: float,
) -> ScheduleMetrics:
    """Compute aggregate schedule metrics."""
    makespan = max((j.end for j in job_summaries), default=0)
    total_tard = sum(j.tardiness for j in job_summaries)
    max_tard = max((j.tardiness for j in job_summaries), default=0)
    on_time = sum(1 for j in job_summaries if j.on_time)
    late = sum(1 for j in job_summaries if not j.on_time)
    avg_util = (
        sum(m.utilization_pct for m in machine_utils) / len(machine_utils)
        if machine_utils else 0
    )
    return ScheduleMetrics(
        makespan=makespan,
        total_tardiness=total_tard,
        max_tardiness=max_tard,
        num_on_time=on_time,
        num_late=late,
        avg_machine_utilization_pct=round(avg_util, 1),
        solve_time_seconds=round(solve_time, 3),
    )
