# OptimEngine — Operational Runbook

This runbook describes how to diagnose and respond to five production incident classes. Each scenario follows a fixed structure — Detection, Triage, Mitigation, Root Cause, Prevention — so that the operator (currently a single maintainer) can act quickly under stress without re-deriving the procedure each time.

The runbook is intentionally specific to OptimEngine's architecture (4-layer + edge proxy on Railway/Vercel, OR-Tools 9.15 CP-SAT solvers, MCP dual-stack, OAuth 2.1 via ScaleKit, OTel + Prometheus + Grafana Cloud + Telegram alerting). Generic SRE boilerplate has been omitted.

## Conventions

- **Detection** lists the signals that should trigger you to open this scenario. If none of these signals are present, you're probably looking at a different scenario.
- **Triage** is the first 5 minutes: a fixed sequence of checks to confirm the scenario class and exclude alternatives.
- **Mitigation** is the action to stop user impact. It is not always the same as fixing root cause.
- **Root cause** is the post-mitigation investigation. Optional during the incident, mandatory during postmortem.
- **Prevention** is the durable fix that should reduce the probability or impact of the same incident recurring.

Throughout, "ops bot" refers to the Telegram bot `@optimengine_alerts_bot`, which receives alerts from both gateways and metric thresholds.

---

## Scenario 1 — Solver L1 Saturated (CPU Bottleneck Under Load)

The L1 solver layer is the system's known bottleneck (see `BENCHMARKS.md`). Under sustained load above ~5 concurrent users, request latency rises and throughput plateaus. This scenario distinguishes a *legitimate* saturation event from a *pathological* one (a single problematic request hanging the worker).

### Detection

- Grafana panel "p95 latency" exceeds 30 s for more than 5 consecutive minutes
- Status mix shifts toward TIMEOUT (more than 30 % of solves return `MODEL_INVALID` or `TIME_LIMIT`)
- Ops bot fires "high latency" alert on `/optimize_*` endpoints
- User-side: REST clients receive timeouts; MCP clients see `tools/call` exceed their default timeout

### Triage (5 minutes)

1. Open the Grafana public dashboard. Confirm whether p95 has been climbing gradually (saturation) or jumped suddenly (single-request hang).
2. Check Railway L1 service metrics: CPU > 90 % sustained → saturation; CPU normal but latency high → single-request hang or downstream issue.
3. Open OTel traces in Grafana for the last 15 minutes. Group by `solver_status`. If the top trace by duration is a single span > 60 s, you have a hang on a specific input.
4. Check inbound traffic source: Railway logs `tail` to identify whether load is coming from one IP (abuse) or distributed (legitimate spike).

### Mitigation

**If saturation (legitimate sustained load):**
- Temporarily increase Railway's L1 service replica count (UI → Service → Settings → Replicas). Cost is linear, scaling is approximately linear up to the next bottleneck (L2 Core Gateway, not yet measured).
- If the load is from x402 paid traffic, no further action is needed: clients are paying for compute and graceful degradation is the documented behavior.
- If the load is anonymous on `/mcp` (free tier), the per-IP rate limit (10 req/hour) should already be active. Verify it is: check Railway env var `MCP_RATE_LIMIT_PER_IP`.

**If single-request hang:**
- Identify the offending input from OTel trace attributes (`n_jobs`, `n_machines`, `n_tasks`).
- The CP-SAT solver has `max_time_in_seconds` configured per endpoint. If a request exceeds this, it returns `UNKNOWN` and the worker is freed. If it's not freeing, restart the L1 service: Railway → L1 → Restart. Latency will spike during restart (cold start ~30 s) but recovers.

### Root Cause

- For saturation: cross-check against `BENCHMARKS.md` knee point (5 users). Are we operating beyond known capacity? If yes, this is expected behavior, not a bug.
- For single-request hang: capture the input payload (from OTel attributes) and reproduce locally with `python -m solver.engine`. File an issue tagged `solver-hang` with the reproducer.

### Prevention

- Future work item: add an admission controller that rejects requests exceeding documented size limits (e.g. `n_jobs > 200`) before they reach the solver. Currently the solver tries any input.
- Future work item: implement horizontal autoscaling on L1 based on CPU. Currently scaling is manual.

---

## Scenario 2 — `/mcp/v2` OAuth Broken (JWKS Unreachable or Token Validation Failing)

The OAuth-protected MCP endpoint validates incoming JWTs locally using PyJWT against ScaleKit's public JWKS. If JWKS retrieval fails or token validation throws, every authenticated MCP client breaks. This is high-severity because there is no graceful degradation path — without auth, requests are rejected.

### Detection

- Spike in 401 responses on `/mcp/v2` in Grafana
- Ops bot fires "auth failure rate > 10 %" alert
- User reports from MCP clients: "tool calls return Unauthorized"
- The free `/mcp` endpoint continues working — this isolates the failure to the OAuth path specifically

### Triage (5 minutes)

1. Verify the ScaleKit JWKS endpoint is reachable from a server that's not your laptop:
   ```
   curl -sS https://optimengine.eu.scalekit.dev/.well-known/jwks.json | head -c 200
   ```
   If this returns 200 with a JSON keyset → JWKS is up; problem is in our validation code.
   If timeout or 5xx → ScaleKit is having issues.
2. Check Railway env vars on L1: `SCALEKIT_ENVIRONMENT_URL` and `SCALEKIT_RESOURCE_ID` are present. A redeploy may have wiped them.
3. Open OTel traces filtered by `http.status_code=401`. The exception attribute will tell you whether the failure is in JWKS fetch (network), JWT decode (key mismatch), or claim validation (issuer/audience).
4. Check the time of the most recent successful auth: if it was within the last minute, this is a fresh outage; if hours ago, the system has been silently broken (worse).

### Mitigation

**If ScaleKit is down (their problem, not ours):**
- There is no fast fix. Document the start time. Communicate publicly via the project README banner if outage exceeds 30 minutes.
- The free `/mcp` endpoint remains available as a fallback for clients that can switch.

**If our validation code is broken:**
- The most likely cause is a dependency upgrade. Check the most recent commit touching `requirements.txt`. If `PyJWT` or `cryptography` was bumped, roll back: Railway → L1 → Deployments → previous deployment → "Redeploy".
- If the issue is a JWKS cache that has stale keys after ScaleKit rotated them, restart the L1 service. The current implementation does not cache JWKS aggressively, so restart is sufficient.

### Root Cause

- Capture the exact exception from the OTel error trace.
- Common patterns:
  - `JWKClientError`: network or DNS — check Railway egress
  - `InvalidSignatureError`: ScaleKit rotated keys; we have stale cache
  - `InvalidIssuerError`: a recent change to `SCALEKIT_ENVIRONMENT_URL` doesn't match the token's `iss` claim
  - `InvalidAudienceError`: the OAuth client was reconfigured with a different audience

### Prevention

- Add a synthetic auth probe: a CI job that attempts a `/mcp/v2` call with a known test token every hour and alerts on failure. Currently we only detect failures after real users encounter them.
- Pin `PyJWT` and `cryptography` to specific versions in `requirements.txt` rather than minimum versions, to eliminate "passive" upgrades through Railway rebuilds.
- Document in `SECURITY.md` (already done) the rationale for using PyJWT directly instead of `scalekit-sdk-python` (protobuf conflict with OR-Tools).

---

## Scenario 3 — Deploy Regression (Push to `main` Breaks Production)

OptimEngine deploys via `git push origin main` to Railway. There is no staging environment. This means a regression introduced in a commit reaches production within minutes. This scenario covers the operator response when the dashboard goes red after a push.

### Detection

- Within 5 minutes of a push, error rate on any L1 endpoint exceeds 1 % (was zero before)
- Health check endpoint returns non-200
- New exceptions appear in OTel traces that were not present in the previous 24 hours
- Ops bot fires "deployment likely regression" composite alert (latency + error rate + health check)

### Triage (5 minutes)

1. Identify the deploying commit:
   ```
   git log --oneline -5
   ```
   Confirm the most recent commit's timestamp aligns with the start of the symptoms.
2. Open the Railway deployment for that service. Find the previous successful deployment. Note its commit SHA — this is your rollback target.
3. Read the GitHub Actions run for the latest commit. If `tests` workflow failed, the regression should have been caught — investigate why it wasn't (bypass? force push?). If tests passed but production broke, the gap between test coverage and production behavior is the bug to investigate later.
4. Check whether the regression is total (every request fails) or partial (only specific endpoints / payloads). Partial = revert is not always required; you may be able to ship a forward-fix faster.

### Mitigation

**Rollback path (preferred when regression is total):**
1. Railway dashboard → Service → Deployments → previous successful deployment → "Redeploy".
2. Wait for redeploy to complete (~60 s).
3. Verify dashboard returns to baseline. Ops bot should fire "recovery" within 2 minutes.
4. The bad commit is still on `main`. Either:
   - `git revert <bad-sha> && git push` (preserves history; preferred for collaborator-visible repos)
   - Force-push the previous SHA (faster but rewrites history; acceptable for single-maintainer)
5. Confirm Railway picks up the revert and stays on the good code.

**Forward-fix path (preferred when regression is small and well-understood):**
1. Write the fix on a branch.
2. Push, watch CI green, merge.
3. Wait for Railway to deploy the merge.
4. This path is faster *only if* the fix is genuinely 5 minutes; otherwise rollback is always faster.

### Root Cause

- Read the diff of the bad commit. Identify the exact change responsible.
- Was there a test that should have caught this? If yes, why didn't it run / why did it pass? If no, this is a coverage gap → write the test as part of the fix.
- Was there a manual smoke test that should have caught this? If yes, why was it skipped?

### Prevention

- The CI workflow already gates pushes via test pass requirement (since the `continue-on-error` removal). Future work: add a deployment-time smoke test that pings `/health` on the new Railway deployment and rolls back automatically if it fails.
- Consider adding a staging Railway environment for high-risk changes (solver internals, auth path). The cost is non-trivial for a side project; revisit when production traffic justifies it.

---

## Scenario 4 — Cascading Failure (L2 Timeouts → L1 Retries → Death Spiral)

The L2 Core Gateway calls L1 solver endpoints and orchestrates payment + observability. If L1 latency rises past L2's request timeout, L2 returns errors. If clients retry, the retry traffic compounds the L1 load, latency rises further, and the system enters a death spiral that does not recover without intervention. This is the canonical distributed-systems failure mode.

### Detection

- Both L1 and L2 services show high error rates simultaneously
- Latency on L2 starts to climb in lockstep with L1 (rather than L2 staying flat)
- Ops bot fires "cascading degradation" composite alert (correlated metrics across services)
- Client-side: aggressive retry storms visible in Railway HTTP logs (same trace ID appearing 5+ times in one minute)

### Triage (5 minutes)

1. Confirm the direction of cause: open Grafana, plot L1 p95 and L2 p95 on the same chart. If L1 is leading L2 by 30-60 seconds, the failure originates at L1 (then L2 piles on through retries). If they rise together, look for a shared dependency (Railway region issue, network).
2. Check whether retry traffic is observable: in OTel traces, count distinct `trace.id` values vs total requests in the last 5 minutes. A ratio <1 means duplicate retries are happening.
3. Identify retry sources: are clients retrying, or is L2 itself doing internal retries? Check L2 code for retry logic. If both, the multiplier is dangerous (3 client retries × 3 L2 retries = 9× original load).

### Mitigation

The standard playbook for cascading failure is to break the loop at the *clients*, not the servers. Servers under load cannot serve their way out of this; you have to reduce input.

1. **Most effective immediate action: enable rate limit at the edge.** Increase the per-IP rate limit on the edge proxy (Vercel) temporarily, e.g. from "no limit" to "10 req/min per IP". This shed load from the most aggressive retriers first.
2. **Second action: temporarily raise L2 timeout.** If L2 is timing out at 30 s but L1 sometimes legitimately needs 45 s under load, L2 is creating false failures. Bump L2 timeout to 90 s for the duration of the incident.
3. **Third action: disable internal L2 retries.** If L2 has built-in retry logic, kill it for the duration. Retry should be a client decision, not a server decision, in this regime.
4. Once the spiral is broken (typically 2-5 minutes after step 1), the system self-recovers as L1 catches up.

### Root Cause

- Was the original L1 latency spike legitimate (real load) or pathological (single bad request)? If legitimate, the fault is in the client retry behavior or the L2 timeout settings. If pathological, you also need scenario 1's investigation.
- Document the timeout budgets at every hop (client → edge → L2 → L1). They should form a strictly decreasing sequence (client timeout > edge > L2 > L1). If not, a hop in the middle creates the false-failure trap.

### Prevention

- Implement circuit breaker on L2 → L1 calls. After N consecutive L1 timeouts, L2 should return 503 immediately for the next M seconds rather than queuing more requests. This bounds the damage.
- Document timeout budgets in `ARCHITECTURE.md` (future work) so they don't drift.
- Consider a retry budget at the edge proxy: cap total retries per minute per IP, regardless of original requests.
- Future work: add a load-shedding endpoint that returns 503 with `Retry-After` when L1 CPU > 95 %, before the spiral starts.

---

## Scenario 5 — Observability Gap (Something is Wrong but Traces are Missing)

The opposite of an alert: silence when there should be signal. If OTel exporters fail, Prometheus scraping breaks, or Grafana ingestion stalls, the system can be misbehaving without anyone noticing. This scenario covers what to do when you suspect "monitoring of the monitoring" has failed.

### Detection

- Grafana dashboards show flat lines or "no data" for normally active panels
- Trace count in the last 15 minutes is dramatically lower than the 24-hour average
- User reports of issues that don't correspond to any alert
- Ops bot is suspiciously quiet (no alerts in hours, on a system that normally fires several per day)

### Triage (5 minutes)

1. Verify the system is actually running. Curl `/health` on each service. If they return 200, the system is up; the gap is in observability.
2. Check OTel exporter destination: the OTLP endpoint configured in `OTEL_EXPORTER_OTLP_ENDPOINT`. Is it Grafana Tempo, Honeycomb, or another collector? Try a direct curl to that URL with a test span via `opentelemetry-cli` or a minimal Python script.
3. Check Prometheus scrape: visit `/metrics` directly on a service (with the bearer token). If it returns metrics, the scrape target is fine; the gap is in Prometheus pull.
4. Check Telegram bot: send a manual test message. If it doesn't arrive, the bot is broken (different incident).

### Mitigation

This scenario is rarely critical to user-visible behavior. The mitigation is to restore visibility, not to fix any user-facing bug.

1. **If OTel exporter is failing:** the most common cause is a wrong endpoint or expired token in environment. Check Railway env `OTEL_EXPORTER_OTLP_HEADERS` for the auth header. Re-paste the token if needed using the silent-prompt pattern (see `SECURITY.md`).
2. **If Grafana ingestion is stalled:** Grafana Cloud free tier has ingestion limits. Check the Grafana Cloud dashboard for usage. If you've hit the cap, traces are being dropped silently. Solutions: reduce sampling rate in `api/observability.py`, or upgrade tier.
3. **If everything looks correct but data still doesn't flow:** restart the L1 service. The OTel SDK initializes at startup and can get into bad states that only restart fixes.

While observability is degraded, fall back to direct Railway logs (`railway logs --service L1`) for any user-reported issues. This is slower but always works.

### Root Cause

- Was the gap caused by an upstream change (Grafana Cloud quota change, ScaleKit rotation, Railway runtime upgrade)?
- Was the gap caused by our own change (recent commit modifying `api/observability.py`, env var update)?
- How long was visibility actually broken? Cross-reference the gap window with any user complaints in that window — there may be issues that went undetected.

### Prevention

- Add a synthetic trace probe: a CI job (or a Railway scheduled task) that emits a test trace every 15 minutes and verifies it appears in Grafana within 5 minutes. Alert on failure.
- Document the observability budget: how much sampling, how much retention, how much it costs. Currently this is implicit; making it explicit prevents silent drift.
- Consider redundant alerting: if the primary alert path fails (Telegram down or OTel down), have a secondary path (email, ntfy.sh, pagerduty free tier).

---

## Postmortem Template

After any incident triggered by this runbook, write a brief postmortem in `incidents/YYYY-MM-DD-short-name.md`. The template:

```
# Incident: <one-line summary>

**Date:** YYYY-MM-DD
**Duration:** HH:MM to HH:MM (NN minutes)
**Scenario class:** <which runbook scenario applied; "novel" if none>
**Severity:** <user-visible / observability-only / no impact>

## Summary
One paragraph: what happened, how it was detected, how it was mitigated.

## Timeline
- HH:MM — first signal
- HH:MM — triage started
- HH:MM — mitigation applied
- HH:MM — recovery confirmed

## Root cause
What actually broke and why.

## Action items
- [ ] Specific change or improvement, with owner and target date
- [ ] ...
```

The act of writing the postmortem is itself the most valuable prevention mechanism. The template is short specifically to reduce friction; long postmortems don't get written.

---

## Changelog

- **2026-05-09**: Initial runbook published. Five scenarios covering compute saturation, auth failure, deploy regression, cascading failure, and observability gap. Reflects the system as of May 2026: 4 layers + edge proxy on Railway/Vercel, OR-Tools 9.15, MCP dual-stack, OAuth via ScaleKit, OTel + Prometheus + Grafana Cloud + Telegram.
