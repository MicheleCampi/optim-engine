# Security Policy

This document describes the security model of OptimEngine: the threat model, the controls in place, and how to report vulnerabilities. It is intentionally specific rather than boilerplate — generic security policies are not credible, and OptimEngine has a non-trivial architecture that deserves a real explanation.

## Reporting a Vulnerability

If you find a security issue, please use one of these two channels:

1. **GitHub Security Advisories** (preferred): open a private advisory at
   https://github.com/MicheleCampi/optim-engine/security/advisories/new
2. **Email**: `michele.campi@outlook.com` with subject prefix `[OPTIMENGINE-SEC]`

**Do not open a public issue** for security matters.

**Response expectations:**
- Acknowledgement within 72 hours
- Initial triage within 7 days
- Fix or mitigation timeline communicated within 14 days

This is a single-maintainer project, so timelines reflect that. For coordinated disclosure, please allow at least 30 days between report and public discussion.

## Threat Model

OptimEngine is a publicly accessible production system that performs CPU-intensive optimization work, exposes paid endpoints via the x402 protocol, and integrates with third-party MCP clients (claude.ai and others). The threat model addresses the following actors and concerns:

| Actor                          | Primary concern                                                                              |
|--------------------------------|----------------------------------------------------------------------------------------------|
| Anonymous internet attacker    | DoS via solver-bound endpoints; abuse of free-tier endpoints to amortize compute on the project |
| Malicious authenticated client | Privilege escalation across MCP scopes; payload injection into solver inputs                 |
| Compromised MCP client         | Unauthorized tool invocation on behalf of the legitimate user                                |
| Browser-origin attacker (CSRF) | Cross-origin requests against `/optimize_*` endpoints from a malicious site                  |
| Insider (single maintainer)    | Accidental secret leak via shell history, screenshots, or commit content                     |

The threat model **does not include**:
- Nation-state adversaries with access to the Railway control plane
- Compromise of upstream dependencies (OR-Tools, FastAPI, ScaleKit) — handled via dependency hygiene, see below
- Physical access to the maintainer's workstation

## Architecture and Trust Boundaries

OptimEngine is built around four trust zones:

```
┌──────────────────────────────────────────────────────────────────┐
│  Public internet                                                 │
│  (browsers, agents, MCP clients, x402 wallets)                   │
└────────────────┬─────────────────────────────────────────────────┘
                 │
        ┌────────┴────────────────┐
        │                         │
        ▼                         ▼
┌───────────────────┐   ┌──────────────────────────────────────────┐
│  Edge proxy       │   │  L1/L2/L3 Compute (Railway)              │
│  (Vercel)         │   │  No CORS — server-to-server only         │
│  CORS whitelist   │   │  API key middleware on all routes        │
│  Browser clients  │   │  OAuth 2.1 (ScaleKit) on /mcp/v2         │
└────────┬──────────┘   │  Bearer token on /metrics                │
         │              │  Rate limiting on /mcp                   │
         └─────────────►│                                          │
                        └──────────────────────────────────────────┘
```

**Key design decision: no CORS on the compute layer.** The L1/L2/L3 services on Railway are configured server-to-server only and explicitly do not include `CORSMiddleware`. Browser-originated traffic goes through the edge proxy on Vercel, which holds a controlled CORS whitelist. This separation ensures that the compute layer can never be reached from a malicious browser origin even if a misconfiguration occurs at the edge.

This decision is documented inline in `api/server.py` near line 114.

## Controls

### Authentication and authorization

| Endpoint surface          | Auth mechanism                          | Notes                                                      |
|---------------------------|-----------------------------------------|------------------------------------------------------------|
| All `/optimize_*` routes  | `X-Engine-Key` header (API key)         | Validated by middleware in `api/server.py`                 |
| `/metrics`                | `Authorization: Bearer <METRICS_TOKEN>` | Separate token from the user-facing API key                |
| `/mcp` (SSE, free tier)   | None (open) + IP rate limit             | Capped at 10 req/hour per IP                                |
| `/mcp/v2` (Streamable HTTP) | OAuth 2.1 (ScaleKit)                  | JWT validated locally via PyJWT against ScaleKit's JWKS    |
| `/.well-known/oauth-*`    | None (intentionally public)             | Required for OAuth client discovery; bypasses API key MW   |
| x402 endpoints (L3)       | x402 protocol payment proof             | On-chain settlement on Base/Solana                         |

**Rationale for the OAuth path:** the project uses ScaleKit for OAuth 2.1 issuance and JWT signing, but validates tokens locally with PyJWT directly rather than the official `scalekit-sdk-python`. This is because the SDK has a `protobuf` version conflict with OR-Tools 9.15. The local validation path verifies signature, issuer, audience, and expiry against ScaleKit's published JWKS. Documented in `api/server.py`.

### Secret management

- All secrets are stored as Railway environment variables, never in the repository.
- The repository has no `.env` or `.env.example` checked in beyond placeholder names.
- Local development uses environment variables provided through a silent shell prompt pattern:
  ```
  read -rs SECRET_NAME && export SECRET_NAME
  ```
  This prevents secrets from appearing in shell history, screenshots, or terminal scrollback.
- `git log` and commits are reviewed before pushing to ensure no secret material is included.
- Secret rotation is manual at this stage (single maintainer); rotation cadence is "on suspected compromise" rather than calendar-based.

### Input validation

All solver endpoints validate inputs via Pydantic v2 models defined per solver (`{solver}/models.py`). This catches:
- Type mismatches and out-of-range numeric values
- Duplicate identifiers (item IDs, machine IDs, vehicle IDs) which can crash solvers
- Zero or negative weights/capacities which produce undefined CP-SAT behavior
- Missing required fields

Pydantic validation runs before any solver code touches the input. Solver internals also enforce mathematical preconditions (e.g. capacity ≥ sum of guaranteed assignments) before invoking CP-SAT.

### Rate limiting

The free-tier `/mcp` endpoint is rate-limited to 10 requests per hour per source IP. This is a deliberate design choice to keep the public free tier available for evaluation while preventing the endpoint from being weaponized as a free compute provider.

The `/mcp/v2` OAuth-protected endpoint relies on OAuth-level rate limits (per client) rather than IP-based limits.

Other endpoints (`/optimize_*` over REST) are protected by the API key requirement; rate limiting at this layer is implicit (no shared free key).

### Dependency hygiene

- `requirements.txt` pins minimum versions for all critical dependencies.
- The project uses Python 3.12 with up-to-date `cryptography`, `PyJWT`, `pydantic`, and OAuth-related libraries.
- GitHub Dependabot is configured to alert on known vulnerable dependencies.
- The CI workflow installs from `requirements.txt` on a clean Ubuntu runner and runs the full test suite (121 tests) on every push, which acts as a smoke test for dependency upgrades.

### Observability and incident detection

- All endpoints emit OpenTelemetry traces (`api/observability.py`).
- Prometheus metrics are exported on `/metrics` (token-gated).
- Telegram alerting is wired into payment events on both x402 gateways (Base and Solana). Anomalies in payment flow surface within seconds.
- Grafana Cloud public dashboard exposes high-level traffic patterns; private alerts cover error-rate and latency thresholds.

This monitoring is sufficient to detect abnormal load patterns or payment failures quickly, but it is **not** a SIEM. Sustained adversarial activity would require additional tooling.

### Data handling

OptimEngine processes optimization payloads (jobs, machines, routes, items) submitted by clients. The system:

- Does **not** persist optimization payloads after the response is returned. Each request is stateless from the application's perspective.
- Does **not** log full payload bodies in OpenTelemetry traces — only attributes (problem size, solver status, duration).
- Does **not** store any personally identifiable information beyond the API key and OAuth subject identifier required for authentication.

Customer-supplied data in payloads (e.g. job names, location names) flows through the solver and back to the client; it is not retained.

## Known Limitations

Honest enumeration of where the security posture has room to grow:

1. **No automated secret scanning in CI yet.** A `gitleaks` step in the GitHub Actions workflow is planned. Until then, commit review is manual.
2. **Single maintainer = single point of failure for response.** If the maintainer is unreachable, security reports may queue. There is no on-call rotation.
3. **No formal SLA for fix delivery.** Response times above are best-effort, not contractual.
4. **The free-tier `/mcp` endpoint is vulnerable to abuse from rotating IP pools** despite the per-IP rate limit. This is an accepted residual risk: the alternative is removing the free tier, which would harm the project's evaluation surface.
5. **Edge proxy CORS whitelist is maintained manually** in the `optim-engine-proxy` repository. There is no automated check that prevents an overly permissive entry.
6. **No penetration test has been performed.** The project is a portfolio system, not a regulated product.

## Out of Scope

The following are intentionally not handled by this policy:

- Vulnerabilities in third-party MCP clients (claude.ai, Smithery clients, etc.) — report to those projects.
- Vulnerabilities in dependencies — report upstream and to GitHub Dependabot.
- Bugs that do not have a security impact — open a regular GitHub issue.
- Optimization-result correctness — these are mathematical bugs, not security issues.

## Changelog

- **2026-05-09**: Initial security policy published. Reflects current state: CORS removed from compute layer (since 2026-04-19), OAuth 2.1 on `/mcp/v2`, OTel + Prometheus + Telegram alerts live, 121-test CI on every push.
