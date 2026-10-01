import pytest

from citruscare.knowledge.repository import (
    EntityType,
    InMemoryKnowledgeRepository,
    KnowledgeEntity,
    KnowledgeRelationship,
    synthetic_repository,
)


def test_fixture_entities_and_relationships_are_explicitly_synthetic() -> None:
    repository = synthetic_repository()
    assert len(repository.all()) >= 9
    assert all("SYNTHETIC DEMO DATA" in item.labels for item in repository.all())
    assert (
        repository.search("synthetic medication")[0].entity_type
        is EntityType.MEDICATION
    )
    assert repository.relationships("MED-DEMO-001")


def test_repository_rejects_duplicate_entities_and_dangling_relations() -> None:
    entity = KnowledgeEntity(
        "item-1", EntityType.EVIDENCE_DOCUMENT, "Fixture", "Placeholder"
    )
    repository = InMemoryKnowledgeRepository((entity,))
    with pytest.raises(ValueError, match="already exists"):
        repository.add_entity(entity)
    with pytest.raises(ValueError, match="unknown entity"):
        repository.add_relationship(
            KnowledgeRelationship("item-1", "related", "missing")
        )
