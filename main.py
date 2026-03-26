from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from env import CommanderEnv
from models import Action, EnvState, Observation, StepResponse
from tasks import TASKS
from grader import grade

app = FastAPI(title="Autonomous Incident Commander (AIOps Environment)")
env = CommanderEnv()

class ResetRequest(BaseModel):
    task_id: str

class GraderRequest(BaseModel):
    task_id: str
    trajectory: List[Dict[str, Any]]

@app.post("/reset", response_model=Observation)
def reset_env(request: ResetRequest):
    try:
        obs = env.reset(request.task_id)
        return obs
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/step", response_model=StepResponse)
def step_env(action: dict):
    try:
        response = env.step(action)
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/state", response_model=EnvState)
def get_state():
    state = env.state()
    if not state:
        raise HTTPException(status_code=400, detail="Environment not initialized. Call /reset first.")
    return state

@app.get("/tasks")
def get_tasks():
    return {"tasks": list(TASKS.keys())}

@app.post("/grader")
def grade_trajectory(request: GraderRequest):
    if request.task_id not in TASKS:
        raise HTTPException(status_code=400, detail=f"Task {request.task_id} not found.")
    score = grade(request.task_id, request.trajectory)
    return {"task_id": request.task_id, "score": score}

@app.get("/baseline")
def run_baseline():
    """ Runs a simple rule-based agent on all tasks and returns scores. """
    results = {}
    total_score = 0.0
    
    print("--- Running Baseline Agent ---")
    
    for task_id in TASKS.keys():
        obs = env.reset(task_id)
        done = False
        trajectory = []
        
        for _ in range(10):
            if done:
                break
                
            # Baseline heuristic: find any degraded/down service
            target_service = None
            for s_name, s_data in obs.services.items():
                if s_data["status"] != "healthy":
                    target_service = s_name
                    break
            
            if not target_service:
                target_service = "auth"
            
            # Action logic based on metrics
            action_type = "run_diagnostics"
            metrics = obs.services[target_service]["metrics"]
            
            if metrics["cpu"] > 80.0:
                action_type = "scale_up"
            if metrics["memory"] > 80.0:
                action_type = "restart_service"
            if metrics["errors"] > 50:
                action_type = "restart_service"
                
            # Fallback for hard task (escalate if it takes too long)
            if len(trajectory) >= 6:
                action_type = "escalate"
                
            action_dict = {
                "action_type": action_type,
                "target_service": target_service
            }
            
            response = env.step(action_dict)
            trajectory.append({
                "action": action_dict,
                "response": response.model_dump()
            })
            
            obs = response.observation
            done = response.done
            
        score = grade(task_id, trajectory)
        results[task_id] = {
            "score": score,
            "steps": len(trajectory)
        }
        total_score += score
        
        print(f"Task: {task_id} | Score: {score:.2f} | Steps: {len(trajectory)}")
        
    avg_score = total_score / len(TASKS)
    print(f"Average Score: {avg_score:.2f}")
    print("------------------------------")
    
    results["average_score"] = avg_score
    return results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
