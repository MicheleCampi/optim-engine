# ⚡ OptimEngine — Operations Scheduling Solver

**The first MCP Server for production scheduling optimization.**

An AI-native solver that assigns tasks to machines optimally using constraint programming. Built for the agentic economy: AI agents discover it, call it, and pay for it — autonomously.

[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)](https://modelcontextprotocol.io)
[![OR-Tools](https://img.shields.io/badge/Solver-OR--Tools%20CP--SAT-green)](https://developers.google.com/optimization)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-yellow)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

---

## What It Does

OptimEngine solves **Flexible Job Shop Scheduling Problems** (FJSP) — one of the most common and computationally hard optimization problems in manufacturing, logistics, and operations.

**The core insight**: LLMs understand scheduling requests in natural language but *cannot compute optimal solutions*. This is an NP-hard problem that requires a constraint programming solver. OptimEngine is that solver, exposed as an MCP tool that any AI agent can call.

### Capabilities

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

---

## Quick Start

### 1. Install & Run

```bash
git clone https://github.com/YOUR_USERNAME/optim-engine.git
cd optim-engine
pip install -r requirements.txt
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

Server starts at `http://localhost:8000`. Docs at `/docs`. MCP endpoint at `/mcp`.

### 2. Connect via MCP (Claude Desktop, Cursor, etc.)

Add to your MCP client configuration:

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

### 3. Call the Solver

```bash
curl -X POST http://localhost:8000/optimize_schedule \
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
        "due_date": 120,
        "priority": 8
      },
      {
        "job_id": "ORDER-002",
        "name": "Anti-Age Serum",
        "tasks": [
          {"task_id": "mixing", "duration": 60, "eligible_machines": ["MIXER-A"]},
          {"task_id": "filling", "duration": 25, "eligible_machines": ["FILLER-1"]},
          {"task_id": "packaging", "duration": 15, "eligible_machines": ["PACK-1"]}
        ],
        "due_date": 150,
        "priority": 10
      }
    ],
    "machines": [
      {"machine_id": "MIXER-A"},
      {"machine_id": "MIXER-B"},
      {"machine_id": "FILLER-1"},
      {"machine_id": "PACK-1"},
      {"machine_id": "PACK-2"}
    ],
    "objective": "minimize_makespan"
  }'
```

### Response

```json
{
  "status": "optimal",
  "message": "Optimal schedule found in 0.03s. Makespan: 105 time units.",
  "schedule": [
    {"job_id": "ORDER-001", "task_id": "mixing", "machine_id": "MIXER-B", "start": 0, "end": 45, "duration": 45},
    {"job_id": "ORDER-002", "task_id": "mixing", "machine_id": "MIXER-A", "start": 0, "end": 60, "duration": 60},
    {"job_id": "ORDER-001", "task_id": "filling", "machine_id": "FILLER-1", "start": 45, "end": 75, "duration": 30},
    {"job_id": "ORDER-002", "task_id": "filling", "machine_id": "FILLER-1", "start": 75, "end": 100, "duration": 25},
    {"job_id": "ORDER-001", "task_id": "packaging", "machine_id": "PACK-2", "start": 75, "end": 95, "duration": 20},
    {"job_id": "ORDER-002", "task_id": "packaging", "machine_id": "PACK-1", "start": 100, "end": 115, "duration": 15}
  ],
  "metrics": {
    "makespan": 115,
    "total_tardiness": 0,
    "num_on_time": 2,
    "avg_machine_utilization_pct": 34.8,
    "solve_time_seconds": 0.031
  },
  "gantt": ["...ready-to-render entries..."]
}
```

---

## MCP Tools

### `optimize_schedule`
Solves a Flexible Job Shop Scheduling Problem.

**Input**: Jobs (with ordered tasks), machines, constraints, objective.
**Output**: Optimized schedule, metrics, Gantt data.

### `validate_schedule`
Validates an existing schedule against constraints.

**Input**: A schedule + original jobs/machines.
**Output**: Violations, metrics, improvement suggestions.

---

## Deployment

### Railway (recommended)
```bash
# From the project directory:
railway login
railway init
railway up
```

### Docker
```bash
docker build -t optim-engine .
docker run -p 8000:8000 optim-engine
```

### Fly.io
```bash
fly launch
fly deploy
```

---

## Architecture

```
AI Agent (Claude, GPT, etc.)
    │
    ▼ MCP Protocol
┌─────────────────────────┐
│  FastAPI + fastapi-mcp   │  ← API layer (validation, routing, MCP)
├─────────────────────────┤
│  OR-Tools CP-SAT Solver  │  ← Computational brain (constraint programming)
├─────────────────────────┤
│  Pydantic Models         │  ← Schema contract (self-documenting for agents)
└─────────────────────────┘
```

**Stack**: Python 3.12 · FastAPI · OR-Tools CP-SAT · fastapi-mcp · Pydantic v2

---

## Tests

```bash
python -m tests.test_solver
```

52 tests covering: basic/flexible job shop, time windows, due dates, machine availability, setup times, all objectives, edge cases, medium-scale instances, real-world cosmetics manufacturing scenario, and schedule validation.

---

## License

MIT

---

*Built with OR-Tools CP-SAT — the constraint programming solver that won gold at MiniZinc competition.*
