"""Append-only JSONL trace (SYSTEM_ARCHITECTURE 12.8). Timestamps are the only volatile field."""
import json
from datetime import datetime, timezone


class TraceLog:
    # Thor's and Loki's own traces are merged into the case's trace only when a phase ends (so the order never depends on who
    # ran first). To let a person watch a slow model work, they stream each event as it happens through this hook, which the
    # orchestrator sets for the duration of a run; the merge later does not repeat what was already streamed.
    default_on_emit = None

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

    def for_side(self):
        """A side's own trace: streams live, is merged later."""
        self.on_emit = TraceLog.default_on_emit
        return self

    def of_type(self, event_type):
        return [e for e in self.events if e["event_type"] == event_type]

    def write_jsonl(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for e in self.events:
                f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
