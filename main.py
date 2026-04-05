from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Any

from env import CommanderEnv, get_critical_service
from models import Action, EnvState, Observation, StepResponse
from tasks import TASKS
from grader import grade

app = FastAPI(
    title="Autonomous Incident Commander (AIOps Environment)",
    description="OpenEnv-compatible AIOps RL environment simulating real-world SRE incident response.",
    version="1.1.0"
)
env = CommanderEnv()

class ResetRequest(BaseModel):
    task_id: str

class GraderRequest(BaseModel):
    task_id: str
    trajectory: List[Dict[str, Any]]


@app.get("/health")
def health_check():
    """Simple health probe — confirms the server is running."""
    return {"status": "ok"}


@app.post("/reset", response_model=Observation)
def reset_env(request: ResetRequest):
    try:
        obs = env.reset(request.task_id)
        return obs
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/step", response_model=StepResponse)
def step_env(action: Action):
    try:
        response = env.step(action.model_dump())
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
        raise HTTPException(status_code=400, detail=f"Task '{request.task_id}' not found.")
    score = grade(request.task_id, request.trajectory)
    return {"task_id": request.task_id, "score": score}


@app.get("/baseline")
def run_baseline():
    """Runs an improved rule-based agent on all tasks and returns scores."""
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

            # Find the service with the most errors (highest priority)
            target_service = max(
                obs.services,
                key=lambda s: obs.services[s]["metrics"]["errors"]
            )

            metrics = obs.services[target_service]["metrics"]

            # Priority: high errors → restart, high CPU → scale_up, else → diagnostics
            if metrics["errors"] > 30:
                action_type = "restart_service"
            elif metrics["cpu"] > 80:
                action_type = "scale_up"
            else:
                action_type = "run_diagnostics"

            # Fallback: escalate if stuck
            if len(trajectory) >= 6:
                action_type = "escalate"

            action_dict = {
                "action_type": action_type,
                "target_service": target_service
            }

            step_num = len(trajectory) + 1
            print(f"  Step {step_num} -> {action_type} on {target_service}")

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

        print(f"Task: {task_id} | Score: {score:.3f} | Steps: {len(trajectory)}")

    avg_score = total_score / len(TASKS)
    print(f"Average Score: {avg_score:.3f}")
    print("------------------------------")

    results["average_score"] = round(avg_score, 4)
    return results


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Minimal live dashboard — shows current environment state."""
    state = env.state()

    if not state:
        html = """
        <html><head><title>AIOps Dashboard</title>
        <style>body{font-family:monospace;background:#0f0f0f;color:#eee;padding:2rem;}</style>
        </head><body>
        <h1>🚨 AIOps Incident Commander</h1>
        <p style="color:#aaa">No active episode. Call <code>POST /reset</code> to initialize.</p>
        <p><a href="/docs" style="color:#4af">→ Open API Docs</a></p>
        </body></html>
        """
        return HTMLResponse(content=html)

    critical = get_critical_service(state)

    status_color = {"healthy": "#22c55e", "degraded": "#eab308", "down": "#ef4444"}

    rows = ""
    for svc_name, svc in state.services.items():
        color = status_color.get(svc.status.value, "#aaa")
        rows += f"""
        <tr>
            <td><b>{svc_name.value}</b></td>
            <td style="color:{color}">⬤ {svc.status.value}</td>
            <td>{svc.metrics.cpu:.1f}%</td>
            <td>{svc.metrics.memory:.1f}%</td>
            <td>{svc.metrics.errors}</td>
        </tr>"""

    logs_html = "".join(f"<li>{log}</li>" for log in state.logs)

    html = f"""
    <html>
    <head>
        <title>AIOps Dashboard</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{ font-family: 'Courier New', monospace; background: #0f0f0f; color: #e5e5e5; padding: 2rem; }}
            h1 {{ color: #f97316; }}
            table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
            th {{ background: #1f1f1f; color: #f97316; padding: 0.5rem 1rem; text-align: left; }}
            td {{ padding: 0.5rem 1rem; border-bottom: 1px solid #2a2a2a; }}
            .badge {{ background:#1e293b; padding:0.2rem 0.6rem; border-radius:4px; font-size:0.85rem; }}
            .critical {{ color: #ef4444; font-weight: bold; }}
            ul {{ background:#1a1a1a; padding: 1rem 1.5rem; border-radius:6px; }}
            li {{ margin: 0.3rem 0; font-size: 0.9rem; color: #94a3b8; }}
            a {{ color: #60a5fa; }}
        </style>
    </head>
    <body>
        <h1>🚨 AIOps Incident Commander</h1>
        <p>Task: <span class="badge">{state.task_id}</span> &nbsp;
           Severity: <span class="badge">{state.severity}</span> &nbsp;
           Steps: <span class="badge">{state.time_elapsed}</span> &nbsp;
           Resolved: <span class="badge">{'✅ Yes' if state.resolved else '❌ No'}</span>
        </p>
        <p>🔴 Critical service: <span class="critical">{critical}</span></p>

        <table>
            <tr><th>Service</th><th>Status</th><th>CPU</th><th>Memory</th><th>Errors</th></tr>
            {rows}
        </table>

        <h3>📋 Logs</h3>
        <ul>{logs_html}</ul>

        <h3>⚡ Available Actions</h3>
        <ul>
            <li><code>restart_service</code> — fixes memory_leak, cpu_spike, db issues</li>
            <li><code>scale_up</code> — reduces CPU load (resolves cpu_spike)</li>
            <li><code>run_diagnostics</code> — reveals root cause, no fix (penalty applies)</li>
            <li><code>ignore</code> — no action (penalty applies)</li>
            <li><code>escalate</code> — partial relief only (penalty applies)</li>
        </ul>
        <p style="color:#555;font-size:0.8rem">Auto-refreshes every 5s · <a href="/docs">API Docs</a> · <a href="/tasks">Tasks</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
