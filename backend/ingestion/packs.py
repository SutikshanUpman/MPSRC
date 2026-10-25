"""Several packs in one case: `pack_paths = [base_reference_pack, live_pack, ...]` (SYSTEM_ARCHITECTURE 23).

Each pack is ingested by `ingest_pack`; the records are then merged in list
order. A doc_id collision never stops a case (Pass 8b rule):
- same normalised body hash -> one document (later pack's copy kept), INFO log;
- different body -> the later pack's copy wins, the earlier copy is quarantined
  (kept for audit, never indexed), INTEGRITY_WARNING with both hashes.
Families are computed per pack by the pipeline, then joined across packs: the
same normalised body under different doc_ids in different packs is one
evidence family (one source), and every doc_id stays citable.
"""
from pathlib import Path

from .pipeline import Corpus, ingest_pack

COMPARED_FIELDS = ["EVENT_ID", "TITLE", "SOURCE_NAME", "SOURCE_TYPE", "RELIABILITY", "PUB_DATE", "PUB_TIME", "COUNTRY", "SECTOR"]


def _same_body(a, b):
    if a["body_hash"] or b["body_hash"]:
        return a["body_hash"] == b["body_hash"]
    return a["raw_file_sha256"] == b["raw_file_sha256"]


def load_packs(pack_paths):
    """Return (corpus, events, quarantined). `corpus.packs` lists every pack's manifest header."""
    corpora = [(str(Path(p)), ingest_pack(p)) for p in pack_paths]
    records, quarantined, events, pack_flags = {}, {}, [], []
    for path, corpus in corpora:
        pack_flags += [dict(f, pack_path=path) for f in corpus.pack_flags]
        for doc_id, rec in corpus.records.items():
            rec["pack_path"] = path
            old = records.get(doc_id)
            if old is not None:
                hashes = {"earlier": {"pack_path": old["pack_path"], "raw_file_sha256": old["raw_file_sha256"],
                                      "normalized_body_sha256": old["body_hash"]},
                          "later": {"pack_path": path, "raw_file_sha256": rec["raw_file_sha256"],
                                    "normalized_body_sha256": rec["body_hash"]}}
                if _same_body(old, rec):
                    differing = [f for f in COMPARED_FIELDS if old["manifest"].get(f) != rec["manifest"].get(f)]
                    events.append({"event_type": "PACK_DOC_ID_DUPLICATE", "level": "INFO", "doc_id": doc_id,
                                   "kept": path, "differing_manifest_fields": differing, **hashes})
                else:
                    old["quarantine_reason"] = "PACK_DOC_ID_COLLISION_EARLIER_COPY"
                    quarantined[doc_id] = old
                    events.append({"event_type": "INTEGRITY_WARNING", "level": "WARNING", "doc_id": doc_id,
                                   "kept": path, "quarantined": old["pack_path"], **hashes})
            records[doc_id] = rec
    events += _cross_pack_families(records, [p for p, _ in corpora])
    merged = Corpus(corpora[-1][1].pack, records, pack_flags)
    merged.packs = [dict(c.pack, pack_path=p) for p, c in corpora]
    return merged, events, quarantined


def _add_flag(rec, flag):
    if flag not in rec["flags"]:
        rec["flags"].append(flag)


def _cross_pack_families(records, pack_order):
    """Same normalised body under different doc_ids in different packs = one evidence family (one source),
    as within a pack (pipeline._families). Every doc_id stays a record and stays citable."""
    by_hash = {}
    for rec in records.values():
        if rec["body_hash"]:
            by_hash.setdefault(rec["body_hash"], []).append(rec)
    events = []
    for recs in by_hash.values():
        if len({r["pack_path"] for r in recs}) < 2:
            continue
        recs.sort(key=lambda r: (pack_order.index(r["pack_path"]), r["doc_id"]))
        families = {r["evidence_family_id"] for r in recs}
        members = sorted(d for d, r in records.items() if r["evidence_family_id"] in families)
        target = recs[0]["evidence_family_id"]
        # Same preference as within a pack: clean status first, then doc_id (same body, same length).
        preferred = sorted(members, key=lambda d: (records[d]["status"] not in ("OK", "RECODED"), d))[0]
        for d in members:
            rec = records[d]
            rec["evidence_family_id"] = target
            rec["family_members"] = members
            rec["preferred_in_family"] = d == preferred
            _add_flag(rec, "EVIDENCE_FAMILY_DUPLICATE")
            if rec in recs:
                _add_flag(rec, "DUPLICATE_CONTENT")
                _add_flag(rec, "CONTENT_HASH_DUPLICATE")
        events.append({"event_type": "CROSS_PACK_DUPLICATE_BODY", "level": "INFO", "doc_ids": [r["doc_id"] for r in recs],
                       "pack_paths": [r["pack_path"] for r in recs], "evidence_family_id": target,
                       "family_members": members, "normalized_body_sha256": recs[0]["body_hash"]})
    return events
