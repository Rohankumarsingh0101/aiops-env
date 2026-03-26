from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

class ServiceName(str, Enum):
    auth = "auth"
    payments = "payments"
    search = "search"

class ActionType(str, Enum):
    restart_service = "restart_service"
    scale_up = "scale_up"
    run_diagnostics = "run_diagnostics"
    ignore = "ignore"
    escalate = "escalate"

class ServiceStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    down = "down"

class Action(BaseModel):
    action_type: ActionType
    target_service: ServiceName

class ServiceMetrics(BaseModel):
    cpu: float
    memory: float
    errors: int

class ServiceState(BaseModel):
    status: ServiceStatus
    metrics: ServiceMetrics
    root_cause: Optional[str] = None

class EnvState(BaseModel):
    task_id: str
    services: Dict[ServiceName, ServiceState]
    severity: int
    time_elapsed: int
    steps_taken: int
    resolved: bool
    logs: List[str] = []

class Observation(BaseModel):
    services: Dict[str, Dict[str, Any]]
    logs: List[str]
    severity: int
    time_elapsed: int

class StepResponse(BaseModel):
    observation: Observation
    reward: float
    done: bool
    info: Dict[str, Any]
