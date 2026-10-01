"""Separate memory types with provenance and explicit retention metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4


class MemoryType(StrEnum):
    CONVERSATION = "conversation"
    ENCOUNTER = "encounter"
    PATIENT_CONTEXT = "patient_context"
    AGENT_TASK = "agent_task"


@dataclass(frozen=True, slots=True)
class RetentionMetadata:
    expires_at: datetime | None = None
    policy: str = "process_only"


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    type: MemoryType
    timestamp: datetime
    provenance: str
    retention: RetentionMetadata
    payload: Any


class MemoryRepository(Protocol):
    def put(self, item: MemoryItem) -> None: ...

    def get(self, item_id: str) -> MemoryItem | None: ...

    def list(self, memory_type: MemoryType | None = None) -> tuple[MemoryItem, ...]: ...


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}

    def put(self, item: MemoryItem) -> None:
        self._items[item.id] = item

    def get(self, item_id: str) -> MemoryItem | None:
        item = self._items.get(item_id)
        if item and item.retention.expires_at:
            if item.retention.expires_at <= datetime.now(UTC):
                self._items.pop(item_id)
                return None
        return item

    def list(self, memory_type: MemoryType | None = None) -> tuple[MemoryItem, ...]:
        return tuple(
            item
            for item in (self.get(item_id) for item_id in tuple(self._items))
            if item is not None and (memory_type is None or item.type == memory_type)
        )


class _TypedMemory:
    memory_type: MemoryType

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        retention_seconds: int | None = None,
    ) -> None:
        if retention_seconds is not None and retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive")
        self.repository = repository
        self.retention_seconds = retention_seconds

    def add(self, payload: Any, provenance: str) -> MemoryItem:
        if not provenance.strip():
            raise ValueError("memory provenance must not be empty")
        now = datetime.now(UTC)
        expires_at = (
            now + timedelta(seconds=self.retention_seconds)
            if self.retention_seconds
            else None
        )
        item = MemoryItem(
            id=str(uuid4()),
            type=self.memory_type,
            timestamp=now,
            provenance=provenance,
            retention=RetentionMetadata(expires_at=expires_at),
            payload=payload,
        )
        self.repository.put(item)
        return item

    def list(self) -> tuple[MemoryItem, ...]:
        return self.repository.list(self.memory_type)


class ConversationMemory(_TypedMemory):
    memory_type = MemoryType.CONVERSATION


class EncounterMemory(_TypedMemory):
    memory_type = MemoryType.ENCOUNTER


class PatientContextMemory(_TypedMemory):
    memory_type = MemoryType.PATIENT_CONTEXT


class AgentTaskMemory(_TypedMemory):
    memory_type = MemoryType.AGENT_TASK
