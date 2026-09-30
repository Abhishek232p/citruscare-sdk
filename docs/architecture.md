# Architecture

## Runtime

`Agent` owns a bounded asynchronous conversation loop. Providers implement the
`Provider` protocol and return an `AssistantTurn`. Tools are registered
explicitly and exposed to compatible models using function schemas. Tool
arguments receive basic schema validation before handler invocation. A turn
limit prevents unbounded model/tool cycles; a tool call received on the final
allowed turn is rejected before the handler runs.

The initial network adapter targets the OpenAI Chat Completions message/tool
format and uses `urllib` in a worker thread. Other providers can be added by
implementing the small protocol; provider credentials and request details stay
outside the agent loop. `ScriptedProvider` allows deterministic offline tests.

## Governance primitives

The optional audit sink receives event names, timestamps, tool names, and
turn counts only. It does not receive user text, tool arguments, or results.
Sink failures are surfaced as `AuditError`, rather than silently discarded.
`ConsentLedger` is a process-local example primitive and not a consent system of
record.

`ClinicalObservation` is a small validated value object. It is not a FHIR
resource or a claim of clinical suitability.

## Deliberately out of scope

This initial implementation does not include patient/provider identity
management, authentication/token issuance, medication decision support,
diagnostics, pharmacy workflows, care journeys, persistent databases, MCP,
streaming, or a REST server. Those domains require separate product, safety,
security, and interoperability requirements and are not represented by empty
placeholder packages.
