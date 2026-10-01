from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest

from citruscare.core.errors import ProviderError
from citruscare.core.messages import Message
from citruscare.models.router import ModelRouter
from citruscare.providers.model import ModelOutput


class FlakyProvider:
    name = "groq"
    model_name = "test-model"
    supports_structured_output = False

    def __init__(self, failures: int, *, retryable: bool = True) -> None:
        self.failures = failures
        self.retryable = retryable
        self.calls = 0

    async def generate(self, messages: Sequence[Message]) -> ModelOutput:
        del messages
        self.calls += 1
        if self.calls <= self.failures:
            raise ProviderError(
                "provider unavailable",
                code=(
                    "LLM_PROVIDER_RATE_LIMITED"
                    if self.retryable
                    else "LLM_PROVIDER_AUTH_FAILED"
                ),
                retryable=self.retryable,
                status_code=429 if self.retryable else 401,
            )
        return ModelOutput("done", self.model_name, self.name)

    async def generate_structured(
        self, messages: Sequence[Message]
    ) -> dict[str, object]:
        del messages
        raise ProviderError("Structured output unsupported")

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        del messages
        yield ""


def test_router_retries_transient_provider_errors_within_bound() -> None:
    provider = FlakyProvider(failures=2)
    router = ModelRouter(
        {"groq": provider},
        default_provider="groq",
        timeout_seconds=1,
        retries=2,
        retry_backoff_seconds=0,
    )

    result = asyncio.run(
        router.generate("general_information", (Message("user", "hello"),))
    )

    assert result.text == "done"
    assert provider.calls == 3


def test_router_does_not_retry_non_transient_provider_errors() -> None:
    provider = FlakyProvider(failures=5, retryable=False)
    router = ModelRouter(
        {"groq": provider},
        default_provider="groq",
        timeout_seconds=1,
        retries=3,
        retry_backoff_seconds=0,
    )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(router.generate("general_information", (Message("user", "hello"),)))

    assert provider.calls == 1
    assert caught.value.status_code == 401
    assert caught.value.provider_name == "groq"
    assert caught.value.model_name == "test-model"
