"""
OpenTelemetry initialization for OptimEngine.

Provides distributed tracing across HTTP layer, solver orchestration, and
inner solve calls. Span hierarchy lets observers see (e.g.) for a stochastic
request: HTTP -> orchestrator -> 30 inner solve_schedule spans, each with
their own attributes (n_jobs, n_machines, makespan, solver_status).

Backend: defaults to ConsoleSpanExporter (stdout) for local/dev. If
OTEL_EXPORTER_OTLP_ENDPOINT env var is set, additionally exports via OTLP/HTTP
to an external collector (Tempo, Jaeger, Honeycomb, etc.).

To disable telemetry entirely, set OTEL_ENABLED=false.
"""
from __future__ import annotations
import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

logger = logging.getLogger(__name__)

_initialized = False


def _parse_otlp_headers() -> dict:
    """Parse OTEL_EXPORTER_OTLP_HEADERS env var into a dict for OTLPSpanExporter.

    Format expected: "key1=value1,key2=value2" (OTel spec).
    Returns empty dict if env var not set.
    """
    raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
    if not raw:
        return {}
    headers = {}
    for pair in raw.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            headers[k.strip()] = v.strip()
    return headers


def init_telemetry() -> None:
    """
    Initialize OpenTelemetry tracing globally.

    Idempotent: safe to call multiple times (subsequent calls are no-ops).
    Reads configuration from environment variables:
      - OTEL_ENABLED: set to 'false' to disable (default: enabled)
      - OTEL_SERVICE_NAME: override service name (default: 'optim-engine')
      - OTEL_SERVICE_VERSION: override version (default: '9.0.0')
      - OTEL_EXPORTER_OTLP_ENDPOINT: if set, also exports via OTLP/HTTP
      - OTEL_CONSOLE_EXPORTER: set to 'false' to suppress console output
                               (default: enabled if OTLP endpoint is NOT set)
    """
    global _initialized
    if _initialized:
        return

    if os.getenv("OTEL_ENABLED", "true").lower() == "false":
        logger.info("OTel disabled via OTEL_ENABLED=false")
        _initialized = True
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "optim-engine")
    service_version = os.getenv("OTEL_SERVICE_VERSION", "9.0.0")
    deployment_env = os.getenv("DEPLOYMENT_ENV", "local")

    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": deployment_env,
    })

    provider = TracerProvider(resource=resource)

    # Console exporter (default ON if no OTLP backend configured)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    use_console = os.getenv(
        "OTEL_CONSOLE_EXPORTER",
        "true" if not otlp_endpoint else "false",
    ).lower() == "true"

    if use_console:
        provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )
        logger.info("OTel ConsoleSpanExporter enabled")

    # OTLP exporter if endpoint configured (Tempo / Jaeger / Honeycomb / etc.)
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=_parse_otlp_headers())
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"OTel OTLP exporter enabled: {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"OTel OTLP exporter setup failed: {e}")

    trace.set_tracer_provider(provider)
    _initialized = True
    logger.info(
        f"OTel initialized — service={service_name} version={service_version} env={deployment_env}"
    )


def get_tracer(name: str) -> trace.Tracer:
    """
    Get a tracer for a module. Call this at module top-level:
        from api.observability import get_tracer
        tracer = get_tracer(__name__)
    """
    return trace.get_tracer(name)
