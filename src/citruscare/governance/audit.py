"""Metadata-only audit events; prompts, arguments, and outputs are excluded."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: str
    occurred_at: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def create(
        cls, event_type: str, metadata: Mapping[str, object] | None = None
    ) -> AuditEvent:
        return cls(
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            metadata=dict(metadata or {}),
        )


class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...


class MemoryAuditSink:
    """In-memory sink for development only; it is neither durable nor tamper-proof."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)
