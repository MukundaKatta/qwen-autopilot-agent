"""Tests for the offline client and the tool-schema renderer.

These cover the standard-library-only parts of ``qwen_client`` (schema rendering
and the FakeQwenClient replay). The live ``QwenClient`` is not exercised because
it requires the optional ``openai`` dependency and a network call.

    python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qwen_autopilot.qwen_client import FakeQwenClient, tool_schemas  # noqa: E402
from qwen_autopilot.tools import SPECS  # noqa: E402
from qwen_autopilot.types import AssistantTurn, ToolCall, ToolKind, ToolSpec  # noqa: E402


class ToolSchemaTests(unittest.TestCase):
    def test_renders_one_function_per_spec(self):
        schemas = tool_schemas(SPECS)
        self.assertEqual(len(schemas), len(SPECS))
        self.assertTrue(all(s["type"] == "function" for s in schemas))

    def test_maps_python_types_to_json_types(self):
        spec = ToolSpec(
            "demo",
            ToolKind.WRITE,
            description="d",
            required_args=("s",),
            arg_types={"s": str, "n": int, "x": float, "b": bool},
        )
        fn = tool_schemas({"demo": spec})[0]["function"]
        props = fn["parameters"]["properties"]
        self.assertEqual(props["s"]["type"], "string")
        self.assertEqual(props["n"]["type"], "integer")
        self.assertEqual(props["x"]["type"], "number")
        self.assertEqual(props["b"]["type"], "boolean")

    def test_required_args_propagated(self):
        fn = tool_schemas(SPECS)[0]["function"]
        self.assertIn("required", fn["parameters"])
        self.assertEqual(fn["parameters"]["type"], "object")

    def test_unknown_type_defaults_to_string(self):
        spec = ToolSpec("d", ToolKind.READ, arg_types={"blob": dict})
        props = tool_schemas({"d": spec})[0]["function"]["parameters"]["properties"]
        self.assertEqual(props["blob"]["type"], "string")


class FakeClientTests(unittest.TestCase):
    def test_replays_script_in_order(self):
        script = [
            AssistantTurn(content="one", tool_calls=[ToolCall("get_metrics", {"service": "a"})]),
            AssistantTurn(content="two", final=True),
        ]
        client = FakeQwenClient(script)
        first = client.chat([])
        second = client.chat([])
        self.assertEqual(first.content, "one")
        self.assertEqual(second.content, "two")
        self.assertTrue(second.final)

    def test_returns_final_turn_when_script_exhausted(self):
        client = FakeQwenClient([])
        turn = client.chat([])
        self.assertTrue(turn.final)
        self.assertEqual(turn.tool_calls, [])

    def test_does_not_mutate_caller_script(self):
        script = [AssistantTurn(content="x", final=True)]
        FakeQwenClient(script).chat([])
        self.assertEqual(len(script), 1)  # constructor copied the list


class PublicSurfaceTests(unittest.TestCase):
    def test_top_level_exports_are_importable(self):
        import qwen_autopilot as qa

        for name in qa.__all__:
            self.assertTrue(hasattr(qa, name), f"{name} declared in __all__ but missing")

    def test_tool_schemas_exported_at_top_level(self):
        import qwen_autopilot as qa

        self.assertIs(qa.tool_schemas, tool_schemas)

    def test_version_is_a_string(self):
        import qwen_autopilot as qa

        self.assertIsInstance(qa.__version__, str)


if __name__ == "__main__":
    unittest.main()
