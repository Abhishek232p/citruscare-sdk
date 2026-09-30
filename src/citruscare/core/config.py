"""Explicit, environment-backed configuration for provider connections."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from citruscare.core.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration values; credentials are never loaded from project files."""

    api_key: str | None = None
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    request_timeout: float = 30.0
    max_turns: int = 8

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ConfigurationError("model must not be empty")
        if not self.base_url.startswith(("https://", "http://")):
            raise ConfigurationError("base_url must use HTTP or HTTPS")
        if not math.isfinite(self.request_timeout) or self.request_timeout <= 0:
            raise ConfigurationError("request_timeout must be greater than zero")
        if self.max_turns < 1:
            raise ConfigurationError("max_turns must be at least one")

    @classmethod
    def from_env(cls) -> Settings:
        """Read only documented CITRUSCARE_* settings from the environment."""
        timeout = os.getenv("CITRUSCARE_REQUEST_TIMEOUT", "30")
        max_turns = os.getenv("CITRUSCARE_MAX_TURNS", "8")
        try:
            parsed_timeout = float(timeout)
            parsed_max_turns = int(max_turns)
        except ValueError as exc:
            raise ConfigurationError(
                "CITRUSCARE_REQUEST_TIMEOUT and CITRUSCARE_MAX_TURNS "
                "must be numeric"
            ) from exc
        return cls(
            api_key=os.getenv("CITRUSCARE_API_KEY"),
            model=os.getenv("CITRUSCARE_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("CITRUSCARE_BASE_URL", "https://api.openai.com/v1"),
            request_timeout=parsed_timeout,
            max_turns=parsed_max_turns,
        )
