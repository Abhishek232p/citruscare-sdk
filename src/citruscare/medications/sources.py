"""Medication data adapters; no medication facts are bundled by this module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from citruscare.knowledge.repository import (
    EntityType,
    KnowledgeEntity,
    KnowledgeRepository,
)


@dataclass(frozen=True, slots=True)
class MedicationRecord:
    id: str
    name: str
    description: str
    source: str
    source_id: str
    provenance: str
    authority: float

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.id,
                self.name,
                self.description,
                self.source,
                self.source_id,
                self.provenance,
            )
        ):
            raise ValueError("Medication records require source provenance")
        if not 0 <= self.authority <= 1:
            raise ValueError("authority must be between zero and one")


class MedicationSource(Protocol):
    source_name: str
    authorized: bool

    def search(self, query: str, limit: int = 10) -> Sequence[MedicationRecord]: ...

    def get(self, medication_id: str) -> MedicationRecord | None: ...


class RepositoryMedicationSource:
    """Read medication records from an injected authorized knowledge repository."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        source_name: str = "injected_knowledge_repository",
        authorized: bool = False,
    ) -> None:
        self.repository = repository
        self.source_name = source_name
        self.authorized = authorized

    def search(self, query: str, limit: int = 10) -> tuple[MedicationRecord, ...]:
        self._require_authorized()
        return tuple(
            self._record(entity)
            for entity in self.repository.search(query, limit)
            if entity.entity_type == EntityType.MEDICATION
        )

    def get(self, medication_id: str) -> MedicationRecord | None:
        self._require_authorized()
        entity = self.repository.get(medication_id)
        if entity is None or entity.entity_type != EntityType.MEDICATION:
            return None
        return self._record(entity)

    def _require_authorized(self) -> None:
        if not self.authorized:
            raise PermissionError("Medication data source is not authorized")

    def _record(self, entity: KnowledgeEntity) -> MedicationRecord:
        return MedicationRecord(
            id=entity.id,
            name=entity.title,
            description=entity.description,
            source=entity.source,
            source_id=entity.source_id or entity.id,
            provenance=entity.provenance,
            authority=0.0,
        )
