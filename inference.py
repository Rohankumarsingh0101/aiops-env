"""
OpenEnv Inference Script — Autonomous Incident Commander (AIOps Environment)
Hybrid Agent v3: early cascade-triggered LLM + deterministic rule fallback.

Required env vars:
  API_BASE_URL  — base URL of the OpenAI-compatible API
  MODEL_NAME    — model identifier (e.g. "gpt-4o")
  HF_TOKEN      — API token (used as OpenAI API key)
  ENV_BASE_URL  — (optional) base URL of the deployed AIOps environment
"""

import os
import json
import requests
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE_URL = os.environ["API_BASE_URL"]
MODEL_NAME   = os.environ["MODEL_NAME"]
HF_TOKEN     = os.environ["HF_TOKEN"]
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "https://rs01019989-aiops.hf.space")

MAX_STEPS = 8
TASK_IDS  = ["easy", "medium", "hard"]
ENV_NAME  = "autonomous-incident-commander"
SERVICES  = ["auth", "payments", "search"]

client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

# ── Environment API ───────────────────────────────────────────────────────────
def env_reset(task_id: str) -> dict:
    r = requests.post(f"{ENV_BASE_URL}/reset", json={"task_id": task_id}, timeout=30)
    r.raise_for_status()
    return r.json()

def env_step(action_type: str, target_service: str) -> dict:
    r = requests.post(
        f"{ENV_BASE_URL}/step",
        json={"action_type": action_type, "target_service": target_service},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

# ── Early Cascade Detection ───────────────────────────────────────────────────
def should_use_llm(obs: dict, history: list[dict]) -> bool:
    """
    Return True immediately if cascade ambiguity is detected, OR if an
    action has been repeated 2+ times (loop guard).

    Cascade signals:
    1. Highest-error service has moderate CPU (<90) AND memory (<90)
       → high errors without extreme resource pressure = likely victim.
    2. Logs mention a DIFFERENT service than the highest-error one.
    3. Multiple services have non-zero errors simultaneously.
    """
    services = obs.get("services", {})
    logs     = obs.get("logs", [])
    if not services:
        return False

    # Loop guard: repeated action → force LLM
    action_counts: dict[str, int] = {}
    for h in history:
        key = f"{h['action']}/{h['service']}"
        action_counts[key] = action_counts.get(key, 0) + 1
    if any(v >= 2 for v in action_counts.values()):
        return True

    loudest = max(services, key=lambda s: services[s].get("metrics", {}).get("errors", 0))
    m       = services[loudest].get("metrics", {})

    # Signal 1: high errors but moderate resource pressure
    if m.get("errors", 0) > 30 and m.get("cpu", 0) < 90 and m.get("memory", 0) < 90:
        return True

    # Signal 2: logs mention a different service
    logs_text = " ".join(logs).lower()
    for svc in SERVICES:
        if svc != loudest and svc in logs_text:
            return True

    # Signal 3: multiple services have non-zero errors
    errored = [s for s in services if services[s].get("metrics", {}).get("errors", 0) > 0]
    if len(errored) > 1:
        return True

    return False

# ── LLM Reasoning ─────────────────────────────────────────────────────────────
def llm_action(obs: dict, history: list[dict]) -> tuple[str, str]:
    """
    SRE-focused prompt instructing the LLM to reason about root cause vs symptom.
    Returns (action_type, target_service).
    """
    services = obs.get("services", {})
    logs     = obs.get("logs", [])

    svc_lines = []
    for svc, data in services.items():
        m = data.get("metrics", {})
        svc_lines.append(
            f"  {svc}: status={data.get('status')}  "
            f"cpu={m.get('cpu')}%  memory={m.get('memory')}%  errors={m.get('errors')}"
        )

    history_lines = [
        f"  Step {i + 1}: {h['action']} on {h['service']} → reward={h['reward']}"
        for i, h in enumerate(history)
    ]

    prompt = f"""You are an SRE diagnosing a production outage.

Important:
* The service with the most errors may NOT be the root cause.
* Cascading failures are common in distributed systems.
* Identify the ROOT CAUSE, not just the loudest symptom.
* restart_service fixes: memory_leak, cpu_spike, db_connection_pool_exhausted
* scale_up fixes: cpu_spike only
* run_diagnostics: reveals root cause in logs, does NOT fix anything (use only once)
* escalate: partial relief only, does NOT resolve the incident

System state:
{chr(10).join(svc_lines)}

Recent logs:
{chr(10).join(f'  {l}' for l in logs[-6:])}

Actions taken so far:
{chr(10).join(history_lines) if history_lines else '  None yet'}

Think:
1. Which service is the root cause vs downstream victim?
2. What is the most efficient next action?

Respond ONLY in this exact format (no explanation, no JSON):
<action_type>/<service>

Example: restart_service/auth"""

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        text = resp.choices[0].message.content.strip().lower()
        # Strip markdown fences, quotes, extra whitespace
        text = text.split("\n")[0].strip("`").strip('"').strip("'").strip()
        # Expected format: action_type/service  e.g. "restart_service/auth"
        if "/" in text:
            parts = text.split("/")
            action = parts[0].strip()
            service = parts[1].strip().split()[0]  # take first word in case of trailing text
            valid_actions  = {"restart_service", "scale_up", "run_diagnostics", "escalate", "ignore"}
            valid_services = {"auth", "payments", "search"}
            if action in valid_actions and service in valid_services:
                return action, service
    except Exception:
        pass

    # Fallback: target the degraded service with the most errors (most likely root cause)
    candidates = [
        (svc, data) for svc, data in services.items()
        if data.get("status") != "healthy"
    ]
    if candidates:
        root_suspect = max(candidates, key=lambda x: x[1].get("metrics", {}).get("errors", 0))
        return "restart_service", root_suspect[0]
    return "run_diagnostics", "auth"



# ── Rule Engine ───────────────────────────────────────────────────────────────
def rule_action(obs: dict, history: list[dict]) -> tuple[str, str]:
    """
    Deterministic metric-based rules for clear-cut cases only.
    Used when there is NO cascade ambiguity.
    """
    services  = obs.get("services", {})
    loudest   = max(services, key=lambda s: services[s].get("metrics", {}).get("errors", 0))
    m         = services[loudest].get("metrics", {})
    last_act  = history[-1]["action"] if history else None

    if m.get("memory", 0) > 90:
        return "restart_service", loudest
    if m.get("cpu", 0) > 85:
        return "scale_up", loudest
    if m.get("errors", 0) > 100:
        return "escalate", loudest
    if last_act != "run_diagnostics":
        return "run_diagnostics", loudest
    return "restart_service", loudest


# ── Task Runner ───────────────────────────────────────────────────────────────
def run_task(task_id: str) -> dict:
    obs     = env_reset(task_id)
    done    = False
    step    = 0
    score   = 0.0
    rewards = []
    history: list[dict] = []

    print(f"[START] task={task_id} env={ENV_NAME} model={MODEL_NAME}")

    while not done and step < MAX_STEPS:
        use_llm = should_use_llm(obs, history)

        if use_llm:
            action_type, target_service = llm_action(obs, history)
            source = "llm"
        else:
            action_type, target_service = rule_action(obs, history)
            source = "rules"

        error_flag = "none"
        try:
            result = env_step(action_type, target_service)
        except Exception as e:
            error_flag = str(e)[:40]
            print(
                f"[STEP] step={step + 1} action={action_type}/{target_service} "
                f"reward=0.00 done=false error={error_flag}"
            )
            break

        obs    = result.get("observation", obs)
        reward = result.get("reward", 0.0)
        done   = result.get("done", False)
        step  += 1
        score += reward
        rewards.append(round(reward, 2))
        history.append({"action": action_type, "service": target_service, "reward": round(reward, 2)})

        print(
            f"[STEP] step={step} action={action_type}/{target_service} "
            f"reward={round(reward, 2)} done={str(done).lower()} error={error_flag}"
        )

    success = done and all(
        svc.get("status") == "healthy"
        for svc in obs.get("services", {}).values()
    )

    rewards_str = ",".join(str(r) for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={step} "
        f"score={round(score, 4)} rewards={rewards_str}"
    )

    return {"task_id": task_id, "success": success, "steps": step, "score": score}


def main():
    results = [run_task(tid) for tid in TASK_IDS]
    avg = sum(r["score"] for r in results) / len(results)
    print(f"\nFinal average score: {round(avg, 4)}")


if __name__ == "__main__":
    main()
