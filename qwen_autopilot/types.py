"""Typed primitives. Closed enums and dataclasses, no magic strings for control flow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ToolKind(str, Enum):
    """Side-effect class of a tool. Drives the destructive-action gate."""

    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class EventKind(str, Enum):
    """Closed set of audit event kinds, so a reviewer/SIEM can parse without guessing."""

    TOOL_OK = "tool_ok"
    TOOL_DENIED = "tool_denied"
    BUDGET_DENIED = "budget_denied"
    SESSION_CLOSE = "session_close"


class DenyReason(str, Enum):
    """Why a tool call was refused. Each governance error maps to exactly one."""

    OVER_BUDGET = "over_budget"
    OVER_CALL_CAP = "over_call_cap"
    EGRESS_BLOCKED = "egress_blocked"
    BAD_ARGS = "bad_args"
    DESTRUCTIVE_BLOCKED = "destructive_blocked"


@dataclass(frozen=True)
class ToolSpec:
    """Declarative description of a tool the agent may call.

    The governance layer reads this; it never trusts the model's view of a tool.
    """

    name: str
    kind: ToolKind
    description: str = ""
    required_args: tuple[str, ...] = ()
    arg_types: dict[str, type] = field(default_factory=dict)
    # Estimated cost (USD) charged against the session budget per call.
    est_cost_usd: float = 0.0
    # Host this tool reaches, checked against the egress allowlist. None = local only.
    host: Optional[str] = None


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class AssistantTurn:
    """Normalized model output, identical shape for the real and fake clients."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    final: bool = False


@dataclass
class AuditEvent:
    kind: EventKind
    tool: Optional[str] = None
    reason: Optional[DenyReason] = None
    args_hash: Optional[str] = None
    cost_usd: float = 0.0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["reason"] = self.reason.value if self.reason is not None else None
        return d


@dataclass
class RemediationReport:
    incident: str
    root_cause: str = ""
    steps: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
