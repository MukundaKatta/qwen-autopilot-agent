"""Tests for the governance layer: each guard allows valid and denies invalid."""

import sys
from pathlib import Path

import pytest

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

READ = ToolSpec("read_x", ToolKind.READ, required_args=("service",), arg_types={"service": str}, est_cost_usd=0.01, host="a.ops.internal")
DESTRUCTIVE = ToolSpec("nuke", ToolKind.DESTRUCTIVE, required_args=("service",), arg_types={"service": str}, est_cost_usd=0.02, host="a.ops.internal")


def ok():
    return GovernedSession(usd_cap=1.0, call_cap=5, allowed_hosts=("*.ops.internal",), allow_destructive=("nuke",))


def test_valid_read_passes_and_audits():
    s = ok()
    s.vet(READ, {"service": "checkout"})
    assert s.calls == 1
    assert s.spent_usd == pytest.approx(0.01)
    assert s.audit[-1].kind is EventKind.TOOL_OK


def test_missing_arg_denied():
    s = ok()
    with pytest.raises(ToolArgsInvalidError):
        s.vet(READ, {})
    assert s.calls == 0
    assert s.audit[-1].kind is EventKind.TOOL_DENIED


def test_wrong_type_denied():
    s = ok()
    with pytest.raises(ToolArgsInvalidError):
        s.vet(READ, {"service": 123})


def test_egress_blocked():
    s = GovernedSession(allowed_hosts=("only.this.host",))
    with pytest.raises(EgressDeniedError):
        s.vet(READ, {"service": "checkout"})


def test_destructive_blocked_unless_enabled():
    s = GovernedSession(allowed_hosts=("*.ops.internal",))  # nuke not enabled
    with pytest.raises(DestructiveActionDenied):
        s.vet(DESTRUCTIVE, {"service": "checkout"})


def test_destructive_allowed_when_enabled():
    s = ok()
    s.vet(DESTRUCTIVE, {"service": "checkout"})
    assert s.calls == 1


def test_budget_cap_blocks_and_does_not_charge():
    s = GovernedSession(usd_cap=0.015, allowed_hosts=("*.ops.internal",), allow_destructive=("nuke",))
    s.vet(READ, {"service": "checkout"})  # 0.01 spent
    with pytest.raises(BudgetExceededError):
        s.vet(DESTRUCTIVE, {"service": "checkout"})  # +0.02 -> over 0.015
    assert s.spent_usd == pytest.approx(0.01)
    assert s.audit[-1].kind is EventKind.BUDGET_DENIED


def test_call_cap():
    s = GovernedSession(usd_cap=100.0, call_cap=2, allowed_hosts=("*.ops.internal",))
    s.vet(READ, {"service": "a"})
    s.vet(READ, {"service": "b"})
    with pytest.raises(CallCapExceededError):
        s.vet(READ, {"service": "c"})


def test_args_hashed_by_default():
    s = ok()
    s.vet(READ, {"service": "secret-customer-123"})
    ev = s.audit[-1]
    assert ev.args_hash is not None
    assert "secret-customer-123" not in (ev.args_hash or "")


def test_session_close_event_on_exit():
    with GovernedSession() as s:
        pass
    assert s.audit[-1].kind is EventKind.SESSION_CLOSE


def test_audit_jsonl_roundtrips():
    import json

    s = ok()
    s.vet(READ, {"service": "checkout"})
    lines = s.audit_jsonl().splitlines()
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["kind"] == "tool_ok"
    assert parsed[0]["tool"] == "read_x"
