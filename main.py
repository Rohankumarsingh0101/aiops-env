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

            response = env.step(Action(**action_dict))
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
        <html><head><title>AIOps Incident Commander</title>
        <meta charset="utf-8">
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body { font-family: 'Segoe UI', system-ui, sans-serif; background:#0a0a0f; color:#e2e8f0; min-height:100vh; }
            .hero { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%); padding:3rem 2rem 2rem; border-bottom:1px solid #1e293b; }
            .hero h1 { font-size:2rem; color:#f97316; margin-bottom:0.3rem; }
            .hero h1 span { color:#60a5fa; }
            .badge { display:inline-block; background:#1e293b; color:#94a3b8; padding:0.15rem 0.5rem; border-radius:4px; font-size:0.75rem; margin-left:0.5rem; }
            .badge.ver { color:#22c55e; }
            .hero p { color:#94a3b8; font-size:0.95rem; max-width:700px; line-height:1.5; margin-top:0.5rem; }
            .content { max-width:900px; margin:0 auto; padding:2rem; }
            .grid { display:grid; grid-template-columns:1fr 1fr; gap:1.2rem; margin:1.5rem 0; }
            .card { background:#111827; border:1px solid #1f2937; border-radius:8px; padding:1.2rem; }
            .card h3 { color:#f97316; font-size:0.9rem; margin-bottom:0.6rem; letter-spacing:0.5px; text-transform:uppercase; }
            .card ul { list-style:none; }
            .card li { padding:0.3rem 0; color:#cbd5e1; font-size:0.85rem; border-bottom:1px solid #1f2937; }
            .card li:last-child { border:none; }
            .card li code { color:#60a5fa; background:#0f172a; padding:0.1rem 0.4rem; border-radius:3px; font-size:0.8rem; }
            .feat { display:flex; gap:0.5rem; align-items:baseline; }
            .feat .dot { color:#22c55e; font-weight:700; }
            .diff { display:inline-block; padding:0.15rem 0.5rem; border-radius:12px; font-size:0.7rem; font-weight:600; margin-left:0.3rem; }
            .diff.easy { background:#064e3b; color:#34d399; }
            .diff.med  { background:#713f12; color:#fbbf24; }
            .diff.hard { background:#7f1d1d; color:#f87171; }
            .actions { display:flex; gap:1rem; margin:1.5rem 0; }
            .btn { display:inline-block; padding:0.7rem 1.5rem; border-radius:6px; text-decoration:none; font-weight:600; font-size:0.9rem; }
            .btn.primary { background:#f97316; color:#fff; }
            .btn.secondary { background:#1e293b; color:#60a5fa; border:1px solid #334155; }
            .btn:hover { opacity:0.9; }
            .quick { background:#111827; border:1px solid #1f2937; border-radius:8px; padding:1.2rem; margin:1.5rem 0; }
            .quick h3 { color:#f97316; font-size:0.9rem; margin-bottom:0.8rem; text-transform:uppercase; letter-spacing:0.5px; }
            .quick pre { background:#0a0a0f; padding:0.8rem 1rem; border-radius:6px; overflow-x:auto; font-size:0.8rem; color:#a5b4fc; line-height:1.6; }
            .footer { color:#475569; font-size:0.75rem; text-align:center; padding:1.5rem; border-top:1px solid #1e293b; }
            .footer a { color:#60a5fa; text-decoration:none; }
        </style>
        </head><body>
        <div class="hero">
            <h1>🚨 AIOps <span>Incident Commander</span> <span class="badge ver">v1.1.0</span></h1>
            <p>A deterministic OpenEnv-compatible reinforcement learning environment where AI agents act as on-call SREs to diagnose and resolve production incidents across distributed microservices.</p>
        </div>
        <div class="content">
            <div class="actions">
                <a href="/docs" class="btn primary">📄 API Documentation</a>
                <a href="/tasks" class="btn secondary">📋 View Tasks</a>
                <a href="/health" class="btn secondary">💚 Health Check</a>
            </div>

            <div class="grid">
                <div class="card">
                    <h3>🏗️ Environment Features</h3>
                    <ul>
                        <li><span class="feat"><span class="dot">✓</span> Cascading failure propagation</span></li>
                        <li><span class="feat"><span class="dot">✓</span> Partial observability (hidden root cause)</span></li>
                        <li><span class="feat"><span class="dot">✓</span> Deceptive metrics (symptom vs root cause)</span></li>
                        <li><span class="feat"><span class="dot">✓</span> Dense reward signal every step</span></li>
                        <li><span class="feat"><span class="dot">✓</span> Fully deterministic transitions</span></li>
                    </ul>
                </div>
                <div class="card">
                    <h3>🎯 Task Difficulty</h3>
                    <ul>
                        <li><code>easy</code> <span class="diff easy">EASY</span> — single service CPU spike</li>
                        <li><code>medium</code> <span class="diff med">MEDIUM</span> — auth→payments cascade</li>
                        <li><code>hard</code> <span class="diff hard">HARD</span> — deceptive signal conflict</li>
                    </ul>
                    <br>
                    <h3>⚡ Available Actions</h3>
                    <ul>
                        <li><code>restart_service</code> — fixes leaks, spikes, db issues</li>
                        <li><code>scale_up</code> — reduces CPU load</li>
                        <li><code>run_diagnostics</code> — reveals root cause</li>
                        <li><code>escalate</code> — partial relief only</li>
                        <li><code>ignore</code> — no action (penalty)</li>
                    </ul>
                </div>
            </div>

            <div class="quick">
                <h3>⚡ Quick Start</h3>
                <pre>
# 1. Reset environment with a task
curl -X POST /reset -H "Content-Type: application/json" \\
     -d '{"task_id": "easy"}'

# 2. Take an action
curl -X POST /step -H "Content-Type: application/json" \\
     -d '{"action_type": "scale_up", "target_service": "search"}'

# 3. Check current state
curl -X GET /state</pre>
            </div>

            <div class="grid">
                <div class="card">
                    <h3>📡 API Endpoints</h3>
                    <ul>
                        <li><code>POST /reset</code> — start a new episode</li>
                        <li><code>POST /step</code> — take an action</li>
                        <li><code>GET  /state</code> — full environment state</li>
                        <li><code>POST /grader</code> — grade a trajectory</li>
                        <li><code>GET  /tasks</code> — list available tasks</li>
                        <li><code>GET  /health</code> — liveness probe</li>
                    </ul>
                </div>
                <div class="card">
                    <h3>🏢 Architecture</h3>
                    <ul>
                        <li><span class="feat"><span class="dot">›</span> 3 microservices: auth, payments, search</span></li>
                        <li><span class="feat"><span class="dot">›</span> Pydantic-typed actions &amp; observations</span></li>
                        <li><span class="feat"><span class="dot">›</span> Grader with efficiency penalties</span></li>
                        <li><span class="feat"><span class="dot">›</span> OpenEnv spec compliant</span></li>
                        <li><span class="feat"><span class="dot">›</span> Docker + HF Spaces deployment</span></li>
                    </ul>
                </div>
            </div>
        </div>
        <div class="footer">
            Autonomous Incident Commander v1.1.0 · OpenEnv Compatible · <a href="/docs">Swagger Docs</a>
        </div>
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
