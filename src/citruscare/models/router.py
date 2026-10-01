"""Task-aware model routing with bounded timeout and retries."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from time import perf_counter
from typing import TYPE_CHECKING

from citruscare.core.errors import ProviderError
from citruscare.providers.model import ModelOutput

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

    from citruscare.core.messages import Message
    from citruscare.providers.model import ModelProvider


@dataclass(frozen=True, slots=True)
class ModelRoute:
    provider_name: str
    model_name: str
    supports_structured_output: bool = False


class ModelRouter:
    TASK_ALIASES = {
        "general": "general_information",
        "reasoning": "clinical_summary",
        "structured_output": "documentation_assistance",
        "summarization": "clinical_summary",
        "retrieval_answer": "evidence_search",
        "documentation": "documentation_assistance",
    }

    def __init__(
        self,
        providers: Mapping[str, ModelProvider],
        routes: Mapping[str, str] | None = None,
        default_provider: str = "mock",
        fallback_providers: Sequence[str] = (),
        timeout_seconds: float = 15.0,
        retries: int = 0,
        retry_backoff_seconds: float = 0.1,
    ) -> None:
        if default_provider not in providers:
            raise ValueError(f"Default provider '{default_provider}' is not configured")
        if any(name not in providers for name in (routes or {}).values()):
            raise ValueError("Task route references an unknown provider")
        if any(name not in providers for name in fallback_providers):
            raise ValueError("Fallback route references an unknown provider")
        if timeout_seconds <= 0 or retries < 0 or retry_backoff_seconds < 0:
            raise ValueError(
                "timeout must be positive and retry limits/backoff non-negative"
            )
        self._providers = dict(providers)
        self._routes = dict(routes or {})
        self._default_provider = default_provider
        self._fallback_providers = tuple(fallback_providers)
        self._timeout_seconds = timeout_seconds
        self._retries = retries
        self._retry_backoff_seconds = retry_backoff_seconds

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    def route_for(self, task: str) -> ModelRoute:
        task = self.TASK_ALIASES.get(task, task)
        provider_name = self._routes.get(task, self._default_provider)
        provider = self._providers[provider_name]
        return ModelRoute(
            provider_name=provider_name,
            model_name=provider.model_name,
            supports_structured_output=provider.supports_structured_output,
        )

    def provider_status(self) -> list[dict[str, object]]:
        return [
            {
                "name": name,
                "model": provider.model_name,
                "configured": True,
                "available": True,
                "supports_structured_output": provider.supports_structured_output,
                "is_default": name == self._default_provider,
                "is_fallback": name in self._fallback_providers,
            }
            for name, provider in sorted(self._providers.items())
        ]

    def provider(self, name: str) -> ModelProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"Provider '{name}' is not configured") from exc

    async def generate(self, task: str, messages: Sequence[Message]) -> ModelOutput:
        return await self.generate_for_request(task, messages, None)

    async def generate_for_request(
        self, task: str, messages: Sequence[Message], request_id: str | None
    ) -> ModelOutput:
        task = self.TASK_ALIASES.get(task, task)
        provider_names = [self._routes.get(task, self._default_provider)]
        provider_names.extend(
            name for name in self._fallback_providers if name not in provider_names
        )
        last_error: Exception | None = None
        last_provider_name: str | None = None
        for provider_name in provider_names:
            last_provider_name = provider_name
            provider = self._providers[provider_name]
            for attempt in range(self._retries + 1):
                try:
                    started = perf_counter()
                    request_method = getattr(provider, "generate_with_request_id", None)
                    operation = (
                        request_method(messages, request_id)
                        if callable(request_method)
                        else provider.generate(messages)
                    )
                    output = await asyncio.wait_for(
                        operation, timeout=self._timeout_seconds
                    )
                    return replace(
                        output.with_route(provider_name, provider.model_name),
                        latency_ms=output.latency_ms
                        if output.latency_ms is not None
                        else round((perf_counter() - started) * 1000, 3),
                        request_id=request_id,
                    )
                except (ProviderError, TimeoutError) as exc:
                    last_error = exc
                    retryable = isinstance(exc, TimeoutError) or exc.retryable
                    if attempt < self._retries and retryable:
                        await asyncio.sleep(
                            min(self._retry_backoff_seconds * (2**attempt), 1.0)
                        )
                        continue
                    break
        if last_error is None:
            raise ProviderError("No configured model route is available")
        if isinstance(last_error, ProviderError):
            raise ProviderError(
                "All configured model providers failed",
                code=last_error.code,
                retryable=last_error.retryable,
                status_code=last_error.status_code,
                provider_name=last_provider_name,
                model_name=(
                    self._providers[last_provider_name].model_name
                    if last_provider_name
                    else None
                ),
            ) from last_error
        raise ProviderError(
            "All configured model providers failed",
            code="LLM_PROVIDER_TIMEOUT",
            status_code=408,
            provider_name=last_provider_name,
            model_name=(
                self._providers[last_provider_name].model_name
                if last_provider_name
                else None
            ),
        ) from last_error

    async def generate_structured(
        self, task: str, messages: Sequence[Message]
    ) -> tuple[ModelOutput, dict[str, Any]]:
        return await self.generate_structured_for_request(task, messages, None)

    async def generate_structured_for_request(
        self, task: str, messages: Sequence[Message], request_id: str | None
    ) -> tuple[ModelOutput, dict[str, Any]]:
        task = self.TASK_ALIASES.get(task, task)
        provider_names = [self._routes.get(task, self._default_provider)]
        provider_names.extend(
            name for name in self._fallback_providers if name not in provider_names
        )
        last_error: Exception | None = None
        last_provider_name: str | None = None
        for provider_name in provider_names:
            last_provider_name = provider_name
            provider = self._providers[provider_name]
            if not provider.supports_structured_output:
                last_error = ProviderError(
                    f"Provider '{provider_name}' does not support structured output"
                )
                continue
            for attempt in range(self._retries + 1):
                try:
                    started = perf_counter()
                    structured_method = getattr(
                        provider, "generate_structured_with_request_id", None
                    )
                    operation = (
                        structured_method(messages, request_id)
                        if callable(structured_method)
                        else provider.generate_structured(messages)
                    )
                    value = await asyncio.wait_for(
                        operation, timeout=self._timeout_seconds
                    )
                    if isinstance(value, ModelOutput):
                        if value.structured is None:
                            raise ProviderError(
                                "Structured provider returned no structured value"
                            )
                        return (
                            replace(
                                value.with_route(provider_name, provider.model_name),
                                request_id=request_id,
                            ),
                            value.structured,
                        )
                    if not isinstance(value, dict):
                        raise ProviderError(
                            "Structured model output must be a JSON object"
                        )
                    try:
                        serialized = json.dumps(value)
                    except (TypeError, ValueError) as exc:
                        raise ProviderError(
                            "Structured model output must contain JSON values"
                        ) from exc
                    output = ModelOutput(
                        text=serialized,
                        model=provider.model_name,
                        provider=provider_name,
                        structured=value,
                        latency_ms=round((perf_counter() - started) * 1000, 3),
                        request_id=request_id,
                    )
                    return output, value
                except (ProviderError, TimeoutError) as exc:
                    last_error = exc
                    retryable = isinstance(exc, TimeoutError) or exc.retryable
                    if attempt < self._retries and retryable:
                        await asyncio.sleep(
                            min(self._retry_backoff_seconds * (2**attempt), 1.0)
                        )
                        continue
                    break
        if last_error is None:
            raise ProviderError("No configured structured model route is available")
        if isinstance(last_error, ProviderError):
            raise ProviderError(
                "All configured structured model providers failed",
                code=last_error.code,
                retryable=last_error.retryable,
                status_code=last_error.status_code,
                provider_name=last_provider_name,
                model_name=(
                    self._providers[last_provider_name].model_name
                    if last_provider_name
                    else None
                ),
            ) from last_error
        raise ProviderError(
            "All configured structured model providers failed",
            code="LLM_PROVIDER_TIMEOUT",
            status_code=408,
            provider_name=last_provider_name,
            model_name=(
                self._providers[last_provider_name].model_name
                if last_provider_name
                else None
            ),
        ) from last_error
