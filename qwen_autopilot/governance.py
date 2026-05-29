"""The governance layer: every tool call the agent makes is vetted here first.

Five independent guards, each with its own typed exception so a caller can reason
about exactly which one fired:

  1. call cap          - stop after N tool calls (runaway-loop backstop)
  2. tool-arg validation - required args present and correctly typed
  3. egress allowlist  - the tool's host must match the allowlist (wildcards ok)
  4. destructive gate  - DESTRUCTIVE tools must be explicitly enabled
  5. cost cap          - projected spend must stay under the USD budget

Every decision, allow or deny, is appended to an audit trail with one event per
line. Tool args are hashed by default so the log is safe to share without leaking
payloads.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from typing import Any, Callable

from .types import AuditEvent, DenyReason, EventKind, ToolKind, ToolSpec


class GovernanceError(Exception):
    """Base class. Subclasses set ``reason`` to a single DenyReason."""

    reason: DenyReason


class CallCapExceededError(GovernanceError):
    reason = DenyReason.OVER_CALL_CAP


class ToolArgsInvalidError(GovernanceError):
    reason = DenyReason.BAD_ARGS


class EgressDeniedError(GovernanceError):
    reason = DenyReason.EGRESS_BLOCKED


class DestructiveActionDenied(GovernanceError):
    reason = DenyReason.DESTRUCTIVE_BLOCKED


class BudgetExceededError(GovernanceError):
    reason = DenyReason.OVER_BUDGET


def _hash_args(args: dict[str, Any]) -> str:
    blob = json.dumps(args, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class GovernedSession:
    """Wraps tool execution with the five guards plus an audit trail.

    Use as a context manager so a SESSION_CLOSE event is always recorded::

        with GovernedSession(usd_cap=0.50, allowed_hosts=["*.internal"]) as gov:
            gov.run(spec, fn, args)
    """

    def __init__(
        self,
        *,
        usd_cap: float = 1.0,
        call_cap: int = 20,
        allowed_hosts: tuple[str, ...] = (),
        allow_destructive: tuple[str, ...] = (),
        hash_args: bool = True,
    ) -> None:
        self.usd_cap = float(usd_cap)
        self.call_cap = int(call_cap)
        self.allowed_hosts = tuple(allowed_hosts)
        self.allow_destructive = set(allow_destructive)
        self.hash_args = hash_args
        self.spent_usd = 0.0
        self.calls = 0
        self.audit: list[AuditEvent] = []

    def __enter__(self) -> "GovernedSession":
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.audit.append(
            AuditEvent(
                kind=EventKind.SESSION_CLOSE,
                cost_usd=round(self.spent_usd, 6),
                detail=f"{self.calls} calls, ${self.spent_usd:.4f} spent",
            )
        )
        return False

    # -- internals -----------------------------------------------------------

    def _maybe_hash(self, args: dict[str, Any]) -> str | None:
        return _hash_args(args) if self.hash_args else None

    def _host_allowed(self, host: str) -> bool:
        return any(fnmatch.fnmatch(host, pat) for pat in self.allowed_hosts)

    def _deny(self, spec: ToolSpec, args: dict[str, Any], reason: DenyReason, detail: str) -> None:
        kind = EventKind.BUDGET_DENIED if reason is DenyReason.OVER_BUDGET else EventKind.TOOL_DENIED
        self.audit.append(
            AuditEvent(
                kind=kind,
                tool=spec.name,
                reason=reason,
                args_hash=self._maybe_hash(args),
                cost_usd=spec.est_cost_usd if reason is DenyReason.OVER_BUDGET else 0.0,
                detail=detail,
            )
        )

    # -- public --------------------------------------------------------------

    def vet(self, spec: ToolSpec, args: dict[str, Any]) -> None:
        """Raise the matching GovernanceError if the call is not permitted.

        Order matters: cheap structural checks first, budget last. The session
        counters only advance when every guard passes.
        """
        if self.calls + 1 > self.call_cap:
            self._deny(spec, args, DenyReason.OVER_CALL_CAP, f"call cap {self.call_cap} reached")
            raise CallCapExceededError(f"call cap {self.call_cap} reached")

        missing = [a for a in spec.required_args if a not in args]
        if missing:
            self._deny(spec, args, DenyReason.BAD_ARGS, f"missing args: {missing}")
            raise ToolArgsInvalidError(f"{spec.name}: missing required args {missing}")

        for key, typ in spec.arg_types.items():
            if key in args and not isinstance(args[key], typ):
                got = type(args[key]).__name__
                self._deny(spec, args, DenyReason.BAD_ARGS, f"arg {key} must be {typ.__name__}, got {got}")
                raise ToolArgsInvalidError(f"{spec.name}: arg {key} must be {typ.__name__}, got {got}")

        if spec.host is not None and not self._host_allowed(spec.host):
            self._deny(spec, args, DenyReason.EGRESS_BLOCKED, f"host {spec.host} not on allowlist")
            raise EgressDeniedError(f"{spec.name}: host {spec.host} not on allowlist")

        if spec.kind is ToolKind.DESTRUCTIVE and spec.name not in self.allow_destructive:
            self._deny(spec, args, DenyReason.DESTRUCTIVE_BLOCKED, f"destructive {spec.name} not enabled")
            raise DestructiveActionDenied(f"{spec.name}: destructive action not enabled for this session")

        if self.spent_usd + spec.est_cost_usd > self.usd_cap + 1e-9:
            self._deny(spec, args, DenyReason.OVER_BUDGET, f"would exceed USD cap {self.usd_cap}")
            raise BudgetExceededError(
                f"{spec.name}: ${self.spent_usd + spec.est_cost_usd:.4f} would exceed cap ${self.usd_cap:.4f}"
            )

        self.calls += 1
        self.spent_usd += spec.est_cost_usd
        self.audit.append(
            AuditEvent(
                kind=EventKind.TOOL_OK,
                tool=spec.name,
                args_hash=self._maybe_hash(args),
                cost_usd=spec.est_cost_usd,
            )
        )

    def run(self, spec: ToolSpec, fn: Callable[..., Any], args: dict[str, Any]) -> Any:
        """Vet, then execute ``fn(**args)``. Raises a GovernanceError if denied."""
        self.vet(spec, args)
        return fn(**args)

    def audit_jsonl(self) -> str:
        """The full audit trail as newline-delimited JSON (one event per line)."""
        return "\n".join(json.dumps(e.to_dict()) for e in self.audit)
