# Security status

## Implemented demo controls

- OpenAI-compatible credentials use `CITRUSCARE_API_KEY`; Groq credentials use
  `GROQ_API_KEY`. Both are read from server process environment and excluded
  from settings representations, API responses, browser code, and provider
  error messages.
- Provider errors are normalized without forwarding raw response bodies;
  provider-failure traces and audit entries contain only operational metadata.
- Optional Groq model discovery is explicitly requested and cached; it is not
  automatically contacted by health checks or model-route listing.
- Request schemas limit lengths, identifier formats, task names, and tool
  request shape; extra fields are rejected.
- Validation responses expose error locations/messages but do not echo the
  submitted body.
- Request IDs, `Cache-Control: no-store`, `nosniff`, frame denial, and a
  no-referrer policy are set on HTTP responses.
- Process-local per-client rate limiting is bounded by a configured key cap.
- The policy engine checks demo identity, permissions, explicit synthetic
  consent, and action risk. Safety checks precede tool and model execution.
- The engine denies unauthorized requests before retrieval, tools, and model
  calls; audit events are metadata-only.
- Tool schemas are validated and tool permissions are enforced by the registry.
- CI runs dependency vulnerability checks with `pip-audit`.

## Not production-ready

This demo has no authentication, authorization token validation, tenant
isolation, durable consent, persistent/tamper-evident audit, encryption/key
management, distributed rate limit, network egress controls, monitoring, or
incident response. Memory, knowledge, consent, audit, and counters are
process-local. The OpenAI-compatible adapter can send configured prompts to an
external service. Do not expose this API publicly or submit real patient data.
Before real health data use, conduct a threat model, privacy and security
review, legal and provider-contract review, clinical governance, penetration
testing, and validated operational controls.

The pattern-based safety checks and synthetic fixture evaluation do not
establish clinical accuracy, safety, regulatory status, or certification.
