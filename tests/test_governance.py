"""Tests for the governance layer: each guard allows valid and denies invalid.

Standard-library ``unittest`` only, matching the project's zero-dependency promise.
Run with::

    python -m unittest discover -s tests
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qwen_autopilot.governance import (  # noqa: E402
    BudgetExceededError,
    CallCapExceededError,
    DestructiveActionDenied,
    EgressDeniedError,
    GovernedSession,
    ToolArgsInvalidError,
)
from qwen_autopilot.types import EventKind, ToolKind, ToolSpec  # noqa: E402

READ = ToolSpec(
    "read_x",
    ToolKind.READ,
    required_args=("service",),
    arg_types={"service": str},
    est_cost_usd=0.01,
    host="a.ops.internal",
)
DESTRUCTIVE = ToolSpec(
    "nuke",
    ToolKind.DESTRUCTIVE,
    required_args=("service",),
    arg_types={"service": str},
    est_cost_usd=0.02,
    host="a.ops.internal",
)


def ok() -> GovernedSession:
    return GovernedSession(
        usd_cap=1.0,
        call_cap=5,
        allowed_hosts=("*.ops.internal",),
        allow_destructive=("nuke",),
    )


class GovernanceTests(unittest.TestCase):
    def test_valid_read_passes_and_audits(self):
        s = ok()
        s.vet(READ, {"service": "checkout"})
        self.assertEqual(s.calls, 1)
        self.assertAlmostEqual(s.spent_usd, 0.01)
        self.assertIs(s.audit[-1].kind, EventKind.TOOL_OK)

    def test_missing_arg_denied(self):
        s = ok()
        with self.assertRaises(ToolArgsInvalidError):
            s.vet(READ, {})
        self.assertEqual(s.calls, 0)
        self.assertIs(s.audit[-1].kind, EventKind.TOOL_DENIED)

    def test_wrong_type_denied(self):
        s = ok()
        with self.assertRaises(ToolArgsInvalidError):
            s.vet(READ, {"service": 123})

    def test_egress_blocked(self):
        s = GovernedSession(allowed_hosts=("only.this.host",))
        with self.assertRaises(EgressDeniedError):
            s.vet(READ, {"service": "checkout"})

    def test_destructive_blocked_unless_enabled(self):
        s = GovernedSession(allowed_hosts=("*.ops.internal",))  # nuke not enabled
        with self.assertRaises(DestructiveActionDenied):
            s.vet(DESTRUCTIVE, {"service": "checkout"})

    def test_destructive_allowed_when_enabled(self):
        s = ok()
        s.vet(DESTRUCTIVE, {"service": "checkout"})
        self.assertEqual(s.calls, 1)

    def test_budget_cap_blocks_and_does_not_charge(self):
        s = GovernedSession(
            usd_cap=0.015, allowed_hosts=("*.ops.internal",), allow_destructive=("nuke",)
        )
        s.vet(READ, {"service": "checkout"})  # 0.01 spent
        with self.assertRaises(BudgetExceededError):
            s.vet(DESTRUCTIVE, {"service": "checkout"})  # +0.02 -> over 0.015
        self.assertAlmostEqual(s.spent_usd, 0.01)
        self.assertIs(s.audit[-1].kind, EventKind.BUDGET_DENIED)

    def test_call_cap(self):
        s = GovernedSession(usd_cap=100.0, call_cap=2, allowed_hosts=("*.ops.internal",))
        s.vet(READ, {"service": "a"})
        s.vet(READ, {"service": "b"})
        with self.assertRaises(CallCapExceededError):
            s.vet(READ, {"service": "c"})

    def test_args_hashed_by_default(self):
        s = ok()
        s.vet(READ, {"service": "secret-customer-123"})
        ev = s.audit[-1]
        self.assertIsNotNone(ev.args_hash)
        self.assertNotIn("secret-customer-123", ev.args_hash or "")

    def test_args_not_hashed_when_disabled(self):
        s = GovernedSession(allowed_hosts=("*.ops.internal",), hash_args=False)
        s.vet(READ, {"service": "checkout"})
        self.assertIsNone(s.audit[-1].args_hash)

    def test_optional_arg_skipped_when_absent(self):
        # ``lines`` is typed but not required; omitting it must not trip arg validation.
        spec = ToolSpec(
            "read_y",
            ToolKind.READ,
            required_args=("service",),
            arg_types={"service": str, "lines": int},
            host="a.ops.internal",
        )
        s = GovernedSession(allowed_hosts=("*.ops.internal",))
        s.vet(spec, {"service": "checkout"})
        self.assertEqual(s.calls, 1)

    def test_local_tool_skips_egress_check(self):
        # host=None means local-only, so an empty allowlist must not block it.
        spec = ToolSpec("local", ToolKind.READ, host=None)
        s = GovernedSession(allowed_hosts=())
        s.vet(spec, {})
        self.assertEqual(s.calls, 1)

    def test_run_executes_only_when_allowed(self):
        s = ok()
        result = s.run(READ, lambda service: {"service": service}, {"service": "checkout"})
        self.assertEqual(result, {"service": "checkout"})

    def test_run_does_not_execute_when_denied(self):
        s = GovernedSession(allowed_hosts=("only.this.host",))
        executed = []
        with self.assertRaises(EgressDeniedError):
            s.run(READ, lambda service: executed.append(service), {"service": "checkout"})
        self.assertEqual(executed, [])  # the function body never ran

    def test_session_close_event_on_exit(self):
        with GovernedSession() as s:
            pass
        self.assertIs(s.audit[-1].kind, EventKind.SESSION_CLOSE)

    def test_audit_jsonl_roundtrips(self):
        s = ok()
        s.vet(READ, {"service": "checkout"})
        lines = s.audit_jsonl().splitlines()
        parsed = [json.loads(line) for line in lines]
        self.assertEqual(parsed[0]["kind"], "tool_ok")
        self.assertEqual(parsed[0]["tool"], "read_x")


if __name__ == "__main__":
    unittest.main()
