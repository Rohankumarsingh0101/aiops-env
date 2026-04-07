"""
OpenEnv Inference Script — Autonomous Incident Commander (AIOps Environment)

Runs an LLM agent against the AIOps environment via the OpenEnv evaluation pipeline.
Uses OpenAI-compatible API. All credentials are sourced from environment variables.

Required env vars:
  API_BASE_URL  — base URL of the OpenAI-compatible API
  MODEL_NAME    — model identifier (e.g. "gpt-4o", "llama-3-70b")
  HF_TOKEN      — Hugging Face token used to access the running Space

Logging format (required by OpenEnv evaluator):
  [START] task=... env=... model=...
  [STEP]  step=... action=... reward=... done=...
  [END]   success=... steps=... score=...
"""

import os
import json
import requests
from openai import OpenAI

# ── Config from environment (no hardcoded keys) ─────────────────────────────
API_BASE_URL = os.environ["API_BASE_URL"]
MODEL_NAME   = os.environ["MODEL_NAME"]
HF_TOKEN     = os.environ["HF_TOKEN"]

ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "https://rs01019989-aiops.hf.space")

MAX_STEPS  = 10          # hard cap — keeps runtime well under 20 min
TASK_IDS   = ["easy", "medium", "hard"]
ENV_NAME   = "autonomous-incident-commander"

# ── OpenAI-compatible client ─────────────────────────────────────────────────
client = OpenAI(
    base_url=API_BASE_URL,
    api_key=HF_TOKEN,
)

# ── Helpers ──────────────────────────────────────────────────────────────────
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

def build_prompt(obs: dict) -> str:
    services = obs.get("services", {})
    logs     = obs.get("logs", [])
    severity = obs.get("severity", "?")

    lines = [
        "You are an on-call SRE agent. Diagnose and resolve the current production incident.",
        f"Severity: {severity}",
        "",
        "Service metrics:",
    ]
    for svc, data in services.items():
        m = data.get("metrics", {})
        lines.append(
            f"  {svc}: status={data.get('status')}  cpu={m.get('cpu')}%  "
            f"memory={m.get('memory')}%  errors={m.get('errors')}"
        )
    lines += ["", "Recent logs:"] + [f"  {l}" for l in logs[-5:]]
    lines += [
        "",
        "Choose ONE action. Reply with a JSON object only, no extra text:",
        '{"action_type": "<restart_service|scale_up|run_diagnostics|escalate|ignore>",',
        ' "target_service": "<auth|payments|search>"}',
    ]
    return "\n".join(lines)

def ask_llm(obs: dict) -> dict:
    prompt = build_prompt(obs)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=128,
    )
    text = response.choices[0].message.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())

def run_task(task_id: str) -> dict:
    obs    = env_reset(task_id)
    done   = False
    step   = 0
    score  = 0.0

    print(f"[START] task={task_id} env={ENV_NAME} model={MODEL_NAME}")

    while not done and step < MAX_STEPS:
        try:
            action = ask_llm(obs)
        except Exception:
            # Fallback safe action if LLM response is malformed
            action = {"action_type": "run_diagnostics", "target_service": "auth"}

        action_type     = action.get("action_type", "run_diagnostics")
        target_service  = action.get("target_service", "auth")

        result   = env_step(action_type, target_service)
        obs      = result.get("observation", obs)
        reward   = result.get("reward", 0.0)
        done     = result.get("done", False)
        step    += 1
        score   += reward

        print(
            f"[STEP] step={step} action={action_type}/{target_service} "
            f"reward={reward} done={done}"
        )

    success = done and all(
        svc.get("status") == "healthy"
        for svc in obs.get("services", {}).values()
    )

    print(f"[END] success={success} steps={step} score={round(score, 4)}")

    return {"task_id": task_id, "success": success, "steps": step, "score": score}


def main():
    results = []
    for task_id in TASK_IDS:
        result = run_task(task_id)
        results.append(result)

    total_score = sum(r["score"] for r in results) / len(results)
    print(f"\nFinal average score: {round(total_score, 4)}")


if __name__ == "__main__":
    main()
