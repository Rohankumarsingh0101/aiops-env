"""
OpenEnv Inference Script — Autonomous Incident Commander (AIOps Environment)
Hybrid Agent: deterministic rule engine + LLM fallback for ambiguous situations.

Required env vars:
  API_BASE_URL  — base URL of the OpenAI-compatible API
  MODEL_NAME    — model identifier (e.g. "gpt-4o")
  HF_TOKEN      — Hugging Face / API token
  ENV_BASE_URL  — (optional) base URL of the deployed AIOps environment
"""

import os
import json
import requests
from openai import OpenAI

# ── Credentials (env vars ONLY) ───────────────────────────────────────────────
API_BASE_URL = os.environ["API_BASE_URL"]
MODEL_NAME   = os.environ["MODEL_NAME"]
HF_TOKEN     = os.environ["HF_TOKEN"]
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "https://rs01019989-aiops.hf.space")

MAX_STEPS  = 8
TASK_IDS   = ["easy", "medium", "hard"]
ENV_NAME   = "autonomous-incident-commander"

client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

# ── Environment API helpers ───────────────────────────────────────────────────
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

# ── Rule-based decision engine ────────────────────────────────────────────────
def rule_based_action(obs: dict, last_action: str | None) -> tuple[str, str] | None:
    """
    Deterministic rules over service metrics.
    Returns (action_type, target_service) or None if ambiguous.
    Priority: errors → memory → cpu → diagnostics (if not repeated).
    Target is always the critical_service from the response info if available,
    otherwise the service with the highest error count.
    """
    services = obs.get("services", {})
    if not services:
        return None

    # Pick the most critical service (highest errors)
    critical_svc = max(services, key=lambda s: services[s].get("metrics", {}).get("errors", 0))
    metrics = services[critical_svc].get("metrics", {})
    cpu     = metrics.get("cpu", 0)
    memory  = metrics.get("memory", 0)
    errors  = metrics.get("errors", 0)

    # Check if all services are healthy (should not happen mid-episode, but guard)
    all_healthy = all(
        s.get("status") == "healthy"
        for s in services.values()
    )
    if all_healthy:
        return None

    # Deterministic priority-based rule engine
    if errors > 100:
        action = "escalate"
    elif memory > 90:
        action = "restart_service"
    elif cpu > 85:
        action = "scale_up"
    else:
        # Avoid repeating run_diagnostics immediately
        if last_action == "run_diagnostics":
            action = "restart_service"   # escalate out of diagnostic loop
        else:
            action = "run_diagnostics"

    return action, critical_svc


def _is_ambiguous(obs: dict) -> bool:
    """Return True if no clear dominant signal is present."""
    services = obs.get("services", {})
    for svc in services.values():
        m = svc.get("metrics", {})
        if m.get("errors", 0) > 100 or m.get("memory", 0) > 90 or m.get("cpu", 0) > 85:
            return False
    return True


# ── LLM fallback ─────────────────────────────────────────────────────────────
def llm_action(obs: dict) -> tuple[str, str]:
    """Ask the LLM only when the signal is ambiguous. Returns (action, service)."""
    services = obs.get("services", {})
    logs     = obs.get("logs", [])
    lines = [
        "You are an on-call SRE agent. Choose ONE action to resolve the incident.",
        "Service metrics:",
    ]
    for svc, data in services.items():
        m = data.get("metrics", {})
        lines.append(
            f"  {svc}: status={data.get('status')}  "
            f"cpu={m.get('cpu')}%  memory={m.get('memory')}%  errors={m.get('errors')}"
        )
    lines += ["Recent logs:"] + [f"  {l}" for l in logs[-4:]]
    lines += [
        'Reply ONLY with JSON: {"action_type": "<restart_service|scale_up|run_diagnostics|escalate|ignore>",',
        '                       "target_service": "<auth|payments|search>"}',
    ]
    prompt = "\n".join(lines)

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=64,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        parsed = json.loads(text)
        return parsed["action_type"], parsed["target_service"]
    except Exception:
        # Safe default — diagnostics on the most errored service
        services = obs.get("services", {})
        fallback_svc = max(services, key=lambda s: services[s].get("metrics", {}).get("errors", 0))
        return "run_diagnostics", fallback_svc


# ── Task runner ───────────────────────────────────────────────────────────────
def run_task(task_id: str) -> dict:
    obs        = env_reset(task_id)
    done       = False
    step       = 0
    total_score = 0.0
    rewards    = []
    last_action = None

    print(f"[START] task={task_id} env={ENV_NAME} model={MODEL_NAME}")

    while not done and step < MAX_STEPS:
        # Decision: rule engine first, LLM only if ambiguous
        rule_result = rule_based_action(obs, last_action)
        if rule_result and not _is_ambiguous(obs):
            action_type, target_service = rule_result
            source = "rules"
        else:
            action_type, target_service = llm_action(obs)
            source = "llm"

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

        obs     = result.get("observation", obs)
        reward  = result.get("reward", 0.0)
        done    = result.get("done", False)
        step   += 1
        total_score += reward
        rewards.append(round(reward, 2))
        last_action = action_type

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
        f"score={round(total_score, 4)} rewards={rewards_str}"
    )

    return {
        "task_id":  task_id,
        "success":  success,
        "steps":    step,
        "score":    total_score,
        "rewards":  rewards,
    }


def main():
    results  = [run_task(tid) for tid in TASK_IDS]
    avg      = sum(r["score"] for r in results) / len(results)
    print(f"\nFinal average score: {round(avg, 4)}")


if __name__ == "__main__":
    main()
