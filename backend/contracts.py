"""Machine-checked contracts for every structure that exists in code today (docs/CONTRACTS.md).

The Case File contract is CASE_FILE_SCHEMA itself (backend/casefile/schema.py);
the others are declared here from the code that builds them. tests/test_contracts.py
validates a mock run of the development pack against all of them, so a shape change breaks a test
before it breaks the dashboard. Structures not built yet (cross-examination,
rulings, briefing, source-span API) have no contract here; docs/CONTRACTS.md
lists them as PENDING.
"""
from .casefile.schema import (CALC_RECORD_SCHEMA, CASE_FILE_SCHEMA, CELL, CHALLENGE_SCHEMA, CITATION_PATTERN,  # noqa: F401
                              CLAIM_SCHEMA, CROSS_EXAMINATION_SCHEMA, LEDGER_CLAIM_SCHEMA, RESPONSE_SCHEMA)
from .llm.provider import validate_schema

STR, INT, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
OPT_STR, OPT_INT, OPT_NUM = {"type": ["string", "null"]}, {"type": ["integer", "null"]}, {"type": ["number", "null"]}
STR_LIST = {"type": "array", "items": STR}

# ---------- Case File parts (views of the one schema) ----------
EXPOSURE_CELL_SCHEMA = CELL
EVIDENCE_PACKET_SCHEMA = CASE_FILE_SCHEMA["properties"]["evidence_packet"]
RUN_RECORD_SCHEMA = CASE_FILE_SCHEMA["properties"]["run_status"]["items"]

# ---------- trade row (backend/ingestion/trade.py _new_row + finalise_rows) ----------
TRADE_ROW_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["row_key", "source_doc_id", "source_layout", "table_id", "native_row_number", "origin", "destination",
                 "sector", "month", "value_amount", "value_currency", "value_scale_raw", "volume_amount", "volume_unit",
                 "volume_unit_raw", "raw_text", "paragraph", "synthetic_paragraph", "parse_status", "flags", "reasons",
                 "usable_for_arithmetic", "sensitivity_row", "repeat_cases", "repeat_months", "cross_doc_matches",
                 "citation"],
    "properties": {
        "row_key": STR, "source_doc_id": STR, "source_layout": {"type": "string", "enum": ["prose_note", "fixed_table"]},
        "table_id": OPT_STR, "native_row_number": OPT_INT, "origin": OPT_STR, "destination": OPT_STR, "sector": OPT_STR,
        "month": OPT_STR, "value_amount": OPT_NUM, "value_currency": OPT_STR, "value_scale_raw": OPT_STR,
        "volume_amount": OPT_NUM, "volume_unit": OPT_STR, "volume_unit_raw": OPT_STR, "raw_text": STR,
        "paragraph": {"type": "string", "pattern": r"^P\d+$"}, "synthetic_paragraph": BOOL,
        "parse_status": {"type": "string", "enum": ["valid", "flagged", "invalid"]},
        "flags": STR_LIST, "reasons": {"type": "array"}, "usable_for_arithmetic": BOOL, "sensitivity_row": BOOL,
        "repeat_cases": STR_LIST, "repeat_months": {"type": "array"}, "cross_doc_matches": {"type": "array"},
        "citation": {"type": "object", "required": ["doc_id", "paragraph", "published_at", "text"],
                     "properties": {"text": {"type": "string", "pattern": CITATION_PATTERN}}},
    },
}

# ---------- OD-1 row_ref (spec md 2023-2030, paragraph contract md 2303, source span md 2382);
# carried today by Case File trade-row evidence (agents/heimdall.py _row_item) ----------
ROW_REF_SCHEMA = {
    "type": "object", "required": ["doc_id", "citation", "row_key", "paragraph", "source_layout", "table_id", "native_row_number"],
    "properties": {"doc_id": STR, "citation": {"type": "string", "pattern": CITATION_PATTERN}, "row_key": STR,
                   "paragraph": {"type": "string", "pattern": r"^P\d+$"},
                   "source_layout": {"type": "string", "enum": ["prose_note", "fixed_table"]},
                   "table_id": OPT_STR, "native_row_number": OPT_INT},
}

# ---------- provider call log (backend/llm/provider.py DeterministicMockProvider.complete) ----------
PROVIDER_CALL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["seq", "provider", "role", "model", "input_hash", "input_tokens_est", "output_tokens_est", "max_output_tokens"],
    "properties": {"seq": INT, "provider": STR, "role": {"type": "string", "enum": ["heimdall", "thor", "loki", "odin_ruling", "odin_briefing"]},
                   "model": STR, "input_hash": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
                   "input_tokens_est": INT, "output_tokens_est": INT, "max_output_tokens": INT},
}

# ---------- budget guard entry (backend/runtime/budget.py BudgetGuard.record) ----------
BUDGET_CALL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["role", "model", "provider", "input_tokens", "output_tokens", "cost_usd", "shadow_cost_usd"],
    "properties": {"role": STR, "model": STR, "provider": STR, "input_tokens": INT, "output_tokens": INT,
                   "cost_usd": {"type": "number"}, "shadow_cost_usd": {"type": "number"},
                   "observed_chars_per_token": {"type": "number"}},
}

# ---------- JSONL trace (backend/runtime/trace.py TraceLog.emit; emitters in agents/heimdall.py, ingestion/packs.py) ----------
EVENT_PAYLOAD_REQUIRED = {
    "CASE_CREATED": ["question", "pack_paths"],
    "PACK_DOC_ID_DUPLICATE": ["doc_id", "kept", "earlier", "later", "differing_manifest_fields"],
    "INTEGRITY_WARNING": ["doc_id", "kept", "quarantined", "earlier", "later"],
    "DOCUMENT_QUARANTINED": ["doc_id", "reason"],
    "AS_OF_DATE_RESOLVED": ["as_of_date", "source"],
    "EVENT_MAPPING": ["decision", "candidates", "min_score", "min_ratio"],
    "EVENT_REJECTED": ["reason", "detail"],
    "SCOPE_DEFAULTED": ["dimension", "source", "values", "reason"],
    "EVENT_VERIFICATION": ["verdict", "reason", "citations"],
    "PREMISE_CHECKED": ["status", "premise_words"],
    "COVERAGE_TESTED": ["cells"],
    "CELL_BUDGET_PROJECTED": ["case_spent_usd", "next_cell_batch_worst_case_usd", "case_limit_usd",
                              "odin_briefing_reserve_usd", "first_batch_affordable", "rule"],
    "SEARCH_COMPLETED": ["query", "filters", "result_doc_ids"],
    "CASE_FILE_BUILT": ["status", "cells"],
    # Stage 2: Heimdall fallback, cross-pack families, Round 1 (agents/counsel.py, agents/tools.py)
    "STANCE_FALLBACK": ["classified"],
    "CROSS_PACK_DUPLICATE_BODY": ["doc_ids", "pack_paths", "evidence_family_id", "family_members", "normalized_body_sha256"],
    "ROUND_1_STARTED": ["sides", "cells"],
    "ROUND_1_COMPLETED": ["claims", "calcs", "failures"],
    "AGENT_STEP_STARTED": ["cells"],
    "AGENT_STEP_COMPLETED": ["turns", "retries"],
    "BATCH_RESIZED": ["max_cells_per_agent_step", "input_cap", "target_share", "fixed_tokens", "batches"],
    "MEMORY_SKIP_OVERRIDDEN": ["agent", "memory_id", "cell", "query", "turn", "reason"],
    "INPUT_REBUILT": ["input_tokens_before", "input_tokens_after", "cap", "dropped_tool_results"],
    "MEMORY_READ": ["memory_ids", "hidden_ids"],
    "MEMORY_HIDDEN": ["memory_id", "max_source_pub_date", "case_as_of"],
    "MEMORY_WRITTEN": ["memory_id", "key", "source_doc_ids", "max_source_pub_date", "written_as_of"],
    "DECISION_CHANGED": ["memory_id", "kind", "before", "after", "turn", "verified"],
    "DECISION_UNVERIFIED": ["memory_id", "kind", "before", "after", "turn", "verified"],
    "SEARCH_EXECUTED": ["agent", "query", "filters", "cache_hit", "result_doc_ids", "spans"],
    "SEARCH_CACHE_HIT": ["agent", "query", "filters", "cache_hit", "result_doc_ids", "spans"],
    "SEARCH_LIMIT_REACHED": ["query", "searches"],
    "TOOL_LIMIT_REACHED": ["tool", "step_calls"],
    "TOOL_CALLED": ["tool", "cells", "row_count"],
    "DOCUMENT_RETRIEVED": ["doc_id", "spans"],
    "CALC_COMPUTED": ["calc_id", "country", "sector", "status", "widened", "crosscheck", "baseline_flags"],
    "CLAIMS_SUBMITTED": ["claim_ids", "turn"],
    "CLAIM_VALIDATION_FAILED": ["attempt", "problems"],
    "AGENT_FAILED": ["agent", "state", "reason", "problems", "step", "run", "round", "attempts", "last_error",
                     "input_tokens", "output_tokens", "cost_usd", "shadow_cost_usd"],
    "BUDGET_CAP_REACHED": ["agent", "detail"],
    # Stage 3: round 2 (agents/cross_exam.py)
    "ROUND_2_STARTED": ["sides"],
    "SEARCH_SHARED_QUERY": ["query", "filters", "agents"],
    "CHALLENGES_SUBMITTED": ["challenge_ids", "targets", "kinds"],
    "RESPONSES_SUBMITTED": ["response_ids", "types", "revised_claim_ids"],
    "REVISION_SET_ASIDE": ["claim_ids", "reason"],
    "CLAIM_SUPERSEDED": ["claim_id", "superseded_by", "challenge_id"],
    "CLAIM_CONCEDED": ["claim_id", "challenge_id", "reason"],
    "ROUND_2_COMPLETED": ["challenges", "responses", "revised_claims", "failures"],
    # Final build: Odin, Run 2, briefing, fallbacks (agents/odin.py, runtime/run2.py, runtime/orchestrator.py)
    "ODIN_RULED": ["run", "rulings", "mode", "decisions", "classes"],
    "ODIN_SENT_BACK": ["gaps"],
    "RUN_2_STARTED": ["cells"],
    "RUN_2_NEW_EVIDENCE": ["families", "citations"],
    "RUN_2_COMPLETED": ["new_evidence_families", "failures", "updated"],
    "CELL_INSUFFICIENT_EVIDENCE": ["country", "sector", "reason", "after_run"],
    "BRIEFING_BUILT": ["completion", "removed", "hash"],
    "FALLBACK_ODIN_RULES": ["reason"],
    "FALLBACK_BRIEFING_TEMPLATE": ["reason"],
    "FALLBACK_BUDGET_STOP": ["detail"],
    "FALLBACK_EVENT_UNVERIFIED": ["detail"],
    "FALLBACK_TRADE_TABLE_UNPARSED": ["doc_id", "handling"],
    "FALLBACK_PACK_LAYOUT": ["detail"],
    "FALLBACK_LLM_RETRY": ["attempt", "error"],
    "FALLBACK_JSON_REPAIR": ["role"],
}
EVENT_TYPES = sorted(EVENT_PAYLOAD_REQUIRED)

TRACE_EVENT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["sequence", "timestamp", "case_id", "run_id", "actor", "level", "event_type", "payload"],
    "properties": {"sequence": INT, "timestamp": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"},
                   "case_id": STR, "run_id": STR, "actor": {"type": "string", "enum": ["heimdall", "thor", "loki", "odin", "runtime"]},
                   "level": {"type": "string", "enum": ["INFO", "WARNING"]},
                   "event_type": {"type": "string", "enum": EVENT_TYPES}, "payload": {"type": "object"}},
}

# Heimdall's packet searches: the SEARCH_COMPLETED payload.
SEARCH_LOG_ENTRY_SCHEMA = {
    "type": "object", "required": ["query", "filters", "result_doc_ids"],
    "properties": {"query": STR, "result_doc_ids": STR_LIST,
                   "filters": {"type": "object", "required": ["event_scope", "published_before_or_on", "countries"],
                               "properties": {"event_scope": STR_LIST, "countries": STR_LIST}}},
}


# Thor/Loki search log (agents/tools.py AgentTools.search): data/runs/<case_id>/search_log.jsonl and the
# SEARCH_EXECUTED / SEARCH_CACHE_HIT payloads.
AGENT_SEARCH_LOG_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["agent", "query", "filters", "cache_hit", "result_doc_ids", "spans"],
    "properties": {"agent": {"type": "string", "enum": ["thor", "loki"]}, "query": STR, "cache_hit": BOOL,
                   "result_doc_ids": STR_LIST,
                   "spans": {"type": "array", "items": {"type": "string", "pattern": CITATION_PATTERN}},
                   "filters": {"type": "object", "additionalProperties": False,
                               "required": ["event_scope", "published_before_or_on", "countries", "sector_boost"],
                               "properties": {"event_scope": {"type": "array", "items": STR, "minItems": 2},
                                              "published_before_or_on": STR, "countries": STR_LIST,
                                              "sector_boost": STR_LIST}}},
}

# Private memory entry (memory/store.py MemoryStore.write): data/memory/<agent>/memory.jsonl.
MEMORY_ENTRY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["memory_id", "agent_id", "key", "kind", "value", "source_case_id", "source_doc_ids",
                 "max_source_pub_date", "written_as_of", "version", "created_from_trace_id", "created_at"],
    "properties": {"memory_id": {"type": "string", "pattern": r"^mem-(heimdall|thor|loki|odin)-[0-9a-f]{10}$"},
                   "agent_id": {"type": "string", "enum": ["heimdall", "thor", "loki", "odin"]}, "key": STR,
                   "kind": {"type": "string", "enum": ["lesson", "case_note"]}, "value": {"type": "object"},
                   "source_case_id": STR, "source_doc_ids": STR_LIST,
                   "max_source_pub_date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                   "written_as_of": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                   "version": INT, "created_from_trace_id": OPT_STR, "created_at": STR},
}


def trace_event_problems(event):
    problems = validate_schema(event, TRACE_EVENT_SCHEMA)
    if not problems:
        for key in EVENT_PAYLOAD_REQUIRED[event["event_type"]]:
            if key not in event["payload"]:
                problems.append(f"{event['event_type']}: payload missing {key!r}")
        if event["event_type"] == "SEARCH_COMPLETED":
            problems += validate_schema(event["payload"], SEARCH_LOG_ENTRY_SCHEMA, "$.payload")
        if event["event_type"] in ("SEARCH_EXECUTED", "SEARCH_CACHE_HIT"):
            problems += validate_schema(event["payload"], AGENT_SEARCH_LOG_SCHEMA, "$.payload")
    return problems


# ---------- final build: rulings, briefing, run_record.json, trap report ----------
from .agents.odin import RULING_SCHEMA  # noqa: E402,F401

PARAGRAPH_SCHEMA = {
    "type": "object",
    "required": ["paragraph_id", "text", "finding_classification", "claim_refs", "citation_refs", "row_refs", "calc_refs",
                 "number_refs", "confidence"],
    "properties": {"paragraph_id": STR, "text": STR, "finding_classification": STR, "claim_refs": STR_LIST,
                   "citation_refs": {"type": "array", "items": {"type": "string", "pattern": CITATION_PATTERN}},
                   "row_refs": {"type": "array", "items": {"type": "object", "required": ["doc_id", "table_id", "native_row_number"],
                                                           "properties": {"doc_id": STR, "table_id": OPT_STR,
                                                                          "native_row_number": OPT_INT}}},
                   "calc_refs": STR_LIST, "number_refs": {"type": "array"}, "confidence": {"type": "number"}},
}
BRIEFING_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "header", "executive_summary", "event_verification", "established", "contested", "conceded",
                 "rejected", "exposure_table", "outlook", "assumptions_limitations", "sources", "removed_by_validator"],
    "properties": {
        "header": {"type": "object", "required": ["case_id", "event", "as_of_date", "completion_status", "flagged_cells",
                                                  "cells_not_assessed", "removed_numbers", "run2_new_evidence_families"],
                   "properties": {"completion_status": {"type": "string", "enum": ["COMPLETE", "INCOMPLETE"]}}},
        "executive_summary": PARAGRAPH_SCHEMA,
        "event_verification": {"type": "array", "items": PARAGRAPH_SCHEMA},
        "established": {"type": "array", "items": PARAGRAPH_SCHEMA},
        "contested": {"type": "array", "items": PARAGRAPH_SCHEMA},
        "conceded": {"type": "array", "items": PARAGRAPH_SCHEMA},
        "rejected": {"type": "array", "items": PARAGRAPH_SCHEMA},
        "exposure_table": {"type": "array", "items": {
            "type": "object", "required": ["country", "sector", "status", "thor", "loki", "odin", "calibration", "calc_refs",
                                           "row_refs"],
            "properties": {"status": {"type": "string", "enum": ["ASSESSED", "INSUFFICIENT_EVIDENCE", "INCOMPLETE_BUDGET_LIMIT"]}}}},
        "outlook": {"type": "object", "required": ["drivers", "risks", "indicators", "assumptions"]},
    },
}
FINAL_RUN_RECORD_SCHEMA = {
    "type": "object",
    "required": ["case_id", "status", "question", "pack_paths", "provider", "input_hashes", "ruling_mode", "rulings", "ac", "runs",
                 "spend", "briefing_hash", "events", "outputs"],
    "properties": {"input_hashes": {"type": "object", "required": ["packs", "config", "prompts"]},
                   "spend": {"type": "object", "required": ["case_spent_usd", "shadow_spent_usd", "model_calls",
                                                            "project_spent_before_usd", "billable"]},
                   "ac": {"type": "object", "required": ["cross_examinations", "rejected_or_conceded", "sent_back",
                                                         "run2_new_evidence_families", "memory_decisions_changed"]}},
}
TRAP_REPORT_SCHEMA = {
    "type": "object", "required": ["case_id", "as_of_date", "summary", "traps"],
    "properties": {"traps": {"type": "array", "items": {"type": "object", "required": ["type", "description", "count", "items"]}}},
}
