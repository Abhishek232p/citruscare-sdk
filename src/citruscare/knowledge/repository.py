"""Provider-neutral synthetic knowledge repository."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class EntityType(StrEnum):
    PATIENT = "Patient"
    MEDICATION = "Medication"
    INGREDIENT = "Ingredient"
    DISEASE = "Disease"
    SYMPTOM = "Symptom"
    DIAGNOSTIC_TEST = "DiagnosticTest"
    LABORATORY_OBSERVATION = "LaboratoryObservation"
    CLINICAL_GUIDELINE = "ClinicalGuideline"
    EVIDENCE_DOCUMENT = "EvidenceDocument"


@dataclass(frozen=True, slots=True)
class KnowledgeEntity:
    id: str
    entity_type: EntityType
    title: str
    description: str
    source: str = "synthetic_demo_fixture"
    source_id: str = ""
    labels: frozenset[str] = frozenset({"SYNTHETIC DEMO DATA"})
    provenance: str = "Generated for local SDK demonstration; not clinical evidence."
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class KnowledgeRelationship:
    source_id: str
    relationship: str
    target_id: str
    provenance: str = "synthetic_demo_fixture"
    source: str = "synthetic_demo_fixture"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("relationship confidence must be between zero and one")


class KnowledgeRepository(Protocol):
    def get(self, entity_id: str) -> KnowledgeEntity | None: ...

    def relationships(
        self, entity_id: str, relationship: str | None = None
    ) -> tuple[KnowledgeRelationship, ...]: ...

    def search(self, query: str, limit: int = 10) -> tuple[KnowledgeEntity, ...]: ...

    def all(
        self, entity_type: EntityType | None = None
    ) -> tuple[KnowledgeEntity, ...]: ...


class InMemoryKnowledgeRepository:
    def __init__(
        self,
        entities: Iterable[KnowledgeEntity] = (),
        relationships: Iterable[KnowledgeRelationship] = (),
    ) -> None:
        self._entities: dict[str, KnowledgeEntity] = {}
        self._relationships: list[KnowledgeRelationship] = []
        for entity in entities:
            self.add_entity(entity)
        for relation in relationships:
            self.add_relationship(relation)

    def add_entity(self, entity: KnowledgeEntity) -> None:
        if entity.id in self._entities:
            raise ValueError(f"Knowledge entity '{entity.id}' already exists")
        self._entities[entity.id] = entity

    def add_relationship(self, relation: KnowledgeRelationship) -> None:
        if (
            relation.source_id not in self._entities
            or relation.target_id not in self._entities
        ):
            raise ValueError("Knowledge relationship references an unknown entity")
        self._relationships.append(relation)

    def get(self, entity_id: str) -> KnowledgeEntity | None:
        return self._entities.get(entity_id)

    def relationships(
        self, entity_id: str, relationship: str | None = None
    ) -> tuple[KnowledgeRelationship, ...]:
        return tuple(
            relation
            for relation in self._relationships
            if relation.source_id == entity_id
            and (relationship is None or relation.relationship == relationship)
        )

    def search(self, query: str, limit: int = 10) -> tuple[KnowledgeEntity, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        tokens = _tokens(query)
        if not tokens:
            return ()
        ranked: list[tuple[float, KnowledgeEntity]] = []
        for entity in self._entities.values():
            corpus = _tokens(
                " ".join(
                    (
                        entity.id,
                        entity.entity_type.value,
                        entity.title,
                        entity.description,
                    )
                )
            )
            overlap = len(tokens & corpus)
            if overlap:
                ranked.append((overlap / len(tokens), entity))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return tuple(entity for _, entity in ranked[:limit])

    def all(self, entity_type: EntityType | None = None) -> tuple[KnowledgeEntity, ...]:
        return tuple(
            entity
            for entity in self._entities.values()
            if entity_type is None or entity.entity_type == entity_type
        )


class KnowledgeGraph(Protocol):
    def get(self, entity_id: str) -> KnowledgeEntity | None: ...

    def relationships(
        self, entity_id: str, relationship: str | None = None
    ) -> tuple[KnowledgeRelationship, ...]: ...

    def add_relationship(self, relation: KnowledgeRelationship) -> None: ...


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9_-]+", value.lower()) if len(token) > 1
    }


def synthetic_repository() -> InMemoryKnowledgeRepository:
    entities = (
        KnowledgeEntity(
            "PATIENT-DEMO-001",
            EntityType.PATIENT,
            "Synthetic patient",
            "Placeholder patient record with no real person or clinical facts.",
        ),
        KnowledgeEntity(
            "ENCOUNTER-DEMO-001",
            EntityType.EVIDENCE_DOCUMENT,
            "Synthetic encounter",
            "Placeholder encounter record; no real medical content.",
        ),
        KnowledgeEntity(
            "MED-DEMO-001",
            EntityType.MEDICATION,
            "Synthetic medication placeholder",
            "Demo-only medication record. Contains no medication advice or facts.",
        ),
        KnowledgeEntity(
            "INGREDIENT-DEMO-001",
            EntityType.INGREDIENT,
            "Synthetic ingredient placeholder",
            "Demo-only ingredient record. Not a real ingredient reference.",
        ),
        KnowledgeEntity(
            "DISEASE-DEMO-001",
            EntityType.DISEASE,
            "Synthetic condition placeholder",
            "Demo-only disease entity. Not a medical diagnosis or fact.",
        ),
        KnowledgeEntity(
            "SYMPTOM-DEMO-001",
            EntityType.SYMPTOM,
            "Synthetic symptom placeholder",
            "Demo-only symptom entity. Not a medical fact.",
        ),
        KnowledgeEntity(
            "TEST-DEMO-001",
            EntityType.DIAGNOSTIC_TEST,
            "Synthetic diagnostic test placeholder",
            "Demo-only test entity. Not a real diagnostic recommendation.",
        ),
        KnowledgeEntity(
            "OBS-DEMO-001",
            EntityType.LABORATORY_OBSERVATION,
            "Synthetic lab observation",
            "Placeholder laboratory record; no real test or patient result.",
        ),
        KnowledgeEntity(
            "GUIDELINE-DEMO-001",
            EntityType.CLINICAL_GUIDELINE,
            "Synthetic guideline placeholder",
            "Synthetic record only. It contains no clinical recommendations.",
        ),
        KnowledgeEntity(
            "EVIDENCE-DEMO-001",
            EntityType.EVIDENCE_DOCUMENT,
            "Synthetic evidence note",
            "This fixture exists to demonstrate retrieval and citations only. "
            "It is not evidence and must not be used for clinical decisions.",
        ),
    )
    relations = (
        KnowledgeRelationship(
            "MED-DEMO-001", "Medication -> Ingredient", "INGREDIENT-DEMO-001"
        ),
        KnowledgeRelationship(
            "MED-DEMO-001", "Medication -> Indication", "DISEASE-DEMO-001"
        ),
        KnowledgeRelationship(
            "MED-DEMO-001", "Medication -> Contraindication", "DISEASE-DEMO-001"
        ),
        KnowledgeRelationship(
            "DISEASE-DEMO-001", "Disease -> Symptom", "SYMPTOM-DEMO-001"
        ),
        KnowledgeRelationship(
            "DISEASE-DEMO-001", "Disease -> DiagnosticTest", "TEST-DEMO-001"
        ),
        KnowledgeRelationship(
            "GUIDELINE-DEMO-001", "Guideline -> Disease", "DISEASE-DEMO-001"
        ),
        KnowledgeRelationship(
            "GUIDELINE-DEMO-001",
            "Guideline -> Recommendation",
            "EVIDENCE-DEMO-001",
        ),
    )
    return InMemoryKnowledgeRepository(entities, relations)
