"""In-memory store for signals the scheduler has prepared and risk-checked, keyed
by a generated id. The Android app's only write path (POST /signals/{id}/confirm)
looks entries up here — nothing else can create a confirmable entry, and popping
an entry on confirm/expiry makes double-confirm impossible."""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass

from core.models import ConsensusSignal
from services.trade_controller import PendingOrder


@dataclass
class StoredSignal:
    pending_id: str
    pending: PendingOrder
    consensus: ConsensusSignal
    created_at: float


class PendingStore:
    def __init__(self, ttl_seconds: int = 300, clock=time.time):
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, StoredSignal] = {}
        self._seen_fingerprints: dict[str, float] = {}

    def add(self, pending: PendingOrder, consensus: ConsensusSignal) -> str:
        pending_id = str(uuid.uuid4())
        self._entries[pending_id] = StoredSignal(
            pending_id=pending_id, pending=pending, consensus=consensus,
            created_at=self._clock())
        return pending_id

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [pid for pid, e in self._entries.items()
                  if now - e.created_at > self.ttl_seconds]
        for pid in expired:
            del self._entries[pid]

    def get(self, pending_id: str) -> StoredSignal | None:
        self._purge_expired()
        return self._entries.get(pending_id)

    def pop(self, pending_id: str) -> StoredSignal | None:
        self._purge_expired()
        return self._entries.pop(pending_id, None)

    def list_active(self) -> list[StoredSignal]:
        self._purge_expired()
        return list(self._entries.values())

    def already_pushed(self, fingerprint: str) -> bool:
        return fingerprint in self._seen_fingerprints

    def mark_pushed(self, fingerprint: str) -> None:
        self._seen_fingerprints[fingerprint] = self._clock()
