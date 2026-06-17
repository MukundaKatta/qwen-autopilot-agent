# qwen-autopilot-agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab.svg)](https://www.python.org)
[![Hackathon: Qwen Cloud](https://img.shields.io/badge/Hackathon-Qwen%20Cloud%20%C2%B7%20Autopilot-615ced.svg)](https://qwencloud-hackathon.devpost.com/)

An autonomous ops-remediation agent on **Qwen Cloud** that diagnoses an incident and
takes the fix end to end, with a hard **governance layer** around every action it
takes. The agent can restart, scale, and roll back services on its own, but it can
only ever do what a cost cap, an egress allowlist, tool-arg validation, and a
destructive-action gate allow, and every decision lands in an append-only audit log.

Built for the **Global AI Hackathon Series with Qwen Cloud**, Autopilot Agent track
(an agent that automates a real-world business workflow end to end).

## Why this is different

Most agent demos give the model the keys and hope. The moment an autopilot agent can
restart prod or move money, "hope" is not a control. The value here is the
deterministic layer between the model and the world:

- **Cost cap** — projected spend is checked before each action; over-budget actions never run.
- **Egress allowlist** — a tool may only reach approved hosts (wildcards supported).
- **Tool-arg validation** — required args present and correctly typed, or the call is refused.
- **Destructive-action gate** — `restart` / `scale` / `rollback` only fire when explicitly enabled.
- **Audit trail** — every allow and deny is one JSONL line; args are hashed so the log is safe to share.

A denied call is not a crash: the reason is fed back to the model so it adapts
(smaller action, different host, fixed args), the way a careful operator would.

## Architecture

```
incident text
     │
     ▼
┌──────────────────┐   plan: tool calls    ┌────────────────────┐
│  AutopilotAgent  │ ───────────────────▶  │  Qwen on Qwen Cloud │
│ (bounded loop)   │ ◀───────────────────  │ (DashScope OpenAI   │
└──────────────────┘   tool calls / final  │  compatible API)    │
     │ every tool call                     └────────────────────┘
     ▼
┌────────────────────────────────────────────────────┐
│           GovernedSession  (the leash)               │
│  call cap · arg validation · egress allowlist        │
│  destructive gate · USD cost cap                     │
│            ── append-only audit (JSONL) ──           │
└────────────────────────────────────────────────────┘
     │ only if every guard passes
     ▼
┌──────────────────┐
│   ops tools       │  metrics / logs / deploys      (read)
│ (Alibaba Cloud)   │  restart / scale / rollback    (destructive)
└──────────────────┘
```

Full write-up with the security boundaries in [docs/architecture.md](docs/architecture.md).

## See it work with no credentials

The agent core and governance layer are pure standard library, so the full stack
(agent loop → governance → tools) runs offline against a scripted fake Qwen client.
No API key, no network, no infrastructure.

```bash
python examples/offline_demo.py
```

It drives one incident and shows reads allowed, a malformed action blocked by
arg validation, a destructive restart blocked because it was not enabled, and a
rollback allowed because the operator enabled exactly that action, then a second
run where the cost cap stops an over-budget action before it executes.

```bash
python -m unittest discover -s tests    # 33 tests, standard library only
```

## Use it from code

```python
from qwen_autopilot import AutopilotAgent, GovernedSession, QwenClient
from qwen_autopilot.tools import SPECS, FUNCS, INTERNAL_HOSTS

session = GovernedSession(
    usd_cap=0.50,                          # hard spend ceiling for this run
    allowed_hosts=INTERNAL_HOSTS,          # only *.ops.internal
    allow_destructive=("rollback_deploy",) # the only autonomous action permitted
)
agent = AutopilotAgent(QwenClient(model="qwen-plus"), session, SPECS, FUNCS)

with session:
    report = agent.run("checkout is throwing 41% errors and p95 is 5.2s since 08:00")

print(report.root_cause, report.actions_taken)
print(session.audit_jsonl())
```

`QwenClient` reads `DASHSCOPE_API_KEY` and calls Qwen models through the DashScope
OpenAI-compatible endpoint. Swap the stub tool bodies in `qwen_autopilot/tools.py`
for real Alibaba Cloud / Kubernetes / observability calls.

## API reference

Everything below is importable from the top-level `qwen_autopilot` package.

### `GovernedSession`

The leash around every tool call. Construct it with the policy for one run, use
it as a context manager so a `SESSION_CLOSE` audit event is always recorded.

```python
GovernedSession(
    *,
    usd_cap: float = 1.0,                 # hard spend ceiling for the run
    call_cap: int = 20,                   # max successful tool calls
    allowed_hosts: tuple[str, ...] = (),  # fnmatch patterns, e.g. ("*.ops.internal",)
    allow_destructive: tuple[str, ...] = (),  # destructive tool names that may run
    hash_args: bool = True,               # SHA-256 args in the audit log
)
```

- `run(spec, fn, args) -> Any` — vet the call against all five guards, then
  execute `fn(**args)`. Raises a `GovernanceError` subclass if denied; the
  function body never runs on a denial.
- `vet(spec, args) -> None` — run the guards without executing (raises on deny).
- `audit_jsonl() -> str` — the full audit trail as newline-delimited JSON.
- Attributes: `spent_usd`, `calls`, `audit` (list of `AuditEvent`).

Each guard raises its own typed exception, all subclasses of `GovernanceError`
with a `.reason` (`DenyReason`): `CallCapExceededError`, `ToolArgsInvalidError`,
`EgressDeniedError`, `DestructiveActionDenied`, `BudgetExceededError`.

### `AutopilotAgent`

```python
AutopilotAgent(client, session, specs, funcs, loop_cap=8)
agent.run(incident: str) -> RemediationReport
```

The bounded loop. `client` is any object with a `chat(messages, tools=...)`
method returning an `AssistantTurn` (`QwenClient` for live, `FakeQwenClient` for
offline). `specs` and `funcs` are the declarative tool registry (see
`qwen_autopilot.tools.SPECS` / `FUNCS`). The loop runs at most `loop_cap` turns.

### `RemediationReport`

Returned by `agent.run`. Fields: `incident`, `root_cause`, `steps` (per-call log
including denials), `actions_taken` (non-read tools that executed), `resolved`
(true only when at least one remediating action ran). `to_dict()` serializes it.

### Clients and schemas

- `QwenClient(model="qwen-plus", api_key=None, base_url=...)` — live DashScope
  client. Needs the optional `openai` SDK and `DASHSCOPE_API_KEY`.
- `FakeQwenClient(script: list[AssistantTurn])` — replays a fixed list of turns
  for offline demos and tests, same `chat` interface, no network.
- `tool_schemas(specs) -> list[dict]` — render `ToolSpec`s into OpenAI/Qwen
  function-calling tool schemas.

## Development

The library and its tests are standard library only, so there is nothing to
install:

```bash
python -m unittest discover -s tests    # 33 tests
python examples/offline_demo.py         # end-to-end offline run
```

## Running on Qwen Cloud + Alibaba Cloud

The hackathon requires the backend to run on Alibaba Cloud and use Qwen models.
Step-by-step (API key, deployment, proof-of-deployment recording) is in
[docs/alibaba-deploy.md](docs/alibaba-deploy.md).

## Layout

```
qwen_autopilot/
  types.py        # closed enums + dataclasses (ToolSpec, AuditEvent, RemediationReport)
  governance.py   # GovernedSession: the five guards + audit trail
  tools.py        # ops toolset (read + destructive) with declarative specs
  qwen_client.py  # live Qwen Cloud client + offline FakeQwenClient (same interface)
  agent.py        # the bounded Autopilot loop
examples/offline_demo.py   # credential-free end-to-end demo
tests/                     # 33 tests (governance + agent + client), zero deps
docs/architecture.md       # architecture + security boundaries
docs/alibaba-deploy.md     # Qwen Cloud / Alibaba Cloud deployment guide
```

## License

MIT. See [LICENSE](LICENSE).
