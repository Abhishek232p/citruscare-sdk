"""Query normalization, lexical entity retrieval, evidence, and context assembly."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from citruscare.context.models import Context, ContextEngine, ContextItem, Provenance
from citruscare.evidence.engine import EvidenceBundle, EvidenceEngine
from citruscare.knowledge.repository import KnowledgeEntity, KnowledgeRepository


class Retriever(Protocol):
    def search(self, query: str, limit: int = 10) -> Sequence[KnowledgeEntity]: ...


class KnowledgeRetriever(Protocol):
    def search_knowledge(
        self, query: str, limit: int = 10
    ) -> Sequence[KnowledgeEntity]: ...


class EvidenceRetriever(Protocol):
    def search_evidence(
        self, query: str, limit: int = 10
    ) -> Sequence[KnowledgeEntity]: ...


class InMemoryKnowledgeRetriever:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def search(self, query: str, limit: int = 10) -> Sequence[KnowledgeEntity]:
        return self.repository.search(query, limit)

    def search_knowledge(
        self, query: str, limit: int = 10
    ) -> Sequence[KnowledgeEntity]:
        return self.repository.search(query, limit)


class InMemoryEvidenceRetriever(InMemoryKnowledgeRetriever):
    def search_evidence(self, query: str, limit: int = 10) -> Sequence[KnowledgeEntity]:
        return tuple(
            entity
            for entity in self.repository.search(query, limit * 2)
            if entity.source == "synthetic_demo_fixture"
        )[:limit]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    normalized_query: str
    extracted_entity_ids: tuple[str, ...]
    knowledge: tuple[KnowledgeEntity, ...]
    evidence: EvidenceBundle
    context: Context


class RetrievalEngine:
    def __init__(
        self,
        knowledge_retriever: KnowledgeRetriever,
        evidence_retriever: EvidenceRetriever,
        evidence_engine: EvidenceEngine | None = None,
        context_engine: ContextEngine | None = None,
    ) -> None:
        self.knowledge_retriever = knowledge_retriever
        self.evidence_retriever = evidence_retriever
        self.evidence_engine = evidence_engine or EvidenceEngine()
        self.context_engine = context_engine or ContextEngine()

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        *,
        user_id: str | None = None,
        patient_id: str | None = None,
        encounter_id: str | None = None,
        permissions: frozenset[str] = frozenset(),
    ) -> RetrievalResult:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        normalized = re.sub(r"\s+", " ", query).strip().casefold()
        knowledge = tuple(self.knowledge_retriever.search_knowledge(normalized, limit))
        evidence_entities = tuple(
            self.evidence_retriever.search_evidence(normalized, limit)
        )
        evidence = self.evidence_engine.from_entities(evidence_entities, normalized)
        extracted_ids = tuple(
            entity.id for entity in knowledge if entity.id.casefold() in normalized
        )
        evidence_items = tuple(
            ContextItem(
                value=item.to_dict(),
                provenance=Provenance(
                    source=item.source,
                    source_id=item.source_id,
                    label=item.kind.value,
                    retrieved_at=item.retrieved_at,
                ),
            )
            for item in evidence.items
        )
        facts = tuple(
            ContextItem(
                value={"id": entity.id, "title": entity.title},
                provenance=Provenance(
                    source=entity.source,
                    source_id=entity.source_id or entity.id,
                    label="SYNTHETIC DEMO DATA",
                ),
            )
            for entity in knowledge
        )
        context = self.context_engine.assemble(
            user_id=user_id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            facts=facts,
            evidence=evidence_items,
            policies=("Informational only; synthetic fixture data.",),
            permissions=permissions,
        )
        return RetrievalResult(
            normalized_query=normalized,
            extracted_entity_ids=extracted_ids,
            knowledge=knowledge,
            evidence=evidence,
            context=context,
        )
