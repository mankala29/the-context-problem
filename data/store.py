"""
Versioned document store with MVCC-like snapshot isolation.

Core idea (borrowed from database theory):
  - Every write creates a new version of a document, never overwriting the old one.
  - A "snapshot" is a consistent read view anchored at a specific timestamp.
  - Two requests reading at different timestamps will see different versions
    of the same document — and therefore construct different contexts.

This is the database-layer analogy for why two LLM calls issued seconds apart
can operate on completely different realities.
"""

import copy
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DocumentVersion:
    doc_id: str
    version: int
    timestamp: float          # seconds since experiment epoch (t=0)
    content: dict
    author: str = "system"

    def age(self, current_time: float) -> float:
        return current_time - self.timestamp


class VersionedStore:
    """
    Append-only document store.  Every write appends a new version.
    Reads are always snapshot-isolated: you see the world as it was
    at a specific point in time.
    """

    def __init__(self):
        # doc_id -> [DocumentVersion, ...] sorted by timestamp ascending
        self._log: dict[str, list[DocumentVersion]] = {}

    # ── Writes ────────────────────────────────────────────────────────────────

    def write(self, doc_id: str, content: dict, timestamp: float,
              author: str = "system") -> DocumentVersion:
        if doc_id not in self._log:
            self._log[doc_id] = []
        version_num = len(self._log[doc_id]) + 1
        dv = DocumentVersion(
            doc_id=doc_id,
            version=version_num,
            timestamp=timestamp,
            content=copy.deepcopy(content),
            author=author,
        )
        self._log[doc_id].append(dv)
        return dv

    # ── Reads ─────────────────────────────────────────────────────────────────

    def read_at(self, doc_id: str, timestamp: float) -> Optional[DocumentVersion]:
        """
        MVCC read: return the latest version whose timestamp <= given timestamp.
        If the document didn't exist yet at that time, returns None.
        """
        result = None
        for v in self._log.get(doc_id, []):
            if v.timestamp <= timestamp:
                result = v
            else:
                break
        return result

    def read_latest(self, doc_id: str) -> Optional[DocumentVersion]:
        versions = self._log.get(doc_id, [])
        return versions[-1] if versions else None

    def all_doc_ids(self) -> list:
        return list(self._log.keys())

    def version_history(self, doc_id: str) -> list:
        return list(self._log.get(doc_id, []))

    # ── Snapshots ─────────────────────────────────────────────────────────────

    def snapshot(self, timestamp: float) -> "Snapshot":
        """
        Begin a read-only transaction at the given timestamp.
        All reads through this snapshot see data as of that moment.
        """
        return Snapshot(self, timestamp)


class Snapshot:
    """
    A consistent read view of the store at a given timestamp.

    Analogy: a database transaction with REPEATABLE READ isolation.
    Every read in this snapshot sees the same version of every document,
    regardless of writes happening concurrently.
    """

    def __init__(self, store: VersionedStore, timestamp: float):
        self.store = store
        self.snapshot_timestamp = timestamp
        self._read_set: list[str] = []

    def read(self, doc_id: str) -> Optional[DocumentVersion]:
        v = self.store.read_at(doc_id, self.snapshot_timestamp)
        self._read_set.append(doc_id)
        return v

    def read_all(self, doc_ids: list) -> list:
        return [v for doc_id in doc_ids if (v := self.read(doc_id)) is not None]
