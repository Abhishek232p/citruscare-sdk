"""CitrusCare SDK public API."""

from citruscare.core.agent import Agent, AgentResult
from citruscare.core.config import Settings
from citruscare.core.errors import (
    AuditError,
    ConfigurationError,
    ProviderError,
    StepLimitExceeded,
    ToolExecutionError,
)
from citruscare.core.messages import AssistantTurn, Message, ToolCall
from citruscare.governance.audit import AuditEvent, AuditSink, MemoryAuditSink
from citruscare.governance.consent import ConsentGrant, ConsentLedger
from citruscare.providers.openai_compatible import OpenAICompatibleProvider
from citruscare.providers.scripted import ScriptedProvider
from citruscare.tools.registry import Tool, ToolRegistry

__all__ = [
    "Agent",
    "AgentResult",
    "AssistantTurn",
    "AuditError",
    "AuditEvent",
    "AuditSink",
    "ConfigurationError",
    "ConsentGrant",
    "ConsentLedger",
    "MemoryAuditSink",
    "Message",
    "OpenAICompatibleProvider",
    "ProviderError",
    "Settings",
    "ScriptedProvider",
    "StepLimitExceeded",
    "Tool",
    "ToolCall",
    "ToolExecutionError",
    "ToolRegistry",
]
