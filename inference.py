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
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME   = os.getenv("MODEL_NAME", "gpt-4o")
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

    prompt = f"""You are an SRE diagnosing a production outage. Choose the next action to resolve it.

Rules:
- The service with the most errors may be a DOWNSTREAM VICTIM, not the root cause
- Cascading failures: auth issues often cause payments failures
- restart_service: fixes memory_leak, cpu_spike, db_connection_pool_exhausted
- scale_up: fixes cpu_spike only (reduces CPU load)
- run_diagnostics: reveals hidden root cause — use ONLY if root cause is unclear
- Do NOT repeat the same action twice

System state:
{chr(10).join(svc_lines)}

Logs:
{chr(10).join(f'  {l}' for l in logs[-6:])}

Steps taken:
{chr(10).join(history_lines) if history_lines else '  None'}

Reply ONLY with JSON (no explanation):
{{"action_type": "restart_service|scale_up|run_diagnostics|escalate|ignore", "target_service": "auth|payments|search"}}"""

    valid_actions  = {"restart_service", "scale_up", "run_diagnostics", "escalate", "ignore"}
    valid_services = {"auth", "payments", "search"}

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=50,
        )
        text = resp.choices[0].message.content.strip()

        # Stage 1: JSON parse
        try:
            cleaned = text
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1].lstrip("json").strip()
            parsed  = json.loads(cleaned)
            action  = parsed.get("action_type", "").strip()
            service = parsed.get("target_service", "").strip()
            if action in valid_actions and service in valid_services:
                return action, service
        except (json.JSONDecodeError, AttributeError, KeyError):
            pass

        # Stage 2: slash format
        clean = text.lower().split("\n")[0].strip("`").strip('"').strip("'")
        if "/" in clean:
            parts   = clean.split("/")
            action  = parts[0].strip()
            service = parts[1].strip().split()[0]
            if action in valid_actions and service in valid_services:
                return action, service

    except Exception:
        pass

    # Fallback: restart the highest-error degraded service
    candidates = [
        (svc, data) for svc, data in services.items()
        if data.get("status") != "healthy"
    ]
    if candidates:
        top = max(candidates, key=lambda x: x[1].get("metrics", {}).get("errors", 0))
        return "restart_service", top[0]
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

        error_flag = "null"
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
            f"reward={reward:.2f} done={str(done).lower()} error={error_flag}"
        )

    success = done and all(
        svc.get("status") == "healthy"
        for svc in obs.get("services", {}).values()
    )

    # Normalize score to [0, 1] as required by OpenEnv spec
    normalized_score = round(min(1.0, score), 2)
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={step} "
        f"score={normalized_score} rewards={rewards_str}"
    )

    return {"task_id": task_id, "success": success, "steps": step, "score": score}


def main():
    results = [run_task(tid) for tid in TASK_IDS]
    avg = sum(r["score"] for r in results) / len(results)
    print(f"\nFinal average score: {round(avg, 4)}")


if __name__ == "__main__":
    main()
