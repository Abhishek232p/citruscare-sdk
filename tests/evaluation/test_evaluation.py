import pytest

from citruscare.evaluation import (
    EvaluationCase,
    EvaluationObservation,
    EvaluationRunner,
)


def test_operational_metrics_are_deterministic() -> None:
    cases = (
        EvaluationCase(
            "case-1",
            "fixture search",
            frozenset({"a", "b"}),
            frozenset({"source-a"}),
        ),
        EvaluationCase("case-2", "empty expected set", frozenset()),
    )
    observations = (
        EvaluationObservation(
            "case-1",
            frozenset({"a", "b", "extra"}),
            frozenset({"source-a"}),
            unsupported_claims=1,
            total_claims=2,
            tool_succeeded=True,
            latency_ms=20,
            grounding_rate=0.75,
            estimated_cost=0.02,
        ),
        EvaluationObservation(
            "case-2",
            frozenset(),
            tool_succeeded=False,
            policy_violation=True,
            latency_ms=40,
            structured_output_valid=False,
            grounding_rate=0.25,
            estimated_cost=0.03,
        ),
    )

    metrics = EvaluationRunner().evaluate(cases, observations)
    assert metrics.retrieval_precision == pytest.approx(1 / 3)
    assert metrics.retrieval_recall == 1
    assert metrics.citation_coverage == 1
    assert metrics.unsupported_claim_rate == 0.5
    assert metrics.tool_execution_success == 0.5
    assert metrics.policy_violations == 1
    assert metrics.latency_ms == 30
    assert metrics.structured_output_validity == 0.5
    assert metrics.grounding_rate == 0.5
    assert metrics.estimated_cost == pytest.approx(0.05)
    assert "not medical accuracy" in metrics.scope


def test_evaluation_requires_one_observation_per_case() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        EvaluationRunner().evaluate((EvaluationCase("case", "query", frozenset()),), ())
