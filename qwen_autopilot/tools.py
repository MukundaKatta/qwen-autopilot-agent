"""A small ops toolset the Autopilot agent can drive.

Read tools are free-ish and local-ish; the three remediation tools are tagged
DESTRUCTIVE so the governance layer blocks them unless explicitly enabled. The
implementations here are deterministic stubs that return canned data, so the
whole agent runs offline with no real infrastructure. Swap the bodies for real
Alibaba Cloud / Kubernetes / observability calls in production.
"""

from __future__ import annotations

from typing import Any

from .types import ToolKind, ToolSpec

# --- canned infrastructure state (stand-in for real telemetry) --------------

_METRICS: dict[str, dict[str, Any]] = {
    "checkout": {"error_rate": 0.41, "p95_latency_ms": 5200, "cpu": 0.93, "replicas": 2},
    "payments": {"error_rate": 0.02, "p95_latency_ms": 240, "cpu": 0.55, "replicas": 4},
}

_DEPLOYS: dict[str, list[dict[str, str]]] = {
    "checkout": [
        {"version": "v2.4.0", "at": "2026-05-29T08:02Z", "status": "current"},
        {"version": "v2.3.7", "at": "2026-05-21T11:40Z", "status": "previous"},
    ],
}


def get_metrics(service: str) -> dict[str, Any]:
    return _METRICS.get(service, {"error": f"unknown service {service!r}"})


def get_logs(service: str, lines: int = 50) -> dict[str, Any]:
    sample = [
        "ERROR OutOfMemoryError in CheckoutHandler",
        "WARN gc pause 1800ms",
        "ERROR upstream payments timeout after 5000ms",
    ]
    return {"service": service, "lines": lines, "tail": sample}


def list_recent_deploys(service: str) -> dict[str, Any]:
    return {"service": service, "deploys": _DEPLOYS.get(service, [])}


def restart_service(service: str) -> dict[str, Any]:
    return {"action": "restart", "service": service, "result": "restarted"}


def scale_service(service: str, replicas: int) -> dict[str, Any]:
    return {"action": "scale", "service": service, "replicas": replicas, "result": "scaled"}


def rollback_deploy(service: str, to_version: str) -> dict[str, Any]:
    return {"action": "rollback", "service": service, "to_version": to_version, "result": "rolled_back"}


# --- declarative specs the governance layer trusts --------------------------

SPECS: dict[str, ToolSpec] = {
    "get_metrics": ToolSpec(
        name="get_metrics",
        kind=ToolKind.READ,
        description="Current metrics (error rate, p95 latency, cpu, replicas) for a service.",
        required_args=("service",),
        arg_types={"service": str},
        est_cost_usd=0.001,
        host="metrics.ops.internal",
    ),
    "get_logs": ToolSpec(
        name="get_logs",
        kind=ToolKind.READ,
        description="Recent log lines for a service.",
        required_args=("service",),
        arg_types={"service": str, "lines": int},
        est_cost_usd=0.001,
        host="logs.ops.internal",
    ),
    "list_recent_deploys": ToolSpec(
        name="list_recent_deploys",
        kind=ToolKind.READ,
        description="Recent deploys for a service, newest first.",
        required_args=("service",),
        arg_types={"service": str},
        est_cost_usd=0.001,
        host="deploy.ops.internal",
    ),
    "restart_service": ToolSpec(
        name="restart_service",
        kind=ToolKind.DESTRUCTIVE,
        description="Restart all pods of a service.",
        required_args=("service",),
        arg_types={"service": str},
        est_cost_usd=0.05,
        host="deploy.ops.internal",
    ),
    "scale_service": ToolSpec(
        name="scale_service",
        kind=ToolKind.DESTRUCTIVE,
        description="Set the replica count for a service.",
        required_args=("service", "replicas"),
        arg_types={"service": str, "replicas": int},
        est_cost_usd=0.10,
        host="deploy.ops.internal",
    ),
    "rollback_deploy": ToolSpec(
        name="rollback_deploy",
        kind=ToolKind.DESTRUCTIVE,
        description="Roll a service back to a previous deployed version.",
        required_args=("service", "to_version"),
        arg_types={"service": str, "to_version": str},
        est_cost_usd=0.05,
        host="deploy.ops.internal",
    ),
}

FUNCS = {
    "get_metrics": get_metrics,
    "get_logs": get_logs,
    "list_recent_deploys": list_recent_deploys,
    "restart_service": restart_service,
    "scale_service": scale_service,
    "rollback_deploy": rollback_deploy,
}

# Hosts the read + deploy tools reach; pass to GovernedSession(allowed_hosts=...).
INTERNAL_HOSTS = ("*.ops.internal",)
