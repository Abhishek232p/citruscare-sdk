"""Deterministic provider useful for tests, examples, and local development."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

from citruscare.core.errors import ProviderError
from citruscare.core.messages import AssistantTurn, Message


class ScriptedProvider:
    def __init__(self, turns: Sequence[AssistantTurn]) -> None:
        self._turns = deque(turns)

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]],
    ) -> AssistantTurn:
        del messages, tools
        if not self._turns:
            raise ProviderError("ScriptedProvider has no remaining responses")
        return self._turns.popleft()
