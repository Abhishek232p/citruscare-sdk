"""Structured event sink contracts with bounded in-memory retention."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    request_id: str
    name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    attributes: Mapping[str, str | int | float | bool | None] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "event": self.name,
            "occurred_at": self.occurred_at.isoformat(),
            "attributes": dict(self.attributes),
        }


class RuntimeEventSink(Protocol):
    def record(self, event: RuntimeEvent) -> None: ...

    def for_request(self, request_id: str) -> Sequence[RuntimeEvent]: ...


class InMemoryEventSink:
    def __init__(self, max_events: int = 10_000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self.max_events = max_events
        self._events: list[RuntimeEvent] = []
        self._lock = RLock()

    def record(self, event: RuntimeEvent) -> None:
        if not event.request_id or not event.name:
            raise ValueError("runtime events require request_id and event name")
        with self._lock:
            self._events.append(event)
            if len(self._events) > self.max_events:
                del self._events[: len(self._events) - self.max_events]

    def for_request(self, request_id: str) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(
                event for event in self._events if event.request_id == request_id
            )
