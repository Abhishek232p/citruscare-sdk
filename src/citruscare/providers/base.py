"""Provider protocol."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from citruscare.core.messages import AssistantTurn, Message


class Provider(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]],
    ) -> AssistantTurn: ...
