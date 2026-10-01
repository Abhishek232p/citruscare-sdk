# Runtime and local deployment

## Local API and playground

Install the package and development dependencies, then start the ASGI app:

```powershell
python -m pip install -e ".[dev]"
python -m uvicorn citruscare.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Open <http://127.0.0.1:8000/>. The UI uses same-origin requests to the API; it
does not contain a mock server or a separate JavaScript fixture. FastAPI's
interactive schema is at <http://127.0.0.1:8000/docs>.

## Model provider selection

The default `CITRUSCARE_MODEL_PROVIDER=mock` is offline and deterministic.
To choose the implemented OpenAI-compatible adapter, set
`CITRUSCARE_MODEL_PROVIDER=openai_compatible`, `CITRUSCARE_API_KEY`, and
optionally `CITRUSCARE_MODEL`, `CITRUSCARE_BASE_URL`, and
`CITRUSCARE_REQUEST_TIMEOUT`. Task routes can be configured as a JSON mapping
in `CITRUSCARE_MODEL_ROUTES`, for example
`{"general_information":"openai_compatible"}`. Fallback routing is disabled
unless `CITRUSCARE_FALLBACK_PROVIDER` is set. Credentials are sent as a Bearer
header, read from environment variables, and never returned by an API endpoint.
Do not send real health information to an external provider in this demo.

Groq is available through the same compatible adapter. Configure
`CITRUSCARE_MODEL_PROVIDER=groq`, `CITRUSCARE_MODEL`,
`GROQ_API_KEY`, and optionally `CITRUSCARE_BASE_URL` (defaults to
`https://api.groq.com/openai/v1` for the Groq default). Routed or fallback
Groq also requires the model and key. Credentials are read only on the server
from process environment; never place them in browser code or request bodies.
The playground's **Discover configured models** action explicitly requests
`/v1/models?discover=true`; ordinary health checks and model-route listing do
not make remote discovery calls. Discovery results use a configurable cache
TTL.

Provider requests use `CITRUSCARE_LLM_TIMEOUT_SECONDS` and
`CITRUSCARE_LLM_MAX_RETRIES`; transient network, timeout, rate-limit, and
selected server failures are retried within the configured bound. Auth,
permission, invalid-request, and model-not-found errors are not retried.
Responses expose normalized provider error codes, never raw vendor bodies or
credentials. `/v1/providers` and `/health` expose safe route metadata only.

Agent limits are configurable with `CITRUSCARE_MAX_AGENT_STEPS`,
`CITRUSCARE_MAX_TOOL_CALLS`, and `CITRUSCARE_AGENT_BUDGET_UNITS`. Knowledge
storage defaults to process-local memory; set
`CITRUSCARE_KNOWLEDGE_BACKEND=sqlite` and `CITRUSCARE_SQLITE_PATH` to enable
SQLite persistence for the synthetic fixtures. This SQLite adapter does not
provide encryption, tenant isolation, or production PHI controls.

## Container

```powershell
docker compose up --build
```

The compose mapping binds to loopback on the host. The container itself listens
on all interfaces as required by container networking. The default model stays
mock. The container is not a production hardening profile.
