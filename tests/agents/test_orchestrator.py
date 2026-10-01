import asyncio

from citruscare.intelligence import IntelligenceRequest, create_demo_orchestrator


def test_orchestrator_returns_structured_response_with_audit_and_provenance() -> None:
    engine = create_demo_orchestrator()
    response = asyncio.run(
        engine.run(
            IntelligenceRequest(
                query="Summarize the synthetic evidence note.",
                request_id="agent-run-test-001",
            )
        )
    )
    assert response.request_id == "agent-run-test-001"
    assert response.status == "ok"
    assert response.provider == "mock"
    assert "could not be verified" not in response.answer
    assert response.evidence[0]["source_id"] == "EVIDENCE-DEMO-001"
    assert response.tool_calls[0]["status"] == "success"
    assert response.audit_id
    assert response.latency_ms >= 0
