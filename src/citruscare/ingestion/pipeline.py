"""Explicitly authorized, auditable record normalization and indexing pipeline."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from citruscare.knowledge.repository import (
    EntityType,
    KnowledgeEntity,
    KnowledgeRepository,
)


@dataclass(frozen=True, slots=True)
class RawRecord:
    source: str
    source_record_id: str
    title: str
    content: str
    entity_type: EntityType
    authorized: bool
    provenance: str
    metadata: Mapping[str, str]


class SourceConnector(Protocol):
    source_name: str
    authorized: bool

    def fetch(self, query: str) -> Sequence[RawRecord]: ...


class IngestionAuditSink(Protocol):
    def record(self, event: Any) -> None: ...


@dataclass(frozen=True, slots=True)
class IngestionResult:
    created_ids: tuple[str, ...]
    duplicates: int
    rejected: int


class IngestionPipeline:
    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        index: Callable[[KnowledgeEntity], None] | None = None,
        audit: IngestionAuditSink | None = None,
    ) -> None:
        self.repository = repository
        self.index = index
        self.audit = audit
        self._fingerprints: set[str] = set()

    def ingest(self, connector: SourceConnector, query: str) -> IngestionResult:
        if not connector.authorized:
            raise PermissionError("Only explicitly authorized connectors may ingest")
        created: list[str] = []
        duplicate_count = 0
        rejected_count = 0
        for raw in connector.fetch(query):
            normalized = self._normalize(raw)
            if normalized is None:
                rejected_count += 1
                continue
            fingerprint = sha256(
                (
                    normalized.source
                    + "\0"
                    + normalized.source_id
                    + "\0"
                    + normalized.title
                    + "\0"
                    + normalized.description
                ).encode("utf-8")
            ).hexdigest()
            if fingerprint in self._fingerprints:
                duplicate_count += 1
                continue
            existing = self.repository.get(normalized.id)
            if existing is not None:
                duplicate_count += 1
                self._fingerprints.add(fingerprint)
                continue
            self.repository.add_entity(normalized)
            self._fingerprints.add(fingerprint)
            if self.index:
                self.index(normalized)
            created.append(normalized.id)
            self._record_event(
                "knowledge_ingested",
                normalized.id,
                normalized.source,
            )
        return IngestionResult(tuple(created), duplicate_count, rejected_count)

    @staticmethod
    def _normalize(raw: RawRecord) -> KnowledgeEntity | None:
        if (
            not raw.authorized
            or not raw.source.strip()
            or not raw.source_record_id.strip()
            or not raw.provenance.strip()
        ):
            return None
        title = re.sub(r"\s+", " ", raw.title).strip()
        description = re.sub(r"\s+", " ", raw.content).strip()
        if not title or not description:
            return None
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", raw.source_record_id).strip("-")
        if not safe_id:
            return None
        return KnowledgeEntity(
            id=safe_id,
            entity_type=raw.entity_type,
            title=title,
            description=description,
            source=raw.source,
            source_id=raw.source_record_id,
            labels=frozenset({"AUTHORIZED SOURCE"}),
            provenance=raw.provenance,
        )

    def _record_event(self, name: str, entity_id: str, source: str) -> None:
        if self.audit is not None:
            self.audit.record(
                {
                    "event": name,
                    "entity_id": entity_id,
                    "source": source,
                }
            )
