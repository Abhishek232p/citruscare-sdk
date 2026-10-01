"""Deterministic retrieval interfaces and in-memory implementation."""

from citruscare.retrieval.engine import (
    InMemoryEvidenceRetriever,
    InMemoryKnowledgeRetriever,
    RetrievalEngine,
    RetrievalResult,
    Retriever,
)

__all__ = [
    "InMemoryEvidenceRetriever",
    "InMemoryKnowledgeRetriever",
    "RetrievalEngine",
    "RetrievalResult",
    "Retriever",
]
