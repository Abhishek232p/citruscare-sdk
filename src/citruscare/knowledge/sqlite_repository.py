"""SQLite-backed repository adapter for authorized local persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from threading import RLock

from citruscare.knowledge.repository import (
    EntityType,
    KnowledgeEntity,
    KnowledgeRelationship,
    _tokens,
)


class SQLiteKnowledgeRepository:
    """Persistent SQLite adapter; deployments remain responsible for data controls."""

    def __init__(self, database_path: str) -> None:
        if not database_path:
            raise ValueError("database_path must not be empty")
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_relationships (
                    source_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    UNIQUE(source_id, relationship, target_id),
                    FOREIGN KEY(source_id) REFERENCES knowledge_entities(id),
                    FOREIGN KEY(target_id) REFERENCES knowledge_entities(id)
                )"""
            )

    def add_entity(self, entity: KnowledgeEntity) -> None:
        payload = {
            "id": entity.id,
            "entity_type": entity.entity_type.value,
            "title": entity.title,
            "description": entity.description,
            "source": entity.source,
            "source_id": entity.source_id,
            "labels": sorted(entity.labels),
            "provenance": entity.provenance,
            "created_at": entity.created_at.isoformat(),
        }
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    "INSERT INTO knowledge_entities(id, entity_type, payload) "
                    "VALUES (?, ?, ?)",
                    (
                        entity.id,
                        entity.entity_type.value,
                        json.dumps(payload),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Knowledge entity '{entity.id}' already exists") from exc

    def add_relationship(self, relation: KnowledgeRelationship) -> None:
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """INSERT INTO knowledge_relationships
                    (source_id, relationship, target_id, provenance, source, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        relation.source_id,
                        relation.relationship,
                        relation.target_id,
                        relation.provenance,
                        relation.source,
                        relation.confidence,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "Relationship has unknown entities or is already recorded"
            ) from exc

    def get(self, entity_id: str) -> KnowledgeEntity | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM knowledge_entities WHERE id = ?",
                (entity_id,),
            ).fetchone()
        return self._deserialize(row["payload"]) if row else None

    def relationships(
        self, entity_id: str, relationship: str | None = None
    ) -> tuple[KnowledgeRelationship, ...]:
        query = "SELECT * FROM knowledge_relationships WHERE source_id = ?"
        parameters: tuple[str, ...] = (entity_id,)
        if relationship is not None:
            query += " AND relationship = ?"
            parameters += (relationship,)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return tuple(
            KnowledgeRelationship(
                source_id=row["source_id"],
                relationship=row["relationship"],
                target_id=row["target_id"],
                provenance=row["provenance"],
                source=row["source"],
                confidence=row["confidence"],
            )
            for row in rows
        )

    def search(self, query: str, limit: int = 10) -> tuple[KnowledgeEntity, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        terms = _tokens(query)
        ranked: list[tuple[float, KnowledgeEntity]] = []
        for entity in self.all():
            corpus = _tokens(
                f"{entity.id} {entity.entity_type.value} {entity.title} "
                f"{entity.description}"
            )
            overlap = len(terms & corpus)
            if overlap:
                ranked.append((overlap / len(terms), entity))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return tuple(entity for _, entity in ranked[:limit])

    def all(self, entity_type: EntityType | None = None) -> tuple[KnowledgeEntity, ...]:
        with self._lock:
            if entity_type is None:
                rows = self._connection.execute(
                    "SELECT payload FROM knowledge_entities ORDER BY id"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT payload FROM knowledge_entities "
                    "WHERE entity_type = ? ORDER BY id",
                    (entity_type.value,),
                ).fetchall()
        return tuple(self._deserialize(row["payload"]) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _deserialize(raw: str) -> KnowledgeEntity:
        value = json.loads(raw)
        return KnowledgeEntity(
            id=value["id"],
            entity_type=EntityType(value["entity_type"]),
            title=value["title"],
            description=value["description"],
            source=value["source"],
            source_id=value["source_id"],
            labels=frozenset(value["labels"]),
            provenance=value["provenance"],
            created_at=datetime.fromisoformat(value["created_at"]),
        )
