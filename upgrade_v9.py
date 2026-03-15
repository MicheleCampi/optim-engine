#!/usr/bin/env python3
"""
OptimEngine v8 → v9.0.0 Upgrade Script
=======================================

Applies ALL 4 scheduling upgrades to solver/models.py and solver/engine.py:

  1. duration_per_machine  — Task duration varies by machine (CNC-1: 120min, CNC-2: 90min)
  2. availability_windows  — Multiple availability windows per machine (shifts, breaks, maintenance)
  3. quality_min/yield_rate — Quality constraints (job requires yield >97%, machine has yield 98%)
  4. setup_times schema    — Sequence-dependent setup times (matrix per machine)

USAGE:
  cd ~/optim-engine
  python upgrade_v9.py

  - Reads solver/models.py and solver/engine.py (must be clean v8)
  - Writes upgraded files in-place
  - Creates .bak backups before overwriting

REQUIREMENTS:
  - Files must be the original v8 versions (git checkout solver/models.py solver/engine.py)
  - Run from the optim-engine project root
"""

import os
import re
import shutil
import sys


# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
MODELS_PATH = "solver/models.py"
ENGINE_PATH = "solver/engine.py"


def backup(path: str):
    """Create a .bak backup of the file."""
    bak = path + ".v8.bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"  ✅ Backup: {bak}")
    else:
        print(f"  ⏭️  Backup already exists: {bak}")


def read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def write(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)
    print(f"  ✅ Written: {path}")


# ═══════════════════════════════════════════════
# UPGRADE 1: models.py
# ═══════════════════════════════════════════════

def upgrade_models(src: str) -> str:
    """Apply all 4 upgrades to models.py."""
    
    # ────────────────────────────────────────────
    # 1a. Add AvailabilityWindow model BEFORE Task
    # ────────────────────────────────────────────
    availability_window_model = '''
class AvailabilityWindow(BaseModel):
    """A time window during which a machine is available (e.g., a shift, post-maintenance)."""
    start: int = Field(..., ge=0, description="Start of availability window")
    end: int = Field(..., ge=0, description="End of availability window")


'''
    # Insert before the Task class definition
    if "class AvailabilityWindow" not in src:
        src = src.replace(
            "class Task(BaseModel):",
            availability_window_model + "class Task(BaseModel):"
        )
        print("    [1a] Added AvailabilityWindow model")
    
    # ────────────────────────────────────────────
    # 1b. Add duration_per_machine to Task
    # ────────────────────────────────────────────
    old_task_setup = '    setup_time: int = Field(0, ge=0, description="Setup time before this task starts on any machine")'
    new_task_fields = '''    duration_per_machine: Optional[dict[str, int]] = Field(
        None,
        description="Per-machine processing times. Overrides 'duration' for listed machines. E.g. {'CNC-1': 120, 'CNC-2': 90}"
    )
    setup_time: int = Field(0, ge=0, description="Setup time before this task starts on any machine (DEPRECATED: prefer setup_times on ScheduleRequest)")'''
    
    if "duration_per_machine" not in src:
        src = src.replace(old_task_setup, new_task_fields)
        print("    [1b] Added duration_per_machine to Task")
    
    # ────────────────────────────────────────────
    # 1c. Add quality_min to Job
    # ────────────────────────────────────────────
    old_job_time_window = '    time_window: Optional[TimeWindow] = Field(None, description="Global time window for this job")'
    new_job_fields = '''    time_window: Optional[TimeWindow] = Field(None, description="Global time window for this job")
    quality_min: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Minimum yield/quality rate required (0.0-1.0). Only machines with yield_rate >= this are eligible."
    )'''
    
    if "quality_min" not in src:
        src = src.replace(old_job_time_window, new_job_fields)
        print("    [1c] Added quality_min to Job")
    
    # ────────────────────────────────────────────
    # 1d. Add yield_rate + availability_windows to Machine
    # ────────────────────────────────────────────
    old_machine_avail_end = '    availability_end: Optional[int] = Field(None, ge=0, description="When the machine stops being available. None = always available.")'
    new_machine_fields = '''    availability_end: Optional[int] = Field(None, ge=0, description="When the machine stops being available. None = always available.")
    availability_windows: Optional[list[AvailabilityWindow]] = Field(
        None,
        description="Multiple availability windows (shifts/breaks). Overrides availability_start/end when provided."
    )
    yield_rate: float = Field(
        1.0, ge=0.0, le=1.0,
        description="Machine quality/yield rate (0.0-1.0). 1.0 = perfect yield. Used with Job.quality_min."
    )'''
    
    if "availability_windows" not in src:
        src = src.replace(old_machine_avail_end, new_machine_fields)
        print("    [1d] Added yield_rate + availability_windows to Machine")
    
    # ────────────────────────────────────────────
    # 1e. Add SetupTimeEntry + setup_times to ScheduleRequest
    # ────────────────────────────────────────────
    setup_time_entry_model = '''

class SetupTimeEntry(BaseModel):
    """Sequence-dependent setup time: switching from one job to another on a specific machine."""
    machine_id: str = Field(..., description="Machine where the setup applies")
    from_job_id: str = Field(..., description="Preceding job (or '*' for any)")
    to_job_id: str = Field(..., description="Following job (or '*' for any)")
    setup_time: int = Field(..., ge=0, description="Setup time in time units")

'''
    # Insert before ScheduleRequest
    if "class SetupTimeEntry" not in src:
        src = src.replace(
            "class ScheduleRequest(BaseModel):",
            setup_time_entry_model + "class ScheduleRequest(BaseModel):"
        )
        print("    [1e] Added SetupTimeEntry model")
    
    # Add setup_times field to ScheduleRequest
    old_max_solve = '''    max_solve_time_seconds: int = Field(
        30, ge=1, le=300,
        description="Maximum solver runtime in seconds"
    )'''
    new_max_solve = '''    max_solve_time_seconds: int = Field(
        30, ge=1, le=300,
        description="Maximum solver runtime in seconds"
    )
    setup_times: Optional[list[SetupTimeEntry]] = Field(
        None,
        description="Sequence-dependent setup times. Overrides Task.setup_time for matching transitions."
    )'''
    
    if "setup_times: Optional[list[SetupTimeEntry]]" not in src:
        src = src.replace(old_max_solve, new_max_solve)
        print("    [1e] Added setup_times to ScheduleRequest")
    
    return src


# ═══════════════════════════════════════════════
# UPGRADE 2: engine.py
# ═══════════════════════════════════════════════

def upgrade_engine(src: str) -> str:
    """Apply all 4 upgrades to engine.py."""
    
    # ────────────────────────────────────────────
    # 2a. Update imports (if SetupTimeEntry not imported)
    # ────────────────────────────────────────────
    old_imports = """from .models import (
    ScheduleRequest, ScheduleResponse, ScheduledTask,
    JobSummary, MachineUtilization, ScheduleMetrics, GanttEntry,
    SolverStatus, ObjectiveType,
)"""
    new_imports = """from .models import (
    ScheduleRequest, ScheduleResponse, ScheduledTask,
    JobSummary, MachineUtilization, ScheduleMetrics, GanttEntry,
    SolverStatus, ObjectiveType, SetupTimeEntry,
)"""
    if "SetupTimeEntry" not in src:
        src = src.replace(old_imports, new_imports)
        print("    [2a] Updated imports")
    
    # ────────────────────────────────────────────
    # 2b. Add quality filtering helper after imports
    # ────────────────────────────────────────────
    quality_helper = '''

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

'''
    marker = "\n\ndef solve_schedule(request: ScheduleRequest) -> ScheduleResponse:"
    if "_get_effective_duration" not in src:
        src = src.replace(marker, quality_helper + "\ndef solve_schedule(request: ScheduleRequest) -> ScheduleResponse:")
        print("    [2b] Added helper functions")
    
    # ────────────────────────────────────────────
    # 2c. Add quality-based machine filtering + availability windows
    #     into the solve_schedule body, right after machine validation
    # ────────────────────────────────────────────
    
    # Replace the machine validation block to add quality filtering
    old_validate_block = """        # Validate all task machine references
        for job in request.jobs:
            for task in job.tasks:
                for mid in task.eligible_machines:
                    if mid not in machine_ids:
                        return ScheduleResponse(
                            status=SolverStatus.ERROR,
                            message=f"Task {job.job_id}/{task.task_id} references unknown machine '{mid}'"
                        )"""
    
    new_validate_block = """        # Validate all task machine references
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
                machine_windows[m.machine_id] = [(w.start, w.end) for w in m.availability_windows]"""
    
    if "quality_eligible" not in src:
        src = src.replace(old_validate_block, new_validate_block)
        print("    [2c] Added quality filtering + setup matrix + availability windows init")
    
    # ────────────────────────────────────────────
    # 2d. Replace horizon computation to account for duration_per_machine
    # ────────────────────────────────────────────
    old_horizon = """        # ── Compute horizon ──
        horizon = sum(
            t.duration + t.setup_time
            for j in request.jobs for t in j.tasks
        )"""
    
    new_horizon = """        # ── Compute horizon (v9: accounts for duration_per_machine + setup_times + availability_windows) ──
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
                    horizon = max(horizon, w.end)"""
    
    if "duration_per_machine" not in src or "max_setup" not in src:
        src = src.replace(old_horizon, new_horizon)
        print("    [2d] Updated horizon computation")
    
    # ────────────────────────────────────────────
    # 2e. Replace the variable creation block to use per-machine durations
    #     and apply quality filtering to eligible machines
    # ────────────────────────────────────────────
    
    # Replace the inner loop that builds variables for each task
    old_task_loop_start = """        for job in request.jobs:
            for task in job.tasks:
                jid, tid = job.job_id, task.task_id
                total_duration = task.duration + task.setup_time
         
                # Global start/end for this task (across alternatives)"""
    
    new_task_loop_start = """        for job in request.jobs:
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
         
                # Global start/end for this task (across alternatives)"""
    
    if "effective_machines" not in src:
        src = src.replace(old_task_loop_start, new_task_loop_start)
        print("    [2e] Added quality-filtered effective_machines")
    
    # ────────────────────────────────────────────
    # 2f. Replace single-machine block to use per-machine duration
    # ────────────────────────────────────────────
    old_single_machine = """                if len(task.eligible_machines) == 1:
                    # ── Single machine: no alternatives needed ──
                    mid = task.eligible_machines[0]
                    interval = model.new_interval_var(
                        t_start, total_duration, t_end, f"interval{suffix}_{mid}"
                    )"""
    
    new_single_machine = """                if len(effective_machines) == 1:
                    # ── Single machine: no alternatives needed ──
                    mid = effective_machines[0]
                    # v9: per-machine duration
                    eff_duration = _get_effective_duration(task, mid) + task.setup_time
                    interval = model.new_interval_var(
                        t_start, eff_duration, t_end, f"interval{suffix}_{mid}"
                    )"""
    
    if "_get_effective_duration(task, mid)" not in src:
        src = src.replace(old_single_machine, new_single_machine)
        print("    [2f] Updated single-machine block with per-machine duration")
    
    # Fix the _TaskVar creation for single machine
    old_single_taskvar = """                    all_task_vars[(jid, tid, mid)] = _TaskVar(
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
                    for mid in task.eligible_machines:"""
    
    new_single_taskvar = """                    all_task_vars[(jid, tid, mid)] = _TaskVar(
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
                    for mid in effective_machines:"""
    
    src = src.replace(old_single_taskvar, new_single_taskvar)
    print("    [2f] Updated single-machine _TaskVar + availability windows")
    
    # ────────────────────────────────────────────
    # 2g. Replace multi-machine block with per-machine duration + availability windows
    # ────────────────────────────────────────────
    old_multi_machine_inner = """                        alt_suffix = f"{suffix}_{mid}"
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
                        )"""

    new_multi_machine_inner = """                        alt_suffix = f"{suffix}_{mid}"
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
                        )"""
    
    if "eff_dur = _get_effective_duration" not in src:
        src = src.replace(old_multi_machine_inner, new_multi_machine_inner)
        print("    [2g] Updated multi-machine block with per-machine duration")
    
    # Replace multi-machine availability block
    old_multi_avail = """                        # Machine availability
                        m = machine_map[mid]
                        if m.availability_start > 0:
                            model.add(alt_start >= m.availability_start).only_enforce_if(presence)
                        if m.availability_end is not None:
                            model.add(alt_end <= m.availability_end).only_enforce_if(presence)"""
    
    new_multi_avail = """                        # Machine availability (v9: windows or legacy)
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
                                model.add(alt_end <= m.availability_end).only_enforce_if(presence)"""
    
    src = src.replace(old_multi_avail, new_multi_avail)
    print("    [2g] Updated multi-machine availability windows")
    
    # ────────────────────────────────────────────
    # 2h. Add sequence-dependent setup time constraints
    #     (after no-overlap, before job time windows)
    # ────────────────────────────────────────────
    old_no_overlap = """        # ── No-overlap per machine ──
        for mid, intervals in machine_intervals.items():
            if len(intervals) > 1:
                model.add_no_overlap(intervals)
        
        # ── Job time window constraints ──"""
    
    new_no_overlap = """        # ── No-overlap per machine ──
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
        
        # ── Job time window constraints ──"""
    
    if "Sequence-dependent setup times" not in src:
        src = src.replace(old_no_overlap, new_no_overlap)
        print("    [2h] Added sequence-dependent setup time constraints")
    
    # ────────────────────────────────────────────
    # 2i. Fix the ScheduledTask duration in solution extraction
    #     to use effective duration instead of task.duration + task.setup_time
    # ────────────────────────────────────────────
    old_extract_st = """                    if chosen_mid is not None:
                        st = ScheduledTask(
                            job_id=jid, task_id=tid, machine_id=chosen_mid,
                            start=chosen_start, end=chosen_end,
                            duration=task.duration + task.setup_time
                        )"""
    
    new_extract_st = """                    if chosen_mid is not None:
                        # v9: effective duration considers per-machine duration
                        eff_d = _get_effective_duration(task, chosen_mid) + task.setup_time
                        st = ScheduledTask(
                            job_id=jid, task_id=tid, machine_id=chosen_mid,
                            start=chosen_start, end=chosen_end,
                            duration=eff_d
                        )"""
    
    if "eff_d = _get_effective_duration" not in src:
        src = src.replace(old_extract_st, new_extract_st)
        print("    [2i] Updated solution extraction with effective duration")
    
    # ────────────────────────────────────────────
    # 2j. Fix solution extraction to use effective_machines
    #     (quality-filtered) instead of task.eligible_machines
    # ────────────────────────────────────────────
    old_extract_loop = """            for job in request.jobs:
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
                                break"""
    
    new_extract_loop = """            for job in request.jobs:
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
                                break"""
    
    if "ext_machines" not in src:
        src = src.replace(old_extract_loop, new_extract_loop)
        print("    [2j] Fixed solution extraction to use quality-filtered machines")
    
    return src


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

def main():
    print("=" * 60)
    print("OptimEngine v8 → v9.0.0 Upgrade")
    print("=" * 60)
    
    # Check we're in the right directory
    if not os.path.exists(MODELS_PATH):
        print(f"\n❌ ERROR: {MODELS_PATH} not found.")
        print("   Run this script from the optim-engine project root.")
        sys.exit(1)
    if not os.path.exists(ENGINE_PATH):
        print(f"\n❌ ERROR: {ENGINE_PATH} not found.")
        sys.exit(1)
    
    # ── Backup ──
    print("\n📦 Creating backups...")
    backup(MODELS_PATH)
    backup(ENGINE_PATH)
    
    # ── Upgrade models.py ──
    print(f"\n🔧 Upgrading {MODELS_PATH}...")
    models_src = read(MODELS_PATH)
    models_new = upgrade_models(models_src)
    write(MODELS_PATH, models_new)
    
    # ── Upgrade engine.py ──
    print(f"\n🔧 Upgrading {ENGINE_PATH}...")
    engine_src = read(ENGINE_PATH)
    engine_new = upgrade_engine(engine_src)
    write(ENGINE_PATH, engine_new)
    
    # ── Summary ──
    print("\n" + "=" * 60)
    print("✅ v9.0.0 UPGRADE COMPLETE")
    print("=" * 60)
    print("""
Upgrades applied:
  1. duration_per_machine — Task.duration_per_machine: dict[str, int]
  2. availability_windows — Machine.availability_windows: list[AvailabilityWindow]
  3. quality_min/yield_rate — Job.quality_min + Machine.yield_rate
  4. setup_times — ScheduleRequest.setup_times: list[SetupTimeEntry]

Next steps:
  1. Run tests:   pytest tests/ -v
  2. Quick smoke:  python -c "from solver.models import *; print('Models OK')"
  3. If good:      git add -A && git commit -m 'v9.0.0: 4 scheduling upgrades'
  4. Deploy:       git push && railway up

Backups saved as:
  - solver/models.py.v8.bak
  - solver/engine.py.v8.bak
""")


if __name__ == "__main__":
    main()
