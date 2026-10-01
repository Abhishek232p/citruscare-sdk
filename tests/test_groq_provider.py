from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient

from citruscare.api.app import create_app
from citruscare.core.config import Settings
from citruscare.core.errors import ConfigurationError
from citruscare.core.messages import Message
from citruscare.intelligence.orchestrator import create_demo_orchestrator
from citruscare.providers.groq import GroqModelProvider


class FakeGroqTransport:
    def __init__(self) -> None:
        self.get_calls: list[tuple[str, Mapping[str, str], float]] = []
        self.post_calls: list[
            tuple[str, Mapping[str, str], Mapping[str, Any], float]
        ] = []

    async def get_json(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        self.get_calls.append((url, headers, timeout))
        return 200, {"data": [{"id": "llama-3.3-70b-versatile"}]}

    async def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        self.post_calls.append((url, headers, payload, timeout))
        return 200, {
            "choices": [
                {"message": {"content": "General education.", "tool_calls": []}}
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }


class UnauthorizedGroqTransport(FakeGroqTransport):
    async def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        self.post_calls.append((url, headers, payload, timeout))
        return 401, {}


def test_groq_provider_uses_server_side_key_and_openai_compatible_api() -> None:
    transport = FakeGroqTransport()
    provider = GroqModelProvider(
        Settings(
            groq_api_key="test-groq-key",
            model="llama-3.3-70b-versatile",
        ),
        transport=transport,
    )

    output = asyncio.run(
        provider.generate_with_request_id(
            (Message("user", "Explain a term.", name="user-label"),), "request-123"
        )
    )

    assert output.provider == "groq"
    assert output.model == "llama-3.3-70b-versatile"
    assert transport.post_calls[0][0] == (
        "https://api.groq.com/openai/v1/chat/completions"
    )
    assert transport.post_calls[0][1]["Authorization"] == "Bearer test-groq-key"
    assert "name" not in transport.post_calls[0][2]["messages"][0]
    assert "test-groq-key" not in repr(provider._provider.settings)


def test_model_discovery_is_explicit_cached_and_can_be_refreshed() -> None:
    transport = FakeGroqTransport()
    provider = GroqModelProvider(
        Settings(groq_api_key="test-groq-key", model="llama-3.3-70b-versatile"),
        transport=transport,
    )

    async def discover_twice_and_refresh() -> None:
        assert await provider.discover_models() == ("llama-3.3-70b-versatile",)
        assert await provider.discover_models() == ("llama-3.3-70b-versatile",)
        assert len(transport.get_calls) == 1
        assert transport.get_calls[0][0] == "https://api.groq.com/openai/v1/models"
        assert transport.get_calls[0][1]["Authorization"] == "Bearer test-groq-key"
        assert await provider.discover_models(refresh=True) == (
            "llama-3.3-70b-versatile",
        )

    asyncio.run(discover_twice_and_refresh())
    assert len(transport.get_calls) == 2


def test_model_discovery_validates_configured_model() -> None:
    provider = GroqModelProvider(
        Settings(groq_api_key="test-groq-key", model="not-in-catalog"),
        transport=FakeGroqTransport(),
    )

    async def validate_model() -> None:
        with pytest.raises(ConfigurationError, match="not available"):
            await provider.validate_configured_model()

    asyncio.run(validate_model())


def test_groq_provider_requires_credentials() -> None:
    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        GroqModelProvider(Settings(model="llama-3.3-70b-versatile"))


def test_groq_environment_requires_model_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CITRUSCARE_MODEL_PROVIDER", "groq")
    monkeypatch.setenv("CITRUSCARE_MODEL_ROUTES", "{}")
    monkeypatch.setenv("CITRUSCARE_FALLBACK_PROVIDER", "")
    monkeypatch.delenv("CITRUSCARE_MODEL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="CITRUSCARE_MODEL"):
        Settings.from_env()
    monkeypatch.setenv("CITRUSCARE_MODEL", "llama-3.3-70b-versatile")
    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        Settings.from_env()


def test_groq_can_be_used_for_a_task_route_with_mock_as_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CITRUSCARE_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("CITRUSCARE_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("CITRUSCARE_MODEL_ROUTES", '{"general_information":"groq"}')
    monkeypatch.setenv("CITRUSCARE_FALLBACK_PROVIDER", "")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    settings = Settings.from_env()
    engine = create_demo_orchestrator(settings)

    assert engine.model_router.route_for("general_information").provider_name == "groq"
    assert engine.model_router.route_for("clinical_summary").provider_name == "mock"


def test_model_discovery_endpoint_only_runs_when_requested() -> None:
    transport = FakeGroqTransport()
    settings = Settings(
        groq_api_key="test-groq-key",
        model="llama-3.3-70b-versatile",
        model_provider="groq",
    )
    engine = create_demo_orchestrator(
        settings, GroqModelProvider(settings, transport=transport)
    )
    client = TestClient(create_app(engine))

    query = client.post(
        "/v1/intelligence/query",
        json={"query": "Explain a general health term."},
    )
    regular = client.get("/v1/models")
    discovered = client.get("/v1/models?discover=true")

    assert query.status_code == 200
    assert query.json()["provider"] == "groq"
    assert query.json()["answer"] == "General education."
    assert regular.status_code == discovered.status_code == 200
    assert regular.json()["discovered_models"] == {}
    assert discovered.json()["discovered_models"]["groq"] == ["llama-3.3-70b-versatile"]
    assert "test-groq-key" not in discovered.text
    assert len(transport.get_calls) == 1


def test_provider_failure_is_normalized_traced_and_audited() -> None:
    settings = Settings(
        groq_api_key="test-groq-key",
        model="llama-3.3-70b-versatile",
        model_provider="groq",
    )
    provider = GroqModelProvider(settings, transport=UnauthorizedGroqTransport())
    engine = create_demo_orchestrator(settings, provider)
    client = TestClient(create_app(engine))

    response = client.post(
        "/v1/intelligence/query",
        json={"query": "Explain a general health term."},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "LLM_PROVIDER_AUTH_FAILED"
    assert body["error"]["retryable"] is False
    assert "test-groq-key" not in response.text
    events = engine.audit_repository.get(body["request_id"])
    failure_event = next(
        event for event in events if event.action == "model_provider_failure"
    )
    assert failure_event.error_code == "LLM_PROVIDER_AUTH_FAILED"
    assert failure_event.provider == "groq"
    trace_events = engine.event_sink.for_request(body["request_id"])
    assert any(event.name == "model_failed" for event in trace_events)
    assert "test-groq-key" not in repr(trace_events)


def test_live_groq_smoke_is_explicitly_opt_in() -> None:
    if os.getenv("CITRUSCARE_RUN_LIVE_LLM_TESTS", "").lower() != "true":
        pytest.skip(
            "Set CITRUSCARE_RUN_LIVE_LLM_TESTS=true to enable live provider tests"
        )
    settings = Settings.from_env()
    provider = GroqModelProvider(settings)

    async def request_live_model() -> None:
        output = await provider.generate(
            (Message("user", "Reply with the word ready."),)
        )
        assert output.text.strip()
        assert output.provider == "groq"

    asyncio.run(request_live_model())
