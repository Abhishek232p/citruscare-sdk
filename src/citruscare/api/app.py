"""FastAPI entrypoint for the local synthetic CitrusCare Intelligence Engine."""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable
from contextvars import ContextVar
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from citruscare.agents import AgentExecutionBudget, MultiAgentOrchestrator
from citruscare.api.schemas import (
    AgentRunBody,
    IntelligenceQueryBody,
    SearchBody,
    ToolExecuteBody,
)
from citruscare.core.config import Settings
from citruscare.core.errors import ProviderError, ToolExecutionError
from citruscare.core.messages import ToolCall
from citruscare.intelligence.orchestrator import (
    AgentOrchestrator,
    IntelligenceRequest,
    TaskType,
    create_demo_orchestrator,
)
from citruscare.medications.sources import RepositoryMedicationSource
from citruscare.runtime.rate_limit import InMemoryRateLimiter
from citruscare.vector.store import (
    FeatureHashEmbeddingProvider,
    InMemoryVectorStore,
    VectorRecord,
)

_REQUEST_ID = ContextVar("citruscare_request_id", default="")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _create_default_orchestrator() -> AgentOrchestrator:
    settings = Settings.from_env()
    return create_demo_orchestrator(settings)


def create_app(
    orchestrator: AgentOrchestrator | None = None,
    *,
    rate_limit: int = 60,
) -> FastAPI:
    engine = orchestrator or _create_default_orchestrator()
    settings = Settings.from_env()
    agents = MultiAgentOrchestrator(
        engine,
        AgentExecutionBudget(
            max_steps=settings.max_agent_steps,
            max_tool_calls=settings.max_tool_calls,
            timeout_seconds=engine.model_router.timeout_seconds,
            budget_units=settings.agent_budget_units,
        ),
    )
    medication_source = RepositoryMedicationSource(
        engine.repository,
        source_name="synthetic_demo_fixture",
        authorized=True,
    )
    embedding_provider = FeatureHashEmbeddingProvider()
    vector_store = InMemoryVectorStore()
    vector_store.upsert(
        tuple(
            VectorRecord(
                id=entity.id,
                vector=tuple(
                    embedding_provider.embed_text(
                        f"{entity.title} {entity.description}"
                    )
                ),
                text=f"{entity.title}: {entity.description}",
                metadata={
                    "entity_type": entity.entity_type.value,
                    "source": entity.source,
                },
            )
            for entity in engine.repository.all()
        )
    )
    limiter = InMemoryRateLimiter(limit=rate_limit, window_seconds=60)
    application = FastAPI(
        title="CitrusCare Intelligence Engine",
        version="0.2.0",
        description=(
            "Synthetic-data informational API. Not for clinical decisions "
            "or production patient data."
        ),
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.orchestrator = engine
    application.state.agents = agents
    application.state.medication_source = medication_source
    application.state.vector_store = vector_store
    application.state.embedding_provider = embedding_provider

    async def run_bounded(
        operation: Awaitable[Any],
    ) -> Any:
        try:
            return await operation
        except TimeoutError as exc:
            raise HTTPException(
                status_code=504, detail="Agent execution timed out."
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=429, detail="Agent execution budget exhausted."
            ) from exc

    application.state.rate_limiter = limiter

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid4())
        )
        token = _REQUEST_ID.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = str(
                round((time.perf_counter() - started) * 1000, 3)
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        finally:
            _REQUEST_ID.reset(token)

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        errors = [
            {
                "location": list(item.get("loc", ())),
                "message": item.get("msg", "Invalid request"),
                "type": item.get("type", "validation_error"),
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"request_id": _REQUEST_ID.get(), "errors": errors},
        )

    @application.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        del request
        status_code = exc.status_code or 502
        if status_code < 400 or status_code > 599:
            status_code = 502
        messages = {
            "LLM_PROVIDER_AUTH_FAILED": (
                "The configured model provider rejected its credentials."
            ),
            "LLM_PROVIDER_PERMISSION_DENIED": (
                "The configured model provider denied access."
            ),
            "LLM_MODEL_NOT_FOUND": "The configured model is unavailable.",
            "LLM_PROVIDER_RATE_LIMITED": (
                "The configured model provider is rate limiting requests."
            ),
            "LLM_PROVIDER_TIMEOUT": "The configured model provider timed out.",
            "LLM_PROVIDER_UNAVAILABLE": (
                "The configured model provider is temporarily unavailable."
            ),
            "LLM_PROVIDER_INVALID_REQUEST": "The model provider rejected the request.",
            "LLM_PROVIDER_INVALID_RESPONSE": (
                "The model provider returned an invalid response."
            ),
        }
        return JSONResponse(
            status_code=status_code,
            content={
                "request_id": _REQUEST_ID.get(),
                "error": {
                    "code": exc.code,
                    "message": messages.get(
                        exc.code, "The configured model provider failed."
                    ),
                    "retryable": exc.retryable,
                },
            },
        )

    def enforce_rate_limit(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(
                status_code=429,
                detail="Request rate limit exceeded; retry later.",
                headers={"Retry-After": "60"},
            )

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    @application.get(
        "/playground", response_class=HTMLResponse, include_in_schema=False
    )
    @application.get("/agents", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/knowledge", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/evidence", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/tools", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/audit", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        content = files("citruscare.api").joinpath("static", "index.html").read_text()
        return HTMLResponse(content)

    @application.get("/assets/{asset_name}", include_in_schema=False)
    async def asset(asset_name: str) -> Response:
        allowed = {"app.css": "text/css", "app.js": "text/javascript"}
        if asset_name not in allowed:
            raise HTTPException(status_code=404, detail="Asset not found")
        body = files("citruscare.api").joinpath("static", asset_name).read_bytes()
        return Response(body, media_type=allowed[asset_name])

    @application.get("/health", response_model=None)
    async def health(request: Request) -> Response | dict[str, Any]:
        if "text/html" in request.headers.get("accept", ""):
            content = (
                files("citruscare.api").joinpath("static", "index.html").read_text()
            )
            return HTMLResponse(content)
        return {
            "status": "ok",
            "service": "citruscare-intelligence-engine",
            "mode": "synthetic_demo",
            "model_provider": engine.model_router.route_for(
                "general_information"
            ).provider_name,
            "model": engine.model_router.route_for("general_information").model_name,
            "provider_configured": True,
            "credentials_exposed": False,
        }

    @application.get("/version")
    async def get_version() -> dict[str, str]:
        try:
            package_version = version("citruscare-sdk")
        except PackageNotFoundError:
            package_version = "unknown"
        return {
            "service": "citruscare-intelligence-engine",
            "version": "0.2.0",
            "sdk_version": package_version,
        }

    @application.post("/v1/intelligence/query")
    async def intelligence_query(
        body: IntelligenceQueryBody, request: Request
    ) -> dict[str, Any]:
        enforce_rate_limit(request)
        request_id = _REQUEST_ID.get()
        result = await run_bounded(
            engine.run(
                IntelligenceRequest(
                    query=body.query,
                    task=TaskType(body.task),
                    patient_id=body.patient_id,
                    encounter_id=body.encounter_id,
                    structured_output=body.structured_output,
                    request_id=request_id,
                )
            )
        )
        return result.to_dict()

    @application.post("/v1/agents/run")
    async def run_agent(body: AgentRunBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        result = await run_bounded(
            agents.run(
                IntelligenceRequest(
                    query=body.query,
                    task=TaskType(body.task),
                    patient_id=body.patient_id,
                    encounter_id=body.encounter_id,
                    structured_output=body.structured_output,
                    request_id=_REQUEST_ID.get(),
                )
            )
        )
        return result.to_dict()

    @application.post("/v1/research")
    async def research(body: AgentRunBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        result = await run_bounded(
            agents.research(
                IntelligenceRequest(
                    query=body.query,
                    task=TaskType.EVIDENCE_SEARCH,
                    patient_id=body.patient_id,
                    encounter_id=body.encounter_id,
                    request_id=_REQUEST_ID.get(),
                )
            )
        )
        return result.to_dict()

    @application.post("/v1/retrieval/search")
    async def retrieval_search(body: SearchBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        result = engine.retrieval.retrieve(body.query, limit=body.limit)
        return {
            "request_id": _REQUEST_ID.get(),
            "query": result.normalized_query,
            "entities": [
                {
                    "id": item.id,
                    "type": item.entity_type.value,
                    "title": item.title,
                    "source": item.source,
                    "provenance": item.provenance,
                }
                for item in result.knowledge
            ],
            "evidence": [item.to_dict() for item in result.evidence.items],
            "synthetic_data": True,
            "context_item_count": len(result.context.facts)
            + len(result.context.evidence),
        }

    @application.post("/v1/evidence/search")
    async def evidence_search(body: SearchBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        result = engine.retrieval.retrieve(body.query, limit=body.limit)
        return {
            "request_id": _REQUEST_ID.get(),
            "query": result.normalized_query,
            "results": [item.to_dict() for item in result.evidence.items],
            "synthetic_data": True,
            "warning": "Evidence fixtures are synthetic and are not clinical evidence.",
        }

    @application.post("/v1/medications/search")
    async def medication_search(body: SearchBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        records = medication_source.search(body.query, body.limit)
        return {
            "request_id": _REQUEST_ID.get(),
            "query": body.query,
            "source": medication_source.source_name,
            "results": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "source": item.source,
                    "source_id": item.source_id,
                    "provenance": item.provenance,
                    "authority": item.authority,
                }
                for item in records
            ],
            "synthetic_data": True,
            "warning": "Synthetic placeholders only; no medication facts or advice.",
        }

    @application.post("/v1/knowledge/search")
    async def knowledge_search(body: SearchBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        entities = engine.repository.search(body.query, body.limit)
        return {
            "request_id": _REQUEST_ID.get(),
            "query": body.query,
            "synthetic_data": True,
            "results": [
                {
                    "id": entity.id,
                    "type": entity.entity_type.value,
                    "title": entity.title,
                    "description": entity.description,
                    "relationships": [
                        {
                            "relationship": relation.relationship,
                            "target_id": relation.target_id,
                        }
                        for relation in engine.repository.relationships(entity.id)
                    ],
                    "source": entity.source,
                    "provenance": entity.provenance,
                }
                for entity in entities
            ],
        }

    @application.post("/v1/vector/search")
    async def vector_search(body: SearchBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        query_vector = embedding_provider.embed_text(body.query)
        matches = vector_store.search(query_vector, body.limit)
        return {
            "request_id": _REQUEST_ID.get(),
            "query": body.query,
            "results": [
                {
                    "id": match.record.id,
                    "text": match.record.text,
                    "score": match.score,
                    "metadata": dict(match.record.metadata),
                }
                for match in matches
            ],
            "synthetic_data": True,
            "embedding_provider": "feature_hash_demo",
            "warning": "Offline feature hashing is not semantic or clinical embedding.",
        }

    @application.post("/v1/tools/execute")
    async def execute_tool(body: ToolExecuteBody, request: Request) -> dict[str, Any]:
        enforce_rate_limit(request)
        call = ToolCall(
            id=f"{_REQUEST_ID.get()}-tool",
            name=body.name,
            arguments=body.arguments,
        )
        try:
            result = await engine.tools.invoke(call, permissions=engine.permissions)
        except ToolExecutionError as exc:
            status_code = 403 if "Permission denied" in str(exc) else 400
            raise HTTPException(status_code, str(exc)) from exc
        return {
            "request_id": _REQUEST_ID.get(),
            "tool": body.name,
            "result": result,
            "synthetic_data": True,
        }

    @application.get("/v1/tools")
    async def list_tools() -> dict[str, Any]:
        return {
            "request_id": _REQUEST_ID.get(),
            "tools": engine.tools.describe(),
        }

    @application.get("/v1/models")
    async def models(discover: bool = False) -> dict[str, Any]:
        task_names = (
            "general_information",
            "clinical_summary",
            "patient_context_summary",
            "medication_information",
            "evidence_search",
            "documentation_assistance",
        )
        tasks = {}
        for task in task_names:
            route = engine.model_router.route_for(task)
            tasks[task] = {
                "provider": route.provider_name,
                "model": route.model_name,
                "supports_structured_output": route.supports_structured_output,
            }
        discovered: dict[str, list[str]] = {}
        if discover:
            for provider_status in engine.model_router.provider_status():
                provider_name = provider_status["name"]
                provider = engine.model_router.provider(str(provider_name))
                discover_models = getattr(provider, "discover_models", None)
                if callable(discover_models):
                    discovered[str(provider_name)] = list(await discover_models())
        return {
            "request_id": _REQUEST_ID.get(),
            "routes": tasks,
            "discovered_models": discovered,
            "discovery_requested": discover,
        }

    @application.get("/v1/providers")
    async def providers() -> dict[str, Any]:
        return {
            "request_id": _REQUEST_ID.get(),
            "providers": engine.model_router.provider_status(),
            "credentials_exposed": False,
        }

    @application.get("/v1/audit/{request_id}")
    async def audit(request_id: str) -> dict[str, Any]:
        events = engine.audit_repository.get(request_id)
        return {
            "request_id": request_id,
            "events": [
                {
                    "audit_id": event.audit_id,
                    "actor": event.actor,
                    "action": event.action,
                    "resource": event.resource,
                    "timestamp": event.timestamp.isoformat(),
                    "result": event.result,
                    "policy_decision": event.policy_decision,
                    "provider": event.provider,
                    "model": event.model,
                    "latency_ms": event.latency_ms,
                    "status": event.status,
                    "error_code": event.error_code,
                    "safety_classification": event.safety_classification,
                    "tool_call_names": list(event.tool_call_names),
                    "evidence_ids": list(event.evidence_ids),
                }
                for event in events
            ],
        }

    return application


app = create_app()
