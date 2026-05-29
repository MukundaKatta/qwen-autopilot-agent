"""Offline, credential-free demo of qwen-autopilot-agent.

Runs the REAL agent loop and the REAL governance layer against a scripted fake
Qwen client and stubbed ops tools, so the exact production code path executes
with no API key and no network.

    python examples/offline_demo.py

It shows, in one incident:
  - read tools (metrics, logs, deploys) allowed and audited
  - a malformed action (replicas="lots") blocked by tool-arg validation
  - a destructive restart blocked because that action was not enabled
  - a rollback allowed because the operator enabled exactly that action
Then a second run shows the USD cost cap stopping an over-budget action.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qwen_autopilot import AutopilotAgent, FakeQwenClient, GovernedSession  # noqa: E402
from qwen_autopilot.tools import FUNCS, INTERNAL_HOSTS, SPECS  # noqa: E402
from qwen_autopilot.types import AssistantTurn, ToolCall  # noqa: E402


def banner(title: str) -> None:
    print(f"\n{'=' * 68}\n{title}\n{'=' * 68}")


def show(report, session) -> None:
    print("\n-- agent steps --")
    for s in report.steps:
        print(f"  {s}")
    print("\n-- remediation report --")
    print(f"  root cause: {report.root_cause}")
    print(f"  actions taken: {report.actions_taken or 'none'}")
    print(f"  resolved: {report.resolved}")
    print("\n-- audit trail (jsonl) --")
    print(session.audit_jsonl())
    print(f"\n  spent ${session.spent_usd:.4f} of ${session.usd_cap:.4f} cap over {session.calls} calls")


def main() -> None:
    banner("Run 1 - diagnose checkout outage, rollback enabled, restart NOT enabled")
    script = [
        AssistantTurn(content="checking metrics", tool_calls=[ToolCall("get_metrics", {"service": "checkout"})]),
        AssistantTurn(content="checking logs", tool_calls=[ToolCall("get_logs", {"service": "checkout", "lines": 20})]),
        AssistantTurn(content="checking deploys", tool_calls=[ToolCall("list_recent_deploys", {"service": "checkout"})]),
        # malformed: replicas must be an int -> blocked by arg validation
        AssistantTurn(content="trying to scale", tool_calls=[ToolCall("scale_service", {"service": "checkout", "replicas": "lots"})]),
        # destructive and not enabled -> blocked by the destructive gate
        AssistantTurn(content="trying a restart", tool_calls=[ToolCall("restart_service", {"service": "payments"})]),
        # destructive but explicitly enabled -> allowed
        AssistantTurn(content="rolling back the bad deploy", tool_calls=[ToolCall("rollback_deploy", {"service": "checkout", "to_version": "v2.3.7"})]),
        AssistantTurn(
            content="checkout OOM started with v2.4.0; rolled back to v2.3.7. Error rate recovering.",
            final=True,
        ),
    ]
    session = GovernedSession(
        usd_cap=1.0,
        call_cap=20,
        allowed_hosts=INTERNAL_HOSTS,
        allow_destructive=("rollback_deploy",),
    )
    with session:
        agent = AutopilotAgent(FakeQwenClient(script), session, SPECS, FUNCS)
        report = agent.run("checkout is throwing 41% errors and p95 is 5.2s since 08:00")
    show(report, session)

    banner("Run 2 - tight $0.05 cost cap stops an expensive action before it runs")
    script2 = [
        AssistantTurn(content="checking metrics", tool_calls=[ToolCall("get_metrics", {"service": "checkout"})]),
        AssistantTurn(content="scaling up", tool_calls=[ToolCall("scale_service", {"service": "checkout", "replicas": 6})]),
        AssistantTurn(content="cannot remediate within the cost budget; escalating to a human", final=True),
    ]
    session2 = GovernedSession(
        usd_cap=0.05,
        allowed_hosts=INTERNAL_HOSTS,
        allow_destructive=("scale_service",),
    )
    with session2:
        agent2 = AutopilotAgent(FakeQwenClient(script2), session2, SPECS, FUNCS)
        report2 = agent2.run("checkout is overloaded, consider scaling")
    show(report2, session2)

    print("\nNote: every denied call above never executed. The agent saw the denial")
    print("reason and adapted, and the audit trail records both the allows and denies.")


if __name__ == "__main__":
    main()
