"""LLM provider adapters."""

from citruscare.providers.base import Provider
from citruscare.providers.openai_compatible import OpenAICompatibleProvider

__all__ = ["OpenAICompatibleProvider", "Provider"]
