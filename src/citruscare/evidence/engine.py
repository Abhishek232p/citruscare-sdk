"""Evidence items preserve source, retrieval time, relevance, and provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class InformationKind(StrEnum):
    OBSERVED_FACT = "OBSERVED FACT"
    RETRIEVED_EVIDENCE = "RETRIEVED EVIDENCE"
    MODEL_GENERATED_TEXT = "MODEL GENERATED TEXT"
    MODEL_INFERENCE = "MODEL INFERENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    source: str
    source_id: str
    title: str
    content: str
    retrieved_at: datetime
    relevance: float
    provenance: str
    kind: InformationKind = InformationKind.RETRIEVED_EVIDENCE
    source_type: str = "unknown"
    authority: float = 0.0
    freshness: float = 1.0
    score: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.relevance <= 1.0:
            raise ValueError("relevance must be between zero and one")
        if not 0.0 <= self.authority <= 1.0:
            raise ValueError("authority must be between zero and one")
        if not 0.0 <= self.freshness <= 1.0:
            raise ValueError("freshness must be between zero and one")
        if not self.source_id or not self.title:
            raise ValueError("evidence requires source_id and title")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.score is None:
            object.__setattr__(
                self,
                "score",
                round(
                    0.6 * self.relevance
                    + 0.25 * self.authority
                    + 0.15 * self.freshness,
                    6,
                ),
            )
        elif not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between zero and one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "content": self.content,
            "retrieved_at": self.retrieved_at.isoformat(),
            "relevance": self.relevance,
            "provenance": self.provenance,
            "kind": self.kind.value,
            "source_type": self.source_type,
            "authority": self.authority,
            "freshness": self.freshness,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    items: tuple[EvidenceItem, ...]
    created_at: datetime
    query: str

    @classmethod
    def create(cls, items: tuple[EvidenceItem, ...], query: str) -> EvidenceBundle:
        return cls(items=items, created_at=datetime.now(UTC), query=query)


class EvidenceEngine:
    def from_entities(self, entities: tuple[Any, ...], query: str) -> EvidenceBundle:
        from citruscare.knowledge.repository import _tokens

        query_tokens = _tokens(query)
        items: list[EvidenceItem] = []
        for entity in entities:
            entity_tokens = _tokens(f"{entity.id} {entity.title} {entity.description}")
            relevance = (
                len(query_tokens & entity_tokens) / len(query_tokens)
                if query_tokens
                else 0.0
            )
            items.append(
                EvidenceItem(
                    source=entity.source,
                    source_id=entity.source_id or entity.id,
                    title=entity.title,
                    content=entity.description,
                    retrieved_at=datetime.now(UTC),
                    relevance=min(1.0, relevance),
                    provenance=entity.provenance,
                    source_type=entity.source,
                    authority=0.0,
                    freshness=1.0,
                )
            )
        return EvidenceBundle.create(tuple(items), query)
