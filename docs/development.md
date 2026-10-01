# Development

## Setup

Requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

No network provider or API key is needed to run unit tests.

## Consumer integration demo

The integration demo is a separately packaged consumer in
`examples/integration_demo`. From the repository root, install the SDK from
this checkout, install the consumer, then run its end-to-end flow and tests:

```powershell
Set-Location examples\integration_demo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ..\..
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m citruscare_integration_demo
.\.venv\Scripts\python.exe -m pytest
```

See [the consumer guide](../examples/integration_demo/README.md) for output
interpretation, commands to launch the local browser playground, and
installation commands for other applications.

## Checks

```powershell
python -m pytest
ruff check .
pip-audit
```

The CI workflow runs these checks on Python 3.11 and 3.12. Keep test fixtures
synthetic and never add real patient data, credentials, or provider responses
containing health information to the repository.

## Adding a provider

Implement `citruscare.providers.base.Provider.complete(messages, tools)` and
return `AssistantTurn`. Translate provider-specific exceptions to
`ProviderError` without including credential values, prompts, or response
bodies in exception text. Add contract tests using a fake transport.

## Adding tools

Register an explicit `Tool` with a JSON object schema and a handler. Restrict
tool capabilities and validate untrusted arguments at the integration
boundary. Tool handlers should be idempotent where possible and must apply
their own authorization, consent, and input validation.
