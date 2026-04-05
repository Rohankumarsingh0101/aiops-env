# 🚨 Autonomous Incident Commander (AIOps Environment)

> A deterministic AIOps reinforcement learning environment for incident response and service recovery.

A **production-grade, OpenEnv-compatible reinforcement learning environment** where an AI agent acts as an on-call **Site Reliability Engineer (SRE)** to diagnose and resolve production incidents in a distributed system.

---

## 🎯 What This Environment Simulates

The environment models a live distributed system with three services: **auth**, **payments**, and **search**. At each episode start, one or more services are degraded or failing due to a hidden root cause (e.g., CPU spike, memory leak, DB connection pool exhaustion).

The agent must:
1. Identify the **most critical failing service** from observable metrics and logs
2. Apply the **correct action** to resolve the root cause
3. Restore all services to a **healthy state**
4. Accomplish this in **minimal steps** to maximize reward

---

## 💡 Why This Environment Is Useful

Most AIOps benchmarks rely on synthetic data with no causal structure. This environment:
- Uses **deterministic, causal transitions** (same root cause → same resolution path)
- Enforces **partial observability** (root cause is hidden — agent must reason from metrics and logs)
- Requires **multi-step reasoning** (no single-step solutions)
- Implements **realistic cascading failures** (auth degradation flows into payments)
- Produces **rich signals** for training or evaluating diagnostic LLMs and RL agents

---

## ⚙️ Tech Stack

- Python 3.10+
- FastAPI + Uvicorn
- Pydantic v2
- Docker

---

## 🚀 Installation

### 🐳 Docker (Recommended)

```bash
docker build -t aiops_env .
docker run --rm -p 7860:7860 aiops_env
```

### 🐍 Local Setup

```bash
pip install fastapi uvicorn pydantic
uvicorn main:app --host 0.0.0.0 --port 7860
```

---

## 📡 API Endpoints

| Endpoint    | Method | Description                        |
| ----------- | ------ | ---------------------------------- |
| `/`         | GET    | Minimal live dashboard             |
| `/health`   | GET    | Health probe — returns `{"status":"ok"}` |
| `/reset`    | POST   | Initialize a new episode           |
| `/step`     | POST   | Execute one action                 |
| `/state`    | GET    | Full debug state (includes hidden vars) |
| `/tasks`    | GET    | List available task IDs            |
| `/grader`   | POST   | Score a full trajectory            |
| `/baseline` | GET    | Run built-in heuristic agent       |
| `/docs`     | GET    | Interactive Swagger UI             |

---

## 🤖 Action Space

| Action              | Description                                      |
| ------------------- | ------------------------------------------------ |
| `restart_service`   | Resolves memory_leak, cpu_spike, db pool issues  |
| `scale_up`          | Resolves cpu_spike; provides partial CPU relief  |
| `run_diagnostics`   | Reveals root cause in logs — no fix, small penalty |
| `ignore`            | No action taken — small penalty                  |
| `escalate`          | Partial error/CPU relief — significant penalty   |

### Example Action Payload

```json
{
  "action_type": "restart_service",
  "target_service": "auth"
}
```

---

## 📊 Observation Space

Each `/step` and `/reset` response returns:

```json
{
  "services": {
    "auth":     { "status": "healthy|degraded|down", "metrics": { "cpu": 40.0, "memory": 50.0, "errors": 5 } },
    "payments": { "status": "healthy|degraded|down", "metrics": { "cpu": 30.0, "memory": 40.0, "errors": 2 } },
    "search":   { "status": "healthy|degraded|down", "metrics": { "cpu": 95.0, "memory": 60.0, "errors": 50 } }
  },
  "logs": ["High CPU usage detected on search service.", "Critical service: search"],
  "severity": 2,
  "time_elapsed": 0
}
```

> ⚠️ `root_cause` is **never** exposed in the observation — the agent must infer it.

---

## 🧮 Reward Logic

```
reward = min(health_score + progress_bonus, 0.95)
```

- **health_score**: weighted average of CPU and error reduction across all services
- **progress_bonus**: delta of total errors before and after action / 1000
- **Penalties**:
  - Targeting wrong service: `-0.10`
  - `run_diagnostics`: `-0.05`
  - `ignore`: `-0.05`
  - `escalate`: `-0.20`
  - Failing to resolve by max_steps: `-0.20`
- **Perfect bonus**: `reward = 1.0` if system is fully resolved in exactly 2 correct steps

**Range: [0.05, 1.0]**

---

## 🏁 Episode Termination

The episode ends when:

1. ✅ **All services are healthy** AND at least **2 steps** have been taken
2. ⏱ **`max_steps` (3) is reached** — even if system is still unhealthy

If max_steps is hit with an unhealthy system, a `-0.20` penalty is applied.

---

## 🗺️ Task Difficulty

| Task      | Scenario                                           | Optimal Steps |
| --------- | -------------------------------------------------- | ------------- |
| 🟢 Easy   | `search` CPU spike — single service degraded        | 1–2           |
| 🟡 Medium | `auth` memory leak cascading to `payments`          | 2             |
| 🔴 Hard   | `payments` appears worst but `auth` is root cause (DB pool exhaustion) | 2–3 |

---

## 📞 Example API Calls

### Start a session

```bash
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "easy"}'
```

### Take a step

```bash
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "scale_up", "target_service": "search"}'
```

### Check health

```bash
curl http://localhost:7860/health
# → {"status": "ok"}
```

### Run baseline agent

```bash
curl http://localhost:7860/baseline
```

---

## 🧠 Why This Environment Is Realistic and Strong

| Property | Implementation |
| -------- | -------------- |
| **Partial Observability** | Root causes are hidden; agent reads metrics + logs |
| **Causal Structure** | Auth degradation cascades deterministically to Payments |
| **Deceptive Scenarios** | Hard task: payments visually worst but auth holds real cause |
| **Multi-Step Requirement** | Done only triggers after ≥2 steps |
| **Expressive Reward** | Rewards sensitive to efficiency, correctness, and recovery quality |
| **Determinism** | Zero randomness — reproducible for benchmarking |

This environment is fully deterministic and reproducible, ensuring fair and consistent evaluation across agents.

---

## 📁 Project Structure

| File | Purpose |
| ---- | ------- |
| `main.py` | FastAPI routes + baseline agent + dashboard |
| `env.py` | Core environment logic and state transitions |
| `models.py` | Pydantic schemas |
| `tasks.py` | Scenario definitions (easy, medium, hard) |
| `grader.py` | Trajectory evaluation |
| `Dockerfile` | Container deployment |

---

## 🧪 Testing

See `TESTING.md` for deterministic test cases covering all scenarios.
