# ⚡ OptimEngine

**Optimization service — 4-layer architecture, OR-Tools CP-SAT, MCP-native, OAuth 2.1, observability-first.**

[![Tests](https://github.com/MicheleCampi/optim-engine/actions/workflows/tests.yml/badge.svg)](https://github.com/MicheleCampi/optim-engine/actions/workflows/tests.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)
[![Production](https://img.shields.io/badge/production-Feb--Oct%202026-lightgrey)](#production-history-feb-oct-2026)

---

## Overview

OptimEngine solves NP-hard optimization problems (scheduling, routing, packing) and quantifies risk under uncertainty (sensitivity, robust, stochastic, Pareto). It exposes 11 tools across 4 intelligence levels (L1 deterministic → L3 prescriptive) over both REST and MCP (SSE + Streamable HTTP with OAuth 2.1).

The system is built around three engineering principles: **mathematical correctness** (real CP-SAT solvers, not LLM approximations), **operational hygiene** (full observability stack, test coverage on business logic, load-tested), and **agent-friendliness** (MCP dual-stack, OAuth, rate limiting, JSON-only contracts).

## Architecture

```mermaid
flowchart TB
    Client[AI Agents / MCP Clients / REST] --> Edge[Edge Proxy<br/>Vercel]
    Edge --> L2[L2 Core Gateway<br/>FastAPI · orchestration]
    L2 --> L1[L1 Solver Layer<br/>OR-Tools 9.15 CP-SAT<br/>FJSP · CVRPTW · Packing · Sensitivity · Robust · Stochastic · Pareto · Prescriptive]
    L2 --> L3[L3 Thin Proxies<br/>Payment rails · MCP discovery]
    L1 --> Obs[Observability<br/>OpenTelemetry · Prometheus · Grafana Cloud]
    L2 --> Obs
    L3 --> Obs
```

Four layers plus edge proxy, deployed across 6 Railway services + 1 Vercel function from February to 23 October 2026, then shut down to stop costs. All layers instrumented with OpenTelemetry tracing, Prometheus middleware, and Telegram alerting on payment events.

## Tech Stack

| Layer            | Technologies                                                      |
|------------------|-------------------------------------------------------------------|
| Runtime          | Python 3.12, FastAPI, Uvicorn                                     |
| Solvers          | OR-Tools 9.15 CP-SAT, NumPy, custom Monte Carlo                   |
| MCP              | FastMCP (SSE + Streamable HTTP), ScaleKit OAuth 2.1, PyJWT        |
| Validation       | Pydantic v2                                                       |
| Observability    | OpenTelemetry SDK, Prometheus client, Grafana Cloud               |
| Load testing     | Locust 2.43                                                       |
| CI               | GitHub Actions, pytest, pytest-cov                                |
| Deploy           | Docker (local); Railway + Vercel until Oct 2026; GitHub Actions   |

## Capabilities

### L1 — Deterministic Optimization

| Solver       | Problem                  | Key features                                                                                          |
|--------------|--------------------------|-------------------------------------------------------------------------------------------------------|
| Scheduling   | Flexible Job Shop (FJSP) | Precedence, time windows, per-machine durations, availability windows, quality gates, setup matrix    |
| Routing      | CVRPTW                   | Capacity, time windows, GPS distances, drop visits, 4 objectives                                      |
| Bin Packing  | Multi-dim packing        | Weight + volume constraints, item quantities, groups, partial packing, 4 objectives                   |

### L2 — Optimization under Uncertainty

| Module                  | Capability                                       | Output                                                          |
|-------------------------|--------------------------------------------------|-----------------------------------------------------------------|
| Sensitivity Analysis    | One-at-a-time parameter perturbation             | Fragility map, sensitivity scores, critical flags, risk ranking |
| Robust Optimization     | Uncertainty ranges → worst-case protection       | Robust solution, price of robustness, feasibility rate          |
| Stochastic Optimization | Probability distributions → Monte Carlo          | Expected value, VaR, CVaR (90/95/99 %), distribution summary    |

### L2.5 — Multi-objective

| Module          | Capability                       | Output                                                          |
|-----------------|----------------------------------|-----------------------------------------------------------------|
| Pareto Frontier | 2-4 competing objectives         | Non-dominated solutions, trade-off ratios, correlation analysis |

### L3 — Prescriptive

| Module               | Capability                                                       | Output                                                              |
|----------------------|------------------------------------------------------------------|---------------------------------------------------------------------|
| Prescriptive Advise  | Historical data → Forecast → Optimize → Risk → Recommend         | Actions, risk-adjusted makespan, feasibility risk assessment        |

## Performance

Load-test benchmark summary (full report: [`BENCHMARKS.md`](./BENCHMARKS.md)):

- **757 requests served, 0 failures** across 20 minutes of cumulative load
- **Infrastructure floor: ~200 ms** (FastAPI + edge proxy + auth + observability overhead)
- **Saturation knee at 5 concurrent users** on the Railway tier used in production; system degrades gracefully past it
- **Bottleneck: solver CPU**, not infrastructure — scaling path is horizontal at L1, not vertical at the gateway

The public Grafana dashboard was retired together with the deployment.

## Testing & CI

[![Tests](https://github.com/MicheleCampi/optim-engine/actions/workflows/tests.yml/badge.svg)](https://github.com/MicheleCampi/optim-engine/actions/workflows/tests.yml)

- **121 tests** across 7 solver modules, all passing
- **77 % overall coverage**, **88 % average on business-logic engines**
- Runs on every push and pull request via GitHub Actions
- Coverage reports uploaded as build artifacts (HTML + XML)

The test suite exercises real CP-SAT solves, not mocks: assertions verify mathematical properties (CVaR ordering, capacity constraints, monotonicity under perturbation) rather than just code paths.

## v9.0.0 Highlights

Four scheduling-engine upgrades that close the gap between academic FJSP and how real workshops operate. All backward compatible with v8 requests.

**Duration per machine** — same task, different times on different machines:

```json
{
  "task_id": "milling",
  "duration": 100,
  "eligible_machines": ["CNC-1", "CNC-2"],
  "duration_per_machine": {"CNC-1": 120, "CNC-2": 80}
}
```

**Availability windows** — multiple shifts and maintenance gaps per machine:

```json
{
  "machine_id": "CNC-1",
  "availability_windows": [
    {"start": 0, "end": 480},
    {"start": 510, "end": 960}
  ]
}
```

**Quality gates** — jobs require minimum quality, machines have yield rates:

```json
{ "job_id": "ORD-BOSCH", "quality_min": 0.97 }
{ "machine_id": "CNC-4", "yield_rate": 0.99 }
```

**Setup-time matrix** — sequence-dependent changeover costs:

```json
{
  "setup_times": [
    {"machine_id": "M1", "from_job_id": "J1", "to_job_id": "J2", "setup_time": 15}
  ]
}
```

## Quick Start (local)

The hosted deployment ran on Railway from February to 23 October 2026 and is now shut down to stop costs. Everything below runs locally with Docker; verified on 2026-11-08 with the exact payload shown.

```bash
docker build -t optim-engine .
docker run --rm -p 8080:8080 -e PORT=8080 optim-engine
```

### REST (curl)

```bash
curl -X POST localhost:8080/optimize_schedule \
  -H "Content-Type: application/json" \
  -d '{
    "jobs": [
      {"job_id": "J1", "tasks": [
        {"task_id": "cut", "duration": 30, "eligible_machines": ["M1", "M2"]},
        {"task_id": "weld", "duration": 20, "eligible_machines": ["M2"]}
      ]}
    ],
    "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
    "objective": "minimize_makespan"
  }'
```

Returns `"status": "optimal"`, makespan 50. Set `ENGINE_API_KEY` to require an `X-Engine-Key` header on solver paths.

### MCP

SSE transport at `http://localhost:8080/mcp`:

```json
{
  "mcpServers": {
    "optim-engine": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

`/mcp/v2` (Streamable HTTP + OAuth 2.1 via ScaleKit) is mounted only when the `SCALEKIT_*` environment variables are set.

## Validation Case Study: MetalPrecision (synthetic)

Synthetic dataset modeled after Italian precision-machining workshops — 4 CNC centers (2015-2023 vintages), 5 client orders modeled on real automotive/industrial customers, 15 tasks. Used to validate solver behavior end-to-end across all 7 modules.

| Tool                    | Result                                                                          |
|-------------------------|---------------------------------------------------------------------------------|
| `optimize_schedule`     | Optimal makespan 225 min, 5/5 on-time, 83.3 % avg utilization, 0.04 s           |
| `validate_schedule`     | Zero violations, 2 improvement suggestions                                       |
| `analyze_sensitivity`   | 73 solves in 3.6 s, most sensitive parameter identified (sensitivity score 8.9)  |
| `optimize_robust`       | Worst-case 210 min, price of robustness 7.7 %, 100 % feasibility                 |
| `optimize_pareto`       | Trade-off frontier: 195/15 min vs 220/0 min, correlation -1.0                    |
| `optimize_stochastic`   | 30 Monte Carlo scenarios, CVaR95 = 188.5, CV 4.7 %                               |
| `prescriptive_advise`   | Forecast +1.3 %/period, risk-adjusted range 167-183                              |

> Customer names in the dataset are illustrative. This is not a live customer deployment; it's a benchmark scenario used for solver validation and demo purposes.

## Production history (Feb-Oct 2026)

From 22 February to 23 October 2026 the service ran in production, then was shut down to stop costs:

| Endpoint (retired)                                | Role                                              |
|---------------------------------------------------|---------------------------------------------------|
| `optim-engine-production.up.railway.app`          | L1 + L2 + L3 compute (Railway, 6 services)        |
| Edge proxy (Vercel)                               | CORS handling, header rewriting, edge caching     |
| MCP connector on claude.ai                        | Tool surface for Claude clients                   |

The load-test numbers above were measured on that deployment.

## Discovery

While in production it was listed for agent-economy discovery on **x402scan**, **Smithery**, and **the402.ai**. The system supports x402 micropayments on Base and Solana for paid-tier endpoints; payment integration is documented in the L3 thin-proxy layer but is not the project's primary focus.

## License

MIT — see [LICENSE](LICENSE).

Built by [Michele Campi](https://github.com/MicheleCampi).
