# Data contracts

These are the JSON shapes the backend produces today, for anyone building on them (dashboard, later stages). Each shape is defined by a validator in code, and `tests/test_contracts.py` checks a mock E5 run against every one. A change to a shape therefore breaks a test, not the dashboard.

- `md` = `docs/SYSTEM_ARCHITECTURE.md`.
- Contract code: `backend/casefile/schema.py` (Case File) and `backend/contracts.py` (everything else).
- Examples come from a mock E5 run (`scripts/run_case.py --pack dev_pack_E5 --question <sample question>`) and are shortened (`…`).

## Status overview

| Structure | Status | Contract (code) | Built by |
|---|---|---|---|
| Case File | BUILT | `backend/casefile/schema.py:152` `CASE_FILE_SCHEMA` | `backend/casefile/model.py:23`, `backend/agents/heimdall.py` `open_case`, `backend/agents/counsel.py:279` `run_round1`, `backend/agents/cross_exam.py:275` `run_round2` (each validates the Case File at the end) |
| exposure_cells | BUILT | `schema.py:29` `CELL`; `contracts.py:18` | `heimdall.py` `open_case` |
| Evidence packet | BUILT | `schema.py:232`; `contracts.py:19` | `heimdall.py:512` `evidence_packet` |
| Coverage, evidence gaps, cell plan | BUILT | `schema.py:221`, `schema.py:227`, `evidence_gaps` | `heimdall.py` `coverage_test`, `cell_plan`; `counsel.py` marks cells `ASSESSED` |
| Run record | BUILT | `schema.py:245` (`run_status` items); `contracts.py:20` | `heimdall.py:603`; `round_1` block from `counsel.py:335`, `round_2` from `cross_exam.py:275` |
| Trade row | BUILT | `contracts.py:24` `TRADE_ROW_SCHEMA` | `backend/ingestion/trade.py:163` `_new_row`, `:452` `finalise_rows` |
| Row ref (OD-1) on Case File trade-row evidence and calc inputs | BUILT | `contracts.py:47` `ROW_REF_SCHEMA` | `heimdall.py:423` `_row_item`; `backend/agents/calc.py` `row_ref` |
| Heimdall search (packet) | BUILT (as a trace payload) | `contracts.py:138` `SEARCH_LOG_ENTRY_SCHEMA` | `heimdall.py` `SEARCH_COMPLETED` |
| Thor/Loki search log | BUILT | `contracts.py:148` `AGENT_SEARCH_LOG_SCHEMA` | `backend/agents/tools.py:74` `search`; `search_log.jsonl` |
| Calc record (`calc_id`) | BUILT | `schema.py:126` `CALC_RECORD_SCHEMA` (cross-check refs `schema.py:120`) | `backend/agents/calc.py:235` `compute_cell` via `tools.py:157`; the agent gets `calc.py:329` `agent_view` |
| Claim / CELL_ESTIMATE | BUILT | `schema.py:43` `CLAIM_SCHEMA` (+ rules in `backend/agents/claims.py`) | Thor/Loki through `counsel.py:213` `run_step` |
| Memory entry | BUILT | `contracts.py:162` `MEMORY_ENTRY_SCHEMA` | `backend/memory/store.py:52` `write` |
| JSONL trace event | BUILT | `contracts.py:128` `TRACE_EVENT_SCHEMA`, `:74` payload keys | `backend/runtime/trace.py:12` `emit` |
| Provider call log | BUILT | `contracts.py:56` `PROVIDER_CALL_SCHEMA` | `backend/llm/provider.py:132`; `provider_calls.jsonl` |
| Budget guard entry | BUILT | `contracts.py:65` `BUDGET_CALL_SCHEMA` | `backend/runtime/budget.py:72` (live calls add `observed_chars_per_token`) |
| Cross-examination: challenge, response (DEFEND / QUALIFY / CONCEDE), entry | BUILT (Stage 3) | `schema.py:85` `CHALLENGE_SCHEMA`, `:97` `RESPONSE_SCHEMA`, `:110` `CROSS_EXAMINATION_SCHEMA` | `backend/agents/cross_exam.py:275` `run_round2` |
| Revised estimate (round 2, `supersedes` / `superseded_by`) | BUILT (Stage 3) | `schema.py:75` `LEDGER_CLAIM_SCHEMA` | `cross_exam.py:358` `_apply` |
| Odin rulings | BUILT (final build) | `backend/agents/odin.py` `RULING_SCHEMA` (also `contracts.RULING_SCHEMA`) | `odin.rule_claims` (rules), `odin.model_pass` (open claims only); `rulings.json`, Case File `ruling_ledger` |
| Briefing with `row_refs`, `calc_refs`, `number_refs` | BUILT (final build) | `contracts.BRIEFING_SCHEMA`, `PARAGRAPH_SCHEMA` | `backend/briefing/__init__.py` `build` + `gate`; `briefing.json`, `briefing.md` |
| Run record (`run_record.json`) | BUILT (final build) | `contracts.FINAL_RUN_RECORD_SCHEMA` | `backend/runtime/orchestrator.py` `run_full_case` |
| Trap report | BUILT (final build) | `contracts.TRAP_REPORT_SCHEMA` | `backend/briefing/trap_report.py`; `trap_report.json` |
| Run 2 record (`run_status[1]`) | BUILT (final build) | `schema.py` run_status item (extra keys allowed) | `backend/runtime/run2.py` |
| Source-span API (`table_id`, `row`) | PENDING (Stage 4) | none | spec md 2376-2382 |

## Case File

Contract: `CASE_FILE_SCHEMA` (`backend/casefile/schema.py:152`). Top level is `additionalProperties: false`, and it is validated on every write (`model.py:42`). Every item that came from a document must carry `doc_id` and a citation matching `[DOC_ID, P#, timestamp]` (`schema.py:11`). `case_id` and `created_at` are the only volatile fields.

Top-level fields, checked by the test against the schema's `required` list:

<!-- contract:case_file_fields -->
```text
schema_version
case_id
created_at
question
pack_paths
status
rejection
as_of_date
as_of_source
event_id
event_name
event_mapping
question_entities
target_countries
target_sectors
exposure_cells
canonical_metric
secondary_metrics
event_scope
scope_assumptions
manifest_scope
event_verification
premise_check
correction_map
coverage
cell_plan
budget_projection
evidence_packet
calc_ledger
claim_ledger
cross_examination
ruling_ledger
evidence_gaps
run_status
```
<!-- /contract:case_file_fields -->

Example (E5, shortened):

```json
{"schema_version": "stage1-1", "case_id": "case-dc3e8a122291", "created_at": "2026-10-25T12:10:15Z",
 "status": "OPEN", "rejection": null, "as_of_date": "2027-01-25", "as_of_source": "question",
 "event_id": "E5", "event_name": "Orvan grain corridor collapse",
 "event_mapping": {"decision": "ACCEPTED", "min_score": 3, "min_ratio": 2.0,
   "candidates": [{"event_id": "E5", "name": "Orvan grain corridor collapse", "score": 13,
                   "name_terms": ["corridor", "orvan"], "title_terms": ["agreement", "corridor", "…"]}]},
 "target_countries": ["Midgard", "Tolan"], "target_sectors": ["Wheat", "Maize"],
 "canonical_metric": "net_value_shortfall_pct", "event_scope": ["E5", "NONE"], "scope_assumptions": [],
 "event_verification": {"verdict": "VERIFIED", "reason": "current Tier 1-2 case-event document asserts the event",
   "citations": [{"doc_id": "ORV-0016", "citation": "[ORV-0016, P6, 2026-09-10 17:45]", "tier": 1, "stance": "ASSERTS", "paragraph": "P6"}, "…"]},
 "premise_check": {"status": "NO_PREMISE_WORDS", "premise_words": [], "findings": [], "citations": []},
 "correction_map": {"relations": [{"type": "CORRECTS",
     "from": {"doc_id": "ORV-0013", "citation": "[ORV-0013, P2, 2026-09-10 09:10]"},
     "to": {"doc_id": "ORV-0043", "citation": "[ORV-0043, P1, 2026-09-09 17:30]"}}, "…"],
   "documents": [{"doc_id": "ORV-0003", "citation": "[ORV-0003, P1, 2026-08-18 10:10]", "tier": 1, "stance": "DENIES",
                  "status": "SUPERSEDED", "superseded_by": "ORV-0013", "corrected_by": null, "…": "…"}]},
 "calc_ledger": ["… see Calc record"], "claim_ledger": ["… see Claim"], "cross_examination": [], "ruling_ledger": [], "…": "…"}
```

### exposure_cells

Contract: `CELL` (`schema.py:29`), `{country, sector}`, in question order (md 95).

```json
{"country": "Midgard", "sector": "Wheat"}
```

### Coverage (with OD-1 row refs), evidence gaps, cell plan

Contracts: `schema.py:221` (coverage), `ROW_REF_SCHEMA` (`contracts.py:47`) for each `kind: trade_row` evidence item, `schema.py:227` (cell plan), `evidence_gaps` in `schema.py`. For a fixed-layout table row, `table_id` and `native_row_number` are filled. For a prose-note row both are `null`, and `row_key` plus `paragraph` locate the row.

```json
{"country": "Midgard", "sector": "Wheat", "status": "COVERED",
 "checks": {"direct_flow": {"passed": true, "evidence": [
   {"doc_id": "ORV-0009", "citation": "[ORV-0009, P2, 2027-01-19 09:20]", "kind": "trade_row", "row_key": "ORV-0009|2026-07",
    "paragraph": "P2", "source_layout": "prose_note", "table_id": null, "native_row_number": null}, "…"]},
   "substitute_flow": {"…": "…"}, "contract_delay": {"…": "…"}}}
```

```json
{"country": "Midgard", "sector": "Maize", "missing": "substitute_flow",
 "queries": ["Midgard Maize alternative suppliers", "Midgard Maize rail road substitute imports"]}
```

```json
{"country": "Midgard", "sector": "Wheat", "rank": 1, "batch": 1, "cell_status": "PENDING",
 "rank_inputs": {"trade_rows": 22, "doc_mentions": 12, "question_order": 1}}
```

### Evidence packet

Contract: `schema.py:232`. Every hit carries `doc_id`, `paragraph`, a citation and masked `text`.

```json
{"top_k_per_cell": 3, "why_narrow": "Run 1 gets one generic query per cell …", "families_seen": ["FAM-11100ab92fd7", "…"],
 "cells": [{"country": "Midgard", "sector": "Wheat", "query": "Orvan Midgard Wheat imports",
   "hits": [{"doc_id": "ORV-0009", "paragraph": "P1", "citation": "[ORV-0009, P1, 2027-01-19 09:20]",
             "title": "Trade note: Orvan to Midgard, wheat, July to December 2026", "text": "Route: Orvan to Midgard, wheat. …",
             "tier": 1, "event_id": "E5", "context_only": false, "evidence_family_id": "FAM-926cca6351ed", "score": 7.491516}, "…"]}, "…"]}
```

### Run record (`run_status[0]`)

Contract: `schema.py:245`.

```json
{"run_number": 1, "state": "HEIMDALL_CASE_OPENED", "stop_reason": null, "integrity_warnings": [],
 "pack_merges": [], "quarantined_documents": [], "llm_calls": 0}
```

`integrity_warnings` items are `INTEGRITY_WARNING` payloads (doc ID, kept and quarantined pack, both raw and body hashes). `quarantined_documents` items are `{doc_id, pack_path, reason}`, with reason `HASH_MISMATCH` or `PACK_DOC_ID_COLLISION_EARLIER_COPY`.

## Trade row (ingestion)

Contract: `TRADE_ROW_SCHEMA` (`contracts.py:24`), with `additionalProperties: false`. The `citation` is always the paragraph bracket (OD-1).

```json
{"row_key": "ORV-0009|2026-07", "source_doc_id": "ORV-0009", "source_layout": "prose_note", "table_id": null,
 "native_row_number": null, "origin": "Orvan", "destination": "Midgard", "sector": "wheat", "month": "2026-07",
 "value_amount": 90000000.0, "value_currency": "USD", "value_scale_raw": "M", "volume_amount": 250000.0, "volume_unit": "tonnes",
 "raw_text": "In July 2026, the value was USD 90.0M and the volume was 250,000 tonnes.", "paragraph": "P2",
 "parse_status": "valid", "usable_for_arithmetic": true, "sensitivity_row": false, "…": "…",
 "citation": {"doc_id": "ORV-0009", "paragraph": "P2", "published_at": "2027-01-19 09:20", "text": "[ORV-0009, P2, 2027-01-19 09:20]"}}
```

## Heimdall search (evidence packet)

Heimdall's packet searches are recorded as the payload of a `SEARCH_COMPLETED` trace event. Thor's and Loki's searches have their own log (next section). Contract: `SEARCH_LOG_ENTRY_SCHEMA` (`contracts.py:123`).

```json
{"query": "Orvan Midgard Wheat imports",
 "filters": {"event_scope": ["E5", "NONE"], "published_before_or_on": "2027-01-25", "countries": ["Midgard"]},
 "result_doc_ids": ["ORV-0009", "ORV-0027", "ATL-0008"]}
```

## JSONL trace event

Contract: `TRACE_EVENT_SCHEMA` (`contracts.py:128`) plus the required payload keys per type (`contracts.py:74`). `actor` is `heimdall`, `thor`, `loki` or `runtime`. Written to `data/runs/<case_id>/events.jsonl`, one JSON object per line. `timestamp` is volatile.

Event types, checked by the test against `EVENT_TYPES`:

<!-- contract:event_types -->
```text
AGENT_FAILED
AGENT_STEP_COMPLETED
AGENT_STEP_STARTED
AS_OF_DATE_RESOLVED
BATCH_RESIZED
BRIEFING_BUILT
BUDGET_CAP_REACHED
CALC_COMPUTED
CASE_CREATED
CASE_FILE_BUILT
CELL_BUDGET_PROJECTED
CELL_INSUFFICIENT_EVIDENCE
CHALLENGES_SUBMITTED
CLAIMS_SUBMITTED
CLAIM_CONCEDED
CLAIM_SUPERSEDED
CLAIM_VALIDATION_FAILED
COVERAGE_TESTED
CROSS_PACK_DUPLICATE_BODY
DECISION_CHANGED
DECISION_UNVERIFIED
DOCUMENT_QUARANTINED
DOCUMENT_RETRIEVED
EVENT_MAPPING
EVENT_REJECTED
EVENT_VERIFICATION
FALLBACK_BRIEFING_TEMPLATE
FALLBACK_BUDGET_STOP
FALLBACK_EVENT_UNVERIFIED
FALLBACK_JSON_REPAIR
FALLBACK_LLM_RETRY
FALLBACK_ODIN_RULES
FALLBACK_PACK_LAYOUT
FALLBACK_TRADE_TABLE_UNPARSED
INPUT_REBUILT
INTEGRITY_WARNING
MEMORY_HIDDEN
MEMORY_READ
MEMORY_SKIP_OVERRIDDEN
MEMORY_WRITTEN
ODIN_RULED
ODIN_SENT_BACK
PACK_DOC_ID_DUPLICATE
PREMISE_CHECKED
RESPONSES_SUBMITTED
ROUND_1_COMPLETED
ROUND_1_STARTED
ROUND_2_COMPLETED
ROUND_2_STARTED
RUN_2_COMPLETED
RUN_2_NEW_EVIDENCE
RUN_2_STARTED
SCOPE_DEFAULTED
SEARCH_CACHE_HIT
SEARCH_COMPLETED
SEARCH_EXECUTED
SEARCH_LIMIT_REACHED
SEARCH_SHARED_QUERY
STANCE_FALLBACK
TOOL_CALLED
TOOL_LIMIT_REACHED
```
<!-- /contract:event_types -->

```json
{"sequence": 4, "timestamp": "2026-10-25T12:10:15Z", "case_id": "case-dc3e8a122291", "run_id": "run-001",
 "actor": "heimdall", "level": "INFO", "event_type": "EVENT_VERIFICATION",
 "payload": {"verdict": "VERIFIED", "reason": "current Tier 1-2 case-event document asserts the event",
             "citations": ["[ORV-0016, P6, 2026-09-10 17:45]", "[ORV-0013, P2, 2026-09-10 09:10]", "[ORV-0034, P1, 2026-09-11 06:20]"]}}
```

## Provider call log and budget guard entry

Contracts: `PROVIDER_CALL_SCHEMA` (`contracts.py:56`) and `BUDGET_CALL_SCHEMA` (`contracts.py:65`). The mock E5 run makes no model call, so the test produces these with one mock call through `BudgetGuard.call` (messages `[{"role": "user", "content": "contract check"}]`).

```json
{"seq": 1, "provider": "mock", "role": "heimdall", "model": "claude-haiku-5-5",
 "input_hash": "45074e019bbdb6d3d1c3b994407363deb921aa6c953c38700292b2cf75d3ef67",
 "input_tokens_est": 11, "output_tokens_est": 1, "max_output_tokens": 2000}
```

```json
{"role": "heimdall", "model": "claude-haiku-5-5", "provider": "mock", "input_tokens": 11, "output_tokens": 1,
 "cost_usd": 0.0, "shadow_cost_usd": 1.6e-06}
```

`shadow_cost_usd` uses the configured prices, which are UNVERIFIED. Mock calls are never billable.

## Thor/Loki search log

Contract: `AGENT_SEARCH_LOG_SCHEMA` (`contracts.py:148`). It is written to `data/runs/<case_id>/search_log.jsonl` and is also the payload of `SEARCH_EXECUTED` / `SEARCH_CACHE_HIT` events. `event_scope` and `published_before_or_on` are the two mandatory metadata filters and are always present. An exact repeat by the same agent is a `cache_hit: true` entry and runs no search.

```json
{"agent": "thor", "cache_hit": false, "query": "Orvan Midgard Wheat disruption delays shortfall",
 "filters": {"event_scope": ["E5", "NONE"], "published_before_or_on": "2027-01-25", "countries": ["Midgard"], "sector_boost": ["Wheat"]},
 "result_doc_ids": ["ORV-0009", "ORV-0027", "ORV-0006", "ORV-0030", "ORV-0022"],
 "spans": ["[ORV-0009, P1, 2027-01-19 09:20]", "[ORV-0027, P1, 2027-01-22 09:05]", "…"]}
```

## Calc record

Contract: `CALC_RECORD_SCHEMA` (`schema.py:126`). These are stored in the Case File `calc_ledger` and written to `calc_ledger.json`. The baseline is the F11 rule (md 2052-2070): primary = same months one year earlier; cross-check = a "% of normal" level or a base-100 index stated in a case-event paragraph that names the route (an event origin and the cell country) or the cell's country and sector. Each scenario credits a share of substitute growth (`credits`, config `calc_substitute_credit`, TUNABLE). The `envelope` is [min, max] over every OK pass: with and without repeated-value rows, plus `crosscheck_scaled` on a `BASELINE_CONFLICT`. Every input row is a row ref.

The calc tool returns a smaller **agent view** (`calc.py:329` `agent_view`) to Thor and Loki: the same dotted field paths for every number (so a `low_ref` / `number_ref` resolves against this record), one citation per input document, and the flagged rows. The full record is what the ledger and the dashboard get.

```json
{"calc_id": "calc-r1-thor-01", "agent": "thor", "country": "Midgard", "sector": "Wheat", "metric": "net_value_shortfall_pct",
 "unit": "percent", "status": "OK", "baseline_basis": "PRIMARY_YOY", "crosscheck": "NONE", "crosscheck_refs": [], "crosscheck_others": [],
 "crosscheck_implied_gross_shortfall_pct": null, "baseline_flags": [], "tolerance_pct_points": 5, "event_month": "2026-09",
 "as_of_date": "2027-01-25", "credits": {"no_credit": 0.0, "half_credit": 0.5, "full_credit": 1.0},
 "direct_inputs": [{"row_key": "ORV-0009|2025-07", "doc_id": "ORV-0009", "paragraph": "P8", "table_id": null,
                    "native_row_number": null, "citation": "[ORV-0009, P8, 2027-01-19 09:20]", "month": "2025-07",
                    "origin": "Orvan", "sensitivity_row": false}, "…"],
 "substitute_inputs": [{"row_key": "ORV-0027|2025-07", "origin": "Vanir", "sensitivity_row": true, "repeat_cases": ["b"],
                        "flags": ["TRADE_ROW_REPEATED_VALUES"], "…": "…"}, "…"],
 "passes": {"with_flagged": {"status": "OK", "paired_months": ["2026-09", "2026-10", "2026-11", "2026-12"], "paired_month_count": 4,
   "baseline_months": ["2025-09", "2025-10", "2025-11", "2025-12"], "months_dropped": [],
   "direct": {"baseline_value": 358300000.0, "post_value": 142100000.0, "value_change_pct": -60.3,
              "baseline_volume": 995000.0, "post_volume": 346000.0, "volume_change_pct": -65.2, "currency": "USD", "volume_unit": "tonnes", "…": "…"},
   "substitute": {"baseline_value": 119200000.0, "post_value": 137800000.0, "value_change_pct": 15.6, "…": "…"},
   "gross_value_shortfall": 216200000.0, "gross_value_shortfall_pct": 60.3, "substitute_offset": 18600000.0,
   "scenarios": {"no_credit": 60.3, "half_credit": 57.7, "full_credit": 55.1}}, "without_flagged": "…"},
 "sensitivity_rows": ["ORV-0027|2025-07", "ORV-0027|2026-09"],
 "envelope": {"no_credit": {"low": 60.3, "high": 60.3}, "half_credit": {"low": 57.6, "high": 57.7}, "full_credit": {"low": 54.8, "high": 55.1}},
 "widened": true, "baseline_conflict": false, "repeat_sensitivity_pct": 0.3,
 "repeat_sensitivity_pct_by_scenario": {"no_credit": 0.0, "half_credit": 0.1, "full_credit": 0.3}, "repeated_row_dependent": false}
```

- `status` is `OK`, `NO_DOCUMENTED_FLOW` (no direct-route row), `NO_BASELINE` (no month pairs with the prior year and no cross-check) or `MIXED_UNITS`.
- `crosscheck` is `NONE`, `AGREE` (within `tolerance_pct_points`, config `baseline_crosscheck_tolerance_pct_points`), `CONFLICT` (flag `BASELINE_CONFLICT`, extra pass `crosscheck_scaled`) or `CROSS_CHECK_ONLY` (flag `BASELINE_PROXY`, `baseline_basis: CROSS_CHECK_ONLY`, pass `crosscheck_proxy`). A cross-check ref is `{doc_id, paragraph, citation, tier, pub_date, month, kind: pct_of_normal | index, level}`.
- each pass also has `scenario_values` (net shortfall in the rows' currency) and `scenario_volumes` (in their volume unit), and the record has `envelope_value` / `envelope_volume` alongside `envelope`, so a range in % maps to the same scenario in USD and tonnes (Stage 3 A5). `direct` adds `unit_price_before` / `unit_price_after` (value / volume);
- `widened` means the repeated rows changed the range; `baseline_conflict` is reported separately. `repeat_sensitivity_pct` is the largest with/without difference over the scenarios, and `null` for a cell with no flagged input (that cell keeps its single-pass range).

## Claim (`CELL_ESTIMATE` / `SUPPORTING`)

Contract: `CLAIM_SCHEMA` (`schema.py:43`), with the runtime rules in `backend/agents/claims.py`:
- exactly one estimate per cell per side, and at most `max_supporting_claims_per_side_per_round` `SUPPORTING` claims over the whole round (all cell batches);
- citations must have been retrieved by that agent (search, `get_document`, trade rows, or the cross-checks returned by `calc`); every claim cites at least one span, except a `CELL_ESTIMATE` without a range, which rests on its calc record;
- every number in `claim_text`, `mechanism` and `assumptions` traces to a calc field or to a whole number in a cited span (citation brackets, IDs, row keys and calendar dates are skipped, md 2309-2317);
- a numeric cell needs a case-event citation;
- a claim citing a repeated row names its flag (`TRADE_ROW_REPEATED_VALUES` / `TRADE_ROW_DUPLICATE`);
- no masked text;
- Loki names a mechanism;
- an `ESTIMATED` cell carries `secondary_metrics` (value change in currency and %, volume change in the rows' unit and %, implied unit price before and after), each equal to `passes.<pass>.direct` of its calc record; other claims carry `null` (Stage 3 A5). The headline range stays `net_value_shortfall_pct`;
- every claim has `supersedes` (`null` in round 1); the ledger copy adds `superseded_by` and a `status` of `submitted`, `superseded` or `withdrawn` (`LEDGER_CLAIM_SCHEMA`, `schema.py:75`).

These are stored in the Case File `claim_ledger` and written to `claim_ledger.json`.

```json
{"claim_id": "claim-loki-001", "agent": "loki", "run": 1, "round": 1, "claim_type": "CELL_ESTIMATE", "claim_kind": "INFERENCE",
 "country": "Midgard", "sector": "Wheat", "metric": "net_value_shortfall_pct", "estimate_status": "ESTIMATED",
 "estimate": {"low": 54.8, "high": 57.7, "unit": "percent",
              "low_ref": {"calc_id": "calc-r1-loki-01", "field": "envelope.full_credit.low"},
              "high_ref": {"calc_id": "calc-r1-loki-01", "field": "envelope.half_credit.high"}},
 "claim_text": "Loki estimates a net value shortfall of 54.8% to 57.7% for Midgard Wheat imports, crediting documented substitute growth in full.",
 "number_refs": [{"value": "54.8", "calc_id": "calc-r1-loki-01", "field": "envelope.full_credit.low"},
                 {"value": "57.7", "calc_id": "calc-r1-loki-01", "field": "envelope.half_credit.high"}],
 "calc_ids": ["calc-r1-loki-01"], "citations": ["[ORV-0009, P4, 2027-01-19 09:20]", "[ORV-0027, P5, 2027-01-22 09:05]"],
 "mechanism": "Documented substitute routes from Vanir into Midgard (trade rows) offset part of the direct-route loss.",
 "assumptions": ["Baseline = the same months one year earlier on the same route (F11 primary rule)",
                 "Documented substitute growth fully replaces lost direct-route value",
                 "Rows flagged TRADE_ROW_REPEATED_VALUES (Vanir to Midgard 2025-07, Vanir to Midgard 2026-09) are used in one pass and left out in the other; the range covers both passes"],
 "confidence": 0.6, "status": "submitted"}
```

A cell with no documented flow carries no range and no number. It cites the result set of the search the agent ran for the cell, background documents included as context; every cell has at least one executed search (Stage 3 A2):

```json
{"claim_id": "claim-thor-004", "claim_type": "CELL_ESTIMATE", "country": "Tolan", "sector": "Maize",
 "estimate_status": "NO_DOCUMENTED_FLOW", "estimate": null, "calc_ids": ["calc-r1-thor-04"],
 "citations": ["[ORV-0046, P1, 2027-01-20 10:05]", "[ORV-0042, P1, 2026-11-25 13:05]", "[ORV-0044, P1, 2027-01-22 10:50]"],
 "claim_text": "No trade row from Orvan into Tolan for Maize is documented in the case scope; the case-event documents retrieved for this cell (cited) carry none, so no range is given.", "…": "…"}
```

A `SOURCED_FACT` quotes one sentence of a Tier 1-2 span it cites:

```json
{"claim_id": "claim-thor-005", "claim_type": "SUPPORTING", "claim_kind": "SOURCED_FACT", "country": "Midgard", "sector": "Wheat",
 "claim_text": "A news report states: \"Midgard's flour millers are booking wheat from Vanir and asking for more rail capacity from Ravik after Orvan's sea loadings fell in September.\"",
 "number_refs": [], "calc_ids": [], "citations": ["[ORV-0006, P1, 2026-10-08 08:45]"], "…": "…"}
```

## Round 2: challenge, response, cross-examination entry (Stage 3)

Contracts: `CHALLENGE_SCHEMA` (`schema.py:85`), `RESPONSE_SCHEMA` (`schema.py:97`) and the Case File entry `CROSS_EXAMINATION_SCHEMA` (`schema.py:110`), which is the challenge with its `response` attached by the runtime (`null` if the defending side failed). They are written to the Case File `cross_examination` and to `cross_examination.json`. Rules (`backend/agents/cross_exam.py:105` `validate_challenges`, `:142` `validate_responses`):
- each side files between 1 and `max_challenges_per_side_per_round` (config, TUNABLE) challenges, at most one per target, only against the other side's round-1 claims, each with citations it retrieved itself;
- `challenge_kind` is one of `SOURCE_TIER`, `INTERESTED_PARTY`, `POST_AS_OF`, `BACKGROUND_ONLY`, `REPEATED_ROWS`, `BASELINE_CHOICE`, `INFERENCE_AS_FACT`, `EVIDENCE_MISREAD`, `ASSUMPTION_ATTACK`, `SINGLE_SOURCE` (the spec's md 1019 example names only `ASSUMPTION_ATTACK`);
- `DEFEND` needs `new_evidence`: cited spans retrieved by the responder in round 2 and not cited in its round 1;
- `QUALIFY` names `revised_claim_id`, a round-2 claim with `supersedes` = the target; a revised range lies inside the original and cites a round-2 calc;
- `CONCEDE` needs a `reason` and applies to `SUPPORTING` claims only;
- numbers in `challenge_text`, `response_text` and `reason` need `number_refs` (a calc field of any calc in the Case File, or a cited span), and no masked text may appear.

Real mock E5 entry (a QUALIFY):

```json
{"challenge_id": "challenge-loki-001", "challenger": "loki", "target_agent": "thor", "target_claim_id": "claim-thor-001",
 "challenge_kind": "ASSUMPTION_ATTACK",
 "challenge_text": "claim-thor-001 sets its high (60.3%) for Midgard Wheat with no credit for substitutes, although the substitute routes behind its own calc grew 15.6% in value (cited rows).",
 "citations": ["[ORV-0027, P5, 2027-01-22 09:05]"],
 "number_refs": [{"value": "60.3", "calc_id": "calc-r1-thor-01", "field": "envelope.no_credit.high"},
                 {"value": "15.6", "calc_id": "calc-r1-thor-01", "field": "passes.with_flagged.substitute.value_change_pct"}],
 "run": 1, "round": 2, "required_response": "DEFEND_QUALIFY_OR_CONCEDE",
 "response": {"response_id": "response-thor-001", "responder": "thor", "challenge_id": "challenge-loki-001",
              "target_claim_id": "claim-thor-001", "response_type": "QUALIFY",
              "response_text": "claim-thor-001 is narrowed to 57.6% to 57.7% as claim-thor-010: no new evidence answers challenge-loki-001.",
              "citations": [], "new_evidence": [],
              "number_refs": [{"value": "57.6", "calc_id": "calc-r1-thor-05", "field": "envelope.half_credit.low"},
                              {"value": "57.7", "calc_id": "calc-r1-thor-05", "field": "envelope.half_credit.high"}],
              "revised_claim_id": "claim-thor-010", "reason": null}}
```

A DEFEND carries its new evidence:

```json
{"response_id": "response-loki-002", "responder": "loki", "challenge_id": "challenge-thor-002", "target_claim_id": "claim-loki-007",
 "response_type": "DEFEND",
 "response_text": "claim-loki-007 stands: the cited index is port-wide, so it is not a measure of this route. A source it did not cite before states: \"The index covers all grain loaded at the port, not only the routes covered by the monthly trade notes.\"",
 "citations": ["[ORV-0012, P7, 2026-12-15 10:00]"], "new_evidence": ["[ORV-0012, P7, 2026-12-15 10:00]"],
 "number_refs": [], "revised_claim_id": null, "reason": null}
```

### Revised estimate (round 2)

A revised claim is an ordinary claim with `round: 2` and `supersedes` set. The runtime sets the target's `status` to `superseded` and its `superseded_by` to the new id (a conceded claim becomes `withdrawn`). Both stay in `claim_ledger`. The current estimate for a cell is the one with `status: submitted`. Calc ids are numbered per run (`calc-r1-...` = Run 1); a round-2 calc record carries `round: 2`.

```json
{"claim_id": "claim-thor-010", "agent": "thor", "run": 1, "round": 2, "claim_type": "CELL_ESTIMATE", "claim_kind": "INFERENCE",
 "country": "Midgard", "sector": "Wheat", "metric": "net_value_shortfall_pct", "estimate_status": "ESTIMATED",
 "estimate": {"low": 57.6, "high": 57.7, "unit": "percent",
              "low_ref": {"calc_id": "calc-r1-thor-05", "field": "envelope.half_credit.low"},
              "high_ref": {"calc_id": "calc-r1-thor-05", "field": "envelope.half_credit.high"}},
 "claim_text": "Thor narrows its Midgard Wheat estimate to 57.6% to 57.7% (half of the documented substitute growth credited) after challenge-loki-001.",
 "calc_ids": ["calc-r1-thor-05"], "citations": ["[ORV-0009, P4, 2027-01-19 09:20]", "[ORV-0027, P5, 2027-01-22 09:05]"],
 "assumptions": ["…", "Revised in cross-examination after challenge-loki-001 (ASSUMPTION_ATTACK)"], "confidence": 0.6,
 "status": "submitted", "secondary_metrics": {"calc_id": "calc-r1-thor-05", "pass": "with_flagged", "…": "…"},
 "supersedes": "claim-thor-001", "superseded_by": null}
```

The run record gains `run_status[0].round_2`: per agent `status`, `steps`, `turns`, `retries`, `tool_calls`, `searches`, `cache_hits`, `challenges`, `responses` (counts by type), `revised_claims`, `model_calls`, token estimates, `shadow_cost_usd`, `failure`; plus `agent_failures`, `concessions`, `qualifications` and `unanswered`.

## Memory entry

Contract: `MEMORY_ENTRY_SCHEMA` (`contracts.py:162`). Stored one store per agent at `data/memory/<agent>/memory.jsonl`, which only the owner can open. The runtime sets `source_doc_ids`, `max_source_pub_date` and `written_as_of`. An entry whose `max_source_pub_date` is after a case's as-of date is hidden for that case (`MEMORY_HIDDEN`). A `case_note` is read only for the same event. `memory_id` hashes key, value and source documents; `source_case_id` and `created_at` are volatile.

```json
{"memory_id": "mem-thor-34dc0ed0db", "agent_id": "thor", "key": "unproductive_query", "kind": "case_note",
 "value": {"event_id": "E5", "country": "Tolan", "sector": "Maize", "template": "t1", "query": "Orvan Tolan Maize disruption delays shortfall"},
 "source_case_id": "case-a2be1d218602", "source_doc_ids": ["ATL-0010", "ORV-0037", "ORV-0042", "ORV-0044", "ORV-0046"],
 "max_source_pub_date": "2027-01-22", "written_as_of": "2027-01-25", "version": 1, "created_from_trace_id": null,
 "created_at": "2026-10-25T12:45:42Z"}
```

The memory-driven change logged in the next case:

```json
{"actor": "thor", "event_type": "DECISION_CHANGED", "level": "INFO",
 "payload": {"memory_id": "mem-thor-34dc0ed0db", "kind": "QUERY_REWRITTEN", "cell": ["Tolan", "Maize"], "turn": 1, "verified": true,
             "before": "Orvan Tolan Maize disruption delays shortfall", "after": "Tolan Maize imports disruption"}, "…": "…"}
```

## Run record: Round 1 block (`run_status[0].round_1`)

```json
{"agents": {"thor": {"status": "OK", "steps": 1, "turns": 3, "retries": 0, "tool_calls": 6, "searches": 4, "cache_hits": 0,
                     "claims": 7, "calcs": 4, "memory_read": [], "memory_hidden": [], "memory_written": ["mem-thor-34dc0ed0db"],
                     "decisions_changed": [], "model_calls": 3, "input_tokens_est": 22439, "output_tokens_est": 2319,
                     "shadow_cost_usd": 0.003403, "failure": null}, "loki": {"…": "…"}},
 "agent_failures": []}
```

`status` is `OK`, `THOR_FAILED` or `LOKI_FAILED`. A failure (also in `agent_failures` and the `AGENT_FAILED` event) carries `reason`, `problems`, `step`, `run`, `round`, `attempts`, `last_error`, `input_tokens`, `output_tokens`, `cost_usd` and `shadow_cost_usd` (md 1706). `INPUT_REBUILT` is logged when a prompt over the role's `max_input_tokens` was rebuilt without its oldest tool results; `DOCUMENT_RETRIEVED` logs each `get_document` call. The run record also carries `handled_failures` (hash mismatches excluded by `case_scope`), `cross_pack_families` and `verification_fallback` (`fired`, `trigger`, `classified`, `calls`).

## OD-1 row-reference chain

| Link | Status | Carries | Test |
|---|---|---|---|
| Trade row (ingestion) | BUILT | `source_doc_id`, `paragraph` (P#), `table_id`, `native_row_number`, `row_key`, `raw_text`, `citation`. A table with no `TABLE_ID` header gets `table_id: null` but keeps its row numbers | `tests/test_contracts.py` (E5 prose row; synthetic tables with and without a table ID) |
| Case File trade-row evidence | BUILT | `doc_id`, `citation`, `paragraph`, `table_id`, `native_row_number`, `row_key` | same |
| `calc_id` inputs | BUILT (Stage 2) | every input is a row ref: `row_key`, `doc_id`, `paragraph`, `table_id`, `native_row_number`, `citation` | `tests/test_stage2.py` `test_calc_reports_value_and_volume_change_with_row_refs` |
| Claim citation | BUILT (Stage 2) | bracket `[DOC_ID, P#, timestamp]` of one input row per document; `calc_ids` lead to every row ref. Flagged rows are named in words (origin, destination, month) in `assumptions`; table rows are not named yet (E5 rows are prose-note months) | `tests/test_stage2.py` `test_citations_are_valid_in_scope_and_retrieved_by_that_agent` |
| Briefing `row_refs` | BUILT | `doc_id`, `paragraph`, `table_id`, `native_row_number`, `row_key` per paragraph and per exposure-table row | `tests/test_final.py` |
| Source-span API `table_id` / `row` | TODO (Stage 4) | `GET /api/sources/{doc_id}/spans/{span_id}?table_id=&row=` (md 2378) | none |
| UI highlight of the named row | TODO (Stage 4) | source drawer highlight (md 2029) | none |

## Final build: rulings, Run 2, briefing, run record

Contracts: `RULING_SCHEMA` (`backend/agents/odin.py`), `BRIEFING_SCHEMA`, `FINAL_RUN_RECORD_SCHEMA`, `TRAP_REPORT_SCHEMA` (`backend/contracts.py`). All are checked by `tests/test_final.py` against a mock E5 run. Output files of one case, under `data/runs/<case_id>/`: `case_file.json`, `claim_ledger.json`, `calc_ledger.json` (each record carries `calc_explain`), `cross_examination.json`, `rulings.json`, `briefing.json`, `briefing.md`, `trap_report.json`, `run_record.json`, `events.jsonl`, `search_log.jsonl`, `provider_calls.jsonl`, `llm_calls.jsonl`, `config.json`.

**Ruling** (one per claim, including superseded and withdrawn ones): `ruling_id`, `claim_id`, `run`, `agent`, `country`, `sector`, `classification` (`ESTABLISHED` / `CONTESTED` / `CONCEDED` / `REJECTED`), `claim_kind` (`SOURCED_FACT` / `INFERENCE`), `decision` (`ACCEPTED` / `QUALIFIED` / `REJECTED`), `rejected_by` (`PRE_RULING_CHECK` / `CONCESSION` / `ODIN`), `rejection_reasons`, `qualification_reasons`, `rationale`, `supporting_refs`, `conflicting_refs`, `confidence`, `decided_by` (`RULES` / `MODEL`). Pre-ruling reason codes: `INVALID_CITATION`, `POST_AS_OF_CITATION`, `OUT_OF_CASE_SCOPE`, `HASH_MISMATCH`, `NOT_RETRIEVED_BY_CLAIMANT`, `ONLY_TIER_4_SUPPORT`, `ONLY_BACKGROUND_SUPPORT`, `ONLY_DAMAGED_FAMILY`, `QUOTE_NOT_VERBATIM` (reject), `COMPANY_STATEMENT_OVERREACH` (qualify).

```json
{"ruling_id": "ruling-odin-003", "claim_id": "claim-loki-006", "run": 1, "agent": "loki", "country": "Tolan", "sector": "Wheat",
 "classification": "CONCEDED", "claim_kind": "SOURCED_FACT", "decision": "REJECTED", "rejected_by": "CONCESSION",
 "rejection_reasons": ["CONCEDED_BY_AUTHOR"], "rationale": "The author conceded this claim after a INTERESTED_PARTY challenge: …",
 "supporting_refs": [{"doc_id": "ORV-0042", "span_id": "ORV-0042:P1"}], "conflicting_refs": [], "confidence": 0.9,
 "created_at": "2027-01-25T00:00:00Z", "decided_by": "RULES", "claim_status": "withdrawn", "superseded_by": null}
```

**Cell result** (Odin's range, `odin.cell_results`): `{country, sector, status (ASSESSED | INSUFFICIENT_EVIDENCE | INCOMPLETE_BUDGET_LIMIT), reason, thor, loki, odin: {low, high, unit, value: {low, high, unit, low_ref, high_ref}, volume: {...}, widened} | null}`; value and volume come from the same scenario field of the same calc record as the percent range.

**Run 2 record** (`run_status[1]`): `run_number: 2`, `gaps` (cell, reason, missing checks, Heimdall's queries), `queries_by_cell` (queries not used in Run 1), `run2_new_evidence_families`, `run2_new_evidence_citations`, `run2_no_evidence_reason` (set when the list is empty), `updated_claims`, `agent_failures`. Run 2 claims have `run: 2`, `round: 1`, and each `CELL_ESTIMATE` supersedes the side's Run-1 estimate for that cell.

**Briefing paragraph** (`PARAGRAPH_SCHEMA`): `paragraph_id`, `text`, `finding_classification`, `claim_refs`, `citation_refs`, `row_refs` (`doc_id`, `paragraph`, `table_id`, `native_row_number`, `row_key`), `calc_refs`, `number_refs` (`{value, calc_id, field}` or `{value, citation}`), `confidence`. Sections: `executive_summary`, `event_verification`, `established`, `contested`, `conceded`, `rejected`, `exposure_table` (Thor / Loki / Odin per cell with `calibration`), `outlook`, `assumptions_limitations`, `sources`, `removed_by_validator`.
