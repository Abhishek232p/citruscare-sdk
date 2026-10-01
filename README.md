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

## Project map

```text
src/citruscare/
  clinical/       minimal observation value object
  core/           agent loop, messages, settings, errors
  governance/     metadata-only audit and in-memory consent primitives
  providers/      provider protocol, OpenAI-compatible and scripted adapters
  tools/          tool definition, validation, and registry
tests/            unit and provider-contract tests
examples/         offline and network-backed examples
docs/             architecture, privacy, development, and branding notes
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
