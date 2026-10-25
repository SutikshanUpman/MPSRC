"""Append-only JSONL trace (SYSTEM_ARCHITECTURE 12.8). Timestamps are the only volatile field."""
import json
from datetime import datetime, timezone


class TraceLog:
    def __init__(self, case_id=None, run_id="run-001"):
        self.case_id = case_id
        self.run_id = run_id
        self.events = []
        self.on_emit = None            # live feed: called with every event as it is emitted

    def emit(self, actor, event_type, payload=None, level="INFO"):
        event = {"sequence": len(self.events) + 1,
                 "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "case_id": self.case_id, "run_id": self.run_id, "actor": actor, "level": level,
                 "event_type": event_type, "payload": payload or {}}
        self.events.append(event)
        if self.on_emit:
            self.on_emit(event)
        return event

    def of_type(self, event_type):
        return [e for e in self.events if e["event_type"] == event_type]

    def write_jsonl(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for e in self.events:
                f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
