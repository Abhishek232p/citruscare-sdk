# CitrusCare SDK

CitrusCare SDK is an independent, early-stage Python toolkit for building
provider-neutral AI agents. It includes bounded tool execution, an
OpenAI Chat Completions-compatible adapter, metadata-only audit events,
process-local consent tracking, and a minimal typed clinical observation value.

The implementation is original CitrusCare code. The public repository
[`eka-care/echo-sdk`](https://github.com/eka-care/echo-sdk) was reviewed for
architecture only; no source code was copied. See
[third-party notices](THIRD_PARTY_NOTICES.md) and the
[branding audit](docs/branding-audit.md).

## Status and safety

This project is alpha software, not a medical device, clinical decision-support
system, EHR, HIPAA-compliant service, or production consent/audit system.
It does not make diagnoses, validate treatment, provide a complete FHIR
implementation, or establish regulatory compliance. Integrators are
responsible for security, clinical validation, applicable law, vendor terms,
and operational controls before handling real health information.

The included consent ledger is in-memory and process-local. The audit sink is
also in-memory and not durable or tamper-resistant. Audit records deliberately
exclude prompts, tool arguments, and model outputs; do not add those fields to
production audit sinks without a privacy and security review.

## Requirements and installation

Python 3.11 or newer is required. The SDK core uses only the standard library.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Quick start (offline)

```python
import asyncio

from citruscare import Agent, AssistantTurn, ScriptedProvider, Tool, ToolCall, ToolRegistry

async def main():
    tools = ToolRegistry()
    tools.register(Tool(
        name="lookup",
        description="Look up a demo reference",
        parameters={
            "type": "object",
            "properties": {"reference": {"type": "string"}},
            "required": ["reference"],
            "additionalProperties": False,
        },
        handler=lambda reference: {"found": reference == "demo"},
    ))
    provider = ScriptedProvider([
        AssistantTurn(tool_calls=(
            ToolCall("call-1", "lookup", {"reference": "demo"}),
        )),
        AssistantTurn(content="The demo reference was found."),
    ])
    result = await Agent(provider, tools).run("Check the demo reference.")
    print(result.content)

asyncio.run(main())
```

Run the self-contained example:

```powershell
python examples\basic_agent.py
```

For a separate consumer application that installs the local package, exercises
the implemented public API, and tests the real HTTP adapter over loopback, see
[the integration demo](examples/integration_demo/README.md).
The same consumer includes a loopback-only [SDK developer playground](examples/integration_demo/README.md#run-on-windows-powershell).

## Intelligence Engine v0.2

This repository also contains an informational-only FastAPI service and
same-origin browser playground built on the SDK. It routes requests through
policy and safety checks, synthetic retrieval and evidence, memory or optional
SQLite knowledge, permission-checked demo tools, bounded task agents, and a
replaceable model provider.
The mock provider is the default; this project does not include or claim a
CitrusCare foundation model.

All engine records are clearly marked **SYNTHETIC DEMO DATA**. Fixtures are
placeholders and not medical facts or recommendations. The engine does not
diagnose, prescribe, or make treatment decisions. It is not a clinical product
or production service and must not receive real patient information.

### Run the API and browser playground

```powershell
python -m pip install -e ".[dev]"
python -m uvicorn citruscare.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Open <http://127.0.0.1:8000/> for the browser UI and
<http://127.0.0.1:8000/docs> for the API schema. The UI calls the running
FastAPI endpoints; it is not a static mock. Docker users can run
`docker compose up --build`, which publishes only on localhost.

The offline orchestration walkthrough is:

```powershell
python examples\intelligence_demo\run.py
```

For HTTP and provider configuration, see
[API documentation](docs/api/api.md) and
[runtime documentation](docs/architecture/runtime.md).

### Engine architecture

The modules under `src/citruscare/` include task-aware provider routing,
retrieval and lexical grounding reports, memory or SQLite knowledge storage,
replaceable vector and authorized-ingestion interfaces, bounded task agents,
runtime traces, medication-source adapters, evaluation, and the API/UI. Offline
hashed-token vectors and synthetic medication records are interface
demonstrations, not clinical infrastructure. See
[the engine architecture](docs/architecture/intelligence-engine.md) and
[the production-readiness checklist](docs/production-readiness.md).

### Limitations

Authentication, tenant isolation, encryption/key management, durable consent and audit,
distributed rate limiting, production observability, security review,
clinical validation, and regulatory assessments are not implemented. The
OpenAI-compatible provider can transmit prompts to the configured vendor.
Do not send real health information to it. The safety layer is demonstrative,
not a clinical safety certification. See
[security limitations](docs/security/security.md) and
[evaluation scope](docs/evaluation/evaluation.md).

## Connecting an OpenAI-compatible endpoint

Set `CITRUSCARE_API_KEY` and, optionally, `CITRUSCARE_MODEL`,
`CITRUSCARE_BASE_URL`, `CITRUSCARE_REQUEST_TIMEOUT`, and
`CITRUSCARE_MAX_TURNS`. See [.env.example](.env.example). Keep credentials
outside source control; `.env` files are ignored.

```python
from citruscare import Agent, Settings, ToolRegistry
from citruscare.providers import OpenAICompatibleProvider

agent = Agent(OpenAICompatibleProvider(Settings.from_env()), ToolRegistry())
result = await agent.run("Say hello.")
```

The adapter sends prompts to the configured provider. Before sending health
information, confirm provider contracts, retention settings, data residency,
access controls, and applicable consent.

For a local PowerShell session, configure the endpoint without placing a key
in source control:

```powershell
$env:CITRUSCARE_MODEL_PROVIDER = "openai_compatible"
$env:CITRUSCARE_API_KEY = "<provider-key>"
$env:CITRUSCARE_FALLBACK_PROVIDER = ""
python -m uvicorn citruscare.api.app:app --host 127.0.0.1 --port 8000
```

Task routing is optional JSON in `CITRUSCARE_MODEL_ROUTES`, for example
`{"general_information":"openai_compatible"}`. Provider fallback is opt-in;
responses and `/v1/providers` expose provider/model metadata but never API keys.

## Connecting Groq

Groq uses the SDK's OpenAI-compatible transport with the server-side
`GROQ_API_KEY`; credentials are never accepted by the browser or returned by
the API. Choose the provider model from Groq's current model catalog. The
service does not contact Groq at startup, and model discovery is only performed
when explicitly requested through `GET /v1/models?discover=true` (results are
cached for `CITRUSCARE_MODEL_DISCOVERY_TTL_SECONDS`).

In PowerShell, set a newly issued key only in the server process environment:

```powershell
$env:CITRUSCARE_MODEL_PROVIDER = "groq"
$env:CITRUSCARE_MODEL = "<groq-model-id>"
$env:GROQ_API_KEY = "<newly-issued-groq-key>"
python -m uvicorn citruscare.api.app:app --host 127.0.0.1 --port 8000
```

`CITRUSCARE_BASE_URL` defaults to `https://api.groq.com/openai/v1` when Groq is
the default provider. Set it only if using an explicitly supported compatible
endpoint. Optional operational controls are
`CITRUSCARE_LLM_TIMEOUT_SECONDS` (30 seconds by default),
`CITRUSCARE_LLM_MAX_RETRIES` (two retries by default), and
`CITRUSCARE_MODEL_DISCOVERY_TTL_SECONDS` (five minutes by default). Only
transient failures are retried. Authentication, permission, invalid-request,
and missing-model errors are not retried. API errors are normalized and do not
include provider response bodies or credentials.

For explicit discovery, visit `http://127.0.0.1:8000/v1/models?discover=true`.
To exercise a real completion in a separately enabled smoke test, set
`CITRUSCARE_RUN_LIVE_LLM_TESTS=true` and run
`python -m pytest tests/test_groq_provider.py -k live`. Live calls are not part
of normal CI. Never use real patient information with this demo engine.

**Credential safety:** a Groq credential was pasted into the preceding
conversation. Treat it as compromised: revoke it in Groq, issue a replacement,
and configure only the replacement through `GROQ_API_KEY` before attempting a
live request. It has not been used or added to this repository.

## Project map

```text
src/citruscare/
  api/            FastAPI endpoints and same-origin developer playground
  agents/         bounded specialist task-agent facades
  context/        typed context with provenance
  clinical/       minimal observation value object
  core/           agent loop, messages, settings, errors
  evaluation/     deterministic operational metrics and fixture cases
  evidence/       provenance-bearing evidence bundles
  governance/     policy, metadata audit, and in-memory consent primitives
  ingestion/      authorized connector and normalization interfaces
  intelligence/   orchestration request/response workflow
  knowledge/      memory and SQLite repositories plus synthetic fixtures
  memory/         typed process-local memory repositories
  medications/    replaceable authorized medication-source adapters
  models/         task-aware provider routing
  observability/  bounded structured runtime events
  providers/      provider protocol, OpenAI-compatible and scripted adapters
  retrieval/      deterministic knowledge/evidence retrieval
  runtime/        bounded in-memory rate limiting
  safety/         structured deterministic safety decisions
  tools/          tool definition, validation, and registry
  vector/         replaceable embeddings and offline vector-store demo
tests/            unit and provider-contract tests
examples/         SDK, consumer, and intelligence examples
docs/             architecture, API, security, evaluation, and development
.github/workflows/ci.yml
```

## Development and validation

```powershell
python -m pytest
ruff check .
pip-audit
```

See [development](docs/development.md), [architecture](docs/architecture.md),
[privacy and security](docs/privacy-and-security.md), and
[branding audit](docs/branding-audit.md).
