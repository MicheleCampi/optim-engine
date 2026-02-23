"""
OptimEngine — FastAPI + MCP Server
The interface layer: exposes scheduling and routing solvers as MCP tools for AI agents.

Architecture:
  FastAPI endpoints → fastapi-mcp auto-wraps → MCP protocol → AI agents discover & call

Four tools exposed:
  1. optimize_schedule — Solve a Flexible Job Shop Scheduling Problem
  2. validate_schedule — Validate an existing schedule against constraints
  3. optimize_routing  — Solve a Capacitated Vehicle Routing Problem with Time Windows
  4. validate_routing  — Validate an existing routing solution (coming soon)
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

from routing.models import (
    RoutingRequest, RoutingResponse,
    RoutingStatus,
)
from routing.engine import solve_routing


# ─────────────────────────────────────────────
# App Configuration
# ─────────────────────────────────────────────

APP_NAME = "OptimEngine"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = """
**Operations Intelligence Solver** — An MCP-native optimization engine.

Two solver modules for AI agents:

### 1. Scheduling (Flexible Job Shop)
Solves Flexible Job Shop Scheduling Problems using Google OR-Tools CP-SAT.
Assign tasks to machines optimally with precedence, time windows, machine eligibility,
setup times, priorities, and multiple objectives (makespan, tardiness, load balance).

### 2. Routing (CVRPTW)
Solves Capacitated Vehicle Routing Problems with Time Windows using OR-Tools routing solver.
Assign delivery locations to vehicles optimally with capacity constraints, time windows,
service times, and multiple objectives (distance, time, vehicle count, route balance).

### Designed for AI Agents
Both solvers are exposed as MCP tools. An AI agent receives an optimization request
in natural language, translates it to structured JSON, calls the appropriate tool,
and returns the optimized solution to the user.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
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

TRACKED_PATHS = ("/optimize_schedule", "/validate_schedule", "/optimize_routing")


@app.middleware("http")
async def track_requests(request: Request, call_next):
    global _request_count, _total_solve_time
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    if request.url.path in TRACKED_PATHS:
        _request_count += 1
        _total_solve_time += elapsed
    return response


# ─────────────────────────────────────────────
# Health & Info Endpoints
# ─────────────────────────────────────────────

@app.get("/", operation_id="root", summary="Server info and status")
async def root():
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
                "description": "Validate an existing schedule against constraints.",
                "endpoint": "/validate_schedule",
            },
            {
                "name": "optimize_routing",
                "description": "Solve a CVRPTW. Assign delivery locations to vehicles optimally with capacity and time windows.",
                "endpoint": "/optimize_routing",
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
    return {"status": "healthy", "version": APP_VERSION}


# ─────────────────────────────────────────────
# Scheduling Tool Endpoints
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

**Supported objectives**: minimize_makespan (default), minimize_total_tardiness, minimize_max_tardiness, balance_load.

**Constraints**: Task precedence, machine eligibility, no-overlap, time windows, machine availability, setup times, priorities.

**Example**:
```json
{
  "jobs": [
    {"job_id": "J1", "tasks": [{"task_id": "cut", "duration": 3, "eligible_machines": ["M1"]}, {"task_id": "weld", "duration": 2, "eligible_machines": ["M2"]}]},
    {"job_id": "J2", "tasks": [{"task_id": "cut", "duration": 2, "eligible_machines": ["M1"]}, {"task_id": "weld", "duration": 4, "eligible_machines": ["M2"]}]}
  ],
  "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
  "objective": "minimize_makespan"
}
```
""",
    tags=["Scheduling"],
)
async def optimize_schedule_endpoint(request: ScheduleRequest) -> ScheduleResponse:
    return solve_schedule(request)


@app.post(
    "/validate_schedule",
    response_model=ValidateResponse,
    operation_id="validate_schedule",
    summary="Validate an existing schedule against constraints",
    description="""
Validates a schedule against job/machine constraints. Checks consistency, machine eligibility,
no-overlap, precedence, time windows, and machine availability.
Returns violation report, metrics, and improvement suggestions.
""",
    tags=["Scheduling"],
)
async def validate_schedule_endpoint(request: ValidateRequest) -> ValidateResponse:
    return validate_schedule(request)


# ─────────────────────────────────────────────
# Routing Tool Endpoints
# ─────────────────────────────────────────────

@app.post(
    "/optimize_routing",
    response_model=RoutingResponse,
    operation_id="optimize_routing",
    summary="Solve a Capacitated Vehicle Routing Problem with Time Windows (CVRPTW)",
    description="""
Solves a vehicle routing optimization problem using OR-Tools routing solver.

**Input**: Depot, delivery locations with demands and time windows, vehicles with capacity.
**Output**: Optimized routes per vehicle with stop order, arrival/departure times, load tracking, and aggregate metrics.

**Supported objectives**: minimize_total_distance (default), minimize_total_time, minimize_vehicles, balance_routes.

**Constraints**: Vehicle capacity, time windows per location, service times, max travel time/distance per vehicle, pickup demands.

**Features**: Custom or coordinate-based distance matrix, Haversine GPS distance, drop infeasible visits with penalty.

**Example — 3 deliveries, 2 vehicles**:
```json
{
  "depot_id": "warehouse",
  "locations": [
    {"location_id": "warehouse", "demand": 0},
    {"location_id": "customer_A", "demand": 20, "time_window_start": 0, "time_window_end": 3000, "service_time": 10},
    {"location_id": "customer_B", "demand": 15, "time_window_start": 500, "time_window_end": 4000, "service_time": 10},
    {"location_id": "customer_C", "demand": 25, "time_window_start": 0, "time_window_end": 5000, "service_time": 15}
  ],
  "vehicles": [
    {"vehicle_id": "truck_1", "capacity": 40},
    {"vehicle_id": "truck_2", "capacity": 40}
  ],
  "distance_matrix": [
    {"from_id": "warehouse", "to_id": "customer_A", "distance": 500, "travel_time": 500},
    {"from_id": "warehouse", "to_id": "customer_B", "distance": 800, "travel_time": 800},
    {"from_id": "warehouse", "to_id": "customer_C", "distance": 600, "travel_time": 600},
    {"from_id": "customer_A", "to_id": "warehouse", "distance": 500, "travel_time": 500},
    {"from_id": "customer_A", "to_id": "customer_B", "distance": 400, "travel_time": 400},
    {"from_id": "customer_A", "to_id": "customer_C", "distance": 700, "travel_time": 700},
    {"from_id": "customer_B", "to_id": "warehouse", "distance": 800, "travel_time": 800},
    {"from_id": "customer_B", "to_id": "customer_A", "distance": 400, "travel_time": 400},
    {"from_id": "customer_B", "to_id": "customer_C", "distance": 300, "travel_time": 300},
    {"from_id": "customer_C", "to_id": "warehouse", "distance": 600, "travel_time": 600},
    {"from_id": "customer_C", "to_id": "customer_A", "distance": 700, "travel_time": 700},
    {"from_id": "customer_C", "to_id": "customer_B", "distance": 300, "travel_time": 300}
  ],
  "objective": "minimize_total_distance"
}
```
""",
    tags=["Routing"],
)
async def optimize_routing_endpoint(request: RoutingRequest) -> RoutingResponse:
    return solve_routing(request)


# ─────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────

@app.exception_handler(422)
async def validation_error_handler(request: Request, exc):
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
            "Operations Intelligence Solver — solves Flexible Job Shop Scheduling (CP-SAT) "
            "and Capacitated Vehicle Routing with Time Windows (CVRPTW). "
            "Assign tasks to machines or deliveries to vehicles optimally. "
            "Supports precedence, time windows, capacity, machine eligibility, "
            "setup times, and multiple objectives."
        ),
        describe_all_responses=True,
        describe_full_response_schema=True,
    )
    mcp.mount()
    print("✅ MCP server mounted at /mcp")
except ImportError:
    print("⚠️  fastapi-mcp not installed. MCP endpoint disabled.")
except Exception as e:
    print(f"⚠️  MCP mount failed: {e}. Server running without MCP.")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=True)
