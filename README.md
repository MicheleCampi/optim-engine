# ⚡ OptimEngine — Operations Intelligence Solver

**The first MCP Server for operations optimization under uncertainty.**

An AI-native solver that assigns tasks to machines, deliveries to vehicles, and items to bins — then tells you what happens when things change. Built for the agentic economy.

[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![OR-Tools](https://img.shields.io/badge/Solver-OR--Tools-green)](https://developers.google.com/optimization)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-yellow)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-145%20passed-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## What It Does

OptimEngine solves NP-hard optimization problems that LLMs cannot compute — and quantifies the risk when parameters are uncertain.

### Level 1 — Deterministic Optimization

| Solver | Problem | Key Features |
|--------|---------|-------------|
| **Scheduling** | Flexible Job Shop (FJSP) | Precedence, time windows, setup times, priorities, 4 objectives |
| **Routing** | CVRPTW | Capacity, time windows, GPS, custom distances, drop visits, 4 objectives |
| **Bin Packing** | Multi-dim packing | Weight + volume, quantities, groups, partial packing, 4 objectives |

### Level 2 — Optimization under Uncertainty

| Module | Capability | Output |
|--------|-----------|--------|
| **Sensitivity Analysis** | Perturb parameters one at a time | Fragility map, sensitivity scores, critical flags, risk ranking |
| **Robust Optimization** | Uncertainty ranges → worst-case protection | Robust solution, price of robustness, feasibility rate |
| **Stochastic Optimization** | Probability distributions → Monte Carlo | Expected value, VaR, CVaR (90/95/99%), distribution summary |

**The core insight**: LLMs understand optimization requests but *cannot compute* optimal solutions or quantify risk. OptimEngine does both.

---

## MCP Tools

| Tool | Level | Endpoint | Description |
|------|-------|----------|-------------|
| `optimize_schedule` | L1 | `/optimize_schedule` | Flexible Job Shop Scheduling |
| `validate_schedule` | L1 | `/validate_schedule` | Schedule verification |
| `optimize_routing` | L1 | `/optimize_routing` | Vehicle Routing + Time Windows |
| `optimize_packing` | L1 | `/optimize_packing` | Bin Packing |
| `analyze_sensitivity` | L2 | `/analyze_sensitivity` | Parametric sensitivity analysis |
| `optimize_robust` | L2 | `/optimize_robust` | Worst-case robust optimization |
| `optimize_stochastic` | L2 | `/optimize_stochastic` | Monte Carlo + CVaR optimization |

---

## Quick Start

### Install & Run
```bash
git clone https://github.com/MicheleCampi/optim-engine.git
cd optim-engine
pip install -r requirements.txt
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### Connect via MCP
```json
{
  "mcpServers": {
    "optim-engine": {
      "command": "mcp-proxy",
      "args": ["https://optim-engine-production.up.railway.app/mcp"]
    }
  }
}
```

---

## Example — Scheduling
```bash
curl -X POST https://optim-engine-production.up.railway.app/optimize_schedule \
  -H "Content-Type: application/json" \
  -d '{
    "jobs": [
      {"job_id": "J1", "tasks": [
        {"task_id": "cut", "duration": 3, "eligible_machines": ["M1", "M2"]},
        {"task_id": "weld", "duration": 2, "eligible_machines": ["M2"]}
      ], "due_date": 10}
    ],
    "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
    "objective": "minimize_makespan"
  }'
```

## Example — Sensitivity Analysis
```bash
curl -X POST https://optim-engine-production.up.railway.app/analyze_sensitivity \
  -H "Content-Type: application/json" \
  -d '{
    "solver_type": "scheduling",
    "solver_request": {
      "jobs": [
        {"job_id": "J1", "tasks": [
          {"task_id": "cut", "duration": 30, "eligible_machines": ["M1", "M2"]},
          {"task_id": "weld", "duration": 20, "eligible_machines": ["M2"]}
        ], "due_date": 80}
      ],
      "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
      "objective": "minimize_makespan"
    },
    "parameters": [
      {"parameter_path": "jobs[J1].tasks[cut].duration", "perturbations": [-50, -20, 20, 50, 100]}
    ]
  }'
```

## Example — Stochastic Optimization
```bash
curl -X POST https://optim-engine-production.up.railway.app/optimize_stochastic \
  -H "Content-Type: application/json" \
  -d '{
    "solver_type": "scheduling",
    "solver_request": {
      "jobs": [
        {"job_id": "J1", "tasks": [
          {"task_id": "cut", "duration": 30, "eligible_machines": ["M1", "M2"]},
          {"task_id": "weld", "duration": 20, "eligible_machines": ["M2"]}
        ], "due_date": 80}
      ],
      "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
      "objective": "minimize_makespan"
    },
    "stochastic_parameters": [
      {"parameter_path": "jobs[J1].tasks[cut].duration", "distribution": "normal", "mean": 30, "std_dev": 8}
    ],
    "optimize_for": "cvar_95",
    "num_scenarios": 50
  }'
```

---

## Use Cases

- **Manufacturing**: Production scheduling with demand uncertainty and machine breakdowns
- **Logistics**: Delivery routing with variable demand and travel times
- **Warehouse**: Bin packing with uncertain item weights and volumes
- **Supply Chain**: End-to-end optimization with risk quantification
- **Finance**: Portfolio-like resource allocation under uncertainty

---

## Architecture
```
AI Agent (Claude, GPT, Gemini, etc.)
    │
    ▼ MCP Protocol
┌─────────────────────────────────────────────────┐
│  FastAPI + fastapi-mcp                           │
├──────────┬──────────┬──────────┬────────────────┤
│  L1      │  L1      │  L1      │  L2            │
│ Schedule │ Routing  │ Packing  │ Sensitivity    │
│ CP-SAT   │ Routing  │ CP-SAT   │ Robust         │
│          │ Library  │          │ Stochastic     │
├──────────┴──────────┴──────────┴────────────────┤
│  OR-Tools Solvers + Monte Carlo Engine           │
├─────────────────────────────────────────────────┤
│  Pydantic v2 Models                              │
└─────────────────────────────────────────────────┘
```

**Stack**: Python 3.12 · FastAPI · OR-Tools · fastapi-mcp · Pydantic v2

---

## Tests
```bash
python -m pytest tests/ -v
```

145 tests across 7 modules: scheduling, routing, packing, sensitivity, robust, stochastic, and validation.

---

## Landing Page

🌐 **[optim-engine.vercel.app](https://v0-optim-engine-landing-page.vercel.app/)**

## Marketplace Listings

- [MCPize](https://mcpize.com/mcp/optim-engine) — 9 MCP tools
- [Apify Store](https://apify.com/hearty_indentation/optim-engine) — 130k+ users/month
- [LobeHub](https://lobehub.com/mcp/michelecampi-optim-engine) — Top MCP directory
- [mcp.so](https://mcp.so/server/optim-engine) — 17k+ MCP servers

---

## License

MIT

---

*Built with Google OR-Tools. The first MCP server combining deterministic optimization with uncertainty analysis.*
