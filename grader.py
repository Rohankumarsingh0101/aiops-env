from typing import List, Dict, Any
from models import ActionType

def grade(task_id: str, trajectory: List[Dict[str, Any]]) -> float:
    """
    Grades a trajectory for a given task.
    Score based on:
    - whether incident was resolved
    - number of steps
    - efficiency of actions
    - unnecessary costly actions
    
    Returns score between 0.0 and 1.0.
    """
    if not trajectory:
        return 0.0
        
    final_step = trajectory[-1].get("response", {})
    final_obs = final_step.get("observation", {})
    
    # Heuristic for resolved: no degraded/down services
    resolved = True
    services = final_obs.get("services", {})
    if not services:
        resolved = False
    else:
        for s_name, s_data in services.items():
            if s_data.get("status") != "healthy":
                resolved = False
                break
                
    # Also check done flag
    done = final_step.get("done", False)
    if not done and not resolved:
        resolved = False
        
    score = 0.0
    
    # 1. Incident Resolved (max 0.5)
    if resolved:
        score += 0.5
        
    # 2. Number of steps (max 0.2)
    # 1 step = 0.2, 10 steps = 0.0
    steps = len(trajectory)
    step_score = max(0.0, 0.2 - ((steps - 1) * 0.022))
    score += step_score
    
    # 3. Efficiency & Cost (max 0.3)
    efficiency_score = 0.3
    for step in trajectory:
        action = step.get("action", {})
        action_type = action.get("action_type")
        
        # Penalize costly actions
        if action_type == ActionType.escalate.value:
            efficiency_score -= 0.15
        elif action_type == ActionType.scale_up.value:
            efficiency_score -= 0.05
        elif action_type == ActionType.ignore.value:
            efficiency_score -= 0.05
            
        # Penalize if action was completely wrong (reward clumped to 0 by env clamp)
        reward = step.get("response", {}).get("reward", 0.0)
        if reward == 0.0:
            efficiency_score -= 0.02
            
    efficiency_score = max(0.0, efficiency_score)
    score += efficiency_score
    
    return max(0.0, min(1.0, score))
