from models import EnvState, ServiceState, ServiceMetrics, ServiceStatus, ServiceName

def get_task_easy() -> EnvState:
    # Single service CPU spike — clear root cause, straightforward resolution
    return EnvState(
        task_id="easy",
        services={
            ServiceName.auth: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=40.0, memory=50.0, errors=0),
            ),
            ServiceName.payments: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=30.0, memory=40.0, errors=0),
            ),
            ServiceName.search: ServiceState(
                status=ServiceStatus.degraded,
                metrics=ServiceMetrics(cpu=95.0, memory=60.0, errors=50),
                root_cause="cpu_spike"
            )
        },
        severity=2,
        time_elapsed=0,
        steps_taken=0,
        resolved=False,
        logs=["High CPU usage detected on search service. Errors elevated."]
    )

def get_task_medium() -> EnvState:
    # Auth memory leak causing cascade into payments — requires two targeted restarts
    return EnvState(
        task_id="medium",
        services={
            ServiceName.auth: ServiceState(
                status=ServiceStatus.degraded,
                metrics=ServiceMetrics(cpu=50.0, memory=98.0, errors=100),
                root_cause="memory_leak"
            ),
            ServiceName.payments: ServiceState(
                status=ServiceStatus.degraded,
                metrics=ServiceMetrics(cpu=80.0, memory=50.0, errors=50),
            ),
            ServiceName.search: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=30.0, memory=30.0, errors=0),
            )
        },
        severity=3,
        time_elapsed=0,
        steps_taken=0,
        resolved=False,
        logs=[
            "Latency spike on auth service. Memory usage critical.",
            "Payments reporting elevated error rate. Possible cascade."
        ]
    )

def get_task_hard() -> EnvState:
    # Deceptive scenario: payments looks worst but auth holds the real root cause.
    # scale_up on payments reduces CPU but errors stay high (misleading partial improvement).
    # Agent must trace the hidden db_connection_pool_exhausted on auth to fully recover.
    return EnvState(
        task_id="hard",
        services={
            ServiceName.auth: ServiceState(
                status=ServiceStatus.healthy,    # Misleadingly appears healthy
                metrics=ServiceMetrics(cpu=40.0, memory=50.0, errors=0),
                root_cause="db_connection_pool_exhausted"  # Hidden root cause
            ),
            ServiceName.payments: ServiceState(
                status=ServiceStatus.degraded,
                metrics=ServiceMetrics(cpu=90.0, memory=80.0, errors=500),
                # No root cause — it is a victim of the auth cascade
            ),
            ServiceName.search: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=40.0, memory=50.0, errors=0),
            )
        },
        severity=4,
        time_elapsed=0,
        steps_taken=0,
        resolved=False,
        logs=[
            "Multiple HTTP 500 errors on payments API.",
            "Alert: Payments service SLA breached.",
            "Database connections occasionally dropping.",
            "Note: Auth service metrics appear nominal — investigate further."
        ]
    )

TASKS = {
    "easy": get_task_easy,
    "medium": get_task_medium,
    "hard": get_task_hard
}
