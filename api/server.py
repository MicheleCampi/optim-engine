"""
OptimEngine — FastAPI + MCP Server
Exposes scheduling, routing, and bin packing solvers as MCP tools for AI agents.

Six tools exposed:
  1. optimize_schedule — Solve a Flexible Job Shop Scheduling Problem
  2. validate_schedule — Validate an existing schedule
  3. optimize_routing  — Solve a CVRPTW
  4. optimize_packing  — Solve a Bin Packing Problem
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

from packing.models import (
    PackingRequest, PackingResponse,
    PackingStatus,
)
from packing.engine import solve_packing


APP_NAME = "OptimEngine"
APP_VERSION = "3.0.0"
APP_DESCRIPTION = """
**Operations Intelligence Solver** — An MCP-native optimization engine.

Three solver modules for AI agents:

### 1. Scheduling (Flexible Job Shop)
Assign tasks to machines optimally with precedence, time windows, setup times, priorities.

### 2. Routing (CVRPTW)
Assign delivery locations to vehicles with capacity constraints and time windows.

### 3. Bin Packing
Assign items to bins/containers optimally with weight, volume, and group constraints.

All solvers use Google OR-Tools and are exposed as MCP tools for AI agent discovery.
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


_request_count = 0
_total_solve_time = 0.0

TRACKED_PATHS = ("/optimize_schedule", "/validate_schedule", "/optimize_routing", "/optimize_packing")


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


@app.get("/", operation_id="root", summary="Server info and status")
async def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "operational",
        "tools": [
            {"name": "optimize_schedule", "description": "Solve a Flexible Job Shop Scheduling Problem.", "endpoint": "/optimize_schedule"},
            {"name": "validate_schedule", "description": "Validate an existing schedule against constraints.", "endpoint": "/validate_schedule"},
            {"name": "optimize_routing", "description": "Solve a CVRPTW. Assign deliveries to vehicles optimally.", "endpoint": "/optimize_routing"},
            {"name": "optimize_packing", "description": "Solve a Bin Packing problem. Assign items to bins optimally.", "endpoint": "/optimize_packing"},
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
# Scheduling
# ─────────────────────────────────────────────

@app.post(
    "/optimize_schedule",
    response_model=ScheduleResponse,
    operation_id="optimize_schedule",
    summary="Solve a Flexible Job Shop Scheduling Problem",
    description="Solves scheduling using OR-Tools CP-SAT. Supports precedence, time windows, machine eligibility, setup times, priorities, and 4 objectives.",
    tags=["Scheduling"],
)
async def optimize_schedule_endpoint(request: ScheduleRequest) -> ScheduleResponse:
    return solve_schedule(request)


@app.post(
    "/validate_schedule",
    response_model=ValidateResponse,
    operation_id="validate_schedule",
    summary="Validate an existing schedule",
    description="Validates a schedule against job/machine constraints. Returns violations and improvement suggestions.",
    tags=["Scheduling"],
)
async def validate_schedule_endpoint(request: ValidateRequest) -> ValidateResponse:
    return validate_schedule(request)


# ─────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────

@app.post(
    "/optimize_routing",
    response_model=RoutingResponse,
    operation_id="optimize_routing",
    summary="Solve a CVRPTW (Vehicle Routing with Time Windows)",
    description="Solves vehicle routing using OR-Tools. Supports capacity, time windows, service times, GPS coordinates, drop visits, and 4 objectives.",
    tags=["Routing"],
)
async def optimize_routing_endpoint(request: RoutingRequest) -> RoutingResponse:
    return solve_routing(request)


# ─────────────────────────────────────────────
# Packing
# ─────────────────────────────────────────────

@app.post(
    "/optimize_packing",
    response_model=PackingResponse,
    operation_id="optimize_packing",
    summary="Solve a Bin Packing Problem",
    description="Solves bin packing using OR-Tools CP-SAT. Supports weight/volume constraints, item quantities, group constraints, partial packing, and 4 objectives (minimize bins, maximize value/items, balance load).",
    tags=["Packing"],
)
async def optimize_packing_endpoint(request: PackingRequest) -> PackingResponse:
    return solve_packing(request)


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
            "Operations Intelligence Solver — Scheduling (FJSP), "
            "Vehicle Routing (CVRPTW), and Bin Packing. "
            "Assign tasks to machines, deliveries to vehicles, or items to bins optimally. "
            "All solvers powered by Google OR-Tools."
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=True)
