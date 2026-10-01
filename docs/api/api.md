# HTTP API

Start the local service using the [runtime guide](../architecture/runtime.md).
All endpoints are served by `citruscare.api.app` and operate on the actual
SDK-backed synthetic engine. Knowledge is process-local by default and can use
the optional SQLite adapter when configured.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | API health JSON (send `Accept: application/json`); browser HTML when `Accept: text/html` |
| `GET` | `/version` | Service and SDK version |
| `POST` | `/v1/intelligence/query` | Validated informational request and structured response |
| `POST` | `/v1/agents/run` | Run the SDK-backed agent orchestration |
| `POST` | `/v1/research` | Run the bounded research task agent |
| `POST` | `/v1/retrieval/search` | Return retrieved knowledge and provenance-bearing evidence |
| `POST` | `/v1/evidence/search` | Return provenance and scoring metadata for evidence fixtures |
| `POST` | `/v1/knowledge/search` | Search synthetic entities and relationships |
| `POST` | `/v1/vector/search` | Search the offline demo vector index |
| `POST` | `/v1/medications/search` | Search the injected medication-source adapter |
| `GET` | `/v1/tools` | Describe registered demo tools and required permissions |
| `POST` | `/v1/tools/execute` | Execute a registered demo tool with validated arguments |
| `GET` | `/v1/models` | Show the provider/model route for each task; no remote discovery |
| `GET` | `/v1/models?discover=true` | Explicitly request cached discovery from providers that support it |
| `GET` | `/v1/providers` | Show safe configured-provider metadata; never credentials |
| `GET` | `/v1/audit/{request_id}` | Read process-local metadata audit events |

Search body example:

```json
{"query":"synthetic evidence note","limit":5}
```

Query body example:

```json
{"query":"Summarize the synthetic evidence note.","task":"general_information","structured_output":false}
```

Set `structured_output` to `true` to request JSON-object output from the selected
provider; unsupported providers fail explicitly, and the response includes the
parsed object in `structured_output`. Responses also include a lexical
`grounding` report, retrieved context, bounded agent trace, model latency and
token usage where the provider reports them. The grounding heuristic is not a
medical fact verifier. Cost metadata is absent unless an adapter supplies it.

Provider failures use a normalized `error` object with a stable error code,
safe message, and retryability indicator. Model-provider failures are traced
and recorded as metadata-only audit events without prompt text, credentials,
or raw provider response bodies. Groq discovery is opt-in and cached; it is
not performed by health checks or ordinary route listing.

Each response includes or echoes `request_id`; the `X-Request-ID` request
header is accepted only when it matches a bounded safe identifier, otherwise
the server generates a UUID. Responses set `Cache-Control: no-store` and
basic browser security headers. Validation errors intentionally omit submitted
request values. The API has an in-memory per-client rate limit; it is not a
distributed limit.
