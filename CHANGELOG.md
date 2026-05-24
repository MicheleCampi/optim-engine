# Changelog

All notable changes to OptimEngine are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Entries before this changelog was introduced (2026-05-24) have been reconstructed from the commit history and from version markers embedded in commit messages — git tags were not created at the time, so versions are dated by their first commit and not by a tag object.

## [Unreleased]

Work since v9.0.0 (March 2026) has focused on production hardening rather than new solver features: payments, observability, load testing, OAuth, MCP transports, and CI. No bump to v10 has been cut because the public solver API is unchanged.

### Added

- **Real-time payment alerts on both x402 gateways.** Base gateway: `sendTelegramAlert` wired into `trackPayment()` in `src/stats.js`, covering all 13 solver handlers. Solana gateway: global Express middleware after `paymentMiddleware` intercepts all 18 paid routes, firing on `res.on('finish')` if status 2xx. Bot `@optimengine_alerts_bot`, chat ID `1432578139`. Env vars `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` on both Railway services. (2026-04 to 2026-05)
- **MCP dual-stack transports.** `/mcp` (SSE, open, rate-limited 10/hr per IP, free tier) and `/mcp/v2` (Streamable HTTP, OAuth 2.1 via ScaleKit). The v2 path validates JWTs locally with PyJWT against ScaleKit's JWKS rather than the `scalekit-sdk-python` SDK, sidestepping a `protobuf` version conflict with OR-Tools 9.15. Discovery via `/.well-known/oauth-protected-resource`. (2026-04-13 to 2026-04-18)
- **x402 monetization on Base and Solana.** Two gateway services in front of the solver layer, 18 paid endpoints each, all registered on x402scan via `@x402/extensions/bazaar declareDiscoveryExtension`. Same solver schemas as the REST API.
- **Smithery registration with 9 tools.** Static `server-card.json` at `/.well-known/mcp/server-card.json` to satisfy discovery without dynamic tool enumeration. (2026-04-18, commit `cf1bb02`)
- **ACP agent registration (#41779).** OptimEngine listed in the Virtuals agent registry.
- **the402.ai integration with 4 services.** Sensitivity, stochastic, routing, and predict-strategy exposed as paid services. Webhook auto-fulfillment via the Core Gateway. Status `failed` is reported on solver non-2xx (422/500) rather than claiming `completed`. (2026-04-14)
- **OpenTelemetry tracing.** `api/observability.py` (`init_telemetry` + `get_tracer`, ConsoleSpanExporter default, OTLP/HTTP via `OTEL_EXPORTER_OTLP_ENDPOINT`). Traced solvers: `solve_schedule` (attrs `n_jobs`, `n_machines`, `n_tasks`, `makespan`, `solver_status`, `solve_time_ms`) and `optimize_stochastic` (`num_scenarios`, `scenarios_feasible`, `recommended_objective`). FastAPIInstrumentor on every endpoint. Live in Railway production with `DEPLOYMENT_ENV=production`. Manual sub-spans added on `routing` for fine-grained CP-SAT observability. (2026-05-06 to 2026-05-17)
- **OTel Grafana Cloud Tempo wiring.** `OTEL_EXPORTER_OTLP_HEADERS` parsing, URL-decoded `Authorization` values, automatic `/v1/traces` suffix append to the OTLP endpoint. (2026-05-07)
- **Prometheus metrics endpoint.** `/metrics` exposed with Bearer-token auth (separate from the user-facing API key), Basic Auth also accepted for Grafana Cloud compatibility. Six solver families instrumented with primary objective tracking. (2026-05-02)
- **Grafana Cloud public dashboard.** Live at `public-dashboards/21137ba340fc4b6e917a4b108db3e109`. Pipeline: Hetzner VM runs Alloy 1.16 scraping `/metrics` every 60 s with Bearer token, then `remote_write` to Mimir (`prod-eu-west-2`, Basic auth, instance `3165722`, policy `alloy-optim-engine-write`). Heartbeat systemd timer every 2 min hits one of the four solver endpoints (schedule/routing/stochastic/validate, weight 50/25/15/10) via `X-Engine-Key` to keep the public dashboard warm. (2026-05-03, 2026-05-16)
- **Locust load testing scaffold.** Multi-solver user (schedule/routing/packing) with randomized parametric generators for routing (CVRPTW), bin packing, and scheduling. Phase C and Phase D dashboard screenshots captured from full load runs. (2026-05-02)
- **CI on every push.** GitHub Actions workflow runs the full pytest suite (121 tests, 77 % overall coverage, 88 % on business logic). Test failures break the build. (2026-05-09)
- **Documentation suite.** `README.md` rewritten as engineering portfolio with 5 working badges and a mermaid architecture diagram. `BENCHMARKS.md` with 757 requests / 0 failures across 4 Locust runs. `SECURITY.md` with explicit threat model, controls table, ASCII trust-boundary diagram, and known limitations. `RUNBOOK.md` with 5 production incident scenarios in Detection-Triage-Mitigation-Root Cause-Prevention structure. (2026-05-09)
- **Dependabot configuration.** Alerts on known vulnerable dependencies. (2026-05-09)
- **API key middleware on all `/optimize_*` endpoints.** `X-Engine-Key` header validation in `api/server.py`. (2026-03-25)
- **MCP rate limiting on the free `/mcp` tier.** 10 requests per hour per source IP, designed to keep the free tier available for evaluation without making the endpoint a free compute provider. (2026-04-13)
- **ERC-8004 on-chain identity registration.** Agent registration file added for protocol-level identity. (2026-03-01)

### Changed

- **CORS removed from the compute layer.** `CORSMiddleware allow_origins=*` was deleted from `api/server.py`; cross-origin traffic now must go through the edge proxy `optim-engine-proxy` (Vercel) which maintains a controlled whitelist. The L1/L2/L3 services on Railway are server-to-server only. CORS comments in code updated to reference the proxy explicitly. (2026-04-20, commit `9144af7`)
- **OAuth Smithery DCR compatibility.** A series of fixes to the OAuth discovery path: resource-scoped authorization server URL, base env URL as `authorization_servers` to match the ScaleKit issuer, proxied metadata endpoint with corrected issuer for Smithery's Dynamic Client Registration. (2026-04-18, commits `498f9d3`, `9974d4d`, `509da9d`)
- **`/metrics` and `/.well-known/*` bypass the `ENGINE_API_KEY` middleware.** Required for Prometheus scrapers and for OAuth client discovery respectively. (2026-05-02, 2026-04-18)
- **`stochastic` solver: removed a redundant defensive `deepcopy` in `_solve`.** No functional change, modest reduction in per-request allocation. (2026-05-10)

### Fixed

- **OTLP endpoint path append.** Grafana Cloud Tempo expects `/v1/traces`; OTel SDK does not auto-append. (2026-05-07)
- **Load test rename.** `time_limit_seconds` renamed to `max_solve_time_seconds` for consistency with solver API. (2026-05-02)
- **`the402.ai` failure reporting.** When a solver returns non-2xx HTTP (422 validation, 500 error), `fulfillJob()` now reports `status=failed` to the402's callback instead of claiming `status=completed`. Early-return after failure callback; success path preserved for valid briefs. (2026-04-14)

### Security

- **API key on every solver endpoint** (2026-03-25, see Added).
- **CORS hardening** (2026-04-20, see Changed).
- **OAuth 2.1 on `/mcp/v2`** (2026-04-18, see Added).

---

## [9.0.0] — 2026-03-15

### Added

- **Four scheduling solver upgrades.** `duration_per_machine` (job durations may vary by machine), `availability_windows` (machines unavailable in specified intervals), `quality_min` and `yield_rate` (quality-aware scheduling), `setup_times` (changeover times between consecutive jobs on the same machine). Backwards compatible with v8 schedules — new fields are optional. (commit `704789f`)
- **MetalPrecision demo.** End-to-end example using all four new features in a stress-test scenario.
- **Landing page** for the v9 release.

### Changed

- Upgrade script whitespace cleanup.
- README rewritten to document v9 features.

---

## [8.0.0] — 2026-02-28

### Added

- **L3 — Prescriptive Intelligence layer complete.** This is the layer that decides which optimization strategy to apply given a problem statement, rather than running a fixed solver. Brings the four-layer architecture to its first complete state.
- **ERC-8004 on-chain identity** preparation.
- **Test count consolidated at 121** with a legacy test cleanup and a Pareto edge-case fix. (commit `4fd2512`, 2026-03-01)

### Changed

- README rewritten with v8.0.0 pricing, L3 description, full-stack architecture overview.

---

## [7.0.0] — 2026-02-28

### Added

- **L2.5 — Multi-objective Pareto Frontier.** Returns the set of non-dominated solutions across competing objectives rather than a single weighted compromise.

---

## [6.0.0] — 2026-02-28

### Added

- **L2 — Stochastic Optimization complete.** Scenario-based optimization with feasibility tracking per scenario and a recommended-objective heuristic across the scenario set.

### Changed

- README updated for v6.0.0 reflecting both L1 and L2 complete.

---

## [5.0.0] — 2026-02-28

### Added

- **Robust Optimization.** Worst-case-aware solver that returns a solution feasible under a defined uncertainty set.

---

## [4.0.0] — 2026-02-28

### Added

- **Sensitivity Analysis.** Quantifies how the optimal objective changes with marginal perturbations to input parameters.

---

## [3.0.0] — 2026-02-24

### Added

- **Bin Packing solver.** Classic bin packing with capacity constraints, suitable for container loading, cutting stock, and similar combinatorial problems.

### Changed

- README updated with bin packing examples.

---

## [2.0.0] — 2026-02-23

### Added

- **CVRPTW routing solver.** Capacitated Vehicle Routing Problem with Time Windows. (commit `9b2fb45`)

### Fixed

- Dockerfile `CMD` port parsing.
- `startCommand` removed; Dockerfile `CMD` handles startup.
- Railway `PORT` variable used without a hardcoded default.
- `routing/` added to Dockerfile for Railway deploy.

### Changed

- README updated for v2.0.0 with routing examples and marketplace links.

---

## [1.0.0] — 2026-02-21

### Added

- **Initial release.** Operations Scheduling Solver MCP Server. CP-SAT-based scheduler with job/machine modelling, exposed via MCP. (commit `7475ead`)
- **Dockerfile** for Railway deployment.

### Removed

- Vendored `venv/` directory removed from the repository in the same day. (commit `6edf523`)

---

## Notes on the reconstruction

This file was introduced on 2026-05-24, after the project had already been versioned informally through commit-message markers (`v1.0.0` through `v9.0.0`) without corresponding git tags. The historical entries were reconstructed from the git log and from project memory; dates are the date of the first commit associated with each version, not a tag date. Going forward, releases will be cut by creating a git tag and bumping the version in this file in the same commit.
