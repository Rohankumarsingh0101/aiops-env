# Autonomous Incident Commander (AIOps Environment)

A production-grade, multi-step, agent-agnostic simulation where an AI agent acts as an on-call Site Reliability Engineer (SRE) handling production incidents across a distributed system.

This project implements an **OpenEnv-compatible interface** using a **FastAPI** backend, fully containerized with **Docker**, designed to benchmark autonomous agents on realistic infrastructure troubleshooting scenarios.

---

## 🚀 Features

* **OpenEnv API Compatibility:** Standardized `reset()`, `step()`, and `state()` endpoints.
* **Partial Observability:** Agents receive service metrics (CPU, Memory, Errors) and system logs, but the actual "root cause" of the outage (e.g., `memory_leak`, `db_connection_pool_exhausted`) is hidden from the observation state.
* **Cascading Failures:** If an incident goes unresolved, system health degrades naturally (e.g., Auth service errors will cascade and trigger Payments service errors).
* **Deterministic Reward Engine:** Agents are penalized for time elapsed (-0.05/step) and for making costly or incorrect decisions (-0.2 to -0.3). Correct analytical and mitigation actions are rewarded, clamped between `0.0` and `1.0`.
* **Built-in Grader:** Evaluates a full incident trajectory, scoring the agent on success rate, steps taken, and action efficiency.
* **Three Included Difficulty Levels:** `easy` (CPU Spike), `medium` (Memory Leak), and `hard` (Misleading logs with a buried database issue).

---

## 🛠 Tech Stack

* **Language:** Python 3.10
* **Framework:** FastAPI
* **Validation:** Pydantic V2
* **Server:** Uvicorn
* **Infrastructure:** Docker

---

## 📦 Installation & Usage

### 🐳 Option 1: Using Docker (Recommended)
This project includes a fully configured Dockerfile to ensure seamless execution.

1. Build the Docker image:
   ```bash
   docker build -t aiops_env .
   ```
2. Run the Docker container:
   ```bash
   docker run --rm -p 7860:7860 --name aiops_api aiops_env
   ```

### 🐍 Option 2: Running Locally natively
1. Create a virtual environment and activate it.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Boot up the Uvicorn server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 7860
   ```

---

## 📡 API Endpoints 

Interactive Swagger docs are available automatically at `http://localhost:7860/docs` while the server is running.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks` | `GET` | Retrieve a list of available incident tasks (`easy`, `medium`, `hard`). |
| `/state` | `GET` | Get the internal state of the environment (Admin/Debug only). |
| `/reset` | `POST` | Initializes an incident task. Accepts `{"task_id": "..."}`. Returns the initial `Observation`. |
| `/step` | `POST` | Execute an action in the environment. Accepts `action_type` and `target_service`. Returns the updated `Observation`, the `reward`, and a `done` flag. |
| `/grader` | `POST` | Submits an agent's `trajectory` to be evaluated for a final efficiency score. |
| `/baseline` | `GET` | Triggers the built-in heuristic agent to solve all tasks and print the benchmarks. |

---

## 🤖 The Action Space (Agents)

When calling `POST /step`, agents must specify an `action_type` and a `target_service`. 

**Target Services:** `auth`, `payments`, `search`  

**Available Actions:**
* `restart_service`: Quickly drops load and fixes simple spikes, but fails to fix underlying database issues.
* `scale_up`: Buys time and reduces immediate load, but at a high cost penalty.
* `run_diagnostics`: Provides targeted log hints for a specific service.
* `ignore`: Does nothing. The system will continue to degrade.
* `escalate`: High cost penalty. Pings L3 support and auto-resolves the incident.

**Example Step Payload:**
```json
{
  "action_type": "scale_up",
  "target_service": "search"
}
```

---

## 🗂 Project Structure

* `main.py` - FastAPI application configuration and REST endpoints.
* `env.py` - Core environment logic handling `reset`, `step` observation parsing, cascading failures, and reward distribution.
* `models.py` - Pydantic definitions for Type Safety and Schema representation.
* `tasks.py` - The initialization states for the `easy`, `medium`, and `hard` environments.
* `grader.py` - Evaluation logic to assess an agent's completion trajectory.
