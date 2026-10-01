"""Informational-only orchestration over SDK agent, policy, tools, and retrieval."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from citruscare.core.agent import Agent
from citruscare.core.config import Settings
from citruscare.core.errors import CitrusCareError, ProviderError
from citruscare.core.messages import AssistantTurn, Message
from citruscare.evidence.engine import EvidenceBundle, InformationKind
from citruscare.evidence.grounding import EvidenceGroundingValidator
from citruscare.governance.consent import ConsentLedger
from citruscare.governance.policy import (
    PolicyEngine,
    PolicyRequest,
)
from citruscare.knowledge.repository import (
    EntityType,
    KnowledgeRepository,
    synthetic_repository,
)
from citruscare.knowledge.sqlite_repository import SQLiteKnowledgeRepository
from citruscare.models.router import ModelRouter
from citruscare.observability.events import (
    InMemoryEventSink,
    RuntimeEvent,
    RuntimeEventSink,
)
from citruscare.providers.groq import GroqModelProvider
from citruscare.providers.model import (
    MockModelProvider,
    ModelOutput,
    ModelProvider,
    OpenAICompatibleModelProvider,
)
from citruscare.retrieval.engine import (
    InMemoryEvidenceRetriever,
    InMemoryKnowledgeRetriever,
    RetrievalEngine,
)
from citruscare.safety.engine import SafetyDecision, SafetyEngine
from citruscare.tools.registry import Tool, ToolCall, ToolRegistry


class TaskType(StrEnum):
    GENERAL_INFORMATION = "general_information"
    CLINICAL_SUMMARY = "clinical_summary"
    PATIENT_CONTEXT_SUMMARY = "patient_context_summary"
    MEDICATION_INFORMATION = "medication_information"
    EVIDENCE_SEARCH = "evidence_search"
    DOCUMENTATION_ASSISTANCE = "documentation_assistance"


@dataclass(frozen=True, slots=True)
class IntelligenceRequest:
    query: str
    task: TaskType = TaskType.GENERAL_INFORMATION
    user_id: str = "synthetic-demo-user"
    patient_id: str | None = None
    encounter_id: str | None = None
    structured_output: bool = False
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class IntelligenceResponse:
    request_id: str
    status: str
    answer: str
    confidence: float | None
    evidence: tuple[dict[str, Any], ...]
    facts: tuple[dict[str, Any], ...]
    inferences: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    requires_human_review: bool
    model: str
    provider: str
    tool_calls: tuple[dict[str, Any], ...]
    audit_id: str
    safety_decision: str
    latency_ms: float
    grounding: dict[str, Any] | None = None
    retrieved_context: tuple[dict[str, Any], ...] = ()
    agent_trace: tuple[dict[str, Any], ...] = ()
    model_latency_ms: float | None = None
    token_usage: dict[str, int] | None = None
    cost_metadata: dict[str, float | str] | None = None
    provider_request_id: str | None = None
    structured_output: dict[str, object] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "answer": self.answer,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "facts": list(self.facts),
            "inferences": list(self.inferences),
            "warnings": list(self.warnings),
            "requires_human_review": self.requires_human_review,
            "model": self.model,
            "provider": self.provider,
            "tool_calls": list(self.tool_calls),
            "audit_id": self.audit_id,
            "safety_decision": self.safety_decision,
            "latency_ms": self.latency_ms,
            "grounding": self.grounding,
            "retrieved_context": list(self.retrieved_context),
            "agent_trace": list(self.agent_trace),
            "model_latency_ms": self.model_latency_ms,
            "token_usage": self.token_usage,
            "cost_metadata": self.cost_metadata,
            "provider_request_id": self.provider_request_id,
            "structured_output": self.structured_output,
        }


@dataclass(frozen=True, slots=True)
class EngineAuditEvent:
    request_id: str
    actor: str
    action: str
    resource: str
    timestamp: datetime
    result: str
    policy_decision: str
    audit_id: str
    provider: str | None = None
    model: str | None = None
    latency_ms: float | None = None
    status: str = "completed"
    error_code: str | None = None
    safety_classification: str | None = None
    tool_call_names: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._events: dict[str, list[EngineAuditEvent]] = {}

    def add(self, event: EngineAuditEvent) -> None:
        self._events.setdefault(event.request_id, []).append(event)

    def get(self, request_id: str) -> tuple[EngineAuditEvent, ...]:
        return tuple(self._events.get(request_id, ()))


class _RouterProvider:
    def __init__(self, router: ModelRouter, task: str, request_id: str) -> None:
        self.router = router
        self.task = task
        self.request_id = request_id
        self.last_output: ModelOutput | None = None

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]],
    ) -> AssistantTurn:
        del tools
        self.last_output = await self.router.generate_for_request(
            self.task, messages, self.request_id
        )
        return AssistantTurn(content=self.last_output.text)


class AgentOrchestrator:
    SUPPORTED_TASKS = frozenset(TaskType)

    def __init__(
        self,
        repository: KnowledgeRepository,
        retrieval: RetrievalEngine,
        model_router: ModelRouter,
        policy_engine: PolicyEngine,
        safety_engine: SafetyEngine,
        tools: ToolRegistry,
        audit_repository: InMemoryAuditRepository | None = None,
        permissions: frozenset[str] = frozenset(),
        event_sink: RuntimeEventSink | None = None,
        grounding_validator: EvidenceGroundingValidator | None = None,
        max_tool_calls: int = 4,
    ) -> None:
        self.repository = repository
        self.retrieval = retrieval
        self.model_router = model_router
        self.policy_engine = policy_engine
        self.safety_engine = safety_engine
        self.tools = tools
        self.audit_repository = audit_repository or InMemoryAuditRepository()
        self.permissions = permissions
        self.event_sink = event_sink or InMemoryEventSink()
        self.grounding_validator = grounding_validator or EvidenceGroundingValidator()
        if max_tool_calls < 0:
            raise ValueError("max_tool_calls must not be negative")
        self.max_tool_calls = max_tool_calls

    def _emit(
        self,
        request_id: str,
        name: str,
        attributes: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        self.event_sink.record(
            RuntimeEvent(
                request_id=request_id,
                name=name,
                attributes=attributes or {},
            )
        )

    async def run(self, request: IntelligenceRequest) -> IntelligenceResponse:
        started = time.perf_counter()
        request_id = request.request_id or str(uuid4())
        if not request.query.strip():
            raise ValueError("query must not be empty")
        if request.task not in self.SUPPORTED_TASKS:
            raise ValueError("unsupported informational task")
        trace_start = len(self.event_sink.for_request(request_id))
        self._emit(request_id, "request_started", {"task": request.task.value})

        patient_id = request.patient_id
        if request.task == TaskType.PATIENT_CONTEXT_SUMMARY and patient_id is None:
            patient_id = "PATIENT-DEMO-001"
        required_permissions = self._required_permissions(request.task)
        policy = self.policy_engine.evaluate(
            PolicyRequest(
                actor_id=request.user_id,
                permissions=self.permissions,
                resource=patient_id or "synthetic-knowledge",
                action=request.task.value,
                purpose="demo-query",
                patient_id=patient_id,
                required_permissions=required_permissions,
                risk_level="low",
            )
        )
        audit_id = self._record_audit(
            request_id,
            request.user_id,
            "intelligence_query",
            patient_id or "synthetic-knowledge",
            "denied" if not policy.allowed else "authorized",
            policy.decision.value,
        )

        if not policy.allowed:
            safety = self.safety_engine.evaluate(
                request.query,
                EvidenceBundle.create((), request.query),
                policy,
                context_available=False,
            )
            self._emit(
                request_id,
                "safety_checked",
                {
                    "decision": safety.decision.value,
                    "classification": safety.classification.value,
                },
            )
            audit_id = self._record_audit(
                request_id,
                request.user_id,
                "intelligence_response",
                patient_id or "synthetic-knowledge",
                safety.decision.value.lower(),
                policy.decision.value,
            )
            self._emit(request_id, "response_completed", {"status": "denied"})
            return IntelligenceResponse(
                request_id=request_id,
                status="denied",
                answer=(
                    "The request was denied by policy; no data or model was accessed."
                ),
                confidence=None,
                evidence=(),
                facts=(),
                inferences=(),
                warnings=safety.warnings,
                requires_human_review=False,
                model="none",
                provider="none",
                tool_calls=(),
                audit_id=audit_id,
                safety_decision=safety.decision.value,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                grounding=self.grounding_validator.validate(
                    "", EvidenceBundle.create((), request.query)
                ).to_dict(),
                agent_trace=tuple(
                    event.to_dict()
                    for event in self.event_sink.for_request(request_id)[trace_start:]
                ),
            )

        self._emit(
            request_id,
            "agent_planned",
            {"agent": request.task.value, "max_steps": 1},
        )
        self._emit(request_id, "agent_step_started", {"step": 1})
        self._emit(request_id, "retrieval_started")
        retrieval = self.retrieval.retrieve(
            request.query,
            user_id=request.user_id,
            patient_id=patient_id,
            encounter_id=request.encounter_id,
            permissions=self.permissions,
        )
        self._emit(
            request_id,
            "retrieval_completed",
            {"evidence_count": len(retrieval.evidence.items)},
        )
        safety = self.safety_engine.evaluate(
            request.query,
            retrieval.evidence,
            policy,
            context_available=bool(retrieval.context.facts),
        )
        tool_name = self._select_tool(request.task)
        tool_call = ToolCall(
            id=f"{request_id}-tool-1",
            name=tool_name,
            arguments=self._tool_arguments(tool_name, request, patient_id),
        )
        tool_result: Any = None
        tool_error: str | None = None
        if safety.decision not in {
            SafetyDecision.DENY,
            SafetyDecision.REQUIRE_HUMAN_REVIEW,
        }:
            if self.max_tool_calls == 0:
                tool_error = "tool call budget exhausted"
            else:
                self._emit(request_id, "tool_started", {"tool": tool_name})
                try:
                    tool_result = await self.tools.invoke(
                        tool_call, permissions=self.permissions
                    )
                except CitrusCareError as exc:
                    tool_error = str(exc)
                self._emit(
                    request_id,
                    "tool_completed",
                    {"tool": tool_name, "success": tool_error is None},
                )

        output: ModelOutput | None = None
        structured_result: dict[str, object] | None = None
        answer = "The request was denied by policy; no model was called."
        if policy.allowed and safety.decision not in {
            SafetyDecision.DENY,
            SafetyDecision.REQUIRE_HUMAN_REVIEW,
        }:
            model_messages = [
                Message(
                    role="system",
                    content=(
                        "You are CitrusCare's informational assistant. For general "
                        "health education, explain common concepts in clear, "
                        "non-personalized language. Do not diagnose, prescribe, "
                        "recommend treatment, or make a clinical decision. Treat "
                        "retrieved demo fixtures as synthetic, not medical "
                        "authority. Attribute retrieved evidence only by its exact "
                        "source_id in square brackets; never invent sources. "
                        "Separate general background from retrieved EVIDENCE, "
                        "state when evidence is unavailable, and explain "
                        "uncertainty. Encourage a qualified clinician for "
                        "individualized or urgent concerns."
                    ),
                ),
                Message(
                    role="user",
                    content=self._compose_prompt(request.query, retrieval.evidence),
                ),
            ]
            self._emit(request_id, "model_started", {"task": request.task.value})
            model_started = time.perf_counter()
            try:
                if request.structured_output:
                    (
                        output,
                        structured_result,
                    ) = await self.model_router.generate_structured_for_request(
                        request.task.value, model_messages, request_id
                    )
                    answer = output.text
                else:
                    bridge = _RouterProvider(
                        self.model_router, request.task.value, request_id
                    )
                    agent_result = await Agent(
                        provider=bridge,
                        tools=ToolRegistry(),
                        instructions=model_messages[0].content,
                        max_turns=1,
                    ).run(model_messages[1].content)
                    answer = agent_result.content
                    output = bridge.last_output
            except ProviderError as exc:
                route = self.model_router.route_for(request.task.value)
                provider_name = exc.provider_name or route.provider_name
                model_name = exc.model_name or route.model_name
                latency_ms = round((time.perf_counter() - model_started) * 1000, 3)
                self._emit(
                    request_id,
                    "model_failed",
                    {
                        "provider": provider_name,
                        "model": model_name,
                        "latency_ms": latency_ms,
                        "error_code": exc.code,
                    },
                )
                self._record_audit(
                    request_id,
                    request.user_id,
                    "model_provider_failure",
                    "model_provider",
                    "failed",
                    policy.decision.value,
                    provider=provider_name,
                    model=model_name,
                    latency_ms=latency_ms,
                    status="failed",
                    error_code=exc.code,
                    safety_classification=safety.classification.value,
                    tool_call_names=(tool_call.name,)
                    if tool_result is not None
                    else (),
                    evidence_ids=tuple(
                        item.source_id for item in retrieval.evidence.items
                    ),
                )
                raise
            self._emit(
                request_id,
                "model_completed",
                {
                    "provider": output.provider if output else "unknown",
                    "model": output.model if output else "unknown",
                    "latency_ms": output.latency_ms if output else None,
                    "total_tokens": (
                        output.token_usage.get("total_tokens")
                        if output and output.token_usage
                        else None
                    ),
                },
            )
        elif safety.decision == SafetyDecision.REQUIRE_HUMAN_REVIEW:
            answer = (
                "This request requires review by a qualified human. "
                "No clinical decision was made."
            )

        grounding = self.grounding_validator.validate(answer, retrieval.evidence)
        if output and grounding.unsupported_claim_count:
            safety = self.safety_engine.evaluate(
                request.query,
                retrieval.evidence,
                policy,
                context_available=bool(retrieval.context.facts),
                unsupported_claims=True,
            )
        if tool_error:
            safety = safety.__class__(
                SafetyDecision.ALLOW_WITH_WARNING,
                safety.warnings + ("A requested tool could not be completed.",),
                False,
                safety.flags + ("tool_execution_failed",),
                safety.classification,
            )
        self._emit(
            request_id,
            "safety_checked",
            {
                "decision": safety.decision.value,
                "classification": safety.classification.value,
                "grounding": grounding.status.value,
            },
        )
        self._emit(request_id, "agent_step_completed", {"step": 1})

        if safety.decision == SafetyDecision.DENY:
            status = "denied"
        elif safety.decision == SafetyDecision.REQUIRE_HUMAN_REVIEW:
            status = "review_required"
        else:
            status = "ok"
        policy_decision = policy.decision.value
        audit_id = self._record_audit(
            request_id,
            request.user_id,
            "intelligence_response",
            patient_id or "synthetic-knowledge",
            safety.decision.value.lower(),
            policy_decision,
            provider=output.provider if output else None,
            model=output.model if output else None,
            latency_ms=output.latency_ms if output else None,
            status=status,
            safety_classification=safety.classification.value,
            tool_call_names=(tool_call.name,) if tool_result is not None else (),
            evidence_ids=tuple(item.source_id for item in retrieval.evidence.items),
        )
        evidence = tuple(item.to_dict() for item in retrieval.evidence.items)
        facts = tuple(
            {
                "kind": InformationKind.OBSERVED_FACT.value,
                "value": item.value,
                "provenance": {
                    "source": item.provenance.source,
                    "source_id": item.provenance.source_id,
                    "label": item.provenance.label,
                },
            }
            for item in retrieval.context.facts
        )
        warnings = list(safety.warnings)
        if output and grounding.unsupported_claim_count:
            warnings.append(
                "Generated text contains claims not lexically supported by "
                "retrieved evidence and is not authoritative."
            )
        if not retrieval.evidence.items:
            warnings.append("Response is not supported by retrieved evidence.")
        route = (
            self.model_router.route_for(request.task.value) if output is None else None
        )
        self._emit(request_id, "response_completed", {"status": status})
        retrieved_context = tuple(
            {
                "value": item.value,
                "source": item.provenance.source,
                "source_id": item.provenance.source_id,
                "label": item.provenance.label,
            }
            for item in retrieval.context.facts
        )
        return IntelligenceResponse(
            request_id=request_id,
            status=status,
            answer=answer,
            confidence=None,
            evidence=evidence,
            facts=facts,
            inferences=(),
            warnings=tuple(dict.fromkeys(warnings)),
            requires_human_review=safety.requires_human_review,
            model=output.model if output else (route.model_name if route else "none"),
            provider=output.provider
            if output
            else (route.provider_name if route else "none"),
            tool_calls=(
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "status": (
                        "success"
                        if tool_result is not None
                        else "failed"
                        if tool_error
                        else "skipped"
                    ),
                    "result": tool_result,
                },
            ),
            audit_id=audit_id,
            safety_decision=safety.decision.value,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            grounding=grounding.to_dict(),
            retrieved_context=retrieved_context,
            agent_trace=tuple(
                event.to_dict()
                for event in self.event_sink.for_request(request_id)[trace_start:]
            ),
            model_latency_ms=output.latency_ms if output else None,
            token_usage=output.token_usage if output else None,
            cost_metadata=output.cost_metadata if output else None,
            provider_request_id=output.provider_request_id if output else None,
            structured_output=structured_result,
        )

    def _record_audit(
        self,
        request_id: str,
        actor: str,
        action: str,
        resource: str,
        result: str,
        policy_decision: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        latency_ms: float | None = None,
        status: str = "completed",
        error_code: str | None = None,
        safety_classification: str | None = None,
        tool_call_names: tuple[str, ...] = (),
        evidence_ids: tuple[str, ...] = (),
    ) -> str:
        audit_id = (
            f"audit-{request_id}-{len(self.audit_repository.get(request_id)) + 1}"
        )
        self.audit_repository.add(
            EngineAuditEvent(
                request_id=request_id,
                actor=actor,
                action=action,
                resource=resource,
                timestamp=datetime.now(UTC),
                result=result,
                policy_decision=policy_decision,
                audit_id=audit_id,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
                safety_classification=safety_classification,
                tool_call_names=tool_call_names,
                evidence_ids=evidence_ids,
            )
        )
        return audit_id

    @staticmethod
    def _required_permissions(task: TaskType) -> frozenset[str]:
        if task == TaskType.PATIENT_CONTEXT_SUMMARY:
            return frozenset({"patient:read"})
        if task == TaskType.MEDICATION_INFORMATION:
            return frozenset({"knowledge:read"})
        return frozenset({"knowledge:read"})

    @staticmethod
    def _select_tool(task: TaskType) -> str:
        if task == TaskType.PATIENT_CONTEXT_SUMMARY:
            return "get_patient_context"
        if task == TaskType.MEDICATION_INFORMATION:
            return "get_medication_information"
        if task == TaskType.EVIDENCE_SEARCH:
            return "search_evidence"
        return "search_knowledge"

    @staticmethod
    def _tool_arguments(
        tool_name: str, request: IntelligenceRequest, patient_id: str | None
    ) -> dict[str, str]:
        if tool_name == "get_patient_context":
            return {"patient_id": patient_id or "PATIENT-DEMO-001"}
        if tool_name == "get_medication_information":
            match = re.search(r"MED-[A-Z]+-\d+", request.query.upper())
            return {"medication_id": match.group(0) if match else "MED-DEMO-001"}
        return {"query": request.query}

    @staticmethod
    def _compose_prompt(query: str, evidence: EvidenceBundle) -> str:
        context = [
            {
                "source_id": item.source_id,
                "title": item.title,
                "content": item.content,
                "kind": item.kind.value,
            }
            for item in evidence.items
        ]
        return (
            f"User question: {query}\n"
            f"Retrieved synthetic context: {json.dumps(context)}\n"
            "Return a concise informational response. Do not infer clinical facts."
        )


def _demo_tools(
    repository: KnowledgeRepository,
    retrieval: RetrievalEngine,
) -> ToolRegistry:
    registry = ToolRegistry()

    def get_patient_context(patient_id: str) -> dict[str, Any]:
        entity = repository.get(patient_id)
        if entity is None or entity.entity_type != EntityType.PATIENT:
            return {"found": False, "label": "SYNTHETIC DEMO DATA"}
        return {
            "found": True,
            "id": entity.id,
            "title": entity.title,
            "description": entity.description,
            "label": "SYNTHETIC DEMO DATA",
            "provenance": entity.provenance,
        }

    def search_knowledge(query: str) -> dict[str, Any]:
        entities = retrieval.knowledge_retriever.search_knowledge(query)
        return {
            "items": [
                {"id": item.id, "type": item.entity_type.value, "title": item.title}
                for item in entities
            ],
            "label": "SYNTHETIC DEMO DATA",
        }

    def search_evidence(query: str) -> dict[str, Any]:
        result = retrieval.retrieve(query)
        return {
            "items": [item.to_dict() for item in result.evidence.items],
            "label": "SYNTHETIC DEMO DATA",
        }

    def get_medication_information(medication_id: str) -> dict[str, Any]:
        entity = repository.get(medication_id)
        if entity is None or entity.entity_type != EntityType.MEDICATION:
            return {"found": False, "label": "SYNTHETIC DEMO DATA"}
        relations = repository.relationships(medication_id)
        return {
            "found": True,
            "id": entity.id,
            "title": entity.title,
            "description": entity.description,
            "relationships": [
                {
                    "relationship": relation.relationship,
                    "target_id": relation.target_id,
                }
                for relation in relations
            ],
            "label": "SYNTHETIC DEMO DATA — not medication advice",
        }

    definitions = (
        (
            "get_patient_context",
            "Get a synthetic patient fixture.",
            "patient_id",
            get_patient_context,
            "patient:read",
        ),
        (
            "search_knowledge",
            "Search synthetic knowledge entities.",
            "query",
            search_knowledge,
            "knowledge:read",
        ),
        (
            "search_evidence",
            "Search synthetic evidence fixtures.",
            "query",
            search_evidence,
            "evidence:read",
        ),
        (
            "get_medication_information",
            "Get a synthetic medication placeholder and its recorded relations.",
            "medication_id",
            get_medication_information,
            "knowledge:read",
        ),
    )
    for name, description, argument, handler, permission in definitions:
        registry.register(
            Tool(
                name=name,
                description=description,
                parameters={
                    "type": "object",
                    "properties": {argument: {"type": "string"}},
                    "required": [argument],
                    "additionalProperties": False,
                },
                handler=handler,
                required_permissions=frozenset({permission}),
            )
        )
    return registry


def create_demo_orchestrator(
    settings: Settings | None = None,
    model_provider: ModelProvider | None = None,
) -> AgentOrchestrator:
    settings = settings or Settings.from_env()
    if settings.knowledge_backend == "sqlite":
        repository = SQLiteKnowledgeRepository(settings.sqlite_path)
        if not repository.all():
            seed = synthetic_repository()
            for entity in seed.all():
                repository.add_entity(entity)
            for entity in seed.all():
                for relation in seed.relationships(entity.id):
                    repository.add_relationship(relation)
    else:
        repository = synthetic_repository()
    consent = ConsentLedger()
    consent.grant("PATIENT-DEMO-001", "demo-query")
    retrieval = RetrievalEngine(
        InMemoryKnowledgeRetriever(repository),
        InMemoryEvidenceRetriever(repository),
    )
    if model_provider is not None:
        provider = model_provider
        default_provider_name = provider.name
    else:
        default_provider_name = settings.model_provider
        if default_provider_name == "groq":
            provider = GroqModelProvider(
                settings,
                discovery_ttl_seconds=settings.model_discovery_ttl_seconds,
            )
        elif default_provider_name == "openai_compatible":
            provider = OpenAICompatibleModelProvider(settings)
        elif default_provider_name == "mock":
            provider = MockModelProvider()
        else:
            raise ValueError(f"Unsupported model provider: {default_provider_name}")
    providers: dict[str, ModelProvider] = {"mock": MockModelProvider()}
    providers[provider.name] = provider
    required_providers = {
        *settings.task_routes.values(),
        *((settings.fallback_provider,) if settings.fallback_provider else ()),
    }
    for provider_name in required_providers - providers.keys():
        if provider_name == "groq":
            providers[provider_name] = GroqModelProvider(
                settings,
                discovery_ttl_seconds=settings.model_discovery_ttl_seconds,
            )
        elif provider_name == "openai_compatible":
            providers[provider_name] = OpenAICompatibleModelProvider(settings)
        else:
            raise ValueError(f"Unsupported model provider: {provider_name}")
    fallback = (
        (settings.fallback_provider,)
        if settings.fallback_provider is not None
        and settings.fallback_provider != default_provider_name
        else ()
    )
    router = ModelRouter(
        providers=providers,
        routes=settings.task_routes,
        default_provider=default_provider_name,
        fallback_providers=fallback,
        timeout_seconds=settings.request_timeout,
        retries=settings.retries,
    )
    permissions = frozenset(
        {
            "patient:read",
            "knowledge:read",
            "evidence:read",
            "tools:execute",
        }
    )
    return AgentOrchestrator(
        repository=repository,
        retrieval=retrieval,
        model_router=router,
        policy_engine=PolicyEngine(consent),
        safety_engine=SafetyEngine(),
        tools=_demo_tools(repository, retrieval),
        permissions=permissions,
        max_tool_calls=settings.max_tool_calls,
    )
