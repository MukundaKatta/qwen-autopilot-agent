"""Tests for the Autopilot loop driving the governed session end to end.

Standard-library ``unittest`` only. Run with::

    python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qwen_autopilot import AutopilotAgent, FakeQwenClient, GovernedSession  # noqa: E402
from qwen_autopilot.tools import FUNCS, INTERNAL_HOSTS, SPECS  # noqa: E402
from qwen_autopilot.types import AssistantTurn, ToolCall  # noqa: E402


def make_agent(script, **session_kw):
    session = GovernedSession(allowed_hosts=INTERNAL_HOSTS, **session_kw)
    agent = AutopilotAgent(FakeQwenClient(script), session, SPECS, FUNCS)
    return agent, session


class AgentLoopTests(unittest.TestCase):
    def test_read_then_rollback_resolves(self):
        script = [
            AssistantTurn(tool_calls=[ToolCall("get_metrics", {"service": "checkout"})]),
            AssistantTurn(
                tool_calls=[
                    ToolCall("rollback_deploy", {"service": "checkout", "to_version": "v2.3.7"})
                ]
            ),
            AssistantTurn(content="rolled back", final=True),
        ]
        agent, session = make_agent(script, usd_cap=1.0, allow_destructive=("rollback_deploy",))
        report = agent.run("checkout errors")
        self.assertTrue(report.resolved)
        self.assertTrue(any("rollback_deploy" in a for a in report.actions_taken))
        self.assertEqual(session.calls, 2)

    def test_destructive_denied_is_fed_back_not_executed(self):
        script = [
            # restart_service is destructive and not enabled for this session
            AssistantTurn(tool_calls=[ToolCall("restart_service", {"service": "checkout"})]),
            AssistantTurn(content="cannot restart, escalating", final=True),
        ]
        agent, session = make_agent(script, usd_cap=1.0)  # no destructive enabled
        report = agent.run("checkout down")
        self.assertEqual(report.actions_taken, [])
        self.assertTrue(any("DENIED" in s for s in report.steps))
        self.assertEqual(session.calls, 0)  # denied call never counted

    def test_bad_args_denied(self):
        script = [
            AssistantTurn(
                tool_calls=[ToolCall("scale_service", {"service": "checkout", "replicas": "lots"})]
            ),
            AssistantTurn(content="bad args", final=True),
        ]
        agent, session = make_agent(script, usd_cap=1.0, allow_destructive=("scale_service",))
        report = agent.run("scale checkout")
        self.assertEqual(report.actions_taken, [])
        self.assertTrue(any("scale_service DENIED" in s for s in report.steps))

    def test_loop_cap_stops_runaway(self):
        # Every turn calls a read tool and never finalizes; loop_cap must stop it.
        script = [
            AssistantTurn(tool_calls=[ToolCall("get_metrics", {"service": "checkout"})])
            for _ in range(50)
        ]
        session = GovernedSession(allowed_hosts=INTERNAL_HOSTS, usd_cap=100.0, call_cap=100)
        agent = AutopilotAgent(FakeQwenClient(script), session, SPECS, FUNCS, loop_cap=4)
        report = agent.run("noisy incident")
        self.assertFalse(report.resolved)
        self.assertEqual(session.calls, 4)  # exactly loop_cap tool turns ran

    def test_unknown_tool_is_ignored_safely(self):
        script = [
            AssistantTurn(tool_calls=[ToolCall("delete_everything", {})]),
            AssistantTurn(content="done", final=True),
        ]
        agent, session = make_agent(script, usd_cap=1.0)
        report = agent.run("incident")
        self.assertEqual(session.calls, 0)
        self.assertTrue(any("unknown tool" in s for s in report.steps))

    def test_read_only_diagnosis_is_not_marked_resolved(self):
        # The agent diagnoses with read tools but takes no remediating action.
        script = [
            AssistantTurn(tool_calls=[ToolCall("get_metrics", {"service": "checkout"})]),
            AssistantTurn(tool_calls=[ToolCall("get_logs", {"service": "checkout"})]),
            AssistantTurn(content="diagnosed, but no action taken", final=True),
        ]
        agent, session = make_agent(script, usd_cap=1.0)
        report = agent.run("investigate checkout")
        self.assertEqual(report.actions_taken, [])
        self.assertFalse(report.resolved)  # stopping talking != resolving

    def test_empty_script_ends_cleanly(self):
        # FakeQwenClient with no scripted turns must terminate, not raise.
        agent, session = make_agent([], usd_cap=1.0)
        report = agent.run("nothing to do")
        self.assertFalse(report.resolved)
        self.assertEqual(session.calls, 0)


if __name__ == "__main__":
    unittest.main()
