⚡ OptimEngine v9.0.0
Operations Intelligence for AI Agents — L1 → L3 in one conversation.
An AI-native MCP Server that assigns tasks to machines, deliveries to vehicles, and items to bins — then tells you what happens when things change. Built for the agentic economy.
Mostra immagine
Mostra immagine
Mostra immagine
Mostra immagine
Mostra immagine

What Is OptimEngine?
OptimEngine solves NP-hard optimization problems that LLMs cannot compute — and quantifies the risk when parameters are uncertain.
11 tools across 4 intelligence levels:
LevelToolsWhat It DoesL1 Deterministicoptimize_schedule, validate_schedule, optimize_routing, optimize_packingOptimal assignments under known constraintsL2 Uncertaintyanalyze_sensitivity, optimize_robust, optimize_stochasticWhat-if analysis, worst-case protection, Monte Carlo riskL2.5 Multi-objectiveoptimize_paretoTrade-off frontiers for competing objectivesL3 Prescriptiveprescriptive_adviseForecast → optimize → risk assess → recommend
Plus health_check and root for server diagnostics.

v9.0.0 — What's New
Four scheduling brain upgrades that close the gap between academic FJSP and how real workshops operate:
1. Duration per machine
Same task, different times on different machines. The solver picks the fastest eligible machine.
json{ "task_id": "milling", "duration": 100, "eligible_machines": ["CNC-1", "CNC-2"],
  "duration_per_machine": {"CNC-1": 120, "CNC-2": 80} }
2. Availability windows
Multiple shifts and maintenance windows per machine. Replaces the single availability_start/end.
json{ "machine_id": "CNC-1", "availability_windows": [
    {"start": 0, "end": 480}, {"start": 510, "end": 960}
  ] }
3. Quality min / yield rate
Jobs can require minimum quality. Machines have yield rates. The solver excludes machines below threshold.
json{ "job_id": "ORD-BOSCH", "quality_min": 0.97 }
{ "machine_id": "CNC-4", "yield_rate": 0.99 }
4. Setup times matrix
Sequence-dependent changeover times. Switching between product families costs time — the solver accounts for it.
json{ "setup_times": [
    {"machine_id": "M1", "from_job_id": "J1", "to_job_id": "J2", "setup_time": 15}
  ] }
All upgrades are backward compatible — v8-style requests work identically. 121 tests passing, zero regressions.

L1 — Deterministic Optimization
SolverProblemKey FeaturesSchedulingFlexible Job Shop (FJSP)Precedence, time windows, per-machine durations, availability windows, quality gates, setup matrix, priorities, 4 objectivesRoutingCVRPTWCapacity, time windows, GPS, custom distances, drop visits, 4 objectivesBin PackingMulti-dim packingWeight + volume, quantities, groups, partial packing, 4 objectives
L2 — Optimization under Uncertainty
ModuleCapabilityOutputSensitivity AnalysisPerturb parameters one at a timeFragility map, sensitivity scores, critical flags, risk rankingRobust OptimizationUncertainty ranges → worst-case protectionRobust solution, price of robustness, feasibility rateStochastic OptimizationProbability distributions → Monte CarloExpected value, VaR, CVaR (90/95/99%), distribution summary
L2.5 — Multi-objective Optimization
ModuleCapabilityOutputPareto Frontier2-4 competing objectivesNon-dominated solutions, trade-off ratios, correlation analysis
L3 — Prescriptive Intelligence
ModuleCapabilityOutputPrescriptive AdviseHistorical data → Forecast → Optimize → Risk → RecommendActions, risk-adjusted makespan, feasibility risk assessment

Live Demo: MetalPrecision S.r.l.
Precision machining workshop — 4 CNC centers (2015-2023), 5 client orders (Bosch, Ducati, Maserati, Comer Industries, Dallara), 15 tasks.
ToolResultoptimize_scheduleOptimal makespan 225 min, 5/5 on-time, 83.3% avg utilization, 0.04svalidate_scheduleZero violations, 2 improvement suggestionsanalyze_sensitivity73 solves in 3.6s, Ducati sgrossatura most sensitive (8.9)optimize_robustWorst-case 210 min, price of robustness 7.7%, 100% feasibleoptimize_paretoMakespan vs tardiness: 195/15min or 220/0min, correlation -1.0optimize_stochastic30 Monte Carlo, CVaR95 = 188.5, CV 4.7%prescriptive_adviseForecast sgrossatura 95 min (+1.3%/period), risk-adjusted range 167-183

Quick Start
claude.ai (Remote MCP)
Add OptimEngine as a Remote MCP connector in Claude Settings → Integrations:
https://optim-engine-production.up.railway.app/mcp
API (curl)
bashcurl -X POST https://optim-engine-production.up.railway.app/optimize_schedule \
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
MCP Client Config
json{
  "mcpServers": {
    "optim-engine": {
      "url": "https://optim-engine-production.up.railway.app/mcp"
    }
  }
}

Available On
PlatformLinkRailway (live)optim-engine-production.up.railway.appGitHubgithub.com/MicheleCampi/optim-engineMCPizemcpize.comApifyapify.comLobeHublobehub.commcp.somcp.soVercel (landing)optim-engine.vercel.appclaude.aiRemote MCP connector

Architecture
┌─────────────────────────────────────────────────────┐
│                   FastMCP Server                     │
│              (SSE + Streamable HTTP)                 │
├─────────────────────────────────────────────────────┤
│  L1 Solvers          │  L2 Uncertainty              │
│  ┌─────────────────┐ │  ┌────────────────────────┐  │
│  │ Scheduling (v9) │ │  │ Sensitivity Analysis   │  │
│  │ Routing         │ │  │ Robust Optimization    │  │
│  │ Bin Packing     │ │  │ Stochastic (MC+CVaR)   │  │
│  │ Validator       │ │  │ Pareto Multi-objective  │  │
│  └─────────────────┘ │  │ Prescriptive (L3)      │  │
│                       │  └────────────────────────┘  │
├─────────────────────────────────────────────────────┤
│  OR-Tools CP-SAT  │  Pydantic Schemas  │  Python 3.12│
└─────────────────────────────────────────────────────┘

License
MIT — see LICENSE.
Built by Michele Campi.
