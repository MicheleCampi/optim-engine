# ⚡ OptimEngine

**Operations Intelligence for AI Agents — L1 → L3 in one conversation.**

11 MCP tools that optimize, quantify risk, forecast, and prescribe. From production scheduling to Monte Carlo simulation. From delivery routing to Pareto frontiers. Ask in natural language, get optimal decisions.

[![Live](https://img.shields.io/badge/status-live-brightgreen)](https://optim-engine-production.up.railway.app/)
[![Version](https://img.shields.io/badge/version-8.0.0-blue)](https://github.com/MicheleCampi/optim-engine)
[![Tests](https://img.shields.io/badge/tests-121%20passing-brightgreen)](https://github.com/MicheleCampi/optim-engine)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![ERC-8004](https://img.shields.io/badge/ERC--8004-Agent%20%2322518-purple)](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432)

---

## 🤖 Use with Claude (60 seconds)

No installation. No code. Works on claude.ai (Free, Pro, Max, Team, Enterprise).

1. Open [claude.ai](https://claude.ai)
2. Click **+** → **Integrations**
3. **Add custom integration**
4. Paste this URL:

```
https://optim-engine-production.up.railway.app/mcp/sse
```

Claude discovers all 11 tools automatically. Try asking:

> *"Schedule 5 production orders on 4 machines, minimize delays"*
>
> *"Optimize delivery routes for 6 clients with 2 trucks"*
>
> *"What happens if dosing time increases 30%? Run sensitivity analysis"*
>
> *"I have historical data for the last 8 weeks. Forecast next month and recommend actions"*

---

## 🧠 What Is OptimEngine?

An **Operations Intelligence Engine** — not a wrapper, not a chatbot. A computational decision brain that solves NP-hard optimization problems and quantifies risk. Powered by Google OR-Tools CP-SAT and Routing solvers.

### 4 Intelligence Levels

| Level | Capability | Question It Answers |
|-------|-----------|-------------------|
| **L1** Deterministic | Scheduling, Routing, Packing, Validation | *What's the optimal plan?* |
| **L2** Uncertainty | Sensitivity, Robust, Stochastic | *How fragile is this plan?* |
| **L2.5** Multi-Objective | Pareto Frontier | *What's the best trade-off?* |
| **L3** Prescriptive | Forecast → Optimize → Risk → Advise | *What should I do and why?* |

### 11 MCP Tools

**L1 — Deterministic Optimization**
- `optimize_schedule` — Flexible Job Shop (FJSP) with precedence, setup times, priorities, 4 objectives
- `optimize_routing` — CVRPTW with capacity, time windows, distance matrix, drop visits
- `optimize_packing` — Multi-dimensional bin packing with weight, volume, groups
- `validate_schedule` — Find overlaps, precedence violations, eligibility errors

**L2 — Optimization under Uncertainty**
- `analyze_sensitivity` — Parametric perturbation, elasticity, risk ranking
- `optimize_robust` — Worst-case / percentile protection, price of robustness
- `optimize_stochastic` — Monte Carlo + CVaR with 4 distributions

**L2.5 — Multi-Objective**
- `optimize_pareto` — 2-4 competing objectives, trade-off analysis, correlation

**L3 — Prescriptive Intelligence**
- `prescriptive_advise` — 4 forecast methods, 3 risk appetites, confidence intervals, action items

**Infrastructure**
- `health_check` — System status
- `root` — Server info, capabilities, tool listing

---

## 📊 Live Demo Results

Every number below comes from a real call to OptimEngine. Zero mock data.

### Digital Twin Decisionale — NovaCosm (Cosmetics Manufacturer)

Full production-to-delivery chain: 6 lines, 8 orders, 5 brand clients.

| Phase | Tool | Result |
|-------|------|--------|
| Plant diagnosis | `optimize_schedule` | 575 min makespan, 2 late, Line 2 bottleneck (82.6%) |
| Cycle time forecast | `prescriptive_advise` | 3 rising trends (+1.1-1.65%/week), +5.6% makespan in 4 weeks |
| What-if: cross-line | `optimize_schedule` | Move 1 product to Line 1 → tardiness -65%, lines balanced |
| Risk profile | `optimize_stochastic` | 50 Monte Carlo, CV 4.5%, 100% feasible |
| Client doubles orders | `optimize_schedule` | Without investment: 530 min tardiness, 50% late |
| + New line investment | `optimize_schedule` | With Line 2B: **0 tardiness, 478 min, 8/8 on-time** |
| Manual schedule check | `validate_schedule` | 4 violations found (overlaps + precedence) |
| Risk ranking | `analyze_sensitivity` | Serum dosing most critical (score 11.3, elasticity 0.227) |
| Delivery routing | `optimize_routing` | 6 clients, 2 trucks, 70 km, all time windows met |
| Truck loading | `optimize_packing` | 8/8 pallets, 0 excluded, route-constrained |

**Strategic decisions generated:** cross-line authorization (saves 125 min/day), maintenance alert (Line 2 degrading), investment quantification (Line 2B enables client growth).

### BevDistri (F&B HoReCa Distribution)

| Tool | Result |
|------|--------|
| `optimize_routing` | 18 clients, 2/3 vehicles used, 132 km, all windows met |
| `prescriptive_advise` | +21% Modena demand in 4 weeks, decision deadline identified |
| `optimize_packing` | 13 items, 2 bins, 0 drops, 97% utilization alert |
| `analyze_sensitivity` | Hotel demand can double without route split |

---

## 🔧 For Developers

### MCP Configuration (Claude Desktop, Cursor)

```json
{
  "mcpServers": {
    "optim-engine": {
      "command": "npx",
      "args": [
        "supergateway",
        "--sse",
        "https://optim-engine-production.up.railway.app/mcp/sse"
      ]
    }
  }
}
```

### Direct API

```bash
curl -X POST https://optim-engine-production.up.railway.app/optimize_schedule \
  -H "Content-Type: application/json" \
  -d '{
    "jobs": [
      {
        "job_id": "ORD-001",
        "priority": 8,
        "due_date": 480,
        "tasks": [
          {"task_id": "dosing", "duration": 90, "eligible_machines": ["line_A", "line_B"], "setup_time": 15},
          {"task_id": "filling", "duration": 60, "eligible_machines": ["line_A", "line_D"], "setup_time": 10}
        ]
      }
    ],
    "machines": [{"machine_id": "line_A"}, {"machine_id": "line_B"}, {"machine_id": "line_D"}],
    "objective": "minimize_makespan"
  }'
```

### Orchestration Pattern: Routing → Packing

When combining routing and packing (e.g., delivery logistics), use this pattern:

1. **Call `optimize_routing`** → get routes with vehicle-to-client assignments
2. **Partition items by route** → each vehicle's items based on routing output
3. **Call `optimize_packing` per vehicle** → separate packing per truck/van

This ensures pallet assignments match delivery routes. See the NovaCosm demo for a complete example.

---

## 🌐 Available On

| Platform | Link |
|----------|------|
| **Claude.ai** | Add as custom integration ([instructions above](#-use-with-claude-60-seconds)) |
| **MCPize** | [mcpize.com/mcp/optim-engine](https://mcpize.com/mcp/optim-engine) |
| **Apify Store** | [apify.com/hearty_indentation/optim-engine](https://apify.com/hearty_indentation/optim-engine) |
| **LobeHub** | [lobehub.com/mcp/michelecampi-optim-engine](https://lobehub.com/mcp/michelecampi-optim-engine) |
| **mcp.so** | [mcp.so/server/optim-engine](https://mcp.so/server/optim-engine) |
| **Railway** | [optim-engine-production.up.railway.app](https://optim-engine-production.up.railway.app/) |
| **ERC-8004** | [Agent #22518 on Base L2](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432) |
| **Landing Page** | [optim-engine-landing.vercel.app](https://optim-engine-landing.vercel.app/) |

---

## 📈 Numbers

| Metric | Value |
|--------|-------|
| Solver modules | 9 |
| MCP tools | 11 |
| Tests passing | 121 |
| Intelligence levels | 4 (L1, L2, L2.5, L3) |
| Forecast methods | 4 |
| Stochastic distributions | 4 |
| Scheduling objectives | 4 |
| Routing objectives | 4 |
| Risk appetites | 3 |
| ERC-8004 Agent | #22518 (Base L2) |
| Capital invested | €0 |

---

## 🏗️ Architecture

```
                    ┌─────────────────────────────────┐
                    │         Claude / AI Agent        │
                    │    (natural language interface)   │
                    └──────────────┬──────────────────┘
                                   │ MCP Protocol
                    ┌──────────────▼──────────────────┐
                    │      OptimEngine v8.0.0          │
                    │      FastAPI + MCP Server        │
                    ├─────────────────────────────────┤
                    │  L1 Deterministic                │
                    │  ├─ Scheduling (CP-SAT FJSP)     │
                    │  ├─ Routing (OR-Tools CVRPTW)    │
                    │  ├─ Packing (CP-SAT)             │
                    │  └─ Validator                    │
                    ├─────────────────────────────────┤
                    │  L2 Uncertainty                  │
                    │  ├─ Sensitivity Analysis          │
                    │  ├─ Robust Optimization           │
                    │  └─ Stochastic (Monte Carlo)     │
                    ├─────────────────────────────────┤
                    │  L2.5 Multi-Objective             │
                    │  └─ Pareto Frontier               │
                    ├─────────────────────────────────┤
                    │  L3 Prescriptive Intelligence     │
                    │  └─ Forecast → Optimize → Advise  │
                    └─────────────────────────────────┘
                         Google OR-Tools · Python
                         Railway · ERC-8004 Base L2
```

---

## 🤝 Consulting & Custom Integration

Need OptimEngine configured for your specific operations? Production scheduling, logistics optimization, risk analysis for your plant?

I build Digital Twin Decisional systems — from scheduling diagnosis to strategic what-if analysis. The solver runs in seconds; the domain expertise makes it useful.

**Michele Campi** — Operations Intelligence Engineer
- GitHub: [@MicheleCampi](https://github.com/MicheleCampi)
- 7+ years operations controlling in cosmetics contract manufacturing
- Built OptimEngine solo: 11 tools, 4 intelligence levels, 121 tests, zero capital

---

## License

MIT — use it freely. The code is open; the intelligence design is the moat.
