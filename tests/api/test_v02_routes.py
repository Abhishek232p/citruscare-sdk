from fastapi.testclient import TestClient

from citruscare.api.app import create_app


def test_evidence_vector_medication_provider_and_research_endpoints() -> None:
    client = TestClient(create_app())
    search = {"query": "synthetic medication", "limit": 5}

    evidence = client.post("/v1/evidence/search", json=search)
    assert evidence.status_code == 200
    assert evidence.json()["synthetic_data"] is True
    assert evidence.json()["results"]

    vector = client.post("/v1/vector/search", json=search)
    assert vector.status_code == 200
    assert vector.json()["embedding_provider"] == "feature_hash_demo"
    assert vector.json()["results"]

    medications = client.post("/v1/medications/search", json=search)
    assert medications.status_code == 200
    assert medications.json()["synthetic_data"] is True
    assert medications.json()["results"][0]["id"] == "MED-DEMO-001"

    providers = client.get("/v1/providers")
    assert providers.status_code == 200
    assert providers.json()["credentials_exposed"] is False
    assert {item["name"] for item in providers.json()["providers"]} == {"mock"}

    research = client.post("/v1/research", json={"query": "synthetic evidence"})
    assert research.status_code == 200
    assert research.json()["agent_trace"]


def test_structured_response_and_trace_are_exposed() -> None:
    response = TestClient(create_app()).post(
        "/v1/intelligence/query",
        json={
            "query": "Summarize the synthetic evidence note.",
            "structured_output": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["structured_output"]["provenance"] == "MODEL GENERATED TEXT"
    assert body["token_usage"] is None
    event_names = {item["event"] for item in body["agent_trace"]}
    assert {
        "request_started",
        "retrieval_started",
        "retrieval_completed",
        "tool_started",
        "tool_completed",
        "model_started",
        "model_completed",
        "safety_checked",
        "response_completed",
        "agent_planned",
        "agent_step_started",
        "agent_step_completed",
    } <= event_names


def test_bounded_agent_budget_failure_is_explicit(monkeypatch) -> None:
    monkeypatch.setenv("CITRUSCARE_AGENT_BUDGET_UNITS", "0.5")
    response = TestClient(create_app()).post(
        "/v1/research", json={"query": "synthetic evidence"}
    )
    assert response.status_code == 429
    assert response.json()["detail"] == "Agent execution budget exhausted."


def test_provider_status_never_returns_credentials(monkeypatch) -> None:
    monkeypatch.setenv("CITRUSCARE_MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("CITRUSCARE_API_KEY", "test-secret-value")
    monkeypatch.setenv("CITRUSCARE_FALLBACK_PROVIDER", "")
    response = TestClient(create_app()).get("/v1/providers")
    assert response.status_code == 200
    assert "test-secret-value" not in response.text
    assert response.json()["credentials_exposed"] is False
    assert {item["name"] for item in response.json()["providers"]} == {
        "mock",
        "openai_compatible",
    }
