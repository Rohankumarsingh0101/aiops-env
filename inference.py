"""
OpenEnv Inference Script — Autonomous Incident Commander (AIOps Environment)
Hybrid Agent v2: cascade-aware rule engine + context-rich LLM reasoning.

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

# ── Cascade Detection ─────────────────────────────────────────────────────────
def detect_cascade_suspect(obs: dict) -> str | None:
    """
    Heuristic: if the loudest service has very high errors but its logs 
    or another service's logs mention a different service, that other 
    service is likely the root cause.

    Checks for:
    1. Log cross-references — logs mention a different service than the max-error one.
    2. Discrepancy — service has very high errors but its own CPU/memory are not extreme
       (suggesting it's reacting to an upstream failure, not causing one).
    """
    services = obs.get("services", {})
    logs     = obs.get("logs", [])
    if not services:
        return None

    # Loudest visible service (most errors)
    loudest = max(services, key=lambda s: services[s].get("metrics", {}).get("errors", 0))
    loudest_metrics = services[loudest].get("metrics", {})

    # Discrepancy check: high errors but CPU and memory are moderate
    high_errors    = loudest_metrics.get("errors", 0) > 50
    moderate_cpu   = loudest_metrics.get("cpu", 0) < 70
    moderate_mem   = loudest_metrics.get("memory", 0) < 80
    looks_like_victim = high_errors and moderate_cpu and moderate_mem

    # Log cross-reference: find mentions of OTHER services in the logs
    logs_text = " ".join(logs).lower()
    for svc in SERVICES:
        if svc != loudest and svc in logs_text:
            if looks_like_victim:
                return svc   # Another service is mentioned AND loudest looks like victim

    # Also: if another service is degraded with fewer errors, it may hold the root cause
    for svc, data in services.items():
        if svc == loudest:
            continue
        if data.get("status") in ("degraded", "down"):
            if data.get("metrics", {}).get("errors", 0) > 0:
                return svc

    return None


# ── Rule Engine ───────────────────────────────────────────────────────────────
def rule_action(obs: dict, history: list[dict], force_llm: bool) -> tuple[str, str, str]:
    """
    Returns (action_type, target_service, source).
    source is one of: 'rules', 'cascade', 'diversity', 'llm'.
    """
    services = obs.get("services", {})

    # Build repeat counters from history
    action_counts: dict[str, int] = {}
    for h in history:
        key = f"{h['action']}/{h['service']}"
        action_counts[key] = action_counts.get(key, 0) + 1

    # Check if any action has been repeated 2+ times → force LLM
    if any(v >= 2 for v in action_counts.values()) or force_llm:
        return (*llm_action(obs, history), "llm")

    # Cascade detection: is the loudest service actually a victim?
    cascade_suspect = detect_cascade_suspect(obs)
    if cascade_suspect:
        svc_data = services.get(cascade_suspect, {})
        metrics  = svc_data.get("metrics", {})
        # Choose action for the suspected root-cause service
        if metrics.get("memory", 0) > 70 or metrics.get("cpu", 0) > 50:
            return "restart_service", cascade_suspect, "cascade"
        return "run_diagnostics", cascade_suspect, "cascade"

    # Standard metric-based rules on highest-error service
    loudest = max(services, key=lambda s: services[s].get("metrics", {}).get("errors", 0))
    metrics = services[loudest].get("metrics", {})
    cpu    = metrics.get("cpu", 0)
    memory = metrics.get("memory", 0)
    errors = metrics.get("errors", 0)

    last_action = history[-1]["action"] if history else None
    last_svc    = history[-1]["service"] if history else None

    if errors > 100:
        action = "escalate"
    elif memory > 90:
        action = "restart_service"
    elif cpu > 85:
        action = "scale_up"
    else:
        action = "run_diagnostics" if last_action != "run_diagnostics" else "restart_service"

    # Action diversity guard: if we're repeating same action/service, try something different
    proposed_key = f"{action}/{loudest}"
    if action_counts.get(proposed_key, 0) >= 1:
        alternatives = [s for s in SERVICES if s != loudest]
        # Pick the next highest-error service
        alt_svc = max(alternatives, key=lambda s: services.get(s, {}).get("metrics", {}).get("errors", 0))
        return "run_diagnostics", alt_svc, "diversity"

    return action, loudest, "rules"


# ── LLM Reasoning ─────────────────────────────────────────────────────────────
def llm_action(obs: dict, history: list[dict]) -> tuple[str, str]:
    """
    Context-rich LLM prompt. Includes full history, explicit cascade reasoning,
    and instruction to respond with action_type/service only.
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

    history_lines = []
    for i, h in enumerate(history, 1):
        history_lines.append(f"  Step {i}: {h['action']} on {h['service']} → reward={h['reward']}")

    prompt = f"""You are an SRE diagnosing a production outage.

Rules:
- High errors may be a symptom, not the root cause
- Cascading failures are common: auth issues often cause payments failures  
- Do not repeatedly act on the same service unless you are certain it is the root cause
- run_diagnostics reveals hidden root causes but does not fix anything
- restart_service fixes memory_leak, cpu_spike, and db_connection_pool issues
- scale_up fixes cpu_spike only

Current system state:
{chr(10).join(svc_lines)}

Recent logs:
{chr(10).join(f'  {l}' for l in logs[-6:])}

Actions taken so far:
{chr(10).join(history_lines) if history_lines else '  None'}

Question: Is the service with the most errors the ROOT CAUSE or a DOWNSTREAM SYMPTOM?
If symptom, target the service mentioned in logs or the degraded service with fewer errors.
If root cause, act on it directly.

Respond with ONLY this JSON (no explanation):
{{"action_type": "<restart_service|scale_up|run_diagnostics|escalate|ignore>", "target_service": "<auth|payments|search>"}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=80,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        parsed = json.loads(text)
        return parsed["action_type"], parsed["target_service"]
    except Exception:
        # Safe fallback: diagnose the quietest non-healthy service
        for svc, data in services.items():
            if data.get("status") != "healthy":
                return "run_diagnostics", svc
        return "run_diagnostics", "auth"


# ── Task Runner ───────────────────────────────────────────────────────────────
def run_task(task_id: str) -> dict:
    obs     = env_reset(task_id)
    done    = False
    step    = 0
    score   = 0.0
    rewards = []
    history: list[dict] = []   # [{action, service, reward}]

    print(f"[START] task={task_id} env={ENV_NAME} model={MODEL_NAME}")

    while not done and step < MAX_STEPS:
        # Determine if we need to force LLM (same action repeated 2x)
        action_counts: dict[str, int] = {}
        for h in history:
            key = f"{h['action']}/{h['service']}"
            action_counts[key] = action_counts.get(key, 0) + 1
        force_llm = any(v >= 2 for v in action_counts.values())

        action_type, target_service, source = rule_action(obs, history, force_llm)
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
