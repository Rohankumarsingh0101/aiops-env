from models import EnvState, Observation, StepResponse, Action, ActionType, ServiceName, ServiceStatus
from tasks import TASKS
import copy

def calculate_health_score(state: EnvState) -> float:
    total_cpu = 0.0
    total_errors = 0
    num_services = len(state.services)
    
    if num_services == 0:
        return 1.0
        
    for s in state.services.values():
        total_cpu += s.metrics.cpu
        total_errors += s.metrics.errors
        
    avg_cpu = total_cpu / num_services
    
    health_score = (
        (100.0 - avg_cpu) / 100.0 +
        (100.0 - total_errors) / 100.0
    ) / 2.0
    
    return max(0.0, min(1.0, health_score))

def is_system_healthy(state: EnvState) -> bool:
    for s in state.services.values():
        if s.status != ServiceStatus.healthy or s.root_cause is not None:
            return False
    return True

def apply_action(state: EnvState, action: Action) -> list[str]:
    target = state.services[action.target_service]
    new_logs = []
    
    if action.action_type == ActionType.restart_service:
        if target.root_cause in ["memory_leak", "cpu_spike", "db_connection_pool_exhausted"]:
            target.root_cause = None
            target.status = ServiceStatus.healthy
            target.metrics.cpu = 30.0
            target.metrics.memory = 30.0
            target.metrics.errors = 0
            new_logs.append(f"Restarted {action.target_service}. Metrics stabilized.")
        else:
            target.metrics.cpu = 30.0
            target.metrics.memory = 30.0
            active_roots = sum(1 for s in state.services.values() if s.root_cause)
            if active_roots == 0:
                target.metrics.errors = 0
                new_logs.append(f"Restarted {action.target_service}. Cascaded errors cleared.")
            else:
                new_logs.append(f"Restarted {action.target_service}. No underlying issue fixed.")
            
    elif action.action_type == ActionType.scale_up:
        if target.root_cause == "cpu_spike":
            target.root_cause = None
            target.status = ServiceStatus.healthy
            target.metrics.cpu = 40.0
            new_logs.append(f"Scaled up {action.target_service}. CPU load normalized.")
        else:
            target.metrics.cpu = max(20.0, target.metrics.cpu - 50.0)
            new_logs.append(f"Scaled up {action.target_service}. Temporary relief.")
            
    elif action.action_type == ActionType.run_diagnostics:
        if target.root_cause:
            if target.root_cause == "cpu_spike":
                new_logs.append(f"Diagnostics on {action.target_service}: CPU usage anomalous.")
            elif target.root_cause == "memory_leak":
                new_logs.append(f"Diagnostics on {action.target_service}: Memory footprint growing linearly. Suggests leak.")
            elif target.root_cause == "db_connection_pool_exhausted":
                new_logs.append(f"Diagnostics on {action.target_service}: 100% DB connections active. Pool exhausted.")
        else:
            if target.status != ServiceStatus.healthy:
                if target.metrics.cpu <= 40 and target.metrics.errors > 0:
                    new_logs.append(f"Diagnostics on {action.target_service}: CPU normalized but errors still elevated.")
                elif target.metrics.cpu > 40 and target.metrics.errors == 0:
                    new_logs.append(f"Diagnostics on {action.target_service}: Errors cleared but CPU still elevated.")
                elif target.metrics.cpu > 40 and target.metrics.errors > 0:
                    new_logs.append(f"Diagnostics on {action.target_service}: CPU elevated and errors detected. Cascading issue.")
                else:
                    new_logs.append(f"Diagnostics on {action.target_service}: Service degraded but immediate metrics normal.")
            else:
                new_logs.append(f"Diagnostics on {action.target_service}: Service functioning within normal parameters.")

    elif action.action_type == ActionType.ignore:
        new_logs.append(f"Ignored alerts on {action.target_service}.")

    elif action.action_type == ActionType.escalate:
        target.metrics.errors = int(target.metrics.errors * 0.3)
        target.metrics.cpu = int(target.metrics.cpu * 0.7)
        new_logs.append(f"Escalated incident to L3 for {action.target_service}. Partial relief.")

    return new_logs

class CommanderEnv:
    def __init__(self):
        self.state_data: EnvState = None
        self.max_steps = 3
        self._action_correct_sequence = True
    
    def reset(self, task_id: str) -> Observation:
        task_id = task_id.strip().lower()
        if task_id not in TASKS:
            raise ValueError(f"Task {task_id} not found")
        
        # Deep copy to ensure we don't modify the original task definition
        self.state_data = copy.deepcopy(TASKS[task_id]())
        self.state_data.time_elapsed = 0
        self._action_correct_sequence = True
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
        if self.state_data.time_elapsed >= self.max_steps:
            raise RuntimeError("Episode finished, please reset environment")
            
        action = Action(**action_dict)
        target = self.state_data.services[action.target_service]
        
        previous_errors = sum(s.metrics.errors for s in self.state_data.services.values())
        
        most_critical_service = max(
            self.state_data.services,
            key=lambda s: self.state_data.services[s].metrics.errors
        ).value
        
        new_logs = apply_action(self.state_data, action)
            
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
        
        current_errors = sum(s.metrics.errors for s in self.state_data.services.values())
        progress_bonus = (previous_errors - current_errors) / 1000.0
        
        health_score = calculate_health_score(self.state_data)
        reward = min(health_score + progress_bonus, 0.95)
        
        if action.target_service != most_critical_service:
            reward -= 0.1
            self._action_correct_sequence = False
            new_logs.append(f"Warning: Targeted {action.target_service}, but {most_critical_service} is more critical.")
        else:
            new_logs.append(f"Progress: Targeted critical service {most_critical_service}.")
            
        if action.action_type == ActionType.escalate:
            reward -= 0.2
        elif action.action_type == ActionType.run_diagnostics:
            reward -= 0.05
            self._action_correct_sequence = False
            
        self.state_data.logs = new_logs
        self.state_data.time_elapsed += 1
        
        for s in self.state_data.services.values():
            if s.metrics.errors == 0:
                s.status = ServiceStatus.healthy
                
        is_system_healthy_check = all(s.metrics.errors == 0 for s in self.state_data.services.values())
        
        if is_system_healthy_check and self.state_data.time_elapsed >= 2:
            done = True
            self.state_data.resolved = True
        elif self.state_data.time_elapsed >= self.max_steps:
            done = True
            if not is_system_healthy_check:
                reward -= 0.2
        else:
            done = False
            
        optimal_path = (self.state_data.time_elapsed == 2 and self._action_correct_sequence)
        
        if done and is_system_healthy_check and optimal_path:
            reward = 1.0
            
        reward = max(min(reward, 1.0), 0.05)
            
        return StepResponse(
            observation=self._get_observation(),
            reward=reward,
            done=done,
            info={"action_correct": (action.target_service == most_critical_service)}
        )
