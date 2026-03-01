# ⚡ OptimEngine — Operations Intelligence Solver

**The first MCP Server for operations optimization across 4 intelligence levels.**

Solves scheduling, routing, and packing — then quantifies risk, finds trade-offs, and prescribes actions. Built for AI agents in the agentic economy.

[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![OR-Tools](https://img.shields.io/badge/Solver-OR--Tools-green)](https://developers.google.com/optimization)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-yellow)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-174%20passed-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## Intelligence Levels

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

### Level 2.5 — Multi-objective Optimization

| Module | Capability | Output |
|--------|-----------|--------|
| **Pareto Frontier** | 2-4 competing objectives | Non-dominated solutions, trade-off analysis, correlation, spread |

### Level 3 — Prescriptive Intelligence

| Module | Capability | Output |
|--------|-----------|--------|
| **Prescriptive Advisor** | Historical data → Forecast → Optimize → Advise | Forecasts, prediction intervals, risk assessment, prioritized actions |

---

## MCP Tools

| Tool | Level | Endpoint |
|------|-------|----------|
| `optimize_schedule` | L1 | `/optimize_schedule` |
| `validate_schedule` | L1 | `/validate_schedule` |
| `optimize_routing` | L1 | `/optimize_routing` |
| `optimize_packing` | L1 | `/optimize_packing` |
| `analyze_sensitivity` | L2 | `/analyze_sensitivity` |
| `optimize_robust` | L2 | `/optimize_robust` |
| `optimize_stochastic` | L2 | `/optimize_stochastic` |
| `optimize_pareto` | L2.5 | `/optimize_pareto` |
| `prescriptive_advise` | L3 | `/prescriptive_advise` |

---

## Pricing

OptimEngine is **free during beta**. All 9 tools, all 4 intelligence levels.

| Plan | Price | Calls/day | Levels | Support |
|------|-------|-----------|--------|---------|
| **Free (Beta)** | €0 | 100 | L1 + L2 + L2.5 + L3 | Community |
| **Pro** | €49/mo | 5,000 | All | Priority |
| **Enterprise** | Custom | Unlimited | All + SLA | Dedicated |

Beta pricing ends when usage thresholds are reached. [Get started free →](https://github.com/MicheleCampi/optim-engine)

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
      "args": [
        "https://optim-engine-production.up.railway.app/mcp"
      ]
    }
  }
}
```

---

## Examples

### Scheduling (L1)
```bash
curl -X POST https://optim-engine-production.up.railway.app/optimize_schedule \
  -H "Content-Type: application/json" \
  -d '{
    "jobs": [
      {"job_id": "J1", "tasks": [
        {"task_id": "cut", "duration": 30, "eligible_machines": ["M1", "M2"]},
        {"task_id": "weld", "duration": 20, "eligible_machines": ["M2"]}
      ], "due_date": 80}
    ],
    "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
    "objective": "minimize_makespan"
  }'
```

### Prescriptive Intelligence (L3)
```bash
curl -X POST https://optim-engine-production.up.railway.app/prescriptive_advise \
  -H "Content-Type: application/json" \
  -d '{
    "solver_type": "scheduling",
    "solver_request": {
      "jobs": [{"job_id": "J1", "tasks": [
        {"task_id": "cut", "duration": 30, "eligible_machines": ["M1"]}
      ], "due_date": 80}],
      "machines": [{"machine_id": "M1"}],
      "objective": "minimize_makespan"
    },
    "forecast_parameters": [{
      "parameter_path": "jobs[J1].tasks[cut].duration",
      "historical_data": [
        {"period": 0, "value": 25}, {"period": 1, "value": 28},
        {"period": 2, "value": 30}, {"period": 3, "value": 33},
        {"period": 4, "value": 35}
      ],
      "forecast_method": "exponential_smoothing"
    }],
    "risk_appetite": "moderate"
  }'
```

---

## Use Cases

- **Manufacturing**: Production scheduling with demand forecasting and risk quantification
- **Logistics**: Delivery routing with variable demand, travel times, and fleet trade-offs
- **Warehouse**: Bin packing with uncertain item weights and multi-objective optimization
- **Supply Chain**: End-to-end prescriptive intelligence: forecast → optimize → advise
- **Finance**: Portfolio-like resource allocation under uncertainty with CVaR metrics

---

## Architecture
```
AI Agent (Claude, GPT, Gemini, etc.)
    │
    ▼ MCP Protocol
┌──────────────────────────────────────────────────────┐
│  FastAPI + fastapi-mcp                                │
├──────────┬──────────┬──────────┬─────────────────────┤
│  L1      │  L1      │  L1      │  L2  L2.5  L3       │
│ Schedule │ Routing  │ Packing  │ Sensitivity          │
│ CP-SAT   │ Routing  │ CP-SAT   │ Robust               │
│          │ Library  │          │ Stochastic            │
│          │          │          │ Pareto                │
│          │          │          │ Prescriptive          │
├──────────┴──────────┴──────────┴─────────────────────┤
│  OR-Tools Solvers + Monte Carlo + Forecasting Engine  │
├──────────────────────────────────────────────────────┤
│  Pydantic v2 Models                                   │
└──────────────────────────────────────────────────────┘
```

---

## Tests
```bash
python -m pytest tests/ -v
```

121 tests across 9 modules.

---

## Landing Page

🌐 **[optim-engine-landing.vercel.app](https://optim-engine-landing.vercel.app/)**

## Marketplace Listings

- [MCPize](https://mcpize.com/mcp/optim-engine) — 11 MCP tools
- [Apify Store](https://apify.com/hearty_indentation/optim-engine)
- [LobeHub](https://lobehub.com/mcp/michelecampi-optim-engine)
- [mcp.so](https://mcp.so/server/optim-engine)

---

## License

MIT

---

*Built by [Michele Campi](https://github.com/MicheleCampi) — Operations Intelligence Engineer*
*The first MCP server with 4 levels of optimization intelligence.*
