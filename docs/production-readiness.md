# Production-readiness assessment

This checklist records the current state of the v0.2 demonstration. It is not
a certification, security assessment, clinical validation, or authorization to
process protected health information.

| Area | Current implementation | Required before production |
|---|---|---|
| Provider routing | Mock by default; opt-in OpenAI-compatible provider; task routing, explicit fallback, timeout and retry settings | Vendor review, contract/data-retention review, model evaluation, operational failover policy, and secret management |
| Knowledge storage | In-memory default; optional SQLite persistence for synthetic entities/relationships | Production database, encryption, tenant isolation, retention/deletion, migrations, backup/restore, and access-control review |
| Retrieval and vectors | Lexical retrieval plus an offline feature-hash vector demonstration | Evaluated domain-appropriate embedding model, vector service, access filtering, deletion propagation, and relevance evaluation |
| Ingestion | Connector protocol requiring an explicit authorization flag, normalization, deduplication, and audit callback | Authorized source agreements, source-specific validation, provenance retention, monitoring, revocation, and ingestion security review |
| Medication data | Replaceable authorized source protocol; API demo uses synthetic placeholders | Licensed and validated source integration, freshness/authority policy, expert review, and jurisdiction-specific controls |
| Agents and tools | One-step specialist facades over a shared runtime; tool permissions, max steps/tool calls, budget checks, and timeout | Identity-aware authorization, workload isolation, adversarial testing, deployment limits, and human approval for consequential operations |
| Grounding | Sentence-level lexical heuristic with source-ID support | Clinically validated grounding and citation evaluation; never treat this heuristic as proof of truth |
| Safety | Demonstration phrase classifier and policy checks; blocks selected high-risk/autonomous requests | Independent safety engineering, clinical governance, misuse testing, and human workflows; no regulatory claims |
| Observability | Bounded in-process events with request ID, stage, timing, and token counts; prompts and credentials are not recorded | Durable privacy-reviewed telemetry, metrics/alerts, access controls, retention policy, and incident response |
| Audit and consent | Process-local demonstration stores | Durable, tamper-evident, access-controlled systems and verified consent lifecycle |
| API security | Request validation, bounded request IDs, no-store/security headers, and process-local rate limit | Authentication, authorization, tenant isolation, distributed rate limiting, abuse controls, deployment/network review |
| Cost tracking | Evaluation accepts supplied estimated cost; provider adapter does not claim pricing | A maintained, versioned pricing source and reconciled provider billing data |
| Evaluation | Synthetic operational fixtures for retrieval, grounding, tools, policy, latency, and output shape | Rights-cleared representative datasets, prospective protocols, clinical/expert review, bias analyses, and release gates |
| Release controls | CI runs tests, lint, package build, dependency audit, and the local integration consumer | Signed artifacts, SBOM, vulnerability response process, deployment approvals, and rollback exercises |

## Data boundary

Every bundled record is a synthetic placeholder. Do not enter real patient data
in the browser playground, SDK examples, tests, logs, or model prompts. The
OpenAI-compatible adapter sends request content to the configured external
provider. SQLite files are not encrypted by this project. Configure an
authorized connector only after verifying its data rights and security
controls; the project does not scrape sources or ship clinical datasets.

## Release decision

**Not production-ready for clinical or patient-data workloads.** The SDK/API
is an alpha engineering demonstration. The infrastructure seams are
replaceable, but the presence of interfaces does not imply an integrated,
validated, secure, or compliant production service.
