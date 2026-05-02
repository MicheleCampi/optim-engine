"""
OptimEngine — FastAPI + MCP Server v9.0.0
Operations Intelligence Solver: L1 + L2 + L2.5 + L3
"""

import os
import time
from collections import defaultdict, deque
from threading import Lock
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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

# ─── Prometheus metrics ───
from api.metrics import (
    PrometheusMiddleware,
    instrument_solver,
    verify_metrics_token,
    metrics_response,
)
from fastapi import Depends

# ─── ScaleKit OAuth via PyJWT (MCP v2 auth) ───
# Uses PyJWT + cryptography to validate ScaleKit-issued JWTs directly,
# avoiding the scalekit-sdk-python package which conflicts with OR-Tools protobuf.
import jwt as pyjwt
import urllib.request
import json as _json

_SCALEKIT_ENV_URL = os.environ.get("SCALEKIT_ENVIRONMENT_URL", "")
_SCALEKIT_RESOURCE_ID = os.environ.get("SCALEKIT_RESOURCE_ID", "")
_SCALEKIT_READY = bool(_SCALEKIT_ENV_URL and _SCALEKIT_RESOURCE_ID)
_jwks_client = None

if _SCALEKIT_READY:
    try:
        _jwks_client = pyjwt.PyJWKClient(
            f"{_SCALEKIT_ENV_URL}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )
        print(f"\u2705 ScaleKit JWKS client initialized for {_SCALEKIT_ENV_URL}")
    except Exception as e:
        print(f"\u26a0\ufe0f  ScaleKit JWKS init failed: {e}")
        _SCALEKIT_READY = False
        _jwks_client = None


APP_NAME = "OptimEngine"
APP_VERSION = "9.0.0"
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
# CORS middleware intenzionalmente rimosso (19 apr 2026).

# ─── Observability ───
app.add_middleware(PrometheusMiddleware)


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request, _: None = Depends(verify_metrics_token)):
    """Prometheus scrape endpoint. Bearer-token protected via METRICS_TOKEN env."""
    return metrics_response()
# OptimEngine è server-to-server only: Next.js proxy, MCP client, agent API calls.
# Nessun browser client legittimo chiama direttamente questo backend.
# Se un domani serve browser access, aggiungere CORSMiddleware con whitelist esplicita,
# mai con allow_origins=["*"].

# ── API Key Protection ──
ENGINE_API_KEY = os.environ.get("ENGINE_API_KEY", "")

@app.middleware("http")
async def check_engine_key(request: Request, call_next):
    # Public paths - no key required
    public_paths = ("/", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico", "/metrics")
    if request.url.path in public_paths or request.url.path.startswith("/mcp") or request.url.path.startswith("/.well-known"):
        return await call_next(request)
    # If ENGINE_API_KEY is set, require it on all solver paths
    if ENGINE_API_KEY:
        provided_key = request.headers.get("X-Engine-Key", "")
        if provided_key != ENGINE_API_KEY:
            return JSONResponse(status_code=403, content={"error": "Forbidden", "message": "Invalid or missing X-Engine-Key"})
    return await call_next(request)

# ─── Rate Limiting MCP (Free Tier) ───
# Protects the open MCP endpoint from abuse while keeping it free for demos.
# Paid production access goes through the x402 gateways (18 endpoints on Base,
# registered on x402scan). This middleware only affects /mcp/messages (tool calls),
# not the SSE handshake at /mcp itself.
MCP_RATE_LIMIT = 10  # requests per hour per IP
MCP_WINDOW_SECONDS = 3600
_mcp_hits: dict = defaultdict(deque)
_mcp_hits_lock = Lock()

@app.middleware("http")
async def mcp_rate_limit(request: Request, call_next):
    # Only rate-limit MCP tool calls (not the SSE handshake on /mcp itself)
    if not (request.url.path.startswith("/mcp/messages") or request.url.path.startswith("/mcp/v2")):
        return await call_next(request)

    # Get real client IP (Railway reverse proxy uses X-Forwarded-For)
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    now = time.time()
    with _mcp_hits_lock:
        hits = _mcp_hits[client_ip]
        # Clean old hits outside the rolling window
        while hits and hits[0] < now - MCP_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= MCP_RATE_LIMIT:
            retry_after = int(hits[0] + MCP_WINDOW_SECONDS - now)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": (
                        f"Free MCP tier: {MCP_RATE_LIMIT} tool calls per hour per IP. "
                        "For production use, visit https://www.x402scan.com and search "
                        "'OptimEngine' to find all 18 paid endpoints (USDC on Base, from $0.05)."
                    ),
                    "retry_after_seconds": retry_after,
                    "free_tier_limit": MCP_RATE_LIMIT,
                    "window": "1 hour",
                    "paid_tier": "https://www.x402scan.com",
                },
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)

    return await call_next(request)

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

# ─── OAuth Protected Resource Discovery (MCP v2) ───
@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    """MCP clients call this to discover the OAuth 2.1 authorization server."""
    base_url = os.environ.get("BASE_URL", "https://optim-engine-production.up.railway.app")
    if not _SCALEKIT_ENV_URL or not _SCALEKIT_RESOURCE_ID:
        return JSONResponse(status_code=503, content={"error": "OAuth not configured"})
    return {
        "authorization_servers": [
            os.environ.get("BASE_URL", "https://optim-engine-production.up.railway.app")
        ],
        "bearer_methods_supported": ["header"],
        "resource": base_url,
        "resource_documentation": f"{base_url}/docs",
        "scopes_supported": [],
    }

@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    """Proxy ScaleKit's OAuth AS metadata with corrected issuer for RFC 8414 compliance.
    Smithery requires issuer == authorization_servers URL. ScaleKit sets issuer to the
    base env URL regardless of the resource path. We serve the metadata ourselves with
    the issuer set to our own BASE_URL so the match succeeds."""
    base_url = os.environ.get("BASE_URL", "https://optim-engine-production.up.railway.app")
    if not _SCALEKIT_ENV_URL or not _SCALEKIT_RESOURCE_ID:
        return JSONResponse(status_code=503, content={"error": "OAuth not configured"})
    # Fetch the real metadata from ScaleKit (resource-scoped)
    try:
        sk_url = f"{_SCALEKIT_ENV_URL}/resources/{_SCALEKIT_RESOURCE_ID}/.well-known/oauth-authorization-server"
        req = urllib.request.Request(sk_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            metadata = _json.loads(resp.read())
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Failed to fetch ScaleKit metadata: {str(e)}"})
    # Override issuer to match our authorization_servers URL (RFC 8414 compliance)
    metadata["issuer"] = base_url
    return metadata

@app.get("/.well-known/mcp/server-card.json")
async def mcp_server_card():
    """Static server card for Smithery discovery — bypasses MCP scanning."""
    return {
        "serverInfo": {
            "name": "OptimEngine",
            "version": "9.0.0"
        },
        "authentication": {
            "required": True,
            "schemes": ["oauth2"]
        },
        "tools": [
            {"name": "optimize_schedule", "description": "Solve a Flexible Job Shop Scheduling Problem — OR-Tools CP-SAT with precedence, time windows, setup times, priorities, 4 objectives", "inputSchema": {"type": "object", "properties": {"jobs": {"type": "array"}, "machines": {"type": "array"}, "objective": {"type": "string"}}, "required": ["jobs", "machines"]}},
            {"name": "validate_schedule", "description": "Validate an existing schedule against constraints", "inputSchema": {"type": "object", "properties": {"jobs": {"type": "array"}, "machines": {"type": "array"}, "schedule": {"type": "array"}}, "required": ["jobs", "machines", "schedule"]}},
            {"name": "optimize_routing", "description": "Solve a CVRPTW — OR-Tools Routing with capacity, time windows, GPS, drop visits", "inputSchema": {"type": "object", "properties": {"depot_id": {"type": "string"}, "locations": {"type": "array"}, "vehicles": {"type": "array"}, "distance_matrix": {"type": "array"}}, "required": ["depot_id", "locations", "vehicles", "distance_matrix"]}},
            {"name": "optimize_packing", "description": "Solve a Bin Packing Problem — OR-Tools CP-SAT with weight/volume, groups, partial packing", "inputSchema": {"type": "object", "properties": {"bins": {"type": "array"}, "items": {"type": "array"}, "objective": {"type": "string"}}, "required": ["bins", "items"]}},
            {"name": "analyze_sensitivity", "description": "Parametric Sensitivity Analysis — perturbs parameters across any L1 solver, returns sensitivity scores, elasticity, risk ranking", "inputSchema": {"type": "object", "properties": {"solver_type": {"type": "string"}, "solver_request": {"type": "object"}}, "required": ["solver_type", "solver_request"]}},
            {"name": "optimize_robust", "description": "Robust Optimization under Uncertainty — scenario-based worst-case protection with modes: worst_case, percentile_90/95, regret", "inputSchema": {"type": "object", "properties": {"solver_type": {"type": "string"}, "solver_request": {"type": "object"}, "uncertain_parameters": {"type": "array"}}, "required": ["solver_type", "solver_request", "uncertain_parameters"]}},
            {"name": "optimize_stochastic", "description": "Stochastic Optimization — Monte Carlo simulation with CVaR risk metrics, normal/uniform/triangular/log-normal distributions", "inputSchema": {"type": "object", "properties": {"solver_type": {"type": "string"}, "solver_request": {"type": "object"}, "stochastic_parameters": {"type": "array"}}, "required": ["solver_type", "solver_request", "stochastic_parameters"]}},
            {"name": "optimize_pareto", "description": "Multi-objective Pareto Frontier — generate trade-off analysis for 2-4 competing objectives", "inputSchema": {"type": "object", "properties": {"solver_type": {"type": "string"}, "objectives": {"type": "array"}, "solver_request": {"type": "object"}}, "required": ["solver_type", "objectives", "solver_request"]}},
            {"name": "prescriptive_advise", "description": "Prescriptive Intelligence — forecast + optimize + risk assess + actionable recommendations with 3 risk appetites", "inputSchema": {"type": "object", "properties": {"solver_type": {"type": "string"}, "solver_request": {"type": "object"}, "forecast_parameters": {"type": "array"}}, "required": ["solver_type", "solver_request", "forecast_parameters"]}}
        ],
        "resources": [],
        "prompts": []
    }

# ─── L1 ───

@app.post("/optimize_schedule", response_model=ScheduleResponse, operation_id="optimize_schedule",
    summary="Solve a Flexible Job Shop Scheduling Problem",
    description="OR-Tools CP-SAT. Precedence, time windows, setup times, priorities, 4 objectives.", tags=["L1 - Scheduling"])
@instrument_solver("/optimize_schedule", objective_path="metrics.makespan")
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
@instrument_solver("/optimize_stochastic", objective_path="recommended_objective")
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
    mcp.mount_sse(mount_path="/mcp")
    print("✅ MCP server mounted at /mcp (SSE, open — free tier)")

    # ── MCP v2: Streamable HTTP + OAuth 2.1 ──
    if _SCALEKIT_READY:
        # Auth middleware that protects only /mcp/v2
        @app.middleware("http")
        async def mcp_v2_auth(request: Request, call_next):
            if not request.url.path.startswith("/mcp/v2"):
                return await call_next(request)
            # Allow .well-known discovery without auth
            if ".well-known" in request.url.path:
                return await call_next(request)
            # Extract Bearer token
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                metadata_url = f"{os.environ.get('BASE_URL', 'https://optim-engine-production.up.railway.app')}/.well-known/oauth-protected-resource"
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "message": "Bearer token required"},
                    headers={"WWW-Authenticate": f'Bearer realm="OAuth", resource_metadata="{metadata_url}"'},
                )
            token = auth_header.split("Bearer ")[1].strip()
            # Validate JWT with ScaleKit's public keys (via PyJWKClient)
            try:
                signing_key = _jwks_client.get_signing_key_from_jwt(token)
                pyjwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=_SCALEKIT_RESOURCE_ID,
                    issuer=_SCALEKIT_ENV_URL,
                    options={"require": ["exp", "iss", "aud"]},
                )
            except Exception:
                metadata_url = f"{os.environ.get('BASE_URL', 'https://optim-engine-production.up.railway.app')}/.well-known/oauth-protected-resource"
                return JSONResponse(
                    status_code=401,
                    content={"error": "invalid_token", "message": "Token validation failed"},
                    headers={"WWW-Authenticate": f'Bearer realm="OAuth", resource_metadata="{metadata_url}"'},
                )
            return await call_next(request)

        mcp.mount_http(mount_path="/mcp/v2")
        print("✅ MCP v2 mounted at /mcp/v2 (Streamable HTTP + OAuth 2.1 via ScaleKit)")
    else:
        print("⚠️  ScaleKit not configured — /mcp/v2 not mounted (missing SCALEKIT_* env vars)")
except ImportError:
    print("⚠️  fastapi-mcp not installed.")
except Exception as e:
    print(f"⚠️  MCP mount failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
