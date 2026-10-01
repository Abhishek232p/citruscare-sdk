"""Deterministic request authorization decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from citruscare.governance.consent import ConsentLedger


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"
    DENY = "DENY"


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    actor_id: str | None
    permissions: frozenset[str]
    resource: str
    action: str
    purpose: str
    patient_id: str | None = None
    required_permissions: frozenset[str] = frozenset()
    risk_level: str = "low"


@dataclass(frozen=True, slots=True)
class PolicyResult:
    decision: PolicyDecision
    allowed: bool
    reason: str


class PolicyEngine:
    def __init__(self, consent_ledger: ConsentLedger | None = None) -> None:
        self.consent_ledger = consent_ledger

    def evaluate(self, request: PolicyRequest) -> PolicyResult:
        if not request.actor_id or not request.actor_id.strip():
            return PolicyResult(PolicyDecision.DENY, False, "Identity is required")
        missing = request.required_permissions - request.permissions
        if missing:
            return PolicyResult(
                PolicyDecision.DENY,
                False,
                "Required permission is not granted",
            )
        if request.patient_id:
            if self.consent_ledger is None or not self.consent_ledger.has_consent(
                request.patient_id, request.purpose
            ):
                return PolicyResult(
                    PolicyDecision.DENY, False, "Active consent is required"
                )
        if request.risk_level == "high":
            return PolicyResult(
                PolicyDecision.REQUIRE_HUMAN_REVIEW,
                False,
                "High-risk action requires human review",
            )
        if request.risk_level == "moderate":
            return PolicyResult(
                PolicyDecision.ALLOW_WITH_WARNING,
                True,
                "Moderate-risk action is informational only",
            )
        return PolicyResult(PolicyDecision.ALLOW, True, "Policy checks passed")
