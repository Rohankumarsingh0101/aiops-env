from typing import List, Dict, Any
from models import ActionType

def _get_action_type(action: Any) -> str:
    """Safely extract action_type from either a dict or an object."""
    if isinstance(action, dict):
        return action.get("action_type", "")
    return getattr(action, "action_type", "")

def grade(task_id: str, trajectory: List[Dict[str, Any]]) -> float:
    """
    Grades a trajectory for a given task.
    Score based on:
    - whether the incident was resolved
    - number of steps taken
    - efficiency and cost of actions used

    Returns score strictly between 0.0 and 1.0 (exclusive).
    """
    if not trajectory:
        return 0.01

    final_step = trajectory[-1].get("response", {})
    final_obs = final_step.get("observation", {})

    # Determine resolved: all services must be healthy
    resolved = True
    services = final_obs.get("services", {})
    if not services:
        resolved = False
    else:
        for s_data in services.values():
            if s_data.get("status") != "healthy":
                resolved = False
                break

    # Cross-check with done flag for consistency
    done = final_step.get("done", False)
    if not done:
        resolved = False

    score = 0.0

    # 1. Incident Resolved (max 0.5)
    if resolved:
        score += 0.5

    # 2. Step efficiency (max 0.2): fewer steps = higher subscore
    steps = len(trajectory)
    step_score = max(0.0, 0.2 - ((steps - 1) * 0.022))
    score += step_score

    # 3. Action quality (max 0.3): penalise costly or wasteful actions
    efficiency_score = 0.3
    for step in trajectory:
        action = step.get("action", {})
        action_type = _get_action_type(action)

        if action_type == ActionType.escalate.value:
            efficiency_score -= 0.15
        elif action_type == ActionType.ignore.value:
            efficiency_score -= 0.10
        elif action_type == ActionType.run_diagnostics.value:
            efficiency_score -= 0.05   # wasted step
        elif action_type == ActionType.scale_up.value:
            efficiency_score -= 0.02   # minor cost

    efficiency_score = max(0.0, efficiency_score)
    score += efficiency_score

    # Spec requires score strictly in (0, 1) — never exactly 0.0 or 1.0
    return max(0.01, min(0.99, score))
