"""Explicit, environment-backed configuration for provider connections."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from citruscare.core.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration values; credentials are never loaded from project files."""

    api_key: str | None = field(default=None, repr=False)
    groq_api_key: str | None = field(default=None, repr=False)
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    request_timeout: float = 30.0
    max_turns: int = 8
    model_provider: str = "mock"
    fallback_provider: str | None = None
    retries: int = 2
    task_routes: Mapping[str, str] = field(default_factory=dict)
    max_agent_steps: int = 4
    max_tool_calls: int = 4
    agent_budget_units: float = 1.0
    knowledge_backend: str = "memory"
    sqlite_path: str = "citruscare-knowledge.sqlite3"
    model_discovery_ttl_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ConfigurationError("model must not be empty")
        if not self.base_url.startswith(("https://", "http://")):
            raise ConfigurationError("base_url must use HTTP or HTTPS")
        if not math.isfinite(self.request_timeout) or self.request_timeout <= 0:
            raise ConfigurationError("request_timeout must be greater than zero")
        if (
            not math.isfinite(self.model_discovery_ttl_seconds)
            or self.model_discovery_ttl_seconds <= 0
        ):
            raise ConfigurationError("model discovery TTL must be greater than zero")
        if self.max_turns < 1:
            raise ConfigurationError("max_turns must be at least one")
        if not self.model_provider.strip():
            raise ConfigurationError("model_provider must not be empty")
        if self.model_provider not in {"mock", "openai_compatible", "groq"}:
            raise ConfigurationError("Unsupported model provider")
        if self.knowledge_backend not in {"memory", "sqlite"}:
            raise ConfigurationError("knowledge_backend must be 'memory' or 'sqlite'")
        if self.knowledge_backend == "sqlite" and not self.sqlite_path.strip():
            raise ConfigurationError("sqlite_path must not be empty")
        if self.fallback_provider is not None and not self.fallback_provider.strip():
            raise ConfigurationError("fallback_provider must not be empty")
        if self.retries < 0:
            raise ConfigurationError("retries must not be negative")
        if self.max_agent_steps < 1 or self.max_tool_calls < 0:
            raise ConfigurationError("agent step and tool-call limits are invalid")
        if not math.isfinite(self.agent_budget_units) or self.agent_budget_units <= 0:
            raise ConfigurationError("agent budget units must be greater than zero")
        if any(
            not key.strip() or not value.strip()
            for key, value in self.task_routes.items()
        ):
            raise ConfigurationError("task routes must use non-empty names")
        object.__setattr__(
            self, "task_routes", MappingProxyType(dict(self.task_routes))
        )

    @classmethod
    def from_env(cls) -> Settings:
        """Read only documented CITRUSCARE_* settings from the environment."""
        provider = os.getenv("CITRUSCARE_MODEL_PROVIDER", "mock").strip()
        timeout = os.getenv(
            "CITRUSCARE_LLM_TIMEOUT_SECONDS",
            os.getenv("CITRUSCARE_REQUEST_TIMEOUT", "30"),
        )
        max_turns = os.getenv("CITRUSCARE_MAX_TURNS", "8")
        retries = os.getenv(
            "CITRUSCARE_LLM_MAX_RETRIES",
            os.getenv("CITRUSCARE_MODEL_RETRIES", "2"),
        )
        max_agent_steps = os.getenv("CITRUSCARE_MAX_AGENT_STEPS", "4")
        max_tool_calls = os.getenv("CITRUSCARE_MAX_TOOL_CALLS", "4")
        agent_budget_units = os.getenv("CITRUSCARE_AGENT_BUDGET_UNITS", "1")
        model_discovery_ttl = os.getenv("CITRUSCARE_MODEL_DISCOVERY_TTL_SECONDS", "300")
        raw_routes = os.getenv("CITRUSCARE_MODEL_ROUTES", "{}")
        model = os.getenv("CITRUSCARE_MODEL")
        if provider == "groq" and not model:
            raise ConfigurationError(
                "CITRUSCARE_MODEL must name a configured Groq model"
            )
        groq_api_key = os.getenv("GROQ_API_KEY")
        default_base_url = (
            "https://api.groq.com/openai/v1"
            if provider == "groq"
            else "https://api.openai.com/v1"
        )
        try:
            parsed_timeout = float(timeout)
            parsed_max_turns = int(max_turns)
            parsed_retries = int(retries)
            parsed_max_agent_steps = int(max_agent_steps)
            parsed_max_tool_calls = int(max_tool_calls)
            parsed_agent_budget_units = float(agent_budget_units)
            parsed_model_discovery_ttl = float(model_discovery_ttl)
            parsed_routes = json.loads(raw_routes)
        except ValueError as exc:
            raise ConfigurationError(
                "Provider, timeout, retry, route, or agent settings are invalid"
            ) from exc
        if not isinstance(parsed_routes, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in parsed_routes.items()
        ):
            raise ConfigurationError("CITRUSCARE_MODEL_ROUTES must be a JSON object")
        fallback_provider = (
            os.getenv(
                "CITRUSCARE_MODEL_FALLBACK",
                os.getenv("CITRUSCARE_FALLBACK_PROVIDER", ""),
            )
            or None
        )
        if (
            provider == "groq"
            or fallback_provider == "groq"
            or "groq" in parsed_routes.values()
        ):
            if not model:
                raise ConfigurationError(
                    "CITRUSCARE_MODEL must name a configured Groq model"
                )
            if not groq_api_key:
                raise ConfigurationError(
                    "GROQ_API_KEY is required for a configured Groq route"
                )
        return cls(
            api_key=os.getenv("CITRUSCARE_API_KEY"),
            groq_api_key=groq_api_key,
            model=model if model is not None else "gpt-4o-mini",
            base_url=os.getenv("CITRUSCARE_BASE_URL", default_base_url),
            request_timeout=parsed_timeout,
            max_turns=parsed_max_turns,
            model_provider=provider,
            fallback_provider=fallback_provider,
            retries=parsed_retries,
            task_routes=parsed_routes,
            max_agent_steps=parsed_max_agent_steps,
            max_tool_calls=parsed_max_tool_calls,
            agent_budget_units=parsed_agent_budget_units,
            knowledge_backend=os.getenv("CITRUSCARE_KNOWLEDGE_BACKEND", "memory"),
            sqlite_path=os.getenv(
                "CITRUSCARE_SQLITE_PATH", "citruscare-knowledge.sqlite3"
            ),
            model_discovery_ttl_seconds=parsed_model_discovery_ttl,
        )
