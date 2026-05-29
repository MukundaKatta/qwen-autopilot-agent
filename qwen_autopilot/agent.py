"""The Autopilot loop: Qwen plans, the governance layer vets, tools execute.

Each turn the model either calls tools or returns a final report. Every tool call
is routed through the GovernedSession, so a denied call does not execute; instead
the denial reason is fed back to the model so it can adapt (ask for a smaller
action, a different host, fix the args), exactly as a careful operator would.
The loop is hard-bounded so it can never run forever.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from .governance import GovernanceError, GovernedSession
from .qwen_client import tool_schemas
from .types import AssistantTurn, RemediationReport, ToolCall, ToolSpec

SYSTEM_PROMPT = (
    "You are an autonomous site-reliability agent. Diagnose the incident using the "
    "read tools first (metrics, logs, recent deploys), form a root cause, then take "
    "the smallest remediation action that fixes it. Some actions are guarded and may "
    "be denied; if a call is denied, read the reason and adapt instead of retrying "
    "blindly. When the incident is resolved, stop calling tools and reply with a final "
    "report."
)


class _ChatClient(Protocol):
    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> AssistantTurn: ...


class AutopilotAgent:
    def __init__(
        self,
        client: _ChatClient,
        session: GovernedSession,
        specs: dict[str, ToolSpec],
        funcs: dict[str, Any],
        loop_cap: int = 8,
    ) -> None:
        self.client = client
        self.session = session
        self.specs = specs
        self.funcs = funcs
        self.loop_cap = loop_cap

    def run(self, incident: str) -> RemediationReport:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": incident},
        ]
        schemas = tool_schemas(self.specs)
        report = RemediationReport(incident=incident)

        for _ in range(self.loop_cap):
            turn = self.client.chat(messages, tools=schemas)

            if turn.final or not turn.tool_calls:
                report.root_cause = turn.content.strip()
                # Resolved means the agent actually took a remediating action,
                # not merely that it stopped talking (it may have escalated).
                report.resolved = bool(report.actions_taken)
                return report

            messages.append({"role": "assistant", "content": turn.content, "tool_calls": _echo(turn.tool_calls)})
            for call in turn.tool_calls:
                result = self._execute(call, report)
                messages.append({"role": "tool", "name": call.name, "content": json.dumps(result, default=str)})

        report.root_cause = "loop cap reached before the agent declared resolution"
        report.resolved = False
        return report

    def _execute(self, call: ToolCall, report: RemediationReport) -> dict[str, Any]:
        spec = self.specs.get(call.name)
        if spec is None:
            report.steps.append(f"unknown tool {call.name} (ignored)")
            return {"error": f"unknown tool {call.name!r}"}
        try:
            out = self.session.run(spec, self.funcs[call.name], call.args)
        except GovernanceError as exc:
            report.steps.append(f"{call.name} DENIED ({exc.reason.value})")
            return {"denied": True, "reason": exc.reason.value, "detail": str(exc)}
        report.steps.append(f"{call.name}({_short(call.args)}) ok")
        from .types import ToolKind

        if spec.kind is not ToolKind.READ:
            report.actions_taken.append(f"{call.name}({_short(call.args)})")
        return {"ok": True, "result": out}


def _echo(calls: list[ToolCall]) -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": c.name, "arguments": json.dumps(c.args, default=str)}}
        for c in calls
    ]


def _short(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items())
