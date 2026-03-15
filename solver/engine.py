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
    SolverStatus, ObjectiveType, SetupTimeEntry,
)


# Named tuples for internal bookkeeping
_TaskVar = collections.namedtuple("_TaskVar", "start end interval duration machine_id job_id task_id")


def _get_effective_duration(task, machine_id: str) -> int:
    """Get task duration for a specific machine, considering duration_per_machine."""
    if task.duration_per_machine and machine_id in task.duration_per_machine:
        return task.duration_per_machine[machine_id]
    return task.duration


def _filter_machines_by_quality(job, machines_map: dict) -> list[str]:
    """Filter eligible machines based on job quality_min and machine yield_rate."""
    if job.quality_min is None:
        return None  # No filtering needed
    return [
        mid for mid, m in machines_map.items()
        if m.yield_rate >= job.quality_min
    ]


def _build_setup_matrix(request) -> dict:
    """Build lookup: (machine_id, from_job_id, to_job_id) -> setup_time."""
    matrix = {}
    if not request.setup_times:
        return matrix
    for entry in request.setup_times:
        matrix[(entry.machine_id, entry.from_job_id, entry.to_job_id)] = entry.setup_time
        # Wildcard expansion would be done at constraint-building time
    return matrix


def _get_setup_time(matrix: dict, machine_id: str, from_job: str, to_job: str) -> int:
    """Lookup setup time with wildcard fallback: exact → from=* → to=* → *,* → 0."""
    if (machine_id, from_job, to_job) in matrix:
        return matrix[(machine_id, from_job, to_job)]
    if (machine_id, "*", to_job) in matrix:
        return matrix[(machine_id, "*", to_job)]
    if (machine_id, from_job, "*") in matrix:
        return matrix[(machine_id, from_job, "*")]
    if (machine_id, "*", "*") in matrix:
        return matrix[(machine_id, "*", "*")]
    return 0


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
        
        # ── v9: Quality-based machine filtering ──
        quality_eligible: dict[str, list[str]] = {}  # job_id -> list of quality-ok machine_ids
        for job in request.jobs:
            if job.quality_min is not None:
                ok_machines = _filter_machines_by_quality(job, machine_map)
                if not ok_machines:
                    return ScheduleResponse(
                        status=SolverStatus.INFEASIBLE,
                        message=f"Job '{job.job_id}' requires quality_min={job.quality_min} but no machine meets this threshold."
                    )
                quality_eligible[job.job_id] = ok_machines
        
        # ── v9: Build setup time matrix ──
        setup_matrix = _build_setup_matrix(request)
        
        # ── v9: Build availability windows lookup ──
        # Convert availability_windows to list of (start, end) tuples per machine
        machine_windows: dict[str, list[tuple[int, int]]] = {}
        for m in request.machines:
            if m.availability_windows:
                machine_windows[m.machine_id] = [(w.start, w.end) for w in m.availability_windows]
        
        # ── Compute horizon (v9: accounts for duration_per_machine + setup_times + availability_windows) ──
        horizon = sum(
            max(
                [t.duration] + 
                (list(t.duration_per_machine.values()) if t.duration_per_machine else [])
            ) + t.setup_time
            for j in request.jobs for t in j.tasks
        )
        # Add extra buffer for sequence-dependent setup times
        if setup_matrix:
            max_setup = max(setup_matrix.values()) if setup_matrix else 0
            horizon += max_setup * sum(len(j.tasks) for j in request.jobs)
        # v9: Extend horizon to cover availability windows
        for m in request.machines:
            if m.availability_windows:
                for w in m.availability_windows:
                    horizon = max(horizon, w.end)
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
            # v9: Filter eligible machines by quality requirement
            job_quality_machines = set(quality_eligible.get(job.job_id, []))
            
            for task in job.tasks:
                jid, tid = job.job_id, task.task_id
                
                # v9: Determine effective eligible machines after quality filtering
                effective_machines = list(task.eligible_machines)
                if job_quality_machines:
                    effective_machines = [m for m in effective_machines if m in job_quality_machines]
                    if not effective_machines:
                        return ScheduleResponse(
                            status=SolverStatus.INFEASIBLE,
                            message=f"Task {jid}/{tid}: no eligible machine meets quality_min={job.quality_min}"
                        )
                
                total_duration = task.duration + task.setup_time
                
                # Global start/end for this task (across alternatives)
                suffix = f"_{jid}_{tid}"
                t_start = model.new_int_var(0, horizon, f"start{suffix}")
                t_end = model.new_int_var(0, horizon, f"end{suffix}")
                task_starts[(jid, tid)] = t_start
                task_ends[(jid, tid)] = t_end
                
                if len(effective_machines) == 1:
                    # ── Single machine: no alternatives needed ──
                    mid = effective_machines[0]
                    # v9: per-machine duration
                    eff_duration = _get_effective_duration(task, mid) + task.setup_time
                    interval = model.new_interval_var(
                        t_start, eff_duration, t_end, f"interval{suffix}_{mid}"
                    )
                    all_task_vars[(jid, tid, mid)] = _TaskVar(
                        start=t_start, end=t_end, interval=interval,
                        duration=eff_duration, machine_id=mid,
                        job_id=jid, task_id=tid
                    )
                    machine_intervals[mid].append(interval)
                    
                    # Apply machine availability (v9: windows or legacy start/end)
                    m = machine_map[mid]
                    if mid in machine_windows:
                        # v9: Multiple availability windows — task must fit within at least one
                        window_bools = []
                        for wi, (ws, we) in enumerate(machine_windows[mid]):
                            wb = model.new_bool_var(f"win_{jid}_{tid}_{mid}_{wi}")
                            model.add(t_start >= ws).only_enforce_if(wb)
                            model.add(t_end <= we).only_enforce_if(wb)
                            window_bools.append(wb)
                        model.add_exactly_one(window_bools)
                    else:
                        if m.availability_start > 0:
                            model.add(t_start >= m.availability_start)
                        if m.availability_end is not None:
                            model.add(t_end <= m.availability_end)
                else:
                    # ── Multiple eligible machines: optional intervals ──
                    alt_presences = []
                    for mid in effective_machines:
                        alt_suffix = f"{suffix}_{mid}"
                        presence = model.new_bool_var(f"pres{alt_suffix}")
                        alt_start = model.new_int_var(0, horizon, f"astart{alt_suffix}")
                        alt_end = model.new_int_var(0, horizon, f"aend{alt_suffix}")
                        # v9: per-machine duration
                        eff_dur = _get_effective_duration(task, mid) + task.setup_time
                        alt_interval = model.new_optional_interval_var(
                            alt_start, eff_dur, alt_end, presence, f"aint{alt_suffix}"
                        )
                        
                        all_task_vars[(jid, tid, mid)] = _TaskVar(
                            start=alt_start, end=alt_end, interval=alt_interval,
                            duration=eff_dur, machine_id=mid,
                            job_id=jid, task_id=tid
                        )
                        presence_literals[(jid, tid, mid)] = presence
                        alt_presences.append(presence)
                        machine_intervals[mid].append(alt_interval)
                        
                        # Link alternative start/end to global start/end when present
                        model.add(alt_start == t_start).only_enforce_if(presence)
                        model.add(alt_end == t_end).only_enforce_if(presence)
                        
                        # Machine availability (v9: windows or legacy)
                        m = machine_map[mid]
                        if mid in machine_windows:
                            # v9: Multiple availability windows
                            window_bools = []
                            for wi, (ws, we) in enumerate(machine_windows[mid]):
                                wb = model.new_bool_var(f"win_{jid}_{tid}_{mid}_{wi}")
                                model.add(alt_start >= ws).only_enforce_if([presence, wb])
                                model.add(alt_end <= we).only_enforce_if([presence, wb])
                                window_bools.append(wb)
                            # If this machine is chosen, exactly one window must hold
                            # If not chosen, windows are unconstrained
                            model.add(sum(window_bools) == 1).only_enforce_if(presence)
                            model.add(sum(window_bools) == 0).only_enforce_if(presence.negated())
                        else:
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
        
        # ── v9: Sequence-dependent setup times ──
        if setup_matrix:
            # For each machine, for each ORDERED pair of tasks from different jobs:
            # create a disjunction: either t1 before t2 (with setup12) or t2 before t1 (with setup21)
            # We iterate i < j to avoid duplicates, creating one bool per pair.
            for mid in machine_ids:
                tasks_on_machine = [
                    (jid, tid, tv) for (jid, tid, m), tv in all_task_vars.items() if m == mid
                ]
                for i in range(len(tasks_on_machine)):
                    for j in range(i + 1, len(tasks_on_machine)):
                        jid1, tid1, tv1 = tasks_on_machine[i]
                        jid2, tid2, tv2 = tasks_on_machine[j]
                        if jid1 == jid2:
                            continue  # same job → handled by precedence
                        
                        st_12 = _get_setup_time(setup_matrix, mid, jid1, jid2)
                        st_21 = _get_setup_time(setup_matrix, mid, jid2, jid1)
                        
                        if st_12 == 0 and st_21 == 0:
                            continue  # no-overlap already handles ordering
                        
                        # Get presence literals (None for single-machine tasks = always present)
                        pres1 = presence_literals.get((jid1, tid1, mid))
                        pres2 = presence_literals.get((jid2, tid2, mid))
                        
                        # b=True → t1 before t2; b=False → t2 before t1
                        b = model.new_bool_var(f"order_{mid}_{jid1}_{tid1}_{jid2}_{tid2}")
                        
                        # Conditions for when both tasks are on this machine
                        cond_fwd = [b]
                        cond_bwd = [b.negated()]
                        if pres1 is not None:
                            cond_fwd.append(pres1)
                            cond_bwd.append(pres1)
                        if pres2 is not None:
                            cond_fwd.append(pres2)
                            cond_bwd.append(pres2)
                        
                        if st_12 > 0:
                            model.add(tv2.start >= tv1.end + st_12).only_enforce_if(cond_fwd)
                        if st_21 > 0:
                            model.add(tv1.start >= tv2.end + st_21).only_enforce_if(cond_bwd)
        
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
                # v9: rebuild effective machines for extraction (same logic as variable creation)
                job_qm = set(quality_eligible.get(job.job_id, []))
                
                for task in job.tasks:
                    jid, tid = job.job_id, task.task_id
                    
                    # v9: effective eligible machines (quality-filtered)
                    ext_machines = list(task.eligible_machines)
                    if job_qm:
                        ext_machines = [m for m in ext_machines if m in job_qm]
                    
                    # Determine which machine was chosen
                    chosen_mid = None
                    chosen_start = None
                    chosen_end = None
                    
                    if len(ext_machines) == 1:
                        mid = ext_machines[0]
                        tv = all_task_vars[(jid, tid, mid)]
                        chosen_mid = mid
                        chosen_start = solver.value(tv.start)
                        chosen_end = solver.value(tv.end)
                    else:
                        for mid in ext_machines:
                            pres = presence_literals.get((jid, tid, mid))
                            if pres is not None and solver.value(pres):
                                tv = all_task_vars[(jid, tid, mid)]
                                chosen_mid = mid
                                chosen_start = solver.value(tv.start)
                                chosen_end = solver.value(tv.end)
                                break
                    
                    if chosen_mid is not None:
                        # v9: effective duration considers per-machine duration
                        eff_d = _get_effective_duration(task, chosen_mid) + task.setup_time
                        st = ScheduledTask(
                            job_id=jid, task_id=tid, machine_id=chosen_mid,
                            start=chosen_start, end=chosen_end,
                            duration=eff_d
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
