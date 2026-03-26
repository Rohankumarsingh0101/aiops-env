from models import EnvState, Observation, StepResponse, Action, ActionType, ServiceName, ServiceStatus
from tasks import TASKS
import copy

class CommanderEnv:
    def __init__(self):
        self.state_data: EnvState = None
    
    def reset(self, task_id: str) -> Observation:
        if task_id not in TASKS:
            raise ValueError(f"Task {task_id} not found")
        
        # Deep copy to ensure we don't modify the original task definition
        self.state_data = copy.deepcopy(TASKS[task_id]())
        return self._get_observation()
    
    def state(self) -> EnvState:
        return self.state_data

    def _get_observation(self) -> Observation:
        obs_services = {}
        for s_name, s_state in self.state_data.services.items():
            obs_services[s_name.value] = {
                "status": s_state.status.value,
                "metrics": s_state.metrics.model_dump()
            }
        
        return Observation(
            services=obs_services,
            logs=self.state_data.logs.copy(),
            severity=self.state_data.severity,
            time_elapsed=self.state_data.time_elapsed
        )

    def step(self, action_dict: dict) -> StepResponse:
        if not self.state_data:
            raise RuntimeError("Environment must be reset before stepping")
            
        action = Action(**action_dict)
        target = self.state_data.services[action.target_service]
        
        reward = 0.0
        reward -= 0.05 # Time penalty per step
        
        # Track if action was helpful
        action_correct = False
        
        # Logs to add this turn
        new_logs = []
        
        if action.action_type == ActionType.restart_service:
            reward -= 0.05 # Low cost
            if target.root_cause in ["memory_leak", "cpu_spike", "db_connection_pool_exhausted"]:
                action_correct = True
                target.root_cause = None
                target.status = ServiceStatus.healthy
                target.metrics.cpu = 30.0
                target.metrics.memory = 30.0
                target.metrics.errors = 0
                new_logs.append(f"Restarted {action.target_service}. Metrics stabilized.")
            else:
                target.metrics.cpu = 30.0
                target.metrics.memory = 30.0
                target.metrics.errors = 0
                new_logs.append(f"Restarted {action.target_service}. No underlying issue fixed.")
                
        elif action.action_type == ActionType.scale_up:
            reward -= 0.1 # Medium cost
            if target.root_cause == "cpu_spike":
                action_correct = True
                target.root_cause = None
                target.status = ServiceStatus.healthy
                target.metrics.cpu = 40.0
                new_logs.append(f"Scaled up {action.target_service}. CPU load normalized.")
            else:
                # Still reduces load slightly but doesn't fix memory leaks/exhausted pools forever
                target.metrics.cpu = max(10, target.metrics.cpu - 30.0)
                new_logs.append(f"Scaled up {action.target_service}. Temporary relief.")
                
        elif action.action_type == ActionType.run_diagnostics:
            reward -= 0.02 # Tiny cost
            if target.root_cause:
                if target.root_cause == "cpu_spike":
                    new_logs.append(f"Diagnostics on {action.target_service}: CPU usage anomalous.")
                elif target.root_cause == "memory_leak":
                    new_logs.append(f"Diagnostics on {action.target_service}: Memory footprint growing linearly. Suggests leak.")
                elif target.root_cause == "db_connection_pool_exhausted":
                    new_logs.append(f"Diagnostics on {action.target_service}: 100% DB connections active. Pool exhausted.")
                action_correct = True # Valid analytical move
            else:
                new_logs.append(f"Diagnostics on {action.target_service}: Service functioning within normal parameters.")

        elif action.action_type == ActionType.ignore:
            reward -= 0.0 # No action cost, but wrong
            new_logs.append(f"Ignored alerts on {action.target_service}.")

        elif action.action_type == ActionType.escalate:
            reward -= 0.3 # High cost
            new_logs.append(f"Escalated incident to L3. Manual intervention triggered.")
            # Auto-resolves everything
            for s in self.state_data.services.values():
                s.root_cause = None
                s.status = ServiceStatus.healthy
                s.metrics.cpu = 30.0
                s.metrics.memory = 30.0
                s.metrics.errors = 0
            action_correct = True

        # Correctness reward
        if action_correct:
            reward += 0.2
        elif action.action_type not in [ActionType.run_diagnostics, ActionType.escalate]:
            reward -= 0.2
            
        # Cascading failures and degradation
        for s_name, s in self.state_data.services.items():
            if s.root_cause:
                s.metrics.cpu = min(100.0, s.metrics.cpu + 15.0)
                s.metrics.memory = min(100.0, s.metrics.memory + 15.0)
                s.metrics.errors += 20
                if s.metrics.cpu > 80 or s.metrics.memory > 80 or s.metrics.errors > 100:
                    s.status = ServiceStatus.degraded
                if s.metrics.cpu == 100.0 and s.metrics.memory == 100.0:
                    s.status = ServiceStatus.down

        # Cascade auth -> payments
        auth = self.state_data.services[ServiceName.auth]
        pay = self.state_data.services[ServiceName.payments]
        if auth.status != ServiceStatus.healthy and not pay.root_cause:
            pay.metrics.errors += auth.metrics.errors // 2
            if pay.metrics.errors > 50:
                pay.status = ServiceStatus.degraded
                new_logs.append("Warning: Initial cascade detected from Auth to Payments.")

        # Update severity
        degraded = sum(1 for s in self.state_data.services.values() if s.status != ServiceStatus.healthy)
        self.state_data.severity = min(5, max(1, degraded + 1))
        
        # Check resolved
        all_fixed = all(s.status == ServiceStatus.healthy and not s.root_cause for s in self.state_data.services.values())
        if all_fixed and not self.state_data.resolved:
            self.state_data.resolved = True
            reward += 1.0
            new_logs.append("Incident resolved successfully.")

        # Update state logs with only the fresh ones
        self.state_data.logs = new_logs
        
        self.state_data.time_elapsed += 1
        self.state_data.steps_taken += 1
        
        # Done condition
        done = self.state_data.resolved or self.state_data.steps_taken >= 10
        
        # Clamp reward 0 to 1
        reward = max(0.0, min(1.0, reward))
        
        return StepResponse(
            observation=self._get_observation(),
            reward=reward,
            done=done,
            info={"action_correct": action_correct}
        )
