import pytest

from citruscare.knowledge.repository import synthetic_repository
from citruscare.retrieval.engine import (
    InMemoryEvidenceRetriever,
    InMemoryKnowledgeRetriever,
    RetrievalEngine,
)


def make_engine() -> RetrievalEngine:
    repository = synthetic_repository()
    return RetrievalEngine(
        InMemoryKnowledgeRetriever(repository),
        InMemoryEvidenceRetriever(repository),
    )


def test_retrieval_normalizes_search_and_preserves_provenance() -> None:
    result = make_engine().retrieve("  SYNTHETIC   EVIDENCE NOTE ")
    assert result.normalized_query == "synthetic evidence note"
    assert result.evidence.items
    assert result.evidence.items[0].source_id == "EVIDENCE-DEMO-001"
    assert result.context.evidence[0].provenance.label == "RETRIEVED EVIDENCE"


def test_retrieval_validates_input_bounds() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        make_engine().retrieve(" ")
    with pytest.raises(ValueError, match="between 1 and 50"):
        make_engine().retrieve("synthetic", limit=51)
