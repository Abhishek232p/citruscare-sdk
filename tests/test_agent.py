from __future__ import annotations

import unittest

from citruscare import (
    Agent,
    AssistantTurn,
    AuditError,
    MemoryAuditSink,
    ScriptedProvider,
    StepLimitExceeded,
    Tool,
    ToolCall,
    ToolExecutionError,
    ToolRegistry,
)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_tool_and_returns_final_response(self) -> None:
        tools = ToolRegistry()
        tools.register(
            Tool(
                name="lookup",
                description="Return a value for a key",
                parameters={
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                    "additionalProperties": False,
                },
                handler=lambda key: {"value": key.upper()},
            )
        )
        provider = ScriptedProvider(
            [
                AssistantTurn(
                    tool_calls=(ToolCall("call-1", "lookup", {"key": "status"}),)
                ),
                AssistantTurn(content="All systems are operational."),
            ]
        )
        audit = MemoryAuditSink()
        result = await Agent(provider, tools, audit_sink=audit).run("Check status")

        self.assertEqual(result.content, "All systems are operational.")
        self.assertEqual(result.turns, 2)
        self.assertEqual(result.messages[-2].content, '{"value":"STATUS"}')
        self.assertEqual(
            [event.event_type for event in audit.events],
            ["run_started", "tool_started", "tool_completed", "run_completed"],
        )
        self.assertNotIn("Check status", repr(audit.events))

    async def test_does_not_execute_tool_when_no_turn_remains(self) -> None:
        executed: list[bool] = []
        tools = ToolRegistry()
        tools.register(
            Tool(
                "mutate",
                "Mutate state",
                {"type": "object", "properties": {}},
                lambda: executed.append(True),
            )
        )
        provider = ScriptedProvider(
            [AssistantTurn(tool_calls=(ToolCall("1", "mutate", {}),))]
        )

        with self.assertRaises(StepLimitExceeded):
            await Agent(provider, tools, max_turns=1).run("Do it")
        self.assertEqual(executed, [])

    async def test_rejects_invalid_tool_arguments(self) -> None:
        tools = ToolRegistry()
        tools.register(
            Tool(
                "lookup",
                "Lookup a value",
                {
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                    "required": ["count"],
                },
                lambda count: count,
            )
        )
        with self.assertRaises(ToolExecutionError):
            await tools.invoke(ToolCall("1", "lookup", {"count": True}))

    async def test_normalizes_handler_failures_without_arguments(self) -> None:
        tools = ToolRegistry()

        def fail(secret: str) -> None:
            raise RuntimeError(f"failed for {secret}")

        tools.register(
            Tool(
                "fail",
                "Fail safely",
                {
                    "type": "object",
                    "properties": {"secret": {"type": "string"}},
                    "required": ["secret"],
                },
                fail,
            )
        )
        with self.assertRaises(ToolExecutionError) as raised:
            await tools.invoke(ToolCall("1", "fail", {"secret": "sensitive"}))
        self.assertNotIn("sensitive", str(raised.exception))

    async def test_supports_async_tool_handlers(self) -> None:
        async def handler(value: str) -> dict[str, str]:
            return {"value": value}

        tools = ToolRegistry()
        tools.register(
            Tool(
                "async_lookup",
                "Asynchronously look up a value",
                {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
                handler,
            )
        )
        result = await tools.invoke(
            ToolCall("call-async", "async_lookup", {"value": "ready"})
        )
        self.assertEqual(result, {"value": "ready"})

    async def test_surfaces_audit_sink_failure(self) -> None:
        class BrokenSink:
            def record(self, event: object) -> None:
                raise OSError("sink unavailable")

        with self.assertRaisesRegex(AuditError, "Could not record audit event"):
            await Agent(
                ScriptedProvider([AssistantTurn(content="unused")]),
                ToolRegistry(),
                audit_sink=BrokenSink(),
            ).run("A prompt that must not reach the audit sink")


if __name__ == "__main__":
    unittest.main()
