# Status pass 8: all 44 review findings

**Source:** `docs/REVIEW_FINAL.md` section A (44 findings: 4 BLOCKER, 21 MAJOR, 19 MINOR).
**Checked against:** `docs/SYSTEM_ARCHITECTURE.md` and `docs/architecture.mmd` after pass 8b, plus the ingestion code in `backend/` and `tests/`. This file is a fresh copy of `docs/STATUS_PASS7.md`, which is kept unchanged as history.
**Method:** each pass 7 line reference was remapped to the current file with a line diff (`difflib`) between the pass 7 and current `SYSTEM_ARCHITECTURE.md`. References into text that pass 8/8b rewrote were located again by grep. No LLM calls.

**Status rules.**
- **FIXED:** the review's fix (or the user-approved replacement) is in the architecture doc. A documented deviation is noted in the row.
- **PARTIAL:** part of the fix is in, or it is implemented in code and tests but the architecture doc does not yet say so.
- **OPEN:** neither.

Line numbers are for `SYSTEM_ARCHITECTURE.md` unless prefixed `mmd:` or a file path. Details of the pass 8 and 8b changes are in `docs/FIX_PASS8.md`.

**Build stages:** ingestion · Heimdall+Case File · Thor/Loki+memory · cross-examination · Odin+briefing · cost ledger+cache · dashboard · logging.

## Counts

| Severity | Total | FIXED | PARTIAL | OPEN |
|---|---:|---:|---:|---:|
| BLOCKER | 4 | 4 | 0 | 0 |
| MAJOR | 21 | 15 | 4 | 2 |
| MINOR | 19 | 3 | 3 | 13 |
| **All** | **44** | **22** | **7** | **15** |

Change from pass 7: MAJOR F04, F07, F11, F12, F15, F16, F22, F23, F31 and MINOR F44 moved from OPEN to FIXED.

## Table

| ID | Sev | Status | Blocks stage | Evidence / what is missing |
|---|---|---|---|---|
| F01 | BLOCKER | FIXED | — | Grid derived from the Case File: md 95-99, 2457 |
| F02 | BLOCKER | FIXED | — | Unit-agnostic grammar: md 1340-1346; code `backend/ingestion/trade.py` |
| F03 | BLOCKER | FIXED | — | Closed as decision OD-1 (`[DOC_ID, P#, timestamp]` only; row named in words; click-through highlights it): md 2023-2030 |
| F06 | BLOCKER | FIXED | — | Model plan and Odin reserve: md 643-659 (reserve now derived, md 658); hard limits and guard: md 1725-1797; budget stop rules: md 1801-1818 |
| F04 | MAJOR | FIXED | — | `pack_paths: [base_reference_pack, live_pack, ...]`: md 2342-2346. Collision rule (pass 8b): same body hash → one document, INFO log; different body → live copy wins, base copy quarantined, `INTEGRITY_WARNING` in the run record; never stops the case: md 2348-2353 |
| F05 | MAJOR | FIXED | — | Verification rule: md 182-186 |
| F07 | MAJOR | FIXED | — | Per-step limits: md 1734-1737; agent failure and wall-clock states with status, briefing and log: md 1685-1711; §25: md 2518. Deviation (pending approval): the wall clock keeps a 120 s briefing reserve instead of going straight to a template (FIX_PASS8 B2) |
| F08 | MAJOR | FIXED | — | Sufficiency criteria (a)-(c): md 2136-2142 |
| F09 | MAJOR | FIXED | — | Pre-ruling checks and concession rule: md 1865-1878; REJECTED example: md 1059-1076 |
| F10 | MAJOR | FIXED | — | Canonical metric `net_value_shortfall_pct`: md 2092; one CELL_ESTIMATE per assessed cell: md 1017 |
| F11 | MAJOR | FIXED | — | Generic baseline rule (YoY primary; index or "% of normal" cross-check; one-only, neither, disagreement): md 2051-2069. Follows the user's spec, not the review's pre-event mean (FIX_PASS8 B3) |
| F12 | MAJOR | FIXED | — | Generic per-cell coverage test, statuses, feeds Odin's send-back: md 2144-2158 |
| F13 | MAJOR | FIXED | — | Background-only rule: md 1420 |
| F14 | MAJOR | FIXED | — | Source rules 1-5: md 1530; trap rows for ORV-0003/0049/0004: md 465-467 |
| F15 | MAJOR | FIXED | — | `source_doc_ids`, `max_source_pub_date`, `written_as_of`: md 1919-1921; as-of hide rule with `MEMORY_HIDDEN`: md 1934 |
| F16 | MAJOR | FIXED | — | `calc_refs` / `number_refs` and the deterministic number validator with on-failure path: md 2294-2317 |
| F17 | MAJOR | PARTIAL | ingestion (doc only) | Implemented and tested (`backend/ingestion/manifest.py`); §14.2 (md 1236) does not state the normalisation rules |
| F18 | MAJOR | PARTIAL | ingestion (doc only) | Implemented and tested (`backend/ingestion/encoding.py`: NUL-share UTF-16 guess, cp1252 fallback); §14.3 TXT (md 1249-1260) still lists BOM-only decoding |
| F19 | MAJOR | PARTIAL | ingestion (doc only) | Implemented and tested (`trade.py` `parse_fixed_tables`); §14.6 (md 1351) still one sentence, no delimiter/column-mapping/`TRADE_TABLE_UNPARSED` rule |
| F20 | MAJOR | OPEN | dashboard | API (md 2328) has no `/feed`, `/case-file`, `/trace`, `/api/packs`, `/api/budget` |
| F21 | MAJOR | OPEN | logging, cost ledger+cache | Replay (md 2396) does not say it uses `DeterministicMockProvider` with recorded responses; no `REPLAY_DIVERGED` |
| F22 | MAJOR | FIXED | — | Score formula and accept rule (top ≥ 3 and ≥ 2x runner-up; else reject with top 3 candidates): md 1438-1455 |
| F23 | MAJOR | FIXED | — | Manifest scope defined, defaulting, `scope_assumptions` shown in the briefing: md 1431, 1459-1480; cells processed by the cell budget rule: md 1820-1839 |
| F31 | MAJOR | FIXED | — | Per-role token caps: md 1743-1748; derived reserve and guard: md 1752, 1781-1797; budget stop rules, live-case startup check: md 1801-1818 |
| F41 | MAJOR | PARTIAL | ingestion (doc only) | Synthetic unseen pack exists (`tests/fixtures/synthetic_pack.py`, 53 tests pass); §29 tests (md 2840) do not describe it, and it has no question/event-mapping part (that waits on Heimdall) |
| F24 | MINOR | OPEN | Heimdall+Case File, Thor/Loki+memory | "Typical arguments" (md 213) not marked as E5-only illustrations kept out of prompts |
| F25 | MINOR | PARTIAL | cross-examination, Odin+briefing | Ruling `decision` enum defined (md 1059); `cell_status` now has `ASSESSED` / `INCOMPLETE_BUDGET_LIMIT` (md 1837); `case_status` and `claim_status` enums still missing |
| F26 | MINOR | OPEN | logging | No trace-event vocabulary in §12.8 (md 1080); example still uses `event_id`. Pass 8/8b added event names in their sections but no central list |
| F27 | MINOR | OPEN | cross-examination | No Defence/Concession JSON schema next to 12.6 (md 1019) |
| F28 | MINOR | OPEN | cross-examination | Thor/Loki tools (md 1590) have no Case File read path, and the "runtime injects the Case File" rule is absent |
| F29 | MINOR | OPEN | Heimdall+Case File | `map_question_to_event` is still an LLM tool (md 1581), not `trial/event_mapping.py` (the scoring rule at md 1438-1455 is now deterministic) |
| F30 | MINOR | OPEN | cost ledger+cache, Thor/Loki+memory | Search caps (md 1730-1731) still allow Run 1 to starve Run 2; no `SEARCH_LIMIT_REACHED` |
| F32 | MINOR | OPEN | cost ledger+cache (diagram only) | Edge still `BUDGET -->|case cap reached| SUFF` (md 553 = mmd:54) |
| F33 | MINOR | OPEN | Heimdall+Case File (doc only) | Trap table (md 451) still labels ORV-0013 "Official correction" |
| F34 | MINOR | PARTIAL | ingestion (doc only) | Rule implemented in code (last unmasked paragraph without terminal punctuation, or strict prefix of a same-title twin); doc states it only for tables (md 1359) |
| F35 | MINOR | OPEN | ingestion, Heimdall+Case File | No "manifest RELIABILITY is authoritative" / `OUTLET_NOT_IN_GUIDE` rule (ranking at md 1504) |
| F36 | MINOR | FIXED | — | "Never derive value from volume using reference price sheets": md 2102 |
| F37 | MINOR | OPEN | logging | `created_at` examples (md 1055, 1076) still use the simulated date |
| F38 | MINOR | OPEN | cost ledger+cache | Two ledger paths (md 1110, 3197), no snapshot rule |
| F39 | MINOR | FIXED | — | Superseded by D1: the unreachable "max_runs reached" branch was replaced by "limit or cap reached before Run 2 searches" (md 1667) |
| F40 | MINOR | PARTIAL | ingestion (doc only) | Code masks TITLE and header values (tested); §26 injection rule (md 2559) still says "paragraph line" only |
| F42 | MINOR | OPEN | ingestion, Heimdall+Case File | Pipeline step "build correction/contradiction relations" (md 1230) still undefined |
| F43 | MINOR | OPEN | Odin+briefing | No statement that the folder tree (md 679) is aspirational, that the evidence graph is a `relations` list, or that sensitivity is one table |
| F44 | MINOR | FIXED | — | Agent-failure edges: md 559-561 = mmd:60-62 (byte-identical, sha256 checked) |

## Open or partial MAJORs by stage

| Stage | Findings |
|---|---|
| ingestion | F17, F18, F19, F41 (all doc updates; the code is done) |
| Heimdall+Case File | none |
| Thor/Loki+memory | none |
| cross-examination | none |
| Odin+briefing | none |
| cost ledger+cache | F21 |
| dashboard | F20 |
| logging | F21 |
