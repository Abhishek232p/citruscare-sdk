"""Knowledge repository interfaces and in-memory synthetic fixture."""

from citruscare.knowledge.repository import (
    EntityType,
    InMemoryKnowledgeRepository,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeRepository,
    synthetic_repository,
)
from citruscare.knowledge.sqlite_repository import SQLiteKnowledgeRepository

__all__ = [
    "EntityType",
    "InMemoryKnowledgeRepository",
    "KnowledgeEntity",
    "KnowledgeRelationship",
    "KnowledgeRepository",
    "SQLiteKnowledgeRepository",
    "synthetic_repository",
]
