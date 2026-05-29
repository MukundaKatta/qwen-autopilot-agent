"""Minimal HTTP wrapper so the agent can run as a backend on Alibaba Cloud.

This is the deployable surface referenced by docs/alibaba-deploy.md. It is kept
separate from the package so the core stays dependency-free; this file needs
FastAPI + uvicorn (see the Dockerfile in the deploy guide).

    pip install -r requirements.txt fastapi uvicorn
    export DASHSCOPE_API_KEY=sk-...
    uvicorn server:app --host 0.0.0.0 --port 8080

POST /remediate  {"incident": "...", "allow_destructive": ["rollback_deploy"], "usd_cap": 0.5}
  -> {"report": {...}, "audit": [ ... ]}
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from qwen_autopilot import AutopilotAgent, GovernedSession, QwenClient
from qwen_autopilot.tools import FUNCS, INTERNAL_HOSTS, SPECS

app = FastAPI(title="qwen-autopilot-agent", version="0.1.0")


class RemediateRequest(BaseModel):
    incident: str
    # Default empty: nothing destructive runs unless the caller opts in per-request.
    allow_destructive: list[str] = []
    usd_cap: float = 0.50
    call_cap: int = 20
    model: str = "qwen-plus"


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "qwen_key_set": bool(os.environ.get("DASHSCOPE_API_KEY"))}


@app.post("/remediate")
def remediate(req: RemediateRequest) -> dict[str, Any]:
    session = GovernedSession(
        usd_cap=req.usd_cap,
        call_cap=req.call_cap,
        allowed_hosts=INTERNAL_HOSTS,
        allow_destructive=tuple(req.allow_destructive),
    )
    with session:
        agent = AutopilotAgent(QwenClient(model=req.model), session, SPECS, FUNCS)
        report = agent.run(req.incident)
    return {
        "report": report.to_dict(),
        "audit": [e.to_dict() for e in session.audit],
        "spent_usd": round(session.spent_usd, 6),
    }
