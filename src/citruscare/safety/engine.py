"""Rule-based safety checks; not a clinical safety certification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from citruscare.evidence.engine import EvidenceBundle
from citruscare.governance.policy import PolicyDecision, PolicyResult


class SafetyDecision(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"
    REQUIRE_HUMAN_REVIEW = "REQUIRE_HUMAN_REVIEW"
    DENY = "DENY"


class RequestClassification(StrEnum):
    INFORMATIONAL = "INFORMATIONAL"
    DOCUMENTATION = "DOCUMENTATION"
    EDUCATIONAL = "EDUCATIONAL"
    CLINICAL_SUPPORT = "CLINICAL_SUPPORT"
    HIGH_RISK = "HIGH_RISK"
    PROHIBITED_AUTONOMOUS_ACTION = "PROHIBITED_AUTONOMOUS_ACTION"


@dataclass(frozen=True, slots=True)
class SafetyResult:
    decision: SafetyDecision
    warnings: tuple[str, ...]
    requires_human_review: bool
    flags: tuple[str, ...]
    classification: RequestClassification = RequestClassification.INFORMATIONAL


_BYPASS = re.compile(
    r"\b(ignore|bypass|disable|skip)\b.{0,40}\b(policy|safety|consent|governance)\b",
    re.IGNORECASE,
)
_HIGH_RISK = re.compile(
    r"\b(diagnos(e|is)|prescrib(e|ing|tion)|dos(age|ing)|"
    r"should i take|treatment plan|emergency treatment)\b",
    re.IGNORECASE,
)


class SafetyEngine:
    @staticmethod
    def classify(query: str) -> RequestClassification:
        normalized = query.casefold()
        if re.search(
            r"\b(autonomously|without (?:a )?clinician|autonomously prescribe|"
            r"autonomously diagnose|"
            r"choose (?:a )?treatment without (?:a )?clinician)\b",
            normalized,
        ):
            return RequestClassification.PROHIBITED_AUTONOMOUS_ACTION
        if _HIGH_RISK.search(query):
            return RequestClassification.HIGH_RISK
        if re.search(r"\b(document|format|summarize notes|draft note)\b", normalized):
            return RequestClassification.DOCUMENTATION
        if re.search(r"\b(teach|explain|learn|educational)\b", normalized):
            return RequestClassification.EDUCATIONAL
        if re.search(r"\b(clinical|care context|patient context)\b", normalized):
            return RequestClassification.CLINICAL_SUPPORT
        return RequestClassification.INFORMATIONAL

    def evaluate(
        self,
        query: str,
        evidence: EvidenceBundle,
        policy: PolicyResult,
        *,
        context_available: bool,
        unsupported_claims: bool = False,
    ) -> SafetyResult:
        flags: list[str] = []
        warnings: list[str] = ["SYNTHETIC DEMO DATA — not for clinical use."]
        classification = self.classify(query)
        if _BYPASS.search(query):
            flags.append("governance_bypass_attempt")
            return SafetyResult(
                SafetyDecision.DENY,
                tuple(warnings + ["Governance bypass requests are denied."]),
                False,
                tuple(flags),
                classification,
            )
        if classification == RequestClassification.PROHIBITED_AUTONOMOUS_ACTION:
            flags.append("prohibited_autonomous_action")
            return SafetyResult(
                SafetyDecision.DENY,
                tuple(warnings + ["Autonomous clinical actions are not supported."]),
                False,
                tuple(flags),
                classification,
            )
        if not policy.allowed:
            flags.append("unauthorized_action")
            return SafetyResult(
                SafetyDecision.DENY,
                tuple(warnings + [policy.reason]),
                False,
                tuple(flags),
                classification,
            )
        if classification == RequestClassification.HIGH_RISK:
            flags.append("high_risk_clinical_request")
            return SafetyResult(
                SafetyDecision.REQUIRE_HUMAN_REVIEW,
                tuple(
                    warnings
                    + ["No diagnosis, prescribing, or treatment advice is provided."]
                ),
                True,
                tuple(flags),
                classification,
            )
        if not context_available:
            flags.append("missing_context")
            warnings.append("No patient or encounter context was supplied.")
        if not evidence.items:
            flags.append("absent_evidence")
            warnings.append("No retrieved evidence supports a factual answer.")
        if unsupported_claims:
            flags.append("unsupported_claims")
            warnings.append("Unsupported model claims were detected.")
        if flags:
            return SafetyResult(
                SafetyDecision.ALLOW_WITH_WARNING,
                tuple(warnings),
                False,
                tuple(flags),
                classification,
            )
        if policy.decision == PolicyDecision.ALLOW_WITH_WARNING:
            return SafetyResult(
                SafetyDecision.ALLOW_WITH_WARNING,
                tuple(warnings + [policy.reason]),
                False,
                tuple(flags),
                classification,
            )
        return SafetyResult(
            SafetyDecision.ALLOW,
            tuple(warnings),
            False,
            tuple(flags),
            classification,
        )
