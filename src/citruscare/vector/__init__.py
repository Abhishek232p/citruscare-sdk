"""Provider-neutral embeddings and vector-store interfaces."""

from citruscare.vector.store import (
    EmbeddingProvider,
    FeatureHashEmbeddingProvider,
    InMemoryVectorStore,
    VectorMatch,
    VectorRecord,
    VectorStore,
)

__all__ = [
    "EmbeddingProvider",
    "FeatureHashEmbeddingProvider",
    "InMemoryVectorStore",
    "VectorMatch",
    "VectorRecord",
    "VectorStore",
]
