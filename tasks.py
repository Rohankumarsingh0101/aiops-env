from models import EnvState, ServiceState, ServiceMetrics, ServiceStatus, ServiceName

def get_task_easy() -> EnvState:
    # CPU spike in one service
    return EnvState(
        task_id="easy",
        services={
            ServiceName.auth: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=40.0, memory=50.0, errors=5),
            ),
            ServiceName.payments: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=30.0, memory=40.0, errors=2),
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
        logs=["High CPU usage detected on search service"]
    )

def get_task_medium() -> EnvState:
    # Memory leak requiring diagnostics + restart
    return EnvState(
        task_id="medium",
        services={
            ServiceName.auth: ServiceState(
                status=ServiceStatus.degraded,
                metrics=ServiceMetrics(cpu=50.0, memory=98.0, errors=100),
                root_cause="memory_leak"
            ),
            ServiceName.payments: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=40.0, memory=40.0, errors=5),
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
        logs=["Latency increased on auth service. Container memory usage critical."]
    )

def get_task_hard() -> EnvState:
    # Cascading multi-service failure with misleading logs
    return EnvState(
        task_id="hard",
        services={
            ServiceName.auth: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=40.0, memory=50.0, errors=10),
                root_cause="db_connection_pool_exhausted" # The real root cause is buried
            ),
            ServiceName.payments: ServiceState(
                status=ServiceStatus.degraded,
                metrics=ServiceMetrics(cpu=90.0, memory=80.0, errors=500),
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
            "Database connections occasionally dropping."
        ]
    )

TASKS = {
    "easy": get_task_easy,
    "medium": get_task_medium,
    "hard": get_task_hard
}
