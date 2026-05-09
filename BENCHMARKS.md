# OptimEngine — Performance Benchmarks

Last run: 2026-05-09
Methodology version: 1.0

This document characterizes the performance envelope of OptimEngine under
synthetic load, identifies the system bottleneck, and reports the steady-state
operating point. All numbers are reproducible from `load_tests/locustfile.py`
against the production deployment on Railway.

## TL;DR

- **Steady-state throughput at design concurrency (5 users, no wait):** 0.38 RPS
  aggregate across `/optimize_schedule`, `/optimize_routing`,
  `/optimize_packing`.
- **System is solver-bound, not infrastructure-bound.** The infrastructure
  floor (FastAPI + edge proxy + auth + observability overhead) is ~200 ms.
  The dominant component of latency is CP-SAT solve time on FJSP and CVRPTW
  workloads.
- **Saturation knee at 5 concurrent users on the current Railway tier.**
  Doubling concurrency to 10 users degrades throughput by 13 % and inflates
  median latency 3x, while still serving every request without error.
- **Zero failures across 757 requests in 20 minutes of cumulative load.**
  The system degrades gracefully past the knee point: it slows, it does not
  break.
- **Scaling path is horizontal at the L1 solver layer**, not vertical at the
  FastAPI gateway. See "Scaling Implications" below.

## Methodology

### Tool
[Locust 2.43.4](https://locust.io) in headless mode, CSV output with full
history. Locust file: `load_tests/locustfile.py`. Generators in
`load_tests/generators/`.

### Workload Mix
The locust users hit three solver endpoints with weighted task distribution
representative of the manufacturing/logistics domain:

| Endpoint              | Default weight | Solver               | Typical complexity |
|-----------------------|----------------|----------------------|--------------------|
| `/optimize_schedule`  | 4              | CP-SAT FJSP          | NP-hard            |
| `/optimize_routing`   | 2              | CP-SAT CVRPTW        | NP-hard            |
| `/optimize_packing`   | 1              | CP-SAT bin packing   | NP-hard            |

Each call randomly selects a problem size class:
- 60 % small (fast solves, mostly OPTIMAL)
- 30 % medium (mixed OPTIMAL/FEASIBLE)
- 10 % large (mostly FEASIBLE/TIMEOUT due to CP-SAT `max_time_in_seconds`)

This produces a realistic dispersion across solver outcome buckets rather
than a degenerate all-OPTIMAL or all-TIMEOUT regime.

### Target
Production deployment at
`https://optim-engine-production.up.railway.app`, fronted by the edge proxy
service (`optim-engine-proxy`). All four layers active: L1 solver (OR-Tools
9.15 / FastAPI), L2 Core Gateway, L3 thin proxies, L4 discovery. OAuth not
exercised on these endpoints (covered by `X-Engine-Key` header).
Observability stack live: OpenTelemetry tracing, Prometheus middleware,
Grafana Cloud dashboard.

### Run Duration
Each run is 5 minutes (300 seconds), `--headless --csv` mode. Locust spawn
rate is 1 user/second except where noted. Runs are sequential against
production with no concurrent traffic from other sources during the
measurement window.

### Caveats
- Single-region client (Bologna, IT) hitting Railway US region. Round-trip
  latency floor includes ~50 ms of transcontinental network time, which is
  not representative of an in-region client. The infrastructure floor
  reported below is therefore an upper bound for a co-located workload.
- Locust users are synchronous: each user waits for the previous response
  before issuing the next request. This caps the achievable throughput at
  `users / mean_response_time`, which is exactly the regime that matters
  for the agentic clients OptimEngine targets (x402 settlement loops, MCP
  tool calls, ACP brief fulfillment) and a poor model for high-fanout
  browser traffic. Choose the model that fits your use case.
- The L1 solver runs with default `num_search_workers` and CP-SAT
  `max_time_in_seconds` configured per endpoint. No custom thread pinning,
  no warm pool. A cold-start penalty exists on the first request after a
  Railway redeploy and is not isolated in this report.
- These are end-to-end black-box measurements. Per-component breakdowns
  (rate limiter, auth, FastAPI dispatch, solver) are visible in the OTel
  traces (Grafana dashboard) but not aggregated into this report.

## Run Configurations

| Run | Users | Wait between tasks | Workload     | Purpose                              |
|-----|-------|--------------------|--------------|--------------------------------------|
| 1   | 5     | 2-5 s              | mixed (4/2/1)| Realistic-but-pessimistic baseline   |
| 2   | 5     | 0.1-0.5 s          | mixed (4/2/1)| Saturation at design concurrency     |
| 3   | 10    | 0.1-0.5 s          | mixed (4/2/1)| Concurrency scaling beyond knee      |
| 4   | 5     | 0.1-0.5 s          | packing only | Infrastructure floor isolation       |

The wait time in Run 1 simulates a slow human user. Runs 2-4 simulate
agentic clients (back-to-back issuance with sub-second think time), which is
the actual production traffic model.

## Results

### Aggregate Metrics

| Metric             | Run 1   | Run 2   | Run 3   | Run 4 (packing-only) |
|--------------------|---------|---------|---------|----------------------|
| Total requests     | 78      | 113     | 88      | 478                  |
| Failures           | 0       | 0       | 0       | 0                    |
| Failure rate       | 0.00 %  | 0.00 %  | 0.00 %  | 0.00 %               |
| Aggregate RPS      | 0.26    | 0.38    | 0.33    | 1.60                 |
| Median latency     | 13.0 s  | 10.0 s  | 30.0 s  | 0.21 s               |
| p95 latency        | 39.0 s  | 25.0 s  | 50.0 s  | 20.0 s               |
| p99 latency        | 43.0 s  | 25.0 s  | 55.0 s  | 22.0 s               |
| Max latency        | 43.1 s  | 29.9 s  | 55.4 s  | 24.3 s               |
| Min latency        | 192 ms  | 196 ms  | 193 ms  | 189 ms               |

Cumulative: **757 requests served, 0 failures, 20 minutes of load**.

### Per-Endpoint Latency (Run 2, saturation, mixed workload)

| Endpoint              | Reqs | p50    | p95    | p99    | Max    |
|-----------------------|------|--------|--------|--------|--------|
| `/optimize_packing`   | 16   | 7.2 s  | 25.0 s | 25.0 s | 25.1 s |
| `/optimize_routing`   | 28   | 20.0 s | 25.0 s | 30.0 s | 29.9 s |
| `/optimize_schedule`  | 69   | 10.0 s | 25.0 s | 25.0 s | 24.9 s |

Routing is the slowest solver class on this workload mix. Schedule is the
most frequent (consistent with the 4/2/1 weight) and the dominant
contributor to aggregate latency.

### Infrastructure Floor (Run 4, packing-only)

The bin-packing endpoint with smallest payloads exhibits a bimodal latency
distribution:

| Percentile | Latency  | Interpretation                                     |
|------------|----------|----------------------------------------------------|
| min        | 189 ms   | Lower bound: parse + auth + edge proxy + serialize |
| p50        | 220 ms   | Trivial-instance solve path                        |
| p75        | 1.1 s    | Easy-instance solve path                           |
| p90        | 11.0 s   | Hard-instance solve path                           |
| p95        | 20.0 s   | Near-timeout instances                             |
| max        | 24.3 s   | TIME_LIMIT instances                               |

The ~200 ms floor isolates the non-solver overhead of the full request path
(client -> edge proxy -> L1 FastAPI -> middleware stack -> response). The
bimodality between p75 and p90 is the signature of a CP-SAT workload: trivial
problem instances finish in milliseconds, while NP-hard worst-case instances
hit the configured `max_time_in_seconds` boundary. Both behaviors are
expected and correct.

## Analysis

### Bottleneck: L1 Solver CPU

Three pieces of evidence converge on L1 CPU saturation as the throughput
ceiling:

1. **Throughput rises when wait time drops, but only up to a point.**
   Run 1 -> Run 2: removing the 2-5 s think time increases aggregate RPS by
   46 % (0.26 -> 0.38). The infrastructure has spare capacity at this load.
2. **Throughput falls when concurrency doubles past the knee.**
   Run 2 -> Run 3: doubling users from 5 to 10 *decreases* aggregate RPS by
   13 % (0.38 -> 0.33). Median latency triples (10 s -> 30 s) because
   requests serialize behind the saturated solver. This is the canonical
   signature of CPU saturation, not network or I/O contention.
3. **Throughput rises 4.2x when the solver workload is light.**
   Run 4 vs Run 2: isolating to bin-packing (typically simpler
   instances) increases aggregate RPS from 0.38 to 1.60 with the same 5
   users. The infrastructure can sustain higher RPS; what limits
   mixed-workload throughput is solver compute time on FJSP and CVRPTW.

### Graceful Degradation

The most operationally significant finding is the failure pattern under
overload: there isn't one. At 200 % of the saturation point (Run 3, 10
users) the system continues to serve every request. Latency degrades, but
the request-handling path holds:

- No 5xx errors
- No connection drops
- No client-side timeouts triggered (within Locust's default 60 s)
- Edge proxy and L1 maintain the connection through the full solve

This is a property of the FastAPI + Uvicorn + Railway combination running
synchronous CPU work: requests queue at the worker level and are processed
in order. There is no thrash, no OOM, no cascade. For the agentic-client
target (x402, MCP, ACP), graceful degradation is preferable to fast
failure: clients are typically willing to wait longer for a correct answer
than to retry against a 503.

### What These Numbers Are Not

Two clarifications to avoid over-claiming:

- **0.38 RPS aggregate is not a system limit.** It is the steady-state
  throughput of *one Railway instance of the L1 solver* under the
  current `num_search_workers` and time-limit configuration. The L2 Core
  Gateway is not the bottleneck. The L3 payment gateways are not the
  bottleneck. Horizontal scale-out of L1 (multiple replicas behind the
  edge proxy, sticky on solver class) is the linear scaling path.
- **The latencies above include a transcontinental network round-trip.**
  An in-region client (e.g. an agent calling from a US-east colocation)
  would see the infrastructure floor closer to 80-100 ms instead of
  ~200 ms. The solver-bound portion of the latency is unaffected by
  client location.

## Scaling Implications

The bottleneck profile points to a specific scaling architecture rather than
a generic "add more boxes" answer:

1. **L1 solver layer** is the only component that benefits from horizontal
   scale-out. A second L1 replica with sticky routing on solver class would
   approximately double aggregate RPS for mixed workloads. Three replicas
   would approximately triple it, until the L2 Core Gateway becomes the next
   bottleneck (not yet measured, but likely well above 5 RPS aggregate).
2. **L2 Core Gateway, L3 proxies, edge proxy** are not bottlenecks at
   current and projected near-term load. They scale horizontally trivially
   if needed.
3. **Per-request optimizations** with a known ROI from prior profiling work:
   `deepcopy` removal in `optimize_stochastic` (separate solver, not
   exercised in these runs but profiled to be the dominant cost there),
   solver warm pool to amortize CP-SAT model construction. Both are
   incremental, not architectural.
4. **What is *not* a useful scaling lever** based on these results:
   rewriting the FastAPI layer in a faster framework, async/await
   reorganization, or moving to a different language for the wrapper. The
   wrapper is not the bottleneck. The CP-SAT C++ kernel already runs at
   native speed and dominates the per-request cost. This conclusion is
   consistent with prior `py-spy` profiling (94 % of `optimize_schedule`
   wall time is in the OR-Tools C++ kernel).

## Reproducibility

```bash
# Setup
git clone https://github.com/MicheleCampi/optim-engine.git
cd optim-engine
python3 -m venv venv && source venv/bin/activate
pip install locust

# Provide the production API key without exposing it in shell history
read -rs ENGINE_API_KEY_PROD && export ENGINE_API_KEY_PROD

mkdir -p load_tests/results

# Run 1: baseline (realistic-but-pessimistic)
locust -f load_tests/locustfile.py \
  --host=https://optim-engine-production.up.railway.app \
  --users=5 --spawn-rate=1 --run-time=300s --headless \
  --csv=load_tests/results/baseline --csv-full-history

# Run 2: saturation at design concurrency
LOCUST_WAIT_MIN=0.1 LOCUST_WAIT_MAX=0.5 \
  locust -f load_tests/locustfile.py \
  --host=https://optim-engine-production.up.railway.app \
  --users=5 --spawn-rate=1 --run-time=300s --headless \
  --csv=load_tests/results/saturation --csv-full-history

# Run 3: concurrency scaling beyond knee
LOCUST_WAIT_MIN=0.1 LOCUST_WAIT_MAX=0.5 \
  locust -f load_tests/locustfile.py \
  --host=https://optim-engine-production.up.railway.app \
  --users=10 --spawn-rate=2 --run-time=300s --headless \
  --csv=load_tests/results/scale10 --csv-full-history

# Run 4: infrastructure floor (packing-only)
WEIGHT_SCHEDULE=0 WEIGHT_ROUTING=0 WEIGHT_PACKING=1 \
  LOCUST_WAIT_MIN=0.1 LOCUST_WAIT_MAX=0.5 \
  locust -f load_tests/locustfile.py \
  --host=https://optim-engine-production.up.railway.app \
  --users=5 --spawn-rate=1 --run-time=300s --headless \
  --csv=load_tests/results/floor_packing --csv-full-history
```

Raw CSV outputs are kept in `load_tests/results/` for each run:
`*_stats.csv` (final aggregates), `*_stats_history.csv` (per-second time
series, used for plotting), `*_failures.csv`, `*_exceptions.csv`.

## Future Work

Items intentionally out of scope of this first benchmark pass, listed in
order of expected information yield:

- Multi-replica L1 measurement to validate horizontal scale-out math.
- Cold-start penalty quantification (first-request latency after redeploy).
- OAuth `/mcp/v2` endpoint benchmarking — same workload mix, different
  auth path, to characterize ScaleKit/PyJWT cost.
- Per-component breakdown via OTel trace aggregation rather than
  black-box timing.
- Comparison against an in-region client to isolate transcontinental
  network contribution to the infrastructure floor.
- `optimize_stochastic` and `optimize_sensitivity` not exercised here;
  they have different cost profiles (Monte Carlo and parametric sweep
  respectively) and warrant a dedicated run.
