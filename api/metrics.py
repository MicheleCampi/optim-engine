"""
OptimEngine — Prometheus metrics module
Centralized metric definitions. Single source of truth.

Design:
- HTTP metrics via middleware (latency, status codes per endpoint)
- Solver metrics via decorator (objective, status, duration per solver)
- /metrics endpoint protected by bearer token (METRICS_TOKEN env var)
"""

import os
import time
from functools import wraps
from typing import Callable

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# ─── Registry ───────────────────────────────────────────────────────────
# Custom registry instead of default global REGISTRY to avoid double-registration
# on uvicorn --reload during development.
REGISTRY = CollectorRegistry()

# ─── HTTP Metrics ───────────────────────────────────────────────────────
HTTP_REQUESTS_TOTAL = Counter(
    "optimengine_http_requests_total",
    "Total HTTP requests by endpoint, method, and status code",
    ["endpoint", "method", "status_code"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION = Histogram(
    "optimengine_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint", "method"],
    # Buckets tuned for OR-Tools workloads:
    # fast endpoints (validate, health) < 100ms
    # most solvers 100ms - 5s
    # heavy stochastic/pareto can hit 10-60s
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=REGISTRY,
)

# ─── Solver Metrics ─────────────────────────────────────────────────────
SOLVER_REQUESTS_TOTAL = Counter(
    "optimengine_solver_requests_total",
    "Total solver invocations by endpoint and solver status",
    ["endpoint", "solver_status"],
    registry=REGISTRY,
)

SOLVER_DURATION = Histogram(
    "optimengine_solver_duration_seconds",
    "Pure solver wall-clock duration (excludes HTTP/validation overhead)",
    ["endpoint"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=REGISTRY,
)

SOLVER_OBJECTIVE_VALUE = Gauge(
    "optimengine_solver_objective_value",
    "Last objective value returned by solver (for trend analysis)",
    ["endpoint"],
    registry=REGISTRY,
)

SOLVER_ACTIVE = Gauge(
    "optimengine_solver_active",
    "Currently executing solver invocations (concurrency)",
    ["endpoint"],
    registry=REGISTRY,
)

# ─── Business Metrics ───────────────────────────────────────────────────
SOLVER_INFEASIBLE_TOTAL = Counter(
    "optimengine_solver_infeasible_total",
    "Solver runs that returned INFEASIBLE (no valid plan exists)",
    ["endpoint"],
    registry=REGISTRY,
)

SOLVER_TIMEOUT_TOTAL = Counter(
    "optimengine_solver_timeout_total",
    "Solver runs that hit time limit (returned UNKNOWN or partial FEASIBLE)",
    ["endpoint"],
    registry=REGISTRY,
)


# ─── HTTP Middleware ────────────────────────────────────────────────────
class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Captures latency + status code for every HTTP request.
    Uses route.path (e.g. /schedule) instead of request.url.path
    so that path params don't blow up cardinality.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start
            # Resolve to route template if matched, else raw path
            route = request.scope.get("route")
            endpoint = route.path if route else request.url.path

            # Skip /metrics itself — don't pollute its own metrics
            if endpoint != "/metrics":
                HTTP_REQUESTS_TOTAL.labels(
                    endpoint=endpoint,
                    method=request.method,
                    status_code=str(status_code),
                ).inc()
                HTTP_REQUEST_DURATION.labels(
                    endpoint=endpoint,
                    method=request.method,
                ).observe(duration)

        return response


# ─── Solver Decorator ───────────────────────────────────────────────────
# Maps OR-Tools status integer codes to readable labels.
# 0=UNKNOWN, 1=MODEL_INVALID, 2=FEASIBLE, 3=INFEASIBLE, 4=OPTIMAL
_STATUS_MAP = {
    0: "UNKNOWN",
    1: "MODEL_INVALID",
    2: "FEASIBLE",
    3: "INFEASIBLE",
    4: "OPTIMAL",
}


def instrument_solver(endpoint: str, objective_path: str | None = None):
    """
    Decorator for solver entrypoints.

    Captures: duration, status, objective_value, active concurrency.

    Args:
        endpoint: Endpoint label for metrics (e.g. "/optimize_schedule").
        objective_path: Dotted attribute path to the primary objective scalar
            on the response object. Examples:
              - "metrics.makespan" (scheduling minimize-makespan)
              - "objective_value" (top-level)
              - None (no objective tracking, e.g. Pareto frontier)
            Path traversal is fail-safe: any missing attribute → no update.

    Status extraction: reads `.status` and accepts either OR-Tools int codes
    or string enums (lowercased like SolverStatus). Falls back to "UNREPORTED".
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            SOLVER_ACTIVE.labels(endpoint=endpoint).inc()
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                _record(endpoint, result, time.perf_counter() - start, objective_path)
                return result
            except Exception:
                SOLVER_REQUESTS_TOTAL.labels(
                    endpoint=endpoint, solver_status="ERROR"
                ).inc()
                raise
            finally:
                SOLVER_ACTIVE.labels(endpoint=endpoint).dec()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            SOLVER_ACTIVE.labels(endpoint=endpoint).inc()
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                _record(endpoint, result, time.perf_counter() - start, objective_path)
                return result
            except Exception:
                SOLVER_REQUESTS_TOTAL.labels(
                    endpoint=endpoint, solver_status="ERROR"
                ).inc()
                raise
            finally:
                SOLVER_ACTIVE.labels(endpoint=endpoint).dec()

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _resolve_path(obj, path: str):
    """Walk dotted attribute path safely. Returns None on any miss."""
    current = obj
    for part in path.split("."):
        if current is None:
            return None
        current = getattr(current, part, None)
    return current


def _record(endpoint: str, result, duration: float, objective_path: str | None) -> None:
    """Extract status + objective from result and update metrics."""
    SOLVER_DURATION.labels(endpoint=endpoint).observe(duration)

    status = getattr(result, "status", None)
    # SolverStatus enum has .value; pydantic may serialize to enum or str
    if hasattr(status, "value"):
        status = status.value
    if isinstance(status, int):
        status_label = _STATUS_MAP.get(status, f"CODE_{status}")
    elif isinstance(status, str):
        status_label = status.upper()
    else:
        status_label = "UNREPORTED"

    SOLVER_REQUESTS_TOTAL.labels(
        endpoint=endpoint, solver_status=status_label
    ).inc()

    if status_label == "INFEASIBLE":
        SOLVER_INFEASIBLE_TOTAL.labels(endpoint=endpoint).inc()
    if status_label in ("UNKNOWN", "TIMEOUT"):
        SOLVER_TIMEOUT_TOTAL.labels(endpoint=endpoint).inc()

    if objective_path:
        objective = _resolve_path(result, objective_path)
        if objective is not None and isinstance(objective, (int, float)):
            SOLVER_OBJECTIVE_VALUE.labels(endpoint=endpoint).set(float(objective))


# ─── /metrics Endpoint Auth ─────────────────────────────────────────────
def verify_metrics_token(request: Request) -> None:
    """
    Bearer token auth for /metrics endpoint.
    Token read from METRICS_TOKEN env var. If unset, /metrics is disabled
    (returns 503) — fail-closed instead of fail-open.
    """
    expected = os.environ.get("METRICS_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Metrics endpoint disabled: METRICS_TOKEN not configured",
        )

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    provided = auth_header[7:].strip()
    # Constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid token")


def metrics_response() -> Response:
    """Render Prometheus exposition format."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
