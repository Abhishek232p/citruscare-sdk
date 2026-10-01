# CitrusCare Intelligence Engine v0.2

## Scope

The engine is an informational, synthetic-data demonstration layered on the
CitrusCare SDK. It is not a clinical decision-support system, medical device,
or source of medical facts. It does not diagnose, prescribe, or make treatment
decisions. No source code from Eka Care's reference repository was copied; see
[third-party notices](../../THIRD_PARTY_NOTICES.md).

## Request path

```text
Browser or client
  -> FastAPI validation, request ID, and process-local rate limit
  -> bounded task-agent selection
  -> AgentOrchestrator
     -> deterministic policy/consent decision
     -> RetrievalEngine -> memory or SQLite KnowledgeRepository
                       -> EvidenceEngine -> provenance-bearing EvidenceBundle
     -> SafetyEngine
     -> permission-checked ToolRegistry
     -> SDK Agent -> ModelRouter -> configured ModelProvider
     -> lexical evidence-grounding assessment
  -> structured IntelligenceResponse, runtime trace, and metadata audit
```

Policy denial returns before retrieval, tools, or model invocation. High-risk
clinical-intent phrases are stopped for human review before any tool or model
call. This phrase matcher is a small demo guardrail, not clinical-grade
classification. Knowledge and evidence fixtures are deliberately placeholders.
The mock provider is the default and produces fixed, non-clinical text. An
OpenAI-compatible provider can be enabled explicitly; any fallback is opt-in.

## Modules

- `models` routes tasks to a configured default or task-specific provider and
  supports bounded timeout, retry, explicit fallback, and JSON-object output.
- `providers` defines the provider contract and mock/OpenAI-compatible adapters.
- `context`, `knowledge`, `retrieval`, `evidence`, and `vector` keep context
  fields separate and preserve source metadata. SQLite knowledge storage is
  available; the included feature-hash vector implementation is only an
  offline interface demo.
- `governance` evaluates identity, explicit permissions, consent, and risk.
- `safety` returns a structured allow, warn, review, or deny decision.
- `tools` validates declared schemas and permissions before handler execution.
- `memory` separates conversation, encounter, patient-context, and agent-task
  records behind an in-memory repository protocol.
- `agents` provide bounded specialist facades over one shared runtime; they do
  not recursively delegate or take clinical action.
- `ingestion` requires an explicitly authorized connector, normalizes and
  deduplicates records, and supports an audit callback. No source connector or
  clinical data is bundled.
- `medications` exposes an authorized replaceable source adapter; the local
  API returns synthetic placeholder records only.
- `observability` provides bounded process-local structured traces without
  request text or credentials.
- `evaluation` computes operational retrieval, grounding, citation, tool,
  policy, latency, estimated-cost, and structured-output metrics from supplied
  labels; it does not score medical accuracy.
- `api` exposes FastAPI endpoints and a same-origin browser playground.

## State and extension points

Repository, retriever, evidence, vector, ingestion, medication-source,
model-provider, and memory protocols are replaceable. SQLite can persist
knowledge entities and relationships when selected; consent, rate-limit
counters, runtime events, and audit events remain process-local. No user
authentication, external healthcare connector, durable audit backend, or
production clinical dataset is configured.
