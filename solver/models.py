"""
OptimEngine — Data Models
Pydantic schemas for the Operations Scheduling Solver.

These models define the API contract between AI agents and the solver.
They must be:
  - Self-documenting (agents read the schema to understand what to send)
  - Flexible (support simple and complex scheduling scenarios)
  - Strict (reject malformed input before it hits the solver)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class ObjectiveType(str, Enum):
    """What the solver should optimize for."""
    MINIMIZE_MAKESPAN = "minimize_makespan"
    MINIMIZE_TOTAL_TARDINESS = "minimize_total_tardiness"
    MINIMIZE_MAX_TARDINESS = "minimize_max_tardiness"
    BALANCE_LOAD = "balance_load"


class SolverStatus(str, Enum):
    """Status of the solver result."""
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"
    ERROR = "error"


# ─────────────────────────────────────────────
# Input Models
# ─────────────────────────────────────────────

class TimeWindow(BaseModel):
    """A time window constraint (earliest start, latest end)."""
    earliest_start: int = Field(0, ge=0, description="Earliest start time (in time units)")
    latest_end: Optional[int] = Field(None, ge=0, description="Latest end time (in time units). None = no deadline.")


class Task(BaseModel):
    """A single task (operation) within a job."""
    task_id: str = Field(..., description="Unique task identifier within this job")
    duration: int = Field(..., gt=0, description="Processing time in time units")
    eligible_machines: list[str] = Field(
        ..., min_length=1,
        description="Machine IDs that can process this task. For flexible scheduling, list multiple."
    )
    setup_time: int = Field(0, ge=0, description="Setup time before this task starts on any machine")

    @field_validator("eligible_machines")
    @classmethod
    def deduplicate_machines(cls, v):
        return list(dict.fromkeys(v))


class Job(BaseModel):
    """A job consisting of ordered tasks that must execute sequentially."""
    job_id: str = Field(..., description="Unique job identifier")
    name: Optional[str] = Field(None, description="Human-readable job name")
    tasks: list[Task] = Field(..., min_length=1, description="Ordered list of tasks. Executed in sequence.")
    priority: int = Field(1, ge=1, le=10, description="Priority (1=lowest, 10=highest)")
    due_date: Optional[int] = Field(None, ge=0, description="Due date in time units. Used for tardiness objectives.")
    time_window: Optional[TimeWindow] = Field(None, description="Global time window for this job")


class Machine(BaseModel):
    """A machine / resource that processes tasks."""
    machine_id: str = Field(..., description="Unique machine identifier")
    name: Optional[str] = Field(None, description="Human-readable machine name")
    availability_start: int = Field(0, ge=0, description="When the machine becomes available")
    availability_end: Optional[int] = Field(None, ge=0, description="When the machine stops being available. None = always available.")


class ScheduleRequest(BaseModel):
    """
    Complete scheduling request.
    
    Send a list of jobs (each with ordered tasks) and machines.
    The solver assigns tasks to machines and determines start times
    to optimize the chosen objective while respecting all constraints.
    """
    jobs: list[Job] = Field(..., min_length=1, max_length=500, description="Jobs to schedule")
    machines: list[Machine] = Field(..., min_length=1, max_length=100, description="Available machines/resources")
    objective: ObjectiveType = Field(
        ObjectiveType.MINIMIZE_MAKESPAN,
        description="Optimization objective"
    )
    max_solve_time_seconds: int = Field(
        30, ge=1, le=300,
        description="Maximum solver runtime in seconds"
    )
    
    @field_validator("jobs")
    @classmethod
    def validate_unique_job_ids(cls, v):
        ids = [j.job_id for j in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate job_id found")
        return v

    @field_validator("machines")
    @classmethod
    def validate_unique_machine_ids(cls, v):
        ids = [m.machine_id for m in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate machine_id found")
        return v


# ─────────────────────────────────────────────
# Output Models
# ─────────────────────────────────────────────

class ScheduledTask(BaseModel):
    """A task assigned to a machine with start/end times."""
    job_id: str
    task_id: str
    machine_id: str
    start: int = Field(..., ge=0, description="Start time")
    end: int = Field(..., ge=0, description="End time")
    duration: int = Field(..., gt=0)


class JobSummary(BaseModel):
    """Summary metrics for a single job."""
    job_id: str
    name: Optional[str] = None
    start: int
    end: int
    makespan: int = Field(..., description="Total time from first task start to last task end")
    tardiness: int = Field(0, ge=0, description="Time past due date (0 if no due date or on time)")
    on_time: bool = True


class MachineUtilization(BaseModel):
    """Utilization metrics for a single machine."""
    machine_id: str
    name: Optional[str] = None
    busy_time: int = Field(..., ge=0)
    idle_time: int = Field(..., ge=0)
    utilization_pct: float = Field(..., ge=0, le=100)
    num_tasks: int = Field(..., ge=0)


class ScheduleMetrics(BaseModel):
    """Aggregate metrics for the entire schedule."""
    makespan: int = Field(..., description="Total schedule length (end of last task)")
    total_tardiness: int = Field(0, description="Sum of all job tardiness")
    max_tardiness: int = Field(0, description="Maximum tardiness across jobs")
    num_on_time: int = Field(0, description="Number of jobs completed on time")
    num_late: int = Field(0, description="Number of late jobs")
    avg_machine_utilization_pct: float = Field(..., description="Average machine utilization %")
    solve_time_seconds: float = Field(..., description="Actual solver runtime")


class GanttEntry(BaseModel):
    """A single entry for Gantt chart rendering."""
    job_id: str
    task_id: str
    machine_id: str
    start: int
    end: int
    label: str = Field(..., description="Display label for the task")


class ScheduleResponse(BaseModel):
    """
    Complete solver response.
    
    Contains the optimized schedule, per-job and per-machine metrics,
    Gantt chart data for visualization, and solver diagnostics.
    """
    status: SolverStatus
    message: str = Field(..., description="Human-readable status message")
    schedule: list[ScheduledTask] = Field(default_factory=list, description="Assigned tasks with times")
    job_summaries: list[JobSummary] = Field(default_factory=list)
    machine_utilization: list[MachineUtilization] = Field(default_factory=list)
    metrics: Optional[ScheduleMetrics] = None
    gantt: list[GanttEntry] = Field(default_factory=list, description="Gantt chart data for rendering")


# ─────────────────────────────────────────────
# Validation Request/Response
# ─────────────────────────────────────────────

class ValidationViolation(BaseModel):
    """A single constraint violation found in a schedule."""
    violation_type: str = Field(..., description="Type: overlap, precedence, machine_eligibility, time_window, etc.")
    severity: str = Field("error", description="error or warning")
    description: str
    affected_tasks: list[str] = Field(default_factory=list)


class ValidateRequest(BaseModel):
    """Validate an existing schedule against constraints."""
    schedule: list[ScheduledTask] = Field(..., min_length=1)
    jobs: list[Job] = Field(..., min_length=1)
    machines: list[Machine] = Field(..., min_length=1)


class ValidateResponse(BaseModel):
    """Validation result."""
    is_valid: bool
    num_violations: int = 0
    violations: list[ValidationViolation] = Field(default_factory=list)
    metrics: Optional[ScheduleMetrics] = None
    improvement_suggestions: list[str] = Field(default_factory=list)
