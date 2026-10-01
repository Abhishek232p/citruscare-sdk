"""Deterministic operational evaluation metrics for synthetic workflows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    query: str
    expected_entity_ids: frozenset[str]
    expected_citation_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    case_id: str
    retrieved_entity_ids: frozenset[str]
    citation_ids: frozenset[str] = frozenset()
    unsupported_claims: int = 0
    total_claims: int = 0
    tool_succeeded: bool | None = None
    policy_violation: bool = False
    latency_ms: float = 0.0
    structured_output_valid: bool = True
    grounding_rate: float = 0.0
    estimated_cost: float = 0.0

    def __post_init__(self) -> None:
        if self.unsupported_claims < 0 or self.total_claims < 0:
            raise ValueError("claim counts must not be negative")
        if self.unsupported_claims > self.total_claims:
            raise ValueError("unsupported_claims cannot exceed total_claims")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        if not 0 <= self.grounding_rate <= 1:
            raise ValueError("grounding_rate must be between zero and one")
        if not math.isfinite(self.estimated_cost) or self.estimated_cost < 0:
            raise ValueError("estimated_cost must not be negative")


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    retrieval_precision: float
    retrieval_recall: float
    citation_coverage: float
    unsupported_claim_rate: float
    tool_execution_success: float
    policy_violations: int
    latency_ms: float
    structured_output_validity: float
    grounding_rate: float
    estimated_cost: float
    cases_evaluated: int
    scope: str = "synthetic operational metrics; not medical accuracy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_precision": self.retrieval_precision,
            "retrieval_recall": self.retrieval_recall,
            "citation_coverage": self.citation_coverage,
            "unsupported_claim_rate": self.unsupported_claim_rate,
            "tool_execution_success": self.tool_execution_success,
            "policy_violations": self.policy_violations,
            "latency_ms": self.latency_ms,
            "structured_output_validity": self.structured_output_validity,
            "grounding_rate": self.grounding_rate,
            "estimated_cost": self.estimated_cost,
            "cases_evaluated": self.cases_evaluated,
            "scope": self.scope,
        }


class EvaluationRunner:
    """Compute observable system metrics from supplied deterministic labels."""

    def evaluate(
        self,
        cases: tuple[EvaluationCase, ...],
        observations: tuple[EvaluationObservation, ...],
    ) -> EvaluationMetrics:
        case_by_id = {case.case_id: case for case in cases}
        observation_by_id = {item.case_id: item for item in observations}
        if len(case_by_id) != len(cases):
            raise ValueError("evaluation case IDs must be unique")
        if len(observation_by_id) != len(observations):
            raise ValueError("observation case IDs must be unique")
        if set(case_by_id) != set(observation_by_id):
            raise ValueError("each case must have exactly one observation")

        precisions: list[float] = []
        recalls: list[float] = []
        citation_coverages: list[float] = []
        unsupported_claims = 0
        total_claims = 0
        tool_results: list[bool] = []
        for case_id, case in case_by_id.items():
            observation = observation_by_id[case_id]
            expected = case.expected_entity_ids
            retrieved = observation.retrieved_entity_ids
            precisions.append(
                len(expected & retrieved) / len(retrieved) if retrieved else 0.0
            )
            recalls.append(
                len(expected & retrieved) / len(expected) if expected else 1.0
            )
            expected_citations = case.expected_citation_ids
            citation_coverages.append(
                len(expected_citations & observation.citation_ids)
                / len(expected_citations)
                if expected_citations
                else 1.0
            )
            unsupported_claims += observation.unsupported_claims
            total_claims += observation.total_claims
            if observation.tool_succeeded is not None:
                tool_results.append(observation.tool_succeeded)

        latencies = [item.latency_ms for item in observations]
        return EvaluationMetrics(
            retrieval_precision=mean(precisions),
            retrieval_recall=mean(recalls),
            citation_coverage=mean(citation_coverages),
            unsupported_claim_rate=(
                unsupported_claims / total_claims if total_claims else 0.0
            ),
            tool_execution_success=(
                sum(tool_results) / len(tool_results) if tool_results else 1.0
            ),
            policy_violations=sum(item.policy_violation for item in observations),
            latency_ms=mean(latencies),
            structured_output_validity=mean(
                item.structured_output_valid for item in observations
            ),
            grounding_rate=mean(item.grounding_rate for item in observations),
            estimated_cost=sum(item.estimated_cost for item in observations),
            cases_evaluated=len(cases),
        )


def synthetic_evaluation_cases() -> tuple[EvaluationCase, ...]:
    """Return retrieval-only fixtures; labels are identifiers, never medical facts."""
    return (
        EvaluationCase(
            "synthetic-evidence-lookup",
            "synthetic evidence note",
            frozenset({"EVIDENCE-DEMO-001"}),
            frozenset({"EVIDENCE-DEMO-001"}),
        ),
        EvaluationCase(
            "synthetic-patient-placeholder",
            "PATIENT-DEMO-001",
            frozenset({"PATIENT-DEMO-001"}),
        ),
        EvaluationCase(
            "synthetic-guideline-placeholder",
            "GUIDELINE-DEMO-001",
            frozenset({"GUIDELINE-DEMO-001"}),
            frozenset({"GUIDELINE-DEMO-001"}),
        ),
    )
