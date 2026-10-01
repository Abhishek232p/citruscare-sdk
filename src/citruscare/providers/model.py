"""Provider-neutral model generation interfaces and implementations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Protocol

from citruscare.core.config import Settings
from citruscare.core.errors import ConfigurationError, ProviderError
from citruscare.core.messages import Message
from citruscare.providers.openai_compatible import (
    AsyncTransport,
    OpenAICompatibleProvider,
)


@dataclass(frozen=True, slots=True)
class ModelOutput:
    text: str
    model: str
    provider: str
    provenance: str = "MODEL GENERATED TEXT"
    structured: dict[str, object] | None = None
    latency_ms: float | None = None
    request_id: str | None = None
    token_usage: dict[str, int] | None = None
    cost_metadata: dict[str, float | str] | None = None
    provider_request_id: str | None = None

    def with_route(self, provider: str, model: str) -> ModelOutput:
        return replace(self, provider=provider, model=model)


class ModelProvider(Protocol):
    name: str
    model_name: str
    supports_structured_output: bool

    async def generate(self, messages: Sequence[Message]) -> ModelOutput: ...

    async def generate_structured(
        self, messages: Sequence[Message]
    ) -> dict[str, object]: ...

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]: ...


class MockModelProvider:
    """Deterministic, non-clinical provider for tests and synthetic demos."""

    name = "mock"
    model_name = "citruscare-demo-model"
    supports_structured_output = True

    async def generate(self, messages: Sequence[Message]) -> ModelOutput:
        started = perf_counter()
        text = (
            "Synthetic informational response. No diagnosis, prescription, or "
            "treatment decision was made."
        )
        return ModelOutput(
            text=text,
            model=self.model_name,
            provider=self.name,
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )

    async def generate_structured(
        self, messages: Sequence[Message]
    ) -> dict[str, object]:
        output = await self.generate(messages)
        return {"answer": output.text, "provenance": output.provenance}

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        output = await self.generate(messages)
        for word in output.text.split():
            yield f"{word} "


class OpenAICompatibleModelProvider:
    """ModelProvider adapter around the SDK's existing compatible provider."""

    name = "openai_compatible"
    supports_structured_output = True

    def __init__(
        self,
        settings: Settings,
        transport: AsyncTransport | None = None,
        *,
        include_message_names: bool = True,
    ) -> None:
        if not settings.api_key:
            raise ConfigurationError("Provider API credentials are required")
        self.model_name = settings.model
        self._provider = OpenAICompatibleProvider(
            settings,
            transport,
            include_message_names=include_message_names,
        )

    async def generate(self, messages: Sequence[Message]) -> ModelOutput:
        output = await self.generate_with_request_id(messages, None)
        return output

    async def generate_with_request_id(
        self, messages: Sequence[Message], request_id: str | None
    ) -> ModelOutput:
        try:
            turn, metadata = await self._provider.complete_with_metadata(
                messages, [], request_id=request_id
            )
        except ProviderError:
            raise
        if turn.tool_calls:
            raise ProviderError(
                "Tool calls must be routed through the CitrusCare agent runtime"
            )
        return ModelOutput(
            text=turn.content or "",
            model=self.model_name,
            provider=self.name,
            latency_ms=metadata["latency_ms"],
            request_id=request_id,
            token_usage=dict(metadata["usage"]),
            provider_request_id=metadata["provider_request_id"],
        )

    async def generate_structured(
        self, messages: Sequence[Message]
    ) -> dict[str, object]:
        output = await self.generate_structured_with_request_id(messages, None)
        if output.structured is None:
            raise ProviderError("Provider returned no structured model output")
        return output.structured

    async def generate_structured_with_request_id(
        self, messages: Sequence[Message], request_id: str | None
    ) -> ModelOutput:
        try:
            turn, metadata = await self._provider.complete_with_metadata(
                messages, [], request_id=request_id, structured=True
            )
        except ProviderError:
            raise
        if turn.tool_calls or not turn.content:
            raise ProviderError("Provider returned no structured JSON content")
        try:
            import json

            value = json.loads(turn.content)
        except (TypeError, ValueError) as exc:
            raise ProviderError("Provider returned invalid structured JSON") from exc
        if not isinstance(value, dict):
            raise ProviderError("Structured model output must be a JSON object")
        return ModelOutput(
            text=turn.content,
            model=self.model_name,
            provider=self.name,
            structured=value,
            latency_ms=metadata["latency_ms"],
            request_id=request_id,
            token_usage=dict(metadata["usage"]),
            provider_request_id=metadata["provider_request_id"],
        )

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        output = await self.generate(messages)
        for word in output.text.split():
            yield f"{word} "
