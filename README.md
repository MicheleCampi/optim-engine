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

> *"Schedule 10 production orders on 8 CNC machines for automotive clients, minimize delays"*
>
> *"Run Monte Carlo simulation with 50 scenarios on the machining times"*
>
> *"What's the worst case if the 5-axis CNC degrades 50%?"*
>
> *"Forecast cycle times from my last 10 weeks of data and recommend actions"*

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

### 🏭 Industrie 4.0 Stress Test — PräzisionsTech GmbH (Automotive)

Mittelstand tedesco: 10 ordini, 8 macchine CNC, 5 clienti tier-1 (Bosch, ZF, Continental, MAHLE, Brose), turno doppio.

| Test | Tool | Result |
|------|------|--------|
| Scheduling 10x8 | `optimize_schedule` | **10/10 on-time, 0 tardiness, 0.05s**. CNC-2 bottleneck at 91.9% |
| Sensitivity 4 params | `analyze_sensitivity` | 25 solves, 0.3s. Grinding most sensitive (7.2), turning MAHLE score 0 |
| Monte Carlo 50 scenarios | `optimize_stochastic` | CV 2.7%, 100% feasible, risk premium 5.6% |
| Robust worst-case CNC-5 | `optimize_robust` | **SPOF detected: Price of Robustness 28.8%**, 100% feasible |
| Forecast CNC degradation | `prescriptive_advise` | 5-axis +0.93%/week, grinding +1.52%/week, spread 3% |
| Multi-objective trade-off | `optimize_pareto` | No conflict (sufficient capacity). Confirms margin |

**Verdict: the brain handles Mittelstand automotive complexity. 39 tasks, 4 phases per order, solved in <1s with strategic insights no spreadsheet could produce.**

### 🧪 Digital Twin — NovaCosm S.r.l. (Cosmetics Contract Manufacturing)

Full DTD with closed loop: 6 lines, 8 orders, 5 brand clients, 4-week simulation.

| Phase | Tool | Result |
|-------|------|--------|
| Plant diagnosis | `optimize_schedule` | 575 min, 2 late, Line 2 bottleneck (82.6%) |
| Forecast + closed loop | `prescriptive_advise` | Trend +1.65%/week → maintenance → DTD detects improvement |
| Cross-line what-if | `optimize_schedule` | Tardiness -65%, lines balanced (82%/76%) |
| Client doubles orders | `optimize_schedule` | Without investment: 530 min tardiness. With Line 2B: **0 tardiness** |
| Monte Carlo risk | `optimize_stochastic` | CV 4.5%, 100% feasible |
| Robust post-maintenance | `optimize_robust` | PoR 0%, 100% feasible, system stable |
| Delivery routing | `optimize_routing` | 6 clients, 2 trucks, 70 km, 0 drops |
| Truck loading | `optimize_packing` | 8/8 pallets, route-constrained |

### 🚛 BevDistri (F&B HoReCa Distribution)

| Tool | Result |
|------|--------|
| `optimize_routing` | 18 clients, 2/3 vehicles, 132 km, all windows met |
| `prescriptive_advise` | +21% Modena demand in 4 weeks |
| `optimize_packing` | 13 items, 2 bins, 97% utilization alert |
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
    "jobs": [{"job_id": "PT-4401", "priority": 10, "due_date": 480,
      "tasks": [
        {"task_id": "turning", "duration": 120, "eligible_machines": ["CNC-1","CNC-2"], "setup_time": 25},
        {"task_id": "grinding", "duration": 90, "eligible_machines": ["GRIND-1"], "setup_time": 20},
        {"task_id": "inspection", "duration": 45, "eligible_machines": ["CMM-1"], "setup_time": 10}
      ]}],
    "machines": [{"machine_id": "CNC-1"}, {"machine_id": "CNC-2"}, {"machine_id": "GRIND-1"}, {"machine_id": "CMM-1"}],
    "objective": "minimize_total_tardiness"
  }'
```

### Orchestration Pattern: Routing → Packing

1. Call `optimize_routing` → get vehicle-to-client assignments
2. Partition items by route
3. Call `optimize_packing` per vehicle (separate call per truck)

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
| Scenarios tested | 4 (CosmetiProd, NovaCosm DTD, BevDistri, PräzisionsTech) |
| Max problem size verified | 10 jobs × 8 machines × 39 tasks |
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

Need OptimEngine configured for your specific operations? Production scheduling, logistics optimization, Digital Twin Decisionale for your plant?

I build DTD systems — from scheduling diagnosis to strategic what-if analysis to closed-loop learning. The solver runs in seconds; the domain expertise makes it useful.

**Michele Campi** — Operations Intelligence Engineer
- GitHub: [@MicheleCampi](https://github.com/MicheleCampi)
- 7+ years operations controlling in cosmetics contract manufacturing
- Built OptimEngine solo: 11 tools, 4 intelligence levels, 121 tests, zero capital
- Verified on 4 industrial scenarios including automotive Mittelstand

---

## License

MIT — use it freely. The code is open; the intelligence design is the moat.

