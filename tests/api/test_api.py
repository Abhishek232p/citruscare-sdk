from fastapi.testclient import TestClient

from citruscare.api.app import create_app


def test_health_version_and_static_assets() -> None:
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "synthetic_demo"

    html = client.get("/health", headers={"Accept": "text/html"})
    assert html.status_code == 200
    assert "SYNTHETIC DEMO DATA" in html.text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/version").json()["service"] == "citruscare-intelligence-engine"


def test_intelligence_endpoint_calls_engine_and_records_audit() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/v1/intelligence/query",
        headers={"X-Request-ID": "integration-req-001"},
        json={"query": "Summarize the synthetic evidence note."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "integration-req-001"
    assert body["provider"] == "mock"
    assert body["safety_decision"] == "ALLOW"
    assert body["confidence"] is None
    assert body["tool_calls"][0]["status"] == "success"
    assert response.headers["X-Request-ID"] == "integration-req-001"
    events = client.get("/v1/audit/integration-req-001").json()["events"]
    assert [event["action"] for event in events] == [
        "intelligence_query",
        "intelligence_response",
    ]


def test_high_risk_query_is_reviewed_without_running_tools() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/agents/run",
        json={"query": "Should I take medication for this symptom?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["requires_human_review"] is True
    assert body["tool_calls"][0]["status"] == "skipped"
    assert not app.state.orchestrator.tools.history


def test_unauthorized_patient_request_does_not_retrieve_or_call_model() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/intelligence/query",
        json={
            "query": "Summarize patient context",
            "task": "patient_context_summary",
            "patient_id": "UNKNOWN-PATIENT",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "denied"
    assert body["evidence"] == []
    assert body["facts"] == []
    assert body["provider"] == "none"
    assert body["tool_calls"] == []


def test_validation_does_not_echo_submitted_query() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/v1/intelligence/query",
        json={"query": "sensitive text", "unexpected": "also sensitive"},
    )

    assert response.status_code == 422
    assert "sensitive text" not in response.text
    assert "also sensitive" not in response.text


def test_whitespace_query_is_rejected_as_validation_error() -> None:
    response = TestClient(create_app()).post(
        "/v1/intelligence/query", json={"query": "   "}
    )
    assert response.status_code == 422


def test_retrieval_knowledge_tools_and_models_routes() -> None:
    client = TestClient(create_app())
    assert client.post(
        "/v1/retrieval/search", json={"query": "synthetic evidence note"}
    ).json()["evidence"]
    assert client.post(
        "/v1/knowledge/search", json={"query": "synthetic medication"}
    ).json()["synthetic_data"]
    tools = client.get("/v1/tools").json()["tools"]
    assert "search_evidence" in {item["name"] for item in tools}
    executed = client.post(
        "/v1/tools/execute",
        json={
            "name": "search_evidence",
            "arguments": {"query": "synthetic evidence note"},
        },
    )
    assert executed.status_code == 200
    assert executed.json()["synthetic_data"]
    routes = client.get("/v1/models").json()["routes"]
    assert routes["general_information"]["provider"] == "mock"


def test_api_rate_limit_is_enforced() -> None:
    client = TestClient(create_app(rate_limit=1))
    first = client.post("/v1/knowledge/search", json={"query": "synthetic"})
    second = client.post("/v1/knowledge/search", json={"query": "synthetic"})
    assert first.status_code == 200
    assert second.status_code == 429
