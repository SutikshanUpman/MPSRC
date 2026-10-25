"""Private agent memory (SYSTEM_ARCHITECTURE 19; review F15).

One append-only JSONL store per agent: <root>/<agent>/memory.jsonl, lasting
across cases. A store can only be opened by its owner; agents share nothing but
the Case File. Every entry carries source_doc_ids, max_source_pub_date and
written_as_of, set by the runtime (never by the agent). At read time an entry
whose max_source_pub_date is after the current case's as-of date is hidden (kept
on disk) and the hide is logged. A case_note is loaded only for the same event.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

AGENTS = ("heimdall", "thor", "loki", "odin")


class MemoryAccessDenied(PermissionError):
    pass


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class MemoryStore:
    def __init__(self, root, owner, requester):
        if owner not in AGENTS:
            raise ValueError(f"unknown agent {owner!r}")
        if requester != owner:
            raise MemoryAccessDenied(f"{requester} cannot open {owner}'s private memory")
        self.owner = owner
        self.path = Path(root) / owner / "memory.jsonl"

    def entries(self):
        if not self.path.is_file():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def read_for_case(self, as_of, event_id):
        """Return (visible, hidden). Hidden = max_source_pub_date after as_of. Case notes need the same event."""
        visible, hidden = [], []
        for e in self.entries():
            if e["max_source_pub_date"] and e["max_source_pub_date"] > as_of:
                hidden.append(e)
            elif e["kind"] == "case_note" and e["value"].get("event_id") != event_id:
                continue
            else:
                visible.append(e)
        return visible, hidden

    def write(self, key, kind, value, source_doc_ids, pub_dates, written_as_of, source_case_id, trace_ref=None):
        """Append one entry unless an identical one (same key, value and source documents) exists.
        The sources are part of the identity: a note hidden for a later as-of date must not block the same
        note re-learned from documents this case may see. Returns the entry or None."""
        memory_id = f"mem-{self.owner}-" + hashlib.sha256(
            _canonical([key, value, sorted(source_doc_ids)]).encode()).hexdigest()[:10]
        if any(e["memory_id"] == memory_id for e in self.entries()):
            return None
        dates = [pub_dates[d] for d in source_doc_ids if pub_dates.get(d)]
        entry = {"memory_id": memory_id, "agent_id": self.owner, "key": key, "kind": kind, "value": value,
                 "source_case_id": source_case_id, "source_doc_ids": sorted(source_doc_ids),
                 "max_source_pub_date": max(dates) if dates else None, "written_as_of": written_as_of,
                 "version": 1, "created_from_trace_id": trace_ref,
                 "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(_canonical(entry) + "\n")
        return entry
