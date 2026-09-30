"""Run a local, deterministic agent without network access or credentials."""

import asyncio

from citruscare import (
    Agent,
    AssistantTurn,
    ScriptedProvider,
    Tool,
    ToolCall,
    ToolRegistry,
)


async def main() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="lookup_reference",
            description="Look up a non-sensitive reference identifier",
            parameters={
                "type": "object",
                "properties": {"identifier": {"type": "string"}},
                "required": ["identifier"],
                "additionalProperties": False,
            },
            handler=lambda identifier: {"found": identifier == "demo"},
        )
    )
    provider = ScriptedProvider(
        [
            AssistantTurn(
                tool_calls=(
                    ToolCall("demo-call", "lookup_reference", {"identifier": "demo"}),
                )
            ),
            AssistantTurn(content="The demonstration reference was found."),
        ]
    )
    result = await Agent(provider, tools).run("Check the demonstration reference.")
    print(result.content)


if __name__ == "__main__":
    asyncio.run(main())
