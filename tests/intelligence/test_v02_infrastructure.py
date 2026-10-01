from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from citruscare.agents import AgentExecutionBudget, MultiAgentOrchestrator
from citruscare.core.errors import ProviderError
from citruscare.core.messages import Message
from citruscare.evidence.engine import EvidenceBundle, EvidenceItem
from citruscare.evidence.grounding import (
    EvidenceGroundingValidator,
    GroundingStatus,
)
from citruscare.ingestion.pipeline import (
    IngestionPipeline,
    RawRecord,
)
from citruscare.intelligence.orchestrator import (
    IntelligenceRequest,
    create_demo_orchestrator,
)
from citruscare.knowledge.repository import (
    EntityType,
    InMemoryKnowledgeRepository,
    KnowledgeEntity,
    KnowledgeRelationship,
)
from citruscare.knowledge.sqlite_repository import SQLiteKnowledgeRepository
from citruscare.medications.sources import RepositoryMedicationSource
from citruscare.models.router import ModelRouter
from citruscare.providers.model import MockModelProvider, ModelOutput
from citruscare.vector.store import (
    FeatureHashEmbeddingProvider,
    InMemoryVectorStore,
    VectorRecord,
)


def _entity(entity_id: str, title: str) -> KnowledgeEntity:
    return KnowledgeEntity(
        id=entity_id,
        entity_type=EntityType.EVIDENCE_DOCUMENT,
        title=title,
        description="Synthetic fixture text.",
    )


def test_grounding_assesses_citation_and_does_not_overclaim_truth() -> None:
    evidence = EvidenceBundle.create(
        (
            EvidenceItem(
                source="synthetic",
                source_id="SRC-1",
                title="Synthetic fixture",
                content="Synthetic fixture text.",
                retrieved_at=datetime.now(UTC),
                relevance=1.0,
                provenance="synthetic",
            ),
        ),
        "fixture",
    )
    validator = EvidenceGroundingValidator()
    supported = validator.validate("Synthetic fixture text [SRC-1].", evidence)
    assert supported.status is GroundingStatus.SUPPORTED
    unsupported = validator.validate("An unrelated claim is asserted.", evidence)
    assert unsupported.status is GroundingStatus.UNSUPPORTED
    assert "not clinical verification" in unsupported.to_dict()["method"]


def test_sqlite_repository_persists_entities_and_enforces_foreign_keys() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "knowledge.sqlite3")
        repository = SQLiteKnowledgeRepository(path)
        with pytest.raises(ValueError, match="unknown entities"):
            repository.add_relationship(
                KnowledgeRelationship("missing", "related", "also-missing")
            )
        repository.add_entity(_entity("A", "First"))
        repository.add_entity(_entity("B", "Second"))
        repository.add_relationship(KnowledgeRelationship("A", "related", "B"))
        repository.close()

        reopened = SQLiteKnowledgeRepository(path)
        assert reopened.get("A").title == "First"
        assert reopened.relationships("A")[0].target_id == "B"
        reopened.close()


def test_ingestion_requires_authorization_deduplicates_and_indexes() -> None:
    repository = InMemoryKnowledgeRepository()
    indexed: list[str] = []

    class Connector:
        source_name = "synthetic-authorized"
        authorized = True

        def fetch(self, query: str) -> tuple[RawRecord, ...]:
            assert query == "fixture"
            return (
                RawRecord(
                    source="synthetic-authorized",
                    source_record_id="ITEM-1",
                    title="  Fixture   title ",
                    content="Fixture content.",
                    entity_type=EntityType.EVIDENCE_DOCUMENT,
                    authorized=True,
                    provenance="Synthetic test fixture.",
                    metadata={},
                ),
                RawRecord(
                    source="synthetic-authorized",
                    source_record_id="ITEM-1",
                    title="Fixture title",
                    content="Fixture content.",
                    entity_type=EntityType.EVIDENCE_DOCUMENT,
                    authorized=True,
                    provenance="Synthetic test fixture.",
                    metadata={},
                ),
            )

    connector = Connector()
    pipeline = IngestionPipeline(
        repository, index=lambda entity: indexed.append(entity.id)
    )
    result = pipeline.ingest(connector, "fixture")
    assert result.created_ids == ("ITEM-1",)
    assert result.duplicates == 1
    assert indexed == ["ITEM-1"]

    connector.authorized = False
    with pytest.raises(PermissionError, match="authorized"):
        pipeline.ingest(connector, "fixture")


def test_vector_search_is_deterministic_and_dimension_safe() -> None:
    embedding = FeatureHashEmbeddingProvider(dimensions=32)
    store = InMemoryVectorStore()
    vector = embedding.embed_text("synthetic evidence fixture")
    store.upsert((VectorRecord("A", tuple(vector), "synthetic evidence fixture"),))
    result = store.search(vector)
    assert result[0].record.id == "A"
    assert result[0].score == pytest.approx(1.0)
    assert store.search(embedding.embed_text("different text"))[0].record.id == "A"
    with pytest.raises(ValueError, match="finite"):
        store.search((float("nan"),))


def test_medication_adapter_requires_authorized_source() -> None:
    repository = InMemoryKnowledgeRepository(
        (
            KnowledgeEntity(
                id="MED-1",
                entity_type=EntityType.MEDICATION,
                title="Synthetic medication placeholder",
                description="Synthetic medication fixture.",
            ),
        )
    )
    source = RepositoryMedicationSource(repository)
    with pytest.raises(PermissionError, match="not authorized"):
        source.search("medication")
    authorized = RepositoryMedicationSource(repository, authorized=True)
    result = authorized.search("medication")
    assert result[0].id == "MED-1"
    assert result[0].authority == 0.0


def test_router_falls_back_only_to_explicitly_configured_provider() -> None:
    class FailingProvider:
        name = "failing"
        model_name = "failing-model"
        supports_structured_output = True

        async def generate(self, messages: tuple[Message, ...]) -> ModelOutput:
            raise ProviderError("unavailable")

        async def generate_structured(
            self, messages: tuple[Message, ...]
        ) -> dict[str, object]:
            raise ProviderError("unavailable")

        async def stream(self, messages: tuple[Message, ...]):
            if False:
                yield ""

    providers = {"primary": FailingProvider(), "fallback": MockModelProvider()}
    no_fallback = ModelRouter(providers, default_provider="primary")
    with pytest.raises(ProviderError, match="All configured"):
        asyncio.run(no_fallback.generate("general", (Message("user", "hello"),)))

    with_fallback = ModelRouter(
        providers,
        default_provider="primary",
        fallback_providers=("fallback",),
    )
    result = asyncio.run(with_fallback.generate("general", (Message("user", "hello"),)))
    assert result.provider == "fallback"


def test_specialized_orchestrator_enforces_unit_budget_before_runtime() -> None:
    orchestrator = MultiAgentOrchestrator(
        create_demo_orchestrator(),
        AgentExecutionBudget(budget_units=0.5),
    )
    with pytest.raises(RuntimeError, match="budget"):
        asyncio.run(orchestrator.run(IntelligenceRequest("synthetic query")))
