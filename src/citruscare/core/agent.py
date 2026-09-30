"""A small provider-neutral agent loop with bounded tool execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from citruscare.core.errors import AuditError, StepLimitExceeded
from citruscare.core.messages import AgentResult, Message
from citruscare.governance.audit import AuditEvent

if TYPE_CHECKING:
    from citruscare.governance.audit import AuditSink
    from citruscare.providers.base import Provider
    from citruscare.tools.registry import ToolRegistry


@dataclass(slots=True)
class Agent:
    provider: Provider
    tools: ToolRegistry
    instructions: str = "You are a helpful assistant."
    max_turns: int = 8
    audit_sink: AuditSink | None = None

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError("max_turns must be at least one")

    async def run(self, prompt: str) -> AgentResult:
        """Run one conversation; tool arguments and model content are not audited."""
        messages = [
            Message(role="system", content=self.instructions),
            Message(role="user", content=prompt),
        ]
        self._audit("run_started")
        try:
            for turn_number in range(1, self.max_turns + 1):
                turn = await self.provider.complete(
                    messages, self.tools.provider_schemas()
                )
                messages.append(
                    Message(
                        role="assistant",
                        content=turn.content or "",
                        tool_calls=turn.tool_calls,
                    )
                )
                if not turn.tool_calls:
                    self._audit("run_completed", {"turns": turn_number})
                    return AgentResult(
                        content=turn.content or "",
                        turns=turn_number,
                        messages=tuple(messages),
                    )
                if turn_number == self.max_turns:
                    raise StepLimitExceeded(
                        f"Agent requested tools after reaching {self.max_turns} turns"
                    )
                for call in turn.tool_calls:
                    self._audit("tool_started", {"tool": call.name})
                    output = await self.tools.invoke(call)
                    self._audit("tool_completed", {"tool": call.name})
                    messages.append(
                        Message(
                            role="tool",
                            content=json.dumps(output, separators=(",", ":")),
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
            raise StepLimitExceeded(
                f"Agent did not finish within {self.max_turns} turns"
            )
        except Exception as exc:
            try:
                self._audit("run_failed", {"error_type": type(exc).__name__})
            except AuditError:
                raise
            raise

    def _audit(
        self, event_type: str, metadata: dict[str, object] | None = None
    ) -> None:
        if self.audit_sink is None:
            return
        try:
            self.audit_sink.record(AuditEvent.create(event_type, metadata or {}))
        except Exception as exc:
            raise AuditError(f"Could not record audit event '{event_type}'") from exc
