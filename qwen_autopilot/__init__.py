"""qwen-autopilot-agent: a governed autonomous ops-remediation agent on Qwen Cloud.

A Qwen-powered Autopilot agent that diagnoses an incident and executes the fix
end to end, with a hard governance layer around every tool call: a cost cap, an
egress allowlist, tool-arg validation, a destructive-action gate, and an
append-only audit trail. Safe enough to actually run a business workflow
unattended.

Built for the Global AI Hackathon Series with Qwen Cloud (Autopilot Agent track).
"""

from .types import (
    ToolKind,
    EventKind,
    DenyReason,
    ToolSpec,
    ToolCall,
    AssistantTurn,
    AuditEvent,
    RemediationReport,
)
from .governance import (
    GovernedSession,
    GovernanceError,
    BudgetExceededError,
    CallCapExceededError,
    EgressDeniedError,
    ToolArgsInvalidError,
    DestructiveActionDenied,
)
from .agent import AutopilotAgent
from .qwen_client import QwenClient, FakeQwenClient

__version__ = "0.1.0"

__all__ = [
    "ToolKind",
    "EventKind",
    "DenyReason",
    "ToolSpec",
    "ToolCall",
    "AssistantTurn",
    "AuditEvent",
    "RemediationReport",
    "GovernedSession",
    "GovernanceError",
    "BudgetExceededError",
    "CallCapExceededError",
    "EgressDeniedError",
    "ToolArgsInvalidError",
    "DestructiveActionDenied",
    "AutopilotAgent",
    "QwenClient",
    "FakeQwenClient",
]
