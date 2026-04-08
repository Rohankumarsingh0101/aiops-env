---
sdk: docker
app_port: 7860
---

# 🚨 Autonomous Incident Commander (AIOps Environment)

> A deterministic AIOps reinforcement learning environment for incident response and service recovery.

A **production-grade, OpenEnv-compatible reinforcement learning environment** where an AI agent acts as an on-call **Site Reliability Engineer (SRE)** to diagnose and resolve production incidents in a distributed system.

## 🔗 Quick Links

* Live App: https://rs01019989-aiops.hf.space/
* API Docs: https://rs01019989-aiops.hf.space/docs
* Health Check: https://rs01019989-aiops.hf.space/health

---

## 🎯 What This Environment Simulates

The environment models a live distributed system with three services: **auth**, **payments**, and **search**. At each episode start, one or more services are degraded or failing due to a hidden root cause (e.g., CPU spike, memory leak, DB connection pool exhaustion).

The agent must:
1. Identify the **most critical failing service** from observable metrics and logs
2. Apply the **correct action** to resolve the root cause
3. Restore all services to a **healthy state**
4. Accomplish this in **minimal steps** to maximize reward

---

## 🔥 Why This Matters

Production systems go down. On-call engineers have minutes — not hours — to identify root causes across dozens of services, read contradictory logs, and apply the right fix in the right order.

Most LLM benchmarks test knowledge recall. **This environment tests decision-making under uncertainty** — the skill that matters in real SRE work.

There is currently no standard, open environment for evaluating AI agents on incident response reasoning. This fills that gap: deterministic, multi-step, causally structured, and directly mappable to real-world SRE problem patterns.

---

## 🧩 What Makes This Hard

**1. Cascading failures.** A root cause on one service (e.g. auth DB pool exhaustion) silently degrades another (payments retry storm). The loudest symptom is never the cause.

**2. Deceptive signals.** The hard task surfaces a service with high errors and high CPU — an obvious target. The actual root cause is a quieter service with normal CPU, slightly elevated memory, and a saturated DB connection pool visible only in logs.

**3. Partial recovery.** Actions like `escalate` and `scale_up` reduce metrics without resolving the underlying failure. An agent that stops after a partial improvement will see `done=True` from max-steps — but `success=False`.

**4. Observation cost.** `run_diagnostics` reveals the root cause but incurs a penalty. An agent must decide when insight is worth the cost versus acting directly.

---

## 🎓 Agent Learning Value

| Skill | How This Environment Trains It |
|---|---|
| **Root cause analysis** | Root cause is never directly exposed — must be inferred from metrics + logs |
| **Decision sequencing** | Order of actions matters; fixing cascade victim before root cause wastes steps |
| **Cost-aware action selection** | Diagnostics, escalation, and wrong-service actions all carry measurable penalties |
| **Multi-step planning** | Minimum 2 steps required; optimal path = 2–3 steps depending on task |

---

## 💥 Example Failure Journey (Hard Task)

```
POST /reset  {"task_id": "hard"}
→ payments: errors=480, cpu=91%  ← loud, obvious
→ auth: errors=30, cpu=45%       ← quiet, suspicious
→ logs: "Connection pool saturation detected on auth DB layer"

POST /step  {"action_type": "scale_up", "target_service": "payments"}
→ payments cpu drops to 41%      ← looks like progress
→ payments errors still 480      ← not resolved (no root cause here)
→ reward=0.12  done=false
→ log: "[PARTIAL] CPU reduced — but errors unchanged. Root cause lies elsewhere."

POST /step  {"action_type": "restart_service", "target_service": "auth"}
→ auth root cause cleared        ← db_connection_pool_exhausted fixed
→ payments errors cascade-clear  ← victim recovers once root cause is gone
→ reward=0.87  done=true  success=true
```

**Lesson:** The first action produced a convincing partial result. A greedy or shallow agent stops there. A reasoning agent reads the logs, correlates auth's connection pool warning, and acts on the root cause.

---

## 🏆 What Makes This Strong (Judge Summary)

| Property | Detail |
|---|---|
| **Deterministic** | Same action sequence always produces identical rewards, states, and logs |
| **Partially Observable** | Root causes are hidden — agents must reason from indirect metrics |
| **Deceptive Task** | Hard task has a quiet service hiding the actual root cause behind a noisy cascade victim |
| **Cascading Failures** | Auth degradation propagates to Payments, testing multi-service reasoning |
| **Partial Recovery** | `escalate` and wrong restarts reduce metrics but don't resolve; agents must continue |
| **Reward Design** | Bounded `[0.05, 1.0]`, correct 2-step optimal path = 1.0, wrong actions = measurable penalty |
| **Production Realism** | Logs use SRE-style narrative: `[RESOLVED]`, `[PARTIAL]`, `[ESCALATED]`, `[WARN]` tags |
| **OpenEnv-Compatible** | Standard `/reset`, `/step`, `/state`, `/health`, Pydantic schemas, 422 on bad input |

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

### 🐍 Local Setup (Standard)

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 7860
```

### ⚡ Local Setup (uv / OpenEnv Multi-mode)

Since this package is packaged for `openenv` multi-mode deployment, you can also use `uv`:

```bash
uv sync
uv run uvicorn server.app:app --host 0.0.0.0 --port 7860
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

## Example API Usage

### Reset
```json
POST /reset
{
  "task_id": "easy"
}
```

### Step
```json
POST /step
{
  "action_type": "scale_up",
  "target_service": "search"
}
```

### Example Response
```json
{
  "observation": {
    "services": {
      "search": {
        "status": "healthy",
        "metrics": {"cpu": 40.0, "memory": 60.0, "errors": 0}
      }
    },
    ...
  },
  "reward": 0.53,
  "done": false,
  "info": {
    "action_correct": true
  }
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
  - `ignore`: `-0.10`
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
