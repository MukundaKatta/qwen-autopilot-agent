# Architecture

qwen-autopilot-agent is three layers: the **model** (Qwen on Qwen Cloud) proposes,
the **governance layer** disposes, and the **tools** act. The model never touches a
tool directly; every call is mediated.

## Data flow

```
                          ┌─────────────────────────────────────┐
                          │            Qwen Cloud               │
                          │   qwen-plus / qwen-max (DashScope    │
                          │   OpenAI-compatible /chat endpoint)  │
                          └───────────────▲─────────────────────┘
        tool schemas + messages           │  assistant turn
        (system, incident, tool results)  │  (content + tool_calls)
                          ┌───────────────┴─────────────────────┐
                          │           AutopilotAgent            │
                          │  - bounded loop (loop_cap)          │
                          │  - normalizes model output           │
                          │  - feeds denial reasons back         │
                          └───────────────┬─────────────────────┘
                                          │ for each proposed tool call
                                          ▼
        ┌──────────────────── GovernedSession (trust boundary) ───────────────────┐
        │  1. call cap            calls + 1 > cap            -> CallCapExceeded     │
        │  2. arg validation      missing / wrong-typed arg  -> ToolArgsInvalid     │
        │  3. egress allowlist    host not matched           -> EgressDenied        │
        │  4. destructive gate    DESTRUCTIVE & not enabled  -> DestructiveDenied   │
        │  5. cost cap            spent + cost > usd_cap      -> BudgetExceeded      │
        │                                                                           │
        │  pass  -> increment counters, log TOOL_OK, execute                        │
        │  fail  -> log TOOL_DENIED / BUDGET_DENIED, raise (call never executes)    │
        │  append-only audit trail (JSONL), tool args hashed                        │
        └───────────────────────────────────┬───────────────────────────────────────┘
                                             │ only if all five guards pass
                                             ▼
                          ┌─────────────────────────────────────┐
                          │      Tools (run on Alibaba Cloud)    │
                          │  read:        get_metrics, get_logs, │
                          │               list_recent_deploys    │
                          │  destructive: restart_service,       │
                          │               scale_service,         │
                          │               rollback_deploy        │
                          └─────────────────────────────────────┘
```

## The trust boundary

The dashed box is the only place that decides what reaches the world. Two
properties make it trustworthy:

1. **The model's view of a tool is never trusted.** Guards read the server-side
   `ToolSpec` (kind, required args, arg types, host, cost), not anything the model
   sends. A model that "claims" a call is cheap or read-only cannot bypass the gate.
2. **Counters only advance on full success.** A denied call charges no budget and
   consumes no call-cap slot, so a refused action cannot starve the run, and the
   ledger in the audit log always reconciles.

## Failure handling

A denied call returns a structured `{"denied": true, "reason": ...}` to the model
instead of throwing the run away. The agent records the denial as a step and lets
the model adapt within the same bounded loop. If the loop hits `loop_cap` without a
resolution, the agent stops and reports `resolved: false` rather than spinning.

## Audit

Every event is one JSONL line with a closed `kind`
(`tool_ok` / `tool_denied` / `budget_denied` / `session_close`), the tool, the deny
reason (if any), a 16-char SHA-256 hash of the args, and the cost. Hashing by
default means the log is safe to ship to a SIEM without leaking payloads, while
still letting you correlate identical calls.
