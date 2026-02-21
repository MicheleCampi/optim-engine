"""
OptimEngine — FastAPI + MCP Server
The interface layer: exposes scheduling solver as MCP tools for AI agents.

Architecture:
  FastAPI endpoints → fastapi-mcp auto-wraps → MCP protocol → AI agents discover & call

Two tools exposed:
  1. optimize_schedule — Solve a Flexible Job Shop Scheduling Problem
  2. validate_schedule — Validate an existing schedule against constraints
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from solver.models import (
    ScheduleRequest, ScheduleResponse,
    ValidateRequest, ValidateResponse,
    SolverStatus,
)
from solver.engine import solve_schedule
from solver.validator import validate_schedule


# ─────────────────────────────────────────────
# App Configuration
# ─────────────────────────────────────────────

APP_NAME = "OptimEngine"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = """
**Operations Scheduling Solver** — An MCP-native optimization engine.

Solves Flexible Job Shop Scheduling Problems using Google OR-Tools CP-SAT solver.
Designed to be called by AI agents via Model Context Protocol (MCP).

### Capabilities
- **Flexible Job Shop Scheduling**: Assign tasks to machines with alternative machine eligibility
- **Multiple objectives**: Minimize makespan, tardiness, or balance machine load
- **Rich constraints**: Precedence, time windows, machine availability, setup times, priorities
- **Schedule validation**: Verify existing schedules and get improvement suggestions
- **Gantt chart data**: Ready-to-render visualization data in every response

### Typical Use Case
An AI agent receives a scheduling request in natural language, translates it to the
structured JSON format, calls `optimize_schedule`, and returns the optimized schedule
to the user in a readable format (table, Gantt chart, text summary).
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    print(f"🚀 {APP_NAME} v{APP_VERSION} starting...")
    print(f"   MCP endpoint: /mcp")
    print(f"   Docs: /docs")
    yield
    print(f"👋 {APP_NAME} shutting down.")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)

# CORS — allow all origins for MCP agent access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Request tracking middleware
# ─────────────────────────────────────────────

_request_count = 0
_total_solve_time = 0.0


@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track request count and timing for health endpoint."""
    global _request_count, _total_solve_time
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    if request.url.path in ("/optimize_schedule", "/validate_schedule"):
        _request_count += 1
        _total_solve_time += elapsed
    return response


# ─────────────────────────────────────────────
# Health & Info Endpoints
# ─────────────────────────────────────────────

@app.get("/", operation_id="root", summary="Server info and status")
async def root():
    """Returns server info, available tools, and usage statistics."""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "operational",
        "tools": [
            {
                "name": "optimize_schedule",
                "description": "Solve a Flexible Job Shop Scheduling Problem. Assign tasks to machines optimally.",
                "endpoint": "/optimize_schedule",
            },
            {
                "name": "validate_schedule",
                "description": "Validate an existing schedule against constraints. Get violations and improvement suggestions.",
                "endpoint": "/validate_schedule",
            },
        ],
        "stats": {
            "requests_served": _request_count,
            "total_solve_time_seconds": round(_total_solve_time, 2),
        },
        "mcp_endpoint": "/mcp",
    }


@app.get("/health", operation_id="health_check", summary="Health check")
async def health():
    """Simple health check for monitoring and load balancers."""
    return {"status": "healthy", "version": APP_VERSION}


# ─────────────────────────────────────────────
# Core Tool Endpoints
# ─────────────────────────────────────────────

@app.post(
    "/optimize_schedule",
    response_model=ScheduleResponse,
    operation_id="optimize_schedule",
    summary="Solve a Flexible Job Shop Scheduling Problem",
    description="""
Solves a scheduling optimization problem using constraint programming (OR-Tools CP-SAT).

**Input**: Jobs with ordered tasks, machines, constraints, and optimization objective.
**Output**: Optimized schedule with task assignments, timing, metrics, and Gantt chart data.

**Supported objectives**:
- `minimize_makespan`: Minimize total schedule length (default)
- `minimize_total_tardiness`: Minimize weighted sum of job delays past due dates
- `minimize_max_tardiness`: Minimize the worst-case job delay
- `balance_load`: Balance work across machines

**Constraints supported**:
- Task precedence (tasks within a job execute in order)
- Machine eligibility (flexible: tasks can run on multiple machines)
- No-overlap (one task per machine at a time)
- Time windows (earliest start, latest end per job)
- Machine availability windows
- Setup times per task
- Job priorities (affect tardiness weighting)

**Example — Simple 3-job, 2-machine problem**:
```json
{
  "jobs": [
    {"job_id": "J1", "tasks": [{"task_id": "cut", "duration": 3, "eligible_machines": ["M1"]}, {"task_id": "weld", "duration": 2, "eligible_machines": ["M2"]}]},
    {"job_id": "J2", "tasks": [{"task_id": "cut", "duration": 2, "eligible_machines": ["M1"]}, {"task_id": "weld", "duration": 4, "eligible_machines": ["M2"]}]},
    {"job_id": "J3", "tasks": [{"task_id": "cut", "duration": 4, "eligible_machines": ["M1", "M2"]}, {"task_id": "weld", "duration": 1, "eligible_machines": ["M2"]}]}
  ],
  "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
  "objective": "minimize_makespan"
}
```
""",
    tags=["Scheduling"],
)
async def optimize_schedule_endpoint(request: ScheduleRequest) -> ScheduleResponse:
    """Solve a scheduling problem. This is the primary MCP tool."""
    return solve_schedule(request)


@app.post(
    "/validate_schedule",
    response_model=ValidateResponse,
    operation_id="validate_schedule",
    summary="Validate an existing schedule against constraints",
    description="""
Validates a schedule (manual or generated) against the original job/machine constraints.

**Checks performed**:
- Consistency (start + duration == end)
- Machine eligibility (task assigned to eligible machine)
- No-overlap (no two tasks overlap on same machine)
- Precedence (tasks within a job respect order)
- Time windows (within job time windows)
- Machine availability
- Missing tasks (warning)

**Returns**: Violation report, metrics (if valid), and improvement suggestions.

Use this tool to:
- Verify a manually created schedule before execution
- Check if a modified schedule still satisfies constraints
- Get suggestions to improve an existing schedule
""",
    tags=["Validation"],
)
async def validate_schedule_endpoint(request: ValidateRequest) -> ValidateResponse:
    """Validate a schedule. This is the second MCP tool."""
    return validate_schedule(request)


# ─────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────

@app.exception_handler(422)
async def validation_error_handler(request: Request, exc):
    """Return helpful error messages for malformed requests."""
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "Invalid request format. Check the schema at /docs for required fields.",
            "details": str(exc),
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Catch-all for server errors."""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error. Please try again or contact support.",
        },
    )


# ─────────────────────────────────────────────
# MCP Integration
# ─────────────────────────────────────────────

try:
    from fastapi_mcp import FastApiMCP

    mcp = FastApiMCP(
        app,
        name="OptimEngine",
        description=(
            "Operations Scheduling Solver — solves Flexible Job Shop Scheduling Problems "
            "using OR-Tools CP-SAT. Assign tasks to machines optimally with support for "
            "precedence, time windows, machine eligibility, setup times, and multiple objectives."
        ),
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp.mount()
    print("✅ MCP server mounted at /mcp")
except ImportError:
    print("⚠️  fastapi-mcp not installed. MCP endpoint disabled. Install with: pip install fastapi-mcp")
except Exception as e:
    print(f"⚠️  MCP mount failed: {e}. Server running without MCP.")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=True)
