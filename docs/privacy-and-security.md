# Privacy and security

This SDK is a library, not a hosted service or compliance certification.
Integrators must perform their own threat modeling and legal/compliance review.

## Included safeguards

- Secrets are read from environment variables and are not written to disk by
  the SDK.
- Provider and tool errors avoid embedding request payloads or tool arguments.
- Audit events intentionally contain metadata only.
- Tool execution is explicit, schema-checked for common JSON types, and bounded
  by a maximum model-turn count.
- Git ignores `.env` files and common build artifacts.

These safeguards are not a substitute for access control, encryption, secure
deployment, retention policy, validated clinical workflows, or a durable and
tamper-evident audit system.

## Handling health information

Do not send protected or sensitive health information to a model provider until
the provider and deployment have been reviewed and approved for that use.
Configure transport security, access restrictions, retention, incident
response, and data residency at the system boundary. This SDK does not redact
PHI, enforce consent automatically, encrypt stored data, or certify HIPAA
compliance.

The included `ConsentLedger` and `MemoryAuditSink` are illustrative,
process-local implementations. Replace them with systems of record appropriate
to the deployment. Protect audit data and identifiers as sensitive data.

## Reporting a vulnerability

Do not file security reports containing patient information or secrets in
public issues. Contact the repository maintainers privately and include a
minimal reproducible description.
