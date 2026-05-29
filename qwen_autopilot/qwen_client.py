"""Qwen Cloud client plus an offline fake with the same interface.

The live client talks to Qwen models through the DashScope OpenAI-compatible
endpoint, so the standard ``openai`` SDK works unchanged. The fake replays a
scripted list of turns, which is what powers the offline demo and the tests with
no API key and no network.
"""

from __future__ import annotations

import os
from typing import Any

from .types import AssistantTurn, ToolCall, ToolSpec

# Qwen Cloud / DashScope international OpenAI-compatible base URL.
DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"


def tool_schemas(specs: dict[str, ToolSpec]) -> list[dict[str, Any]]:
    """Render ToolSpecs into OpenAI/Qwen function-calling tool schemas."""
    _json_type = {str: "string", int: "integer", float: "number", bool: "boolean"}
    out: list[dict[str, Any]] = []
    for spec in specs.values():
        props = {
            name: {"type": _json_type.get(typ, "string")} for name, typ in spec.arg_types.items()
        }
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": list(spec.required_args),
                    },
                },
            }
        )
    return out


class QwenClient:
    """Live Qwen Cloud client via the DashScope OpenAI-compatible API.

    Requires ``pip install openai`` and a ``DASHSCOPE_API_KEY`` (or pass api_key).
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str = DASHSCOPE_BASE_URL,
    ) -> None:
        from openai import OpenAI  # optional dependency; only needed for live runs

        key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        if not key:
            raise RuntimeError("set DASHSCOPE_API_KEY or pass api_key to use the live Qwen client")
        self.model = model
        self._client = OpenAI(api_key=key, base_url=base_url)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> AssistantTurn:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
        )
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            import json

            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(name=tc.function.name, args=args))
        return AssistantTurn(content=msg.content or "", tool_calls=calls, final=not calls)


class FakeQwenClient:
    """Offline client that replays a fixed list of AssistantTurns in order.

    Lets the full agent loop run with no key and no network, so the demo and
    tests exercise the real governance + agent code paths deterministically.
    """

    def __init__(self, script: list[AssistantTurn]) -> None:
        self._script = list(script)
        self._i = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> AssistantTurn:
        if self._i >= len(self._script):
            # Nothing scripted left: end the run cleanly.
            return AssistantTurn(content="(no further actions)", final=True)
        turn = self._script[self._i]
        self._i += 1
        return turn
