"""
OptimEngine — FastAPI + MCP Server v8.0.0
Operations Intelligence Solver: L1 + L2 + L2.5 + L3
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from solver.models import ScheduleRequest, ScheduleResponse
from solver.engine import solve_schedule
from solver.models import ValidateRequest, ValidateResponse
from solver.validator import validate_schedule

from routing.models import RoutingRequest, RoutingResponse
from routing.engine import solve_routing

from packing.models import PackingRequest, PackingResponse
from packing.engine import solve_packing

from sensitivity.models import SensitivityRequest, SensitivityResponse
from sensitivity.engine import analyze_sensitivity as run_sensitivity

from robust.models import RobustRequest, RobustResponse
from robust.engine import optimize_robust as run_robust

from stochastic.models import StochasticRequest, StochasticResponse
from stochastic.engine import optimize_stochastic as run_stochastic

from pareto.models import ParetoRequest, ParetoResponse
from pareto.engine import optimize_pareto as run_pareto

from prescriptive.models import PrescriptiveRequest, PrescriptiveResponse
from prescriptive.engine import prescriptive_advise as run_prescriptive


APP_NAME = "OptimEngine"
APP_VERSION = "8.0.0"
APP_DESCRIPTION = """
**Operations Intelligence Solver** — MCP-native optimization across 4 intelligence levels.

### Level 1 — Deterministic Optimization
1. **Scheduling** (FJSP) — Tasks to machines.
2. **Routing** (CVRPTW) — Deliveries to vehicles.
3. **Bin Packing** — Items to containers.

### Level 2 — Optimization under Uncertainty
4. **Sensitivity Analysis** — Which parameters break the plan.
5. **Robust Optimization** — Worst-case protection.
6. **Stochastic Optimization** — Monte Carlo + CVaR risk metrics.

### Level 2.5 — Multi-objective Optimization
7. **Pareto Frontier** — Trade-off analysis across competing objectives.

### Level 3 — Prescriptive Intelligence
8. **Prescriptive Advisor** — Forecast + Optimize + Risk + Actionable Recommendations.

All solvers use Google OR-Tools. Exposed as MCP tools for AI agent discovery.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 {APP_NAME} v{APP_VERSION} starting...")
    yield
    print(f"👋 {APP_NAME} shutting down.")


app = FastAPI(title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_request_count = 0
_total_solve_time = 0.0
TRACKED_PATHS = ("/optimize_schedule", "/validate_schedule", "/optimize_routing", "/optimize_packing",
    "/analyze_sensitivity", "/optimize_robust", "/optimize_stochastic", "/optimize_pareto", "/prescriptive_advise")

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
        "name": APP_NAME, "version": APP_VERSION, "status": "operational",
        "capabilities": {
            "level_1": "Deterministic Optimization (scheduling, routing, packing)",
            "level_2": "Optimization under Uncertainty (sensitivity, robust, stochastic)",
            "level_2_5": "Multi-objective Optimization (pareto frontier)",
            "level_3": "Prescriptive Intelligence (forecast + optimize + advise)",
        },
        "tools": [
            {"name": "optimize_schedule", "endpoint": "/optimize_schedule"},
            {"name": "validate_schedule", "endpoint": "/validate_schedule"},
            {"name": "optimize_routing", "endpoint": "/optimize_routing"},
            {"name": "optimize_packing", "endpoint": "/optimize_packing"},
            {"name": "analyze_sensitivity", "endpoint": "/analyze_sensitivity"},
            {"name": "optimize_robust", "endpoint": "/optimize_robust"},
            {"name": "optimize_stochastic", "endpoint": "/optimize_stochastic"},
            {"name": "optimize_pareto", "endpoint": "/optimize_pareto"},
            {"name": "prescriptive_advise", "endpoint": "/prescriptive_advise"},
        ],
        "stats": {"requests_served": _request_count, "total_solve_time_seconds": round(_total_solve_time, 2)},
        "mcp_endpoint": "/mcp",
    }

@app.get("/health", operation_id="health_check", summary="Health check")
async def health():
    return {"status": "healthy", "version": APP_VERSION}

# ─── L1 ───

@app.post("/optimize_schedule", response_model=ScheduleResponse, operation_id="optimize_schedule",
    summary="Solve a Flexible Job Shop Scheduling Problem",
    description="OR-Tools CP-SAT. Precedence, time windows, setup times, priorities, 4 objectives.", tags=["L1 - Scheduling"])
async def ep_schedule(request: ScheduleRequest) -> ScheduleResponse:
    return solve_schedule(request)

@app.post("/validate_schedule", response_model=ValidateResponse, operation_id="validate_schedule",
    summary="Validate an existing schedule", description="Validates against constraints.", tags=["L1 - Scheduling"])
async def ep_validate(request: ValidateRequest) -> ValidateResponse:
    return validate_schedule(request)

@app.post("/optimize_routing", response_model=RoutingResponse, operation_id="optimize_routing",
    summary="Solve a CVRPTW", description="OR-Tools Routing. Capacity, time windows, GPS, drop visits.", tags=["L1 - Routing"])
async def ep_routing(request: RoutingRequest) -> RoutingResponse:
    return solve_routing(request)

@app.post("/optimize_packing", response_model=PackingResponse, operation_id="optimize_packing",
    summary="Solve a Bin Packing Problem", description="OR-Tools CP-SAT. Weight/volume, groups, partial packing.", tags=["L1 - Packing"])
async def ep_packing(request: PackingRequest) -> PackingResponse:
    return solve_packing(request)

# ─── L2 ───

@app.post("/analyze_sensitivity", response_model=SensitivityResponse, operation_id="analyze_sensitivity",
    summary="Parametric Sensitivity Analysis",
    description="Perturbs parameters across any L1 solver. Returns sensitivity scores, elasticity, risk ranking.", tags=["L2 - Uncertainty"])
async def ep_sensitivity(request: SensitivityRequest) -> SensitivityResponse:
    return run_sensitivity(request)

@app.post("/optimize_robust", response_model=RobustResponse, operation_id="optimize_robust",
    summary="Robust Optimization under Uncertainty",
    description="Scenario-based worst-case protection. Modes: worst_case, percentile_90/95, regret_minimization.", tags=["L2 - Uncertainty"])
async def ep_robust(request: RobustRequest) -> RobustResponse:
    return run_robust(request)

@app.post("/optimize_stochastic", response_model=StochasticResponse, operation_id="optimize_stochastic",
    summary="Stochastic Optimization (Monte Carlo + CVaR)",
    description="Monte Carlo simulation with CVaR risk metrics. Normal, uniform, triangular, log-normal distributions.", tags=["L2 - Uncertainty"])
async def ep_stochastic(request: StochasticRequest) -> StochasticResponse:
    return run_stochastic(request)

# ─── L2.5 ───

@app.post("/optimize_pareto", response_model=ParetoResponse, operation_id="optimize_pareto",
    summary="Multi-objective Pareto Frontier",
    description="Generate Pareto frontier for 2-4 competing objectives. Trade-off analysis with correlation and spread.", tags=["L2.5 - Multi-objective"])
async def ep_pareto(request: ParetoRequest) -> ParetoResponse:
    return run_pareto(request)

# ─── L3 ───

@app.post("/prescriptive_advise", response_model=PrescriptiveResponse, operation_id="prescriptive_advise",
    summary="Prescriptive Intelligence — Forecast + Optimize + Advise",
    description=(
        "Full prescriptive pipeline. Provide historical time series data for uncertain parameters. "
        "The engine forecasts future values (exponential smoothing, moving average, linear trend, seasonal naive), "
        "optimizes using forecasted values, assesses risk across conservative/moderate/aggressive scenarios, "
        "and generates prioritized actionable recommendations. Supports 3 risk appetites."
    ), tags=["L3 - Prescriptive"])
async def ep_prescriptive(request: PrescriptiveRequest) -> PrescriptiveResponse:
    return run_prescriptive(request)

# ─── Error Handlers ───

@app.exception_handler(422)
async def err_422(request: Request, exc):
    return JSONResponse(status_code=422, content={"status": "error", "message": "Invalid request format.", "details": str(exc)})

@app.exception_handler(500)
async def err_500(request: Request, exc):
    return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error."})

# ─── MCP ───

try:
    from fastapi_mcp import FastApiMCP
    mcp = FastApiMCP(app, name="OptimEngine",
        description=(
            "Operations Intelligence Solver — "
            "L1: Scheduling (FJSP), Routing (CVRPTW), Bin Packing. "
            "L2: Sensitivity, Robust, Stochastic (Monte Carlo + CVaR). "
            "L2.5: Multi-objective Pareto Frontier. "
            "L3: Prescriptive Intelligence (Forecast + Optimize + Advise). "
            "All powered by Google OR-Tools."
        ), describe_all_responses=True, describe_full_response_schema=True)
    mcp.mount()
    print("✅ MCP server mounted at /mcp")
except ImportError:
    print("⚠️  fastapi-mcp not installed.")
except Exception as e:
    print(f"⚠️  MCP mount failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
