# 🚨 Autonomous Incident Commander (AIOps Environment)

A production-grade **OpenEnv-compatible reinforcement learning environment** where an AI agent acts as an on-call **Site Reliability Engineer (SRE)** to diagnose and resolve production incidents in a distributed system.

This environment simulates real-world infrastructure failures with deterministic transitions, multi-step reasoning, and reward-based evaluation.

---

# 🎯 Objective

The agent must:

* Identify the **most critical failing service**
* Apply appropriate actions
* Restore the system to a **healthy state**
* Optimize for **efficiency and correctness**

---

# 🧠 Key Features

## ✅ OpenEnv Compliance

* `POST /reset`
* `POST /step`
* `GET /state`

---

## ✅ Deterministic Environment

* No randomness
* Same input → same output
* Fully reproducible results

---

## ✅ Multi-Step Decision Making

* Requires **2–3 steps** to resolve incidents
* Prevents trivial one-step solutions

---

## ✅ Partial Observability

* Agent sees:

  * CPU, Memory, Errors
  * Logs
* Root cause is hidden

---

## ✅ Reward System (0.05 → 1.0)

Reward is based on:

* System health (CPU + errors)
* Progress improvement
* Correct prioritization
* Penalties for:

  * wrong actions
  * unnecessary steps

---

## ✅ Difficulty Levels

| Task      | Description                     |
| --------- | ------------------------------- |
| 🟢 Easy   | Single service degradation      |
| 🟡 Medium | Multiple services degraded      |
| 🔴 Hard   | High-severity cascading failure |

---

# ⚙️ Tech Stack

* Python 3.10
* FastAPI
* Pydantic
* Uvicorn
* Docker

---

# 🚀 Installation

## 🐳 Docker (Recommended)

```bash
docker build -t aiops_env .
docker run --rm -p 7860:7860 aiops_env
```

---

## 🐍 Local Setup

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 7860
```

---

# 📡 API Endpoints

| Endpoint    | Method | Description            |
| ----------- | ------ | ---------------------- |
| `/reset`    | POST   | Initialize environment |
| `/step`     | POST   | Execute action         |
| `/state`    | GET    | Debug state            |
| `/tasks`    | GET    | Available tasks        |
| `/grader`   | POST   | Evaluate trajectory    |
| `/baseline` | GET    | Run baseline agent     |

---

# 🤖 Action Space

## Services

* `auth`
* `payments`
* `search`

---

## Actions

| Action            | Description               |
| ----------------- | ------------------------- |
| `restart_service` | Fixes service issues      |
| `scale_up`        | Reduces load              |
| `run_diagnostics` | Provides insight (no fix) |
| `ignore`          | No action                 |
| `escalate`        | Partial fix + penalty     |

---

## Example

```json
{
  "action_type": "scale_up",
  "target_service": "search"
}
```

---

# 📊 Observation Space

Each step returns:

```json
{
  "services": {
    "service_name": {
      "status": "healthy | degraded",
      "metrics": {
        "cpu": int,
        "memory": int,
        "errors": int
      }
    }
  },
  "logs": [],
  "severity": int,
  "time_elapsed": int
}
```

---

# 🧮 Reward Logic

```text
reward = health_score + progress_bonus
```

* Range: **0.05 → 1.0**
* Penalizes:

  * wrong service targeting
  * unnecessary actions
* Rewards:

  * fixing critical services
  * efficient resolution

---

# 🏁 Episode Termination

Episode ends when:

* ✅ All services are healthy
  OR
* ⏱ max steps reached

---

# 🧪 Testing

See full testing scenarios in:

👉 **TESTING.md**

---

# 📁 Project Structure

* `main.py` → API routes
* `env.py` → environment logic
* `models.py` → schemas
* `tasks.py` → scenarios
* `grader.py` → evaluation

---

# 🧠 Baseline Agent

Run:

```bash
GET /baseline
```

* Demonstrates deterministic solving
* Produces reproducible scores

---

# 🏆 Summary

This environment evaluates an agent’s ability to:

* prioritize critical failures
* reason across multiple steps
* optimize decisions under constraints

It is designed for **real-world AIOps simulation and agent benchmarking**.

---
