"""In-memory consent ledger primitive for integration and testing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock


@dataclass(frozen=True, slots=True)
class ConsentGrant:
    subject_id: str
    purpose: str
    granted_at: datetime
    revoked_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.revoked_at is None


class ConsentLedger:
    """Process-local consent state; persist and govern it in a production system."""

    def __init__(self) -> None:
        self._grants: dict[tuple[str, str], ConsentGrant] = {}
        self._lock = RLock()

    def grant(self, subject_id: str, purpose: str) -> ConsentGrant:
        self._validate(subject_id, purpose)
        record = ConsentGrant(subject_id, purpose, datetime.now(UTC))
        with self._lock:
            self._grants[(subject_id, purpose)] = record
        return record

    def revoke(self, subject_id: str, purpose: str) -> ConsentGrant:
        self._validate(subject_id, purpose)
        with self._lock:
            current = self._grants.get((subject_id, purpose))
            if current is None or not current.active:
                raise ValueError("No active consent grant exists for this purpose")
            revoked = ConsentGrant(
                subject_id, purpose, current.granted_at, datetime.now(UTC)
            )
            self._grants[(subject_id, purpose)] = revoked
            return revoked

    def has_consent(self, subject_id: str, purpose: str) -> bool:
        with self._lock:
            grant = self._grants.get((subject_id, purpose))
            return bool(grant and grant.active)

    @staticmethod
    def _validate(subject_id: str, purpose: str) -> None:
        if not subject_id.strip() or not purpose.strip():
            raise ValueError("subject_id and purpose must not be empty")
