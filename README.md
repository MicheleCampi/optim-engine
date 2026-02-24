# ⚡ OptimEngine — Operations Intelligence Solver

**The first MCP Server for production scheduling and vehicle routing optimization.**

An AI-native solver that assigns tasks to machines and deliveries to vehicles optimally using constraint programming. Built for the agentic economy: AI agents discover it, call it, and pay for it — autonomously.

[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![OR-Tools](https://img.shields.io/badge/Solver-OR--Tools-green)](https://developers.google.com/optimization)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-yellow)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-71%20passed-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## What It Does

OptimEngine solves two families of NP-hard optimization problems that LLMs cannot compute:

### 1. Scheduling — Flexible Job Shop (FJSP)
Assign tasks to machines optimally with precedence, time windows, machine eligibility, setup times, priorities, and multiple objectives.

### 2. Routing — CVRPTW
Assign delivery locations to vehicles optimally with capacity constraints, time windows, service times, GPS coordinates, and multiple objectives.

**The core insight**: LLMs understand optimization requests in natural language but *cannot compute optimal solutions*. These are NP-hard problems that require specialized solvers. OptimEngine is that solver, exposed as MCP tools that any AI agent can call.

---

## MCP Tools

| Tool | Problem | Input | Output |
|------|---------|-------|--------|
| `optimize_schedule` | Flexible Job Shop Scheduling | Jobs, tasks, machines, constraints | Optimal schedule + Gantt + metrics |
| `validate_schedule` | Schedule verification | Schedule + constraints | Violations + suggestions |
| `optimize_routing` | Vehicle Routing + Time Windows | Depot, locations, vehicles, capacity | Optimal routes + stop times + metrics |

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
      "args": ["http://localhost:8000/mcp"]
    }
  }
}
```

Or use the hosted endpoint:
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
      {
        "job_id": "ORDER-001",
        "name": "Moisturizing Cream",
        "tasks": [
          {"task_id": "mixing", "duration": 45, "eligible_machines": ["MIXER-A", "MIXER-B"]},
          {"task_id": "filling", "duration": 30, "eligible_machines": ["FILLER-1"]},
          {"task_id": "packaging", "duration": 20, "eligible_machines": ["PACK-1", "PACK-2"]}
        ],
        "due_date": 120, "priority": 8
      },
      {
        "job_id": "ORDER-002",
        "name": "Anti-Age Serum",
        "tasks": [
          {"task_id": "mixing", "duration": 60, "eligible_machines": ["MIXER-A"]},
          {"task_id": "filling", "duration": 25, "eligible_machines": ["FILLER-1"]},
          {"task_id": "packaging", "duration": 15, "eligible_machines": ["PACK-1"]}
        ],
        "due_date": 150, "priority": 10
      }
    ],
    "machines": [
      {"machine_id": "MIXER-A"}, {"machine_id": "MIXER-B"},
      {"machine_id": "FILLER-1"}, {"machine_id": "PACK-1"}, {"machine_id": "PACK-2"}
    ],
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
      {"location_id": "customer_A", "demand": 20, "time_window_start": 0, "time_window_end": 3000, "service_time": 10},
      {"location_id": "customer_B", "demand": 15, "time_window_start": 500, "time_window_end": 4000, "service_time": 10},
      {"location_id": "customer_C", "demand": 25, "time_window_start": 0, "time_window_end": 5000, "service_time": 15}
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

---

## Use Cases

- **Manufacturing**: Production scheduling for contract manufacturing (cosmetics, pharma, food)
- **Logistics**: Last-mile delivery routing with time windows
- **Workshop**: Job shop scheduling for machine shops and fabrication
- **Food Delivery**: Multi-driver route optimization with capacity
- **Resource Allocation**: Assign tasks to workers/rooms/equipment optimally
- **Supply Chain**: Coordinate scheduling + routing for end-to-end planning

---

## Architecture
```
AI Agent (Claude, GPT, Gemini, etc.)
    │
    ▼ MCP Protocol
┌──────────────────────────────┐
│  FastAPI + fastapi-mcp        │  ← API layer (validation, MCP)
├──────────────────────────────┤
│  Scheduling   │  Routing      │
│  OR-Tools     │  OR-Tools     │
│  CP-SAT       │  Routing Lib  │  ← Computational brain
├──────────────────────────────┤
│  Pydantic Models              │  ← Schema contract (self-documenting)
└──────────────────────────────┘
```

**Stack**: Python 3.12 · FastAPI · OR-Tools (CP-SAT + Routing) · fastapi-mcp · Pydantic v2

---

## Deployment

### Hosted (ready to use)
```
https://optim-engine-production.up.railway.app
```

### Docker
```bash
docker build -t optim-engine .
docker run -p 8000:8000 optim-engine
```

### Railway
```bash
railway login && railway init && railway up
```

---

## Tests
```bash
pip install pytest
python -m pytest tests/ -v
```

71 tests covering: flexible job shop, time windows, due dates, machine availability, setup times, all objectives, CVRPTW routing, capacity constraints, drop visits, GPS distances, real-world manufacturing and delivery scenarios.

---

## Marketplace Listings

- [MCPize](https://mcpize.com/mcp/optim-engine)
- [Apify Store](https://apify.com/hearty_indentation/optim-engine)
- [LobeHub](https://lobehub.com/mcp/michelecampi-optim-engine)

---

## License

MIT

---

*Built with Google OR-Tools — the optimization toolkit used by Google for fleet routing, scheduling, and resource allocation at scale.*
