"""
Retrieval layer with configurable degradation modes.

In real systems, retrieval failure is not binary.
Context can be degraded in multiple ways without the system knowing:
  - COMPLETE    : full, current data
  - STALE       : data from N seconds ago (cache not invalidated)
  - INCOMPLETE  : only a subset of fields returned (timeout, size limit)
  - NOISY       : correct structure but wrong values (data race, partial write)
  - INCONSISTENT: different documents read from different points in time
"""

import copy
import random
from data.store import VersionedStore

random.seed(42)  # reproducible noise


class RetrievalMode:
    COMPLETE     = "complete"
    STALE        = "stale"
    INCOMPLETE   = "incomplete"
    NOISY        = "noisy"
    INCONSISTENT = "inconsistent"


class Retriever:

    def __init__(self, store: VersionedStore, stale_by: float = 600.0):
        self.store = store
        self.stale_by = stale_by  # how many seconds "stale" means

    def retrieve(self, doc_ids: list, current_time: float,
                 mode: str = RetrievalMode.COMPLETE) -> tuple:
        """
        Returns (documents, retrieval_meta).
        retrieval_meta describes what happened during retrieval.
        """
        dispatch = {
            RetrievalMode.COMPLETE:     self._complete,
            RetrievalMode.STALE:        self._stale,
            RetrievalMode.INCOMPLETE:   self._incomplete,
            RetrievalMode.NOISY:        self._noisy,
            RetrievalMode.INCONSISTENT: self._inconsistent,
        }
        fn = dispatch.get(mode, self._complete)
        return fn(doc_ids, current_time)

    # ── Retrieval modes ───────────────────────────────────────────────────────

    def _complete(self, doc_ids, current_time):
        snap = self.store.snapshot(current_time)
        docs = self._to_dicts(snap.read_all(doc_ids), current_time)
        meta = {"mode": RetrievalMode.COMPLETE, "snapshot_time": current_time,
                "docs_returned": len(docs), "warning": None}
        return docs, meta

    def _stale(self, doc_ids, current_time):
        stale_time = current_time - self.stale_by
        snap = self.store.snapshot(stale_time)
        docs = self._to_dicts(snap.read_all(doc_ids), current_time)
        for d in docs:
            d["_retrieval_staleness_seconds"] = self.stale_by
        meta = {"mode": RetrievalMode.STALE,
                "snapshot_time": stale_time,
                "docs_returned": len(docs),
                "warning": f"data is {self.stale_by}s old — may not reflect current state"}
        return docs, meta

    def _incomplete(self, doc_ids, current_time):
        docs, meta = self._complete(doc_ids, current_time)
        truncated = []
        for doc in docs:
            keys = list(doc.keys())
            # keep doc_id + first half of remaining keys
            keep = keys[:max(2, len(keys) // 2)]
            truncated.append({k: doc[k] for k in keep})
        meta["mode"] = RetrievalMode.INCOMPLETE
        meta["warning"] = "response truncated — token/size limit hit during retrieval"
        meta["fields_dropped_per_doc"] = len(docs[0]) - len(truncated[0]) if docs else 0
        return truncated, meta

    def _noisy(self, doc_ids, current_time):
        docs, meta = self._complete(doc_ids, current_time)
        corruptions = [
            ("severity",          "P3"),
            ("status",            "monitoring"),
            ("error_rate",        "2%"),
            ("recommended_action","no immediate action required"),
        ]
        noisy = []
        for doc in docs:
            doc = copy.deepcopy(doc)
            field, bad_value = random.choice(corruptions)
            if field in doc:
                doc[f"_original_{field}"] = doc[field]  # keep for experiment visibility
                doc[field] = bad_value
            noisy.append(doc)
        meta["mode"] = RetrievalMode.NOISY
        meta["warning"] = "data integrity issue — one or more fields may contain stale cached values"
        return noisy, meta

    def _inconsistent(self, doc_ids, current_time):
        """
        Each document is read from a different point in time.
        This simulates a retrieval pipeline that reads from multiple
        replicas or cache layers with different lag.
        """
        docs = []
        read_times = []
        for i, doc_id in enumerate(doc_ids):
            # alternate between current and 5-min-old reads
            t = current_time if i % 2 == 0 else current_time - 300
            v = self.store.read_at(doc_id, t)
            read_times.append(t)
            if v:
                d = {"doc_id": v.doc_id, "version": v.version,
                     "data_timestamp": v.timestamp, **v.content}
                docs.append(d)
        meta = {"mode": RetrievalMode.INCONSISTENT,
                "snapshot_time": "mixed",
                "read_times": read_times,
                "docs_returned": len(docs),
                "warning": "documents read from different replicas — context is not temporally consistent"}
        return docs, meta

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dicts(versions, current_time) -> list:
        result = []
        for v in versions:
            d = {"doc_id": v.doc_id, "version": v.version,
                 "data_timestamp": v.timestamp,
                 "data_age_seconds": round(current_time - v.timestamp, 1)}
            d.update(v.content)
            result.append(d)
        return result
