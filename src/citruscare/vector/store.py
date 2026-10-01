"""Replaceable vector contracts and an offline feature-hash implementation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from threading import RLock
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> Sequence[float]: ...

    def embed_documents(
        self, documents: Sequence[str]
    ) -> Sequence[Sequence[float]]: ...


@dataclass(frozen=True, slots=True)
class VectorRecord:
    id: str
    vector: tuple[float, ...]
    text: str
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VectorMatch:
    record: VectorRecord
    score: float


class VectorStore(Protocol):
    def upsert(self, records: Sequence[VectorRecord]) -> None: ...

    def search(
        self, vector: Sequence[float], limit: int = 10
    ) -> Sequence[VectorMatch]: ...

    def delete(self, record_id: str) -> bool: ...


class FeatureHashEmbeddingProvider:
    """Dependency-free hashed token features for local interface demonstrations."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions

    def embed_text(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("text must not be empty")
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9_-]+", text.casefold())
        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return tuple(value / norm for value in vector) if norm else tuple(vector)

    def embed_documents(
        self, documents: Sequence[str]
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(self.embed_text(document) for document in documents)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}
        self._lock = RLock()

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        checked = tuple(records)
        for record in checked:
            if not record.id or not record.vector or not record.text:
                raise ValueError("vector records require id, vector, and text")
            if any(not math.isfinite(component) for component in record.vector):
                raise ValueError("vector components must be finite")
        with self._lock:
            for record in checked:
                self._records[record.id] = record

    def search(
        self, vector: Sequence[float], limit: int = 10
    ) -> tuple[VectorMatch, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not vector or any(not math.isfinite(component) for component in vector):
            raise ValueError("query vector must contain finite components")
        query_norm = math.sqrt(sum(component * component for component in vector))
        if query_norm == 0:
            raise ValueError("query vector must not be zero")
        with self._lock:
            records = tuple(self._records.values())
        matches: list[VectorMatch] = []
        for record in records:
            if len(record.vector) != len(vector):
                continue
            record_norm = math.sqrt(
                sum(component * component for component in record.vector)
            )
            if record_norm == 0:
                continue
            score = sum(a * b for a, b in zip(vector, record.vector, strict=True)) / (
                query_norm * record_norm
            )
            matches.append(VectorMatch(record, score))
        return tuple(
            sorted(matches, key=lambda match: (-match.score, match.record.id))[:limit]
        )

    def delete(self, record_id: str) -> bool:
        with self._lock:
            return self._records.pop(record_id, None) is not None
