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
        logs=["Search CPU at 95% \u2014 likely scaling bottleneck"]
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
            "Auth latency spike + memory 98% \u2014 possible memory leak",
            "Payments reporting elevated error rate. Possible cascade."
        ]
    )

def get_task_hard() -> EnvState:
    # Deceptive scenario: Payments is loud — high errors and CPU — making it look like the culprit.
    # Auth is quiet but harbours the hidden db_connection_pool_exhausted root cause.
    # Auth CPU normal (45%), memory slightly elevated (72%) — easy to overlook.
    # Cascade path: auth pool exhaustion → upstream timeouts → payments retry storm.
    # Optimal path: run_diagnostics on auth → restart auth → restart payments
    return EnvState(
        task_id="hard",
        services={
            ServiceName.auth: ServiceState(
                status=ServiceStatus.degraded,   # degraded but metrics look mild
                metrics=ServiceMetrics(cpu=45.0, memory=72.0, errors=30),
                root_cause="db_connection_pool_exhausted"  # hidden root cause
            ),
            ServiceName.payments: ServiceState(
                status=ServiceStatus.degraded,
                metrics=ServiceMetrics(cpu=91.0, memory=78.0, errors=480),
                # No root_cause — it is a cascade victim of auth
            ),
            ServiceName.search: ServiceState(
                status=ServiceStatus.healthy,
                metrics=ServiceMetrics(cpu=38.0, memory=44.0, errors=0),
            )
        },
        severity=4,
        time_elapsed=0,
        steps_taken=0,
        resolved=False,
        logs=[
            "ALERT: Payments error rate at 480 req/s — SLA breached.",
            "Payments: retry storm observed — clients retrying failed upstream calls.",
            "Payments CPU at 91% — likely amplified by retry load, not CPU-bound root cause.",
            "Auth: upstream dependency timeout detected on DB connection layer.",
            "Auth: connection pool saturation detected — 98% of pool slots occupied.",
            "Note: Auth CPU appears normal. Memory slightly elevated. Investigate DB pool.",
        ]
    )


TASKS = {
    "easy": get_task_easy,
    "medium": get_task_medium,
    "hard": get_task_hard
}
