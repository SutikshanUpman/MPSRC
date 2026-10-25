"""Case File JSON schema (SYSTEM_ARCHITECTURE 3, plus the Heimdall outputs of 5.1, 15, 17, 21).

The spec's Case File fields keep their names: case_id, event_id, event_name,
as_of_date, target_countries, target_sectors, exposure_cells, canonical_metric,
secondary_metrics, event_scope, scope_assumptions, claim_ledger,
cross_examination, ruling_ledger, evidence_gaps, run_status. The other keys hold
Heimdall's outputs. Every item that came from a document is a CITED object: it
must carry `doc_id` and a `[DOC_ID, P#, timestamp]` citation.
"""

CITATION_PATTERN = r"^\[[A-Z][A-Z0-9]*-\d+, P\d+, \d{4}-\d{2}-\d{2}( \d{2}:\d{2})?\]$"
VOLATILE_FIELDS = ("case_id", "created_at")

STR = {"type": "string"}
OPT_STR = {"type": ["string", "null"]}
INT = {"type": "integer"}
NUM = {"type": "number"}
BOOL = {"type": "boolean"}
OPT_NUM = {"type": ["number", "null"]}
STR_LIST = {"type": "array", "items": STR}


def cited(extra_required=(), **props):
    return {"type": "object", "required": ["doc_id", "citation", *extra_required],
            "properties": {"doc_id": STR, "citation": {"type": "string", "pattern": CITATION_PATTERN}, **props}}


CITED_LIST = {"type": "array", "items": cited()}
CELL = {"type": "object", "required": ["country", "sector"], "properties": {"country": STR, "sector": STR}}

NUMBER_REF = {"type": "object", "required": ["value"],
              "properties": {"value": STR, "calc_id": STR, "field": STR,
                             "citation": {"type": "string", "pattern": CITATION_PATTERN}}}
VALUE_REF = {"type": "object", "required": ["calc_id", "field"], "properties": {"calc_id": STR, "field": STR}}

# Secondary metrics on a CELL_ESTIMATE (md 2091-2103): value and volume change and the implied unit price,
# each equal to the calc record's passes.<pass>.direct.<field>. The headline range stays net_value_shortfall_pct.
SECONDARY_NUMBERS = ["value_change", "value_change_pct", "volume_change", "volume_change_pct", "unit_price_before",
                     "unit_price_after"]
SECONDARY_REQUIRED = ["calc_id", "pass", "currency", "volume_unit"] + SECONDARY_NUMBERS

# Claim (spec 12.5, md 985-1017; Stage 2). claim_kind uses SOURCED_FACT / INFERENCE.
CLAIM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["claim_id", "agent", "run", "round", "claim_type", "claim_kind", "country", "sector", "metric",
                 "estimate_status", "estimate", "claim_text", "number_refs", "calc_ids", "citations", "mechanism",
                 "assumptions", "confidence", "status"],
    "properties": {
        "claim_id": {"type": "string", "pattern": r"^claim-(thor|loki)-\d{3}$"},
        "agent": {"type": "string", "enum": ["thor", "loki"]}, "run": INT, "round": INT,
        "claim_type": {"type": "string", "enum": ["CELL_ESTIMATE", "SUPPORTING"]},
        "claim_kind": {"type": "string", "enum": ["SOURCED_FACT", "INFERENCE"]},
        "country": STR, "sector": STR, "metric": OPT_STR,
        "estimate_status": {"type": ["string", "null"], "enum": ["ESTIMATED", "NO_DOCUMENTED_FLOW", "NO_BASELINE", "MIXED_UNITS", None]},
        "estimate": {"type": ["object", "null"], "required": ["low", "high", "unit", "low_ref", "high_ref"],
                     "properties": {"low": NUM, "high": NUM, "unit": {"type": "string", "enum": ["percent"]},
                                    "low_ref": VALUE_REF, "high_ref": VALUE_REF}},
        "claim_text": STR,
        "number_refs": {"type": "array", "items": NUMBER_REF},
        "calc_ids": STR_LIST,
        "citations": {"type": "array", "items": {"type": "string", "pattern": CITATION_PATTERN}},
        "mechanism": OPT_STR,
        "assumptions": STR_LIST,
        "confidence": NUM,
        "status": {"type": "string", "enum": ["submitted"]},
        "secondary_metrics": {"type": ["object", "null"], "required": SECONDARY_REQUIRED,
                              "properties": {"calc_id": STR, "pass": STR, "currency": OPT_STR, "volume_unit": OPT_STR,
                                             **{f: OPT_NUM for f in SECONDARY_NUMBERS}}},
        "supersedes": OPT_STR,
    },
}
CLAIM_SCHEMA["required"] += ["secondary_metrics", "supersedes"]

# The ledger copy of a claim: the runtime adds superseded_by and moves status on after round 2.
LEDGER_CLAIM_SCHEMA = {**CLAIM_SCHEMA, "required": CLAIM_SCHEMA["required"] + ["superseded_by"],
                       "properties": {**CLAIM_SCHEMA["properties"], "superseded_by": OPT_STR,
                                      "status": {"type": "string", "enum": ["submitted", "superseded", "withdrawn"]}}}

CITATIONS = {"type": "array", "items": {"type": "string", "pattern": CITATION_PATTERN}}
CHALLENGE_KINDS = ["SOURCE_TIER", "INTERESTED_PARTY", "POST_AS_OF", "BACKGROUND_ONLY", "REPEATED_ROWS", "BASELINE_CHOICE",
                   "INFERENCE_AS_FACT", "EVIDENCE_MISREAD", "ASSUMPTION_ATTACK", "SINGLE_SOURCE"]
RESPONSE_TYPES = ["DEFEND", "QUALIFY", "CONCEDE"]

# Round 2 (spec 12.6 md 1019-1036, section 18 md 1850-1897; review F27 for the response shape).
CHALLENGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["challenge_id", "challenger", "target_agent", "target_claim_id", "challenge_kind", "challenge_text",
                 "citations", "number_refs", "run", "round", "required_response"],
    "properties": {"challenge_id": {"type": "string", "pattern": r"^challenge-(thor|loki)-\d{3}$"},
                   "challenger": {"type": "string", "enum": ["thor", "loki"]},
                   "target_agent": {"type": "string", "enum": ["thor", "loki"]},
                   "target_claim_id": {"type": "string", "pattern": r"^claim-(thor|loki)-\d{3}$"},
                   "challenge_kind": {"type": "string", "enum": CHALLENGE_KINDS}, "challenge_text": STR,
                   "citations": CITATIONS, "number_refs": {"type": "array", "items": NUMBER_REF}, "run": INT, "round": INT,
                   "required_response": {"type": "string", "enum": ["DEFEND_QUALIFY_OR_CONCEDE"]}},
}
RESPONSE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["response_id", "responder", "challenge_id", "target_claim_id", "response_type", "response_text",
                 "citations", "new_evidence", "number_refs", "revised_claim_id", "reason"],
    "properties": {"response_id": {"type": "string", "pattern": r"^response-(thor|loki)-\d{3}$"},
                   "responder": {"type": "string", "enum": ["thor", "loki"]},
                   "challenge_id": {"type": "string", "pattern": r"^challenge-(thor|loki)-\d{3}$"},
                   "target_claim_id": {"type": "string", "pattern": r"^claim-(thor|loki)-\d{3}$"},
                   "response_type": {"type": "string", "enum": RESPONSE_TYPES}, "response_text": STR,
                   "citations": CITATIONS, "new_evidence": CITATIONS, "number_refs": {"type": "array", "items": NUMBER_REF},
                   "revised_claim_id": OPT_STR, "reason": OPT_STR},
}
# Case File cross_examination entry: the challenge with its response attached by the runtime.
CROSS_EXAMINATION_SCHEMA = {**CHALLENGE_SCHEMA, "required": CHALLENGE_SCHEMA["required"] + ["response"],
                            "properties": {**CHALLENGE_SCHEMA["properties"],
                                           "response": {"type": ["object", "null"], **{k: v for k, v in RESPONSE_SCHEMA.items()
                                                                                         if k != "type"}}}}

ROW_INPUT = {"type": "object", "required": ["row_key", "doc_id", "paragraph", "table_id", "native_row_number", "citation"],
             "properties": {"row_key": STR, "doc_id": STR, "paragraph": {"type": "string", "pattern": r"^P\d+$"},
                            "table_id": OPT_STR, "native_row_number": {"type": ["integer", "null"]},
                            "citation": {"type": "string", "pattern": CITATION_PATTERN}}}

XC_REF = {"type": "object", "required": ["doc_id", "paragraph", "citation", "tier", "pub_date", "month", "kind", "level"],
          "properties": {"doc_id": STR, "paragraph": {"type": "string", "pattern": r"^P\d+$"},
                         "citation": {"type": "string", "pattern": CITATION_PATTERN}, "month": STR,
                         "kind": {"type": "string", "enum": ["pct_of_normal", "index"]}, "level": NUM}}

# Calc record (spec 21, md 2052-2070 baseline, md 2227-2242 repeated rows; Stage 2 backend/agents/calc.py).
CALC_RECORD_SCHEMA = {
    "type": "object",
    "required": ["calc_id", "agent", "country", "sector", "metric", "unit", "status", "baseline_basis", "crosscheck",
                 "crosscheck_refs", "crosscheck_others", "crosscheck_implied_gross_shortfall_pct", "baseline_flags",
                 "event_month", "as_of_date", "credits", "direct_inputs", "substitute_inputs", "passes", "envelope",
                 "envelope_value", "envelope_volume",
                 "sensitivity_rows", "widened", "baseline_conflict", "repeat_sensitivity_pct",
                 "repeat_sensitivity_pct_by_scenario", "repeated_row_dependent"],
    "properties": {"calc_id": {"type": "string", "pattern": r"^calc-r\d+-(thor|loki)-\d{2}$"},
                   "status": {"type": "string", "enum": ["OK", "NO_DOCUMENTED_FLOW", "NO_BASELINE", "MIXED_UNITS"]},
                   "baseline_basis": {"type": "string", "enum": ["PRIMARY_YOY", "CROSS_CHECK_ONLY", "NONE"]},
                   "crosscheck": {"type": "string", "enum": ["NONE", "AGREE", "CONFLICT", "CROSS_CHECK_ONLY"]},
                   "crosscheck_refs": {"type": "array", "items": XC_REF},
                   "crosscheck_others": {"type": "array", "items": XC_REF},
                   "crosscheck_implied_gross_shortfall_pct": {"type": ["number", "null"]},
                   "baseline_flags": {"type": "array", "items": {"type": "string",
                                                                 "enum": ["BASELINE_CONFLICT", "BASELINE_PROXY"]}},
                   "direct_inputs": {"type": "array", "items": ROW_INPUT},
                   "substitute_inputs": {"type": "array", "items": ROW_INPUT},
                   "widened": BOOL, "baseline_conflict": BOOL, "repeated_row_dependent": BOOL,
                   "repeat_sensitivity_pct": {"type": ["number", "null"]}},
}

CHECK = {"type": "object", "required": ["passed", "evidence"],
         "properties": {"passed": BOOL, "evidence": {"type": "array", "items": cited(kind=STR)}}}

CASE_FILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "case_id", "created_at", "question", "pack_paths", "status", "rejection",
        "as_of_date", "as_of_source", "event_id", "event_name", "event_mapping", "question_entities",
        "target_countries", "target_sectors", "exposure_cells", "canonical_metric", "secondary_metrics",
        "event_scope", "scope_assumptions", "manifest_scope", "event_verification", "premise_check",
        "correction_map", "coverage", "cell_plan", "budget_projection", "evidence_packet",
        "calc_ledger", "claim_ledger", "cross_examination", "ruling_ledger", "evidence_gaps", "run_status",
    ],
    "properties": {
        "schema_version": STR,
        "case_id": STR,
        "created_at": STR,
        "question": STR,
        "pack_paths": {"type": "array", "items": STR, "minItems": 1},
        "status": {"type": "string", "enum": ["OPEN", "EVENT_REJECTED"]},
        "rejection": {"type": ["object", "null"], "required": ["reason", "detail"],
                      "properties": {"reason": STR, "detail": STR}},
        "as_of_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "as_of_source": {"type": "string", "enum": ["question", "manifest"]},
        "event_id": OPT_STR,
        "event_name": OPT_STR,
        "event_mapping": {
            "type": "object", "required": ["decision", "candidates", "min_score", "min_ratio"],
            "properties": {
                "decision": {"type": "string", "enum": ["ACCEPTED", "REJECTED_NO_MATCH", "REJECTED_AMBIGUOUS_EVENT"]},
                "candidates": {"type": "array", "items": {
                    "type": "object", "required": ["event_id", "score", "name_terms", "title_terms"],
                    "properties": {"event_id": STR, "name": OPT_STR, "score": INT, "name_terms": STR_LIST,
                                   "title_terms": STR_LIST}}},
                "min_score": NUM, "min_ratio": NUM},
        },
        "question_entities": {"type": "object", "required": ["countries", "sectors", "excluded_as_event_origin"],
                              "properties": {"countries": STR_LIST, "sectors": STR_LIST,
                                             "excluded_as_event_origin": STR_LIST}},
        "target_countries": STR_LIST,
        "target_sectors": STR_LIST,
        "exposure_cells": {"type": "array", "items": CELL},
        "canonical_metric": STR,
        "secondary_metrics": STR_LIST,
        "event_scope": STR_LIST,
        "scope_assumptions": {"type": "array", "items": {
            "type": "object", "required": ["dimension", "source", "values", "reason"],
            "properties": {"dimension": {"type": "string", "enum": ["countries", "sectors"]},
                           "source": {"type": "string", "enum": ["manifest_scope", "manifest_headers"]},
                           "values": STR_LIST, "reason": STR}}},
        "manifest_scope": {"type": ["object", "null"], "required": ["source", "scope_countries", "scope_sectors",
                                                                     "route_countries", "event_origins"],
                           "properties": {"source": STR, "scope_countries": STR_LIST, "scope_sectors": STR_LIST,
                                          "route_countries": STR_LIST, "event_origins": STR_LIST,
                                          "scope_doc_ids": STR_LIST, "scope_row_count": INT}},
        "event_verification": {"type": ["object", "null"], "required": ["verdict", "reason", "citations"],
                               "properties": {"verdict": {"type": "string", "enum": ["VERIFIED", "EVENT_REJECTED"]},
                                              "reason": STR, "subject_terms": STR_LIST,
                                              "citations": {"type": "array", "items": cited(("tier", "stance"), tier=INT, stance=STR)}}},
        "premise_check": {"type": ["object", "null"], "required": ["status", "premise_words", "findings", "citations"],
                          "properties": {"status": {"type": "string", "enum": ["NO_PREMISE_WORDS", "VERIFIED", "REJECTED_PREMISE"]},
                                         "premise_words": STR_LIST,
                                         "findings": {"type": "array", "items": {"type": "object", "required": ["premise", "supported", "citations"],
                                                                                 "properties": {"premise": STR, "supported": BOOL, "citations": CITED_LIST}}},
                                         "citations": CITED_LIST}},
        "correction_map": {"type": ["object", "null"], "required": ["documents", "relations"],
                           "properties": {"documents": {"type": "array", "items": cited(("tier", "stance", "status"), tier=INT, stance=STR, status=STR)},
                                          "relations": {"type": "array", "items": {
                                              "type": "object", "required": ["type", "from", "to"],
                                              "properties": {"type": {"type": "string", "enum": ["CORRECTS", "SUPERSEDED_BY"]},
                                                             "from": cited(), "to": cited()}}}}},
        "coverage": {"type": "array", "items": {
            "type": "object", "required": ["country", "sector", "status", "checks"],
            "properties": {"country": STR, "sector": STR,
                           "status": {"type": "string", "enum": ["COVERED", "PARTIAL", "NO_DIRECT_FLOW"]},
                           "checks": {"type": "object", "required": ["direct_flow", "substitute_flow", "contract_delay"],
                                      "properties": {"direct_flow": CHECK, "substitute_flow": CHECK, "contract_delay": CHECK}}}}},
        "cell_plan": {"type": "array", "items": {
            "type": "object", "required": ["country", "sector", "rank", "rank_inputs", "batch", "cell_status"],
            "properties": {"country": STR, "sector": STR, "rank": INT, "batch": {"type": ["integer", "null"]},
                           "cell_status": {"type": "string", "enum": ["PENDING", "ASSESSED", "INCOMPLETE_BUDGET_LIMIT"]}}}},
        "budget_projection": {"type": ["object", "null"]},
        "evidence_packet": {"type": ["object", "null"], "required": ["top_k_per_cell", "why_narrow", "cells", "families_seen"],
                            "properties": {"top_k_per_cell": INT, "why_narrow": STR, "families_seen": STR_LIST,
                                           "cells": {"type": "array", "items": {
                                               "type": "object", "required": ["country", "sector", "query", "hits"],
                                               "properties": {"query": STR, "hits": {"type": "array", "items": cited(("paragraph", "text"))}}}}}},
        "calc_ledger": {"type": "array", "items": CALC_RECORD_SCHEMA},
        "claim_ledger": {"type": "array", "items": LEDGER_CLAIM_SCHEMA},
        "cross_examination": {"type": "array", "items": CROSS_EXAMINATION_SCHEMA},
        "ruling_ledger": {"type": "array"},
        "evidence_gaps": {"type": "array", "items": {
            "type": "object", "required": ["country", "sector", "missing", "queries"],
            "properties": {"missing": {"type": "string", "enum": ["direct_flow", "substitute_flow", "contract_delay"]},
                           "queries": {"type": "array", "items": STR, "minItems": 2}}}},
        "run_status": {"type": "array", "items": {
            "type": "object", "required": ["run_number", "state", "stop_reason", "integrity_warnings",
                                           "quarantined_documents", "llm_calls"],
            "properties": {"run_number": INT, "state": STR, "stop_reason": OPT_STR,
                           "integrity_warnings": {"type": "array"},
                           "quarantined_documents": {"type": "array", "items": {
                               "type": "object", "required": ["doc_id", "pack_path", "reason"],
                               "properties": {"doc_id": STR, "pack_path": STR, "reason": STR}}},
                           "llm_calls": INT}}},
    },
}
