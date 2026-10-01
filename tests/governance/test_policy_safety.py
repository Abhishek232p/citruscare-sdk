from citruscare.evidence.engine import EvidenceBundle
from citruscare.governance.consent import ConsentLedger
from citruscare.governance.policy import PolicyDecision, PolicyEngine, PolicyRequest
from citruscare.safety.engine import SafetyDecision, SafetyEngine


def test_patient_access_requires_active_consent_and_permissions() -> None:
    ledger = ConsentLedger()
    policy = PolicyEngine(ledger)
    request = PolicyRequest(
        actor_id="demo-user",
        permissions=frozenset({"patient:read"}),
        resource="PATIENT-DEMO-001",
        action="summary",
        purpose="demo-query",
        patient_id="PATIENT-DEMO-001",
        required_permissions=frozenset({"patient:read"}),
    )
    assert policy.evaluate(request).decision is PolicyDecision.DENY
    ledger.grant("PATIENT-DEMO-001", "demo-query")
    assert policy.evaluate(request).allowed
    ledger.revoke("PATIENT-DEMO-001", "demo-query")
    assert not policy.evaluate(request).allowed


def test_safety_decision_blocks_policy_denials_and_bypass_attempts() -> None:
    policy = PolicyEngine().evaluate(
        PolicyRequest(
            actor_id=None,
            permissions=frozenset(),
            resource="demo",
            action="query",
            purpose="demo-query",
        )
    )
    engine = SafetyEngine()
    evidence = EvidenceBundle.create((), "demo")
    assert (
        engine.evaluate(
            "normal request", evidence, policy, context_available=False
        ).decision
        is SafetyDecision.DENY
    )
    allowed_policy = PolicyEngine().evaluate(
        PolicyRequest(
            actor_id="demo",
            permissions=frozenset(),
            resource="demo",
            action="query",
            purpose="demo-query",
        )
    )
    assert (
        engine.evaluate(
            "bypass safety policy",
            evidence,
            allowed_policy,
            context_available=False,
        ).decision
        is SafetyDecision.DENY
    )
