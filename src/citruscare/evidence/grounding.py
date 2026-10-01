"""Conservative lexical grounding checks; not a medical fact verifier."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from citruscare.evidence.engine import EvidenceBundle
from citruscare.knowledge.repository import _tokens


class GroundingStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    claim: str
    status: GroundingStatus
    supporting_source_ids: tuple[str, ...]
    missing_citation: bool
    uncertainty_detected: bool


@dataclass(frozen=True, slots=True)
class GroundingReport:
    status: GroundingStatus
    claims: tuple[ClaimAssessment, ...]
    unsupported_claim_count: int
    missing_citation_count: int
    grounding_rate: float

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "claims": [
                {
                    "claim": claim.claim,
                    "status": claim.status.value,
                    "supporting_source_ids": list(claim.supporting_source_ids),
                    "missing_citation": claim.missing_citation,
                    "uncertainty_detected": claim.uncertainty_detected,
                }
                for claim in self.claims
            ],
            "unsupported_claim_count": self.unsupported_claim_count,
            "missing_citation_count": self.missing_citation_count,
            "grounding_rate": self.grounding_rate,
            "method": "lexical heuristic; not clinical verification",
        }


class EvidenceGroundingValidator:
    _UNCERTAINTY = re.compile(
        r"\b(may|might|could|possibly|uncertain|unknown|not enough information)\b",
        re.IGNORECASE,
    )
    _CITATION = re.compile(r"\[([A-Za-z0-9_-]+)\]")
    _DISCLAIMERS = (
        "synthetic informational response",
        "no diagnosis",
        "not for clinical use",
        "no source-of-truth response",
        "review the attached retrieved evidence",
        "synthetic-data warning before use",
    )

    def validate(self, answer: str, evidence: EvidenceBundle) -> GroundingReport:
        sentences = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+", answer.strip())
            if part.strip()
        ]
        if not sentences:
            return GroundingReport(GroundingStatus.UNKNOWN, (), 0, 0, 0.0)
        claim_reports = tuple(
            self._assess(sentence, evidence) for sentence in sentences
        )
        statuses = {claim.status for claim in claim_reports}
        if statuses == {GroundingStatus.SUPPORTED}:
            overall = GroundingStatus.SUPPORTED
        elif GroundingStatus.UNSUPPORTED in statuses:
            overall = (
                GroundingStatus.PARTIALLY_SUPPORTED
                if GroundingStatus.SUPPORTED in statuses
                or GroundingStatus.PARTIALLY_SUPPORTED in statuses
                else GroundingStatus.UNSUPPORTED
            )
        elif GroundingStatus.PARTIALLY_SUPPORTED in statuses:
            overall = GroundingStatus.PARTIALLY_SUPPORTED
        else:
            overall = GroundingStatus.UNKNOWN
        supported = sum(
            claim.status == GroundingStatus.SUPPORTED for claim in claim_reports
        )
        return GroundingReport(
            status=overall,
            claims=claim_reports,
            unsupported_claim_count=sum(
                claim.status == GroundingStatus.UNSUPPORTED for claim in claim_reports
            ),
            missing_citation_count=sum(
                claim.missing_citation for claim in claim_reports
            ),
            grounding_rate=supported / len(claim_reports),
        )

    def _assess(self, claim: str, evidence: EvidenceBundle) -> ClaimAssessment:
        lowered = claim.casefold()
        if any(disclaimer in lowered for disclaimer in self._DISCLAIMERS):
            return ClaimAssessment(claim, GroundingStatus.UNKNOWN, (), False, True)
        explicit_ids = set(self._CITATION.findall(claim))
        valid_explicit = explicit_ids & {item.source_id for item in evidence.items}
        claim_tokens = _tokens(claim)
        matches: list[tuple[float, str]] = []
        for item in evidence.items:
            source_tokens = _tokens(f"{item.title} {item.content}")
            overlap = len(claim_tokens & source_tokens)
            score = overlap / len(claim_tokens) if claim_tokens else 0.0
            if item.source_id in valid_explicit or score >= 0.35:
                matches.append((score, item.source_id))
        sources = tuple(
            source_id
            for _, source_id in sorted(matches, key=lambda pair: (-pair[0], pair[1]))
        )
        uncertainty = bool(self._UNCERTAINTY.search(claim))
        if valid_explicit:
            status = GroundingStatus.SUPPORTED
        elif matches:
            status = GroundingStatus.PARTIALLY_SUPPORTED
        elif not evidence.items or uncertainty:
            status = GroundingStatus.UNKNOWN
        else:
            status = GroundingStatus.UNSUPPORTED
        return ClaimAssessment(
            claim=claim,
            status=status,
            supporting_source_ids=sources,
            missing_citation=bool(matches) and not bool(valid_explicit),
            uncertainty_detected=uncertainty,
        )
