"""Groq adapter over CitrusCare's existing OpenAI-compatible transport."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace

from citruscare.core.config import Settings
from citruscare.core.errors import ConfigurationError, ProviderError
from citruscare.providers.model import OpenAICompatibleModelProvider
from citruscare.providers.openai_compatible import AsyncTransport


class GroqModelProvider(OpenAICompatibleModelProvider):
    """Server-side Groq Chat Completions provider with optional model discovery."""

    name = "groq"
    default_base_url = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: AsyncTransport | None = None,
        discovery_ttl_seconds: float | None = None,
    ) -> None:
        if not (settings.groq_api_key or settings.api_key):
            raise ConfigurationError("GROQ_API_KEY is required for the Groq provider")
        if not settings.model.strip():
            raise ConfigurationError("CITRUSCARE_MODEL must name a Groq model")
        if discovery_ttl_seconds is not None and discovery_ttl_seconds <= 0:
            raise ValueError("discovery_ttl_seconds must be positive")
        groq_settings = replace(
            settings,
            api_key=settings.groq_api_key or settings.api_key,
            base_url=(
                self.default_base_url
                if settings.base_url == "https://api.openai.com/v1"
                else settings.base_url
            ),
        )
        super().__init__(
            groq_settings,
            transport,
            include_message_names=False,
        )
        self.discovery_ttl_seconds = discovery_ttl_seconds or 300.0
        self._model_cache: tuple[float, tuple[str, ...]] | None = None
        self._model_cache_lock = asyncio.Lock()

    async def discover_models(self, *, refresh: bool = False) -> tuple[str, ...]:
        now = time.monotonic()
        cached = self._model_cache
        if (
            not refresh
            and cached is not None
            and now - cached[0] < self.discovery_ttl_seconds
        ):
            return cached[1]
        async with self._model_cache_lock:
            now = time.monotonic()
            cached = self._model_cache
            if (
                not refresh
                and cached is not None
                and now - cached[0] < self.discovery_ttl_seconds
            ):
                return cached[1]
            get_json = getattr(self._provider.transport, "get_json", None)
            if not callable(get_json):
                raise ProviderError(
                    "Configured transport does not support model discovery",
                    code="LLM_MODEL_DISCOVERY_UNAVAILABLE",
                )
            status, body = await get_json(
                f"{self._provider.settings.base_url.rstrip('/')}/models",
                {
                    "Authorization": f"Bearer {self._provider.settings.api_key}",
                    "Accept": "application/json",
                },
                self._provider.settings.request_timeout,
            )
            if status < 200 or status >= 300:
                from citruscare.providers.openai_compatible import (
                    _http_provider_error,
                )

                raise _http_provider_error(status)
            raw_models = body.get("data")
            if not isinstance(raw_models, list):
                raise ProviderError(
                    "Model discovery response is malformed",
                    code="LLM_PROVIDER_INVALID_RESPONSE",
                )
            model_ids = tuple(
                sorted(
                    {
                        item["id"]
                        for item in raw_models
                        if isinstance(item, dict)
                        and isinstance(item.get("id"), str)
                        and item["id"]
                    }
                )
            )
            if not model_ids:
                raise ProviderError(
                    "Model discovery returned no model identifiers",
                    code="LLM_PROVIDER_INVALID_RESPONSE",
                )
            self._model_cache = (time.monotonic(), model_ids)
            return model_ids

    async def validate_configured_model(self) -> str:
        available = await self.discover_models()
        if self.model_name not in available:
            raise ConfigurationError(
                f"Configured Groq model '{self.model_name}' is not available"
            )
        return self.model_name
