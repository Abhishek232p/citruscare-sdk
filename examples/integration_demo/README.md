# CitrusCare SDK consumer integration demo

This is a separate consumer application. It installs the SDK distribution from
the local repository and imports `citruscare` as an application dependency; it
does not add the SDK's `src` directory to `PYTHONPATH`.

The demo exercises the public agent, scripted and OpenAI-compatible providers,
settings, synchronous and asynchronous tools, tool schemas, agent messages and
results, errors, audit, consent, and clinical observation APIs.

The HTTP adapter check makes a real `urllib` request to a loopback HTTP
conformance endpoint. That endpoint returns a fixed OpenAI-compatible response
and is **not an LLM**, is not a third-party provider, and does not generate
content. The demo labels that response explicitly. The other agent flow uses
the SDK's real deterministic `ScriptedProvider`. No SDK components or
transports are replaced by mocks.

All data is synthetic. This demo is not clinical software and must not be used
with patient information.

## Run on Windows PowerShell

From the repository root:

```powershell
Set-Location examples\integration_demo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ..\..
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m citruscare_integration_demo
.\.venv\Scripts\python.exe -m pytest
```

Launch the local developer playground after installing the consumer above:

```powershell
.\.venv\Scripts\python.exe -m citruscare_integration_demo.web --host 127.0.0.1 --port 8765
```

Then open <http://127.0.0.1:8765/>. Keep the terminal open while using the
playground and press `Ctrl+C` to stop it. The server refuses non-loopback
addresses, accepts no user-provided demo payloads, and uses synthetic values.
It is a local developer tool, not an internet-facing website or production
patient application.

The first editable install installs the SDK itself from this repository. The
second installs this consumer app and its test dependency. The SDK has no
runtime third-party dependencies.

Expected key output includes:

```text
"distribution": "citruscare-sdk"
"content": "Reference DEMO-REF-001 is active."
"direct_sync_tool_result": "Status: active"
"consent_active_after_revoke": false
"ai_generated": false
```

## Install the SDK in another Python application

Create/activate that application's environment, then install this local SDK
checkout by its path:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e C:\Users\abhis\CitrusCare\citruscare-sdk
```

For a non-editable local installation, use:

```powershell
python -m pip install C:\Users\abhis\CitrusCare\citruscare-sdk
```

After publishing the distribution to a package index, consumers can instead
install the published version with `python -m pip install citruscare-sdk`.

## Minimal consumer code

```python
import asyncio

from citruscare import Agent, AssistantTurn, ScriptedProvider, ToolRegistry


async def main() -> None:
    provider = ScriptedProvider(
        [AssistantTurn(content="Installed SDK is callable.")]
    )
    result = await Agent(provider, ToolRegistry()).run("Run a smoke test.")
    print(result.content)


asyncio.run(main())
```

Run the actual HTTP provider against a configured compatible service by setting
`CITRUSCARE_API_KEY`, and optionally `CITRUSCARE_MODEL` and
`CITRUSCARE_BASE_URL`, then construct `OpenAICompatibleProvider(Settings.from_env())`.
The demo's loopback protocol endpoint is only for offline transport validation.
