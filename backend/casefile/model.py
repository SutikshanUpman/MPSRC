"""Case File object: build, validate on write, serialise to JSON.

`case_id` and `created_at` are the only volatile fields (VOLATILE_FIELDS); with
the mock provider everything else is a pure function of question + packs + config.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..llm.provider import validate_schema
from .schema import CASE_FILE_SCHEMA, VOLATILE_FIELDS

SCHEMA_VERSION = "stage1-1"
CANONICAL_METRIC = "net_value_shortfall_pct"
SECONDARY_METRICS = ["value_shortfall", "volume_shortfall"]


class CaseFileInvalid(ValueError):
    pass


def new_case_file(question, pack_paths, case_id=None, created_at=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id or f"case-{uuid.uuid4().hex[:12]}",
        "created_at": created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "question": question, "pack_paths": [str(p) for p in pack_paths],
        "status": "OPEN", "rejection": None, "as_of_date": None, "as_of_source": None,
        "event_id": None, "event_name": None, "event_mapping": None,
        "question_entities": {"countries": [], "sectors": [], "excluded_as_event_origin": []},
        "target_countries": [], "target_sectors": [], "exposure_cells": [],
        "canonical_metric": CANONICAL_METRIC, "secondary_metrics": list(SECONDARY_METRICS),
        "event_scope": [], "scope_assumptions": [], "manifest_scope": None,
        "event_verification": None, "premise_check": None, "correction_map": None,
        "coverage": [], "cell_plan": [], "budget_projection": None, "evidence_packet": None,
        "calc_ledger": [], "claim_ledger": [], "cross_examination": [], "ruling_ledger": [], "evidence_gaps": [],
        "run_status": [],
    }


def validate(cf):
    problems = validate_schema(cf, CASE_FILE_SCHEMA)
    if problems:
        raise CaseFileInvalid("; ".join(problems[:20]))
    return cf


def to_json(cf):
    return json.dumps(cf, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def stable_json(cf):
    """Serialisation with the volatile fields removed, for determinism checks."""
    return to_json({k: v for k, v in cf.items() if k not in VOLATILE_FIELDS})


def write(cf, path):
    validate(cf)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_json(cf))
    return path
