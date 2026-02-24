# ⚡ OptimEngine — Operations Intelligence Solver

**The first MCP Server for production scheduling, vehicle routing, and bin packing optimization.**

An AI-native solver that assigns tasks to machines, deliveries to vehicles, and items to bins optimally using constraint programming. Built for the agentic economy: AI agents discover it, call it, and pay for it — autonomously.

[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![OR-Tools](https://img.shields.io/badge/Solver-OR--Tools-green)](https://developers.google.com/optimization)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-yellow)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-97%20passed-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## What It Does

OptimEngine solves three families of NP-hard optimization problems that LLMs cannot compute:

### 1. Scheduling — Flexible Job Shop (FJSP)
Assign tasks to machines optimally with precedence, time windows, machine eligibility, setup times, priorities, and multiple objectives.

### 2. Routing — CVRPTW
Assign delivery locations to vehicles optimally with capacity constraints, time windows, service times, GPS coordinates, and multiple objectives.

### 3. Bin Packing
Assign items to bins/containers optimally with weight/volume constraints, item quantities, group constraints, and multiple objectives.

**The core insight**: LLMs understand optimization requests in natural language but *cannot compute optimal solutions*. These are NP-hard problems that require specialized solvers. OptimEngine is that solver, exposed as MCP tools that any AI agent can call.

---

## MCP Tools

| Tool | Problem | Input | Output |
|------|---------|-------|--------|
| `optimize_schedule` | Flexible Job Shop Scheduling | Jobs, tasks, machines, constraints | Optimal schedule + Gantt + metrics |
| `validate_schedule` | Schedule verification | Schedule + constraints | Violations + suggestions |
| `optimize_routing` | Vehicle Routing + Time Windows | Depot, locations, vehicles, capacity | Optimal routes + stop times + metrics |
| `optimize_packing` | Bin Packing | Items (weight/volume), bins (capacity) | Optimal assignments + bin summaries + metrics |

---

## Scheduling Capabilities

| Feature | Details |
|---------|---------|
| **Flexible Job Shop** | Tasks can run on multiple eligible machines |
| **Precedence** | Tasks within a job execute in defined order |
| **Time Windows** | Earliest start, latest end per job |
| **Machine Availability** | Machines have operational windows |
| **Setup Times** | Per-task setup time before processing |
| **Priorities** | Job priority (1-10) for weighted objectives |
| **4 Objectives** | Minimize makespan, total/max tardiness, balance load |
| **Schedule Validation** | Verify existing schedules, get violation reports |
| **Gantt Data** | Ready-to-render visualization in every response |

## Routing Capabilities

| Feature | Details |
|---------|---------|
| **Capacity Constraints** | Per-vehicle maximum load |
| **Time Windows** | Earliest/latest arrival per location |
| **Service Times** | Time spent at each delivery point |
| **GPS Coordinates** | Haversine distance from lat/lon |
| **Custom Distance Matrix** | Override with your own distances/times |
| **Drop Visits** | Skip infeasible locations with penalty |
| **Per-Vehicle Limits** | Max travel time/distance per vehicle |
| **4 Objectives** | Minimize distance, time, vehicles, or balance routes |

## Packing Capabilities

| Feature | Details |
|---------|---------|
| **Weight + Volume** | Dual-dimension capacity constraints |
| **Item Quantities** | Pack N copies of an item type |
| **Bin Types** | Multiple bin sizes with different costs |
| **Group Constraints** | Keep related items in the same bin |
| **Max Items per Bin** | Limit number of items per container |
| **Partial Packing** | Allow unpacked items for over-constrained problems |
| **4 Objectives** | Minimize bins, maximize value/items, balance load |

---

## Quick Start

### 1. Install & Run
```bash
git clone https://github.com/MicheleCampi/optim-engine.git
cd optim-engine
pip install -r requirements.txt
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

Server starts at `http://localhost:8000`. Docs at `/docs`. MCP endpoint at `/mcp`.

### 2. Connect via MCP (Claude Desktop, Cursor, etc.)
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
      ], "due_date": 10},
      {"job_id": "J2", "tasks": [
        {"task_id": "cut", "duration": 4, "eligible_machines": ["M1"]},
        {"task_id": "weld", "duration": 3, "eligible_machines": ["M2"]}
      ], "due_date": 12}
    ],
    "machines": [{"machine_id": "M1"}, {"machine_id": "M2"}],
    "objective": "minimize_makespan"
  }'
```

## Example — Routing
```bash
curl -X POST https://optim-engine-production.up.railway.app/optimize_routing \
  -H "Content-Type: application/json" \
  -d '{
    "depot_id": "warehouse",
    "locations": [
      {"location_id": "warehouse", "demand": 0},
      {"location_id": "customer_A", "demand": 20, "time_window_end": 3000, "service_time": 10},
      {"location_id": "customer_B", "demand": 15, "time_window_end": 4000, "service_time": 10},
      {"location_id": "customer_C", "demand": 25, "time_window_end": 5000, "service_time": 15}
    ],
    "vehicles": [
      {"vehicle_id": "truck_1", "capacity": 40},
      {"vehicle_id": "truck_2", "capacity": 40}
    ],
    "distance_matrix": [
      {"from_id": "warehouse", "to_id": "customer_A", "distance": 500, "travel_time": 500},
      {"from_id": "warehouse", "to_id": "customer_B", "distance": 800, "travel_time": 800},
      {"from_id": "warehouse", "to_id": "customer_C", "distance": 600, "travel_time": 600},
      {"from_id": "customer_A", "to_id": "warehouse", "distance": 500, "travel_time": 500},
      {"from_id": "customer_A", "to_id": "customer_B", "distance": 400, "travel_time": 400},
      {"from_id": "customer_A", "to_id": "customer_C", "distance": 700, "travel_time": 700},
      {"from_id": "customer_B", "to_id": "warehouse", "distance": 800, "travel_time": 800},
      {"from_id": "customer_B", "to_id": "customer_A", "distance": 400, "travel_time": 400},
      {"from_id": "customer_B", "to_id": "customer_C", "distance": 300, "travel_time": 300},
      {"from_id": "customer_C", "to_id": "warehouse", "distance": 600, "travel_time": 600},
      {"from_id": "customer_C", "to_id": "customer_A", "distance": 700, "travel_time": 700},
      {"from_id": "customer_C", "to_id": "customer_B", "distance": 300, "travel_time": 300}
    ],
    "objective": "minimize_total_distance"
  }'
```

## Example — Bin Packing
```bash
curl -X POST https://optim-engine-production.up.railway.app/optimize_packing \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"item_id": "laptop", "weight": 3, "volume": 8, "value": 1200, "quantity": 10},
      {"item_id": "monitor", "weight": 8, "volume": 25, "value": 500, "quantity": 5},
      {"item_id": "keyboard", "weight": 1, "volume": 3, "value": 80, "quantity": 20}
    ],
    "bins": [
      {"bin_id": "small_box", "weight_capacity": 20, "volume_capacity": 50, "cost": 5, "quantity": 5},
      {"bin_id": "large_box", "weight_capacity": 50, "volume_capacity": 120, "cost": 12, "quantity": 3}
    ],
    "objective": "minimize_bins"
  }'
```

---

## Use Cases

- **Manufacturing**: Production scheduling for contract manufacturing (cosmetics, pharma, food)
- **Logistics**: Last-mile delivery routing with time windows and capacity
- **Warehouse**: Bin packing for palletization, container loading, order fulfillment
- **Cloud/IT**: Resource allocation (VMs to servers, jobs to clusters)
- **Food Delivery**: Multi-driver route optimization
- **Supply Chain**: End-to-end scheduling + routing + packing

---

## Architecture
```
AI Agent (Claude, GPT, Gemini, etc.)
    │
    ▼ MCP Protocol
┌────────────────────────────────────────┐
│  FastAPI + fastapi-mcp                  │  ← API layer
├────────────┬────────────┬──────────────┤
│ Scheduling │  Routing   │  Bin Packing │
│ CP-SAT     │  Routing   │  CP-SAT      │
│            │  Library   │              │  ← OR-Tools solvers
├────────────┴────────────┴──────────────┤
│  Pydantic Models                        │  ← Schema contract
└────────────────────────────────────────┘
```

**Stack**: Python 3.12 · FastAPI · OR-Tools (CP-SAT + Routing) · fastapi-mcp · Pydantic v2

---

## Tests
```bash
pip install pytest
python -m pytest tests/ -v
```

97 tests covering: flexible job shop, time windows, due dates, machine availability, setup times, CVRPTW routing, capacity, GPS distances, bin packing, weight/volume constraints, group constraints, partial packing, and realistic manufacturing/delivery/warehouse scenarios.

---

## Landing Page

🌐 **[optim-engine.vercel.app](https://v0-optim-engine-landing-page.vercel.app/)**

## Marketplace Listings

- [MCPize](https://mcpize.com/mcp/optim-engine) — 6 MCP tools
- [Apify Store](https://apify.com/hearty_indentation/optim-engine) — 130k+ users/month
- [LobeHub](https://lobehub.com/mcp/michelecampi-optim-engine) — Top MCP directory

---

## License

MIT

---

*Built with Google OR-Tools — the optimization toolkit used by Google for fleet routing, scheduling, and resource allocation at scale.*
