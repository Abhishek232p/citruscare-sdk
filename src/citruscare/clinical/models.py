"""Basic observation value object; this is not a FHIR implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

ObservationValue: TypeAlias = str | int | float | bool


@dataclass(frozen=True, slots=True)
class ClinicalObservation:
    code: str
    value: ObservationValue
    unit: str | None
    effective_at: datetime
    subject_reference: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("observation code must not be empty")
        if not self.subject_reference.strip():
            raise ValueError("subject_reference must not be empty")
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at must include a timezone")
        if isinstance(self.value, float) and not (
            float("-inf") < self.value < float("inf")
        ):
            raise ValueError("numeric observation values must be finite")
