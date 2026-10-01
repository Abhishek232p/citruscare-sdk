"""Context data structures with explicit source provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Provenance:
    source: str
    source_id: str
    label: str = "UNKNOWN"
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ContextItem:
    value: Any
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class Context:
    user_id: str | None = None
    patient_id: str | None = None
    encounter_id: str | None = None
    organization_id: str | None = None
    conversation_id: str | None = None
    facts: tuple[ContextItem, ...] = ()
    evidence: tuple[ContextItem, ...] = ()
    tool_results: tuple[ContextItem, ...] = ()
    policies: tuple[str, ...] = ()
    permissions: frozenset[str] = frozenset()


class ContextEngine:
    def assemble(
        self,
        *,
        user_id: str | None = None,
        patient_id: str | None = None,
        encounter_id: str | None = None,
        organization_id: str | None = None,
        conversation_id: str | None = None,
        facts: tuple[ContextItem, ...] = (),
        evidence: tuple[ContextItem, ...] = (),
        tool_results: tuple[ContextItem, ...] = (),
        policies: tuple[str, ...] = (),
        permissions: frozenset[str] = frozenset(),
    ) -> Context:
        return Context(
            user_id=user_id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            organization_id=organization_id,
            conversation_id=conversation_id,
            facts=facts,
            evidence=evidence,
            tool_results=tool_results,
            policies=policies,
            permissions=permissions,
        )
