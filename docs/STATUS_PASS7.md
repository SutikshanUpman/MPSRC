# Status pass 7: all 44 review findings

**Source:** `docs/REVIEW_FINAL.md` section A (44 findings: 4 BLOCKER, 21 MAJOR, 19 MINOR).
**Checked against:** `docs/SYSTEM_ARCHITECTURE.md` and `docs/architecture.mmd` after pass 7, plus the ingestion code in `backend/` and `tests/`. Read-only: nothing was changed to produce this table.
**Method:** for each finding, grep for the review's fix text or its key terms, then read the line range. No LLM calls.

**Status rules.**
- **FIXED:** the review's fix (or the user-approved replacement) is in the architecture doc.
- **PARTIAL:** part of the fix is in, or it is implemented in code and tests but the architecture doc does not yet say so.
- **OPEN:** neither.

Line numbers are for `SYSTEM_ARCHITECTURE.md` unless prefixed `mmd:` or a file path.

**Build stages:** ingestion · Heimdall+Case File · Thor/Loki+memory · cross-examination · Odin+briefing · cost ledger+cache · dashboard · logging.

## Counts

| Severity | Total | FIXED | PARTIAL | OPEN |
|---|---:|---:|---:|---:|
| BLOCKER | 4 | 4 | 0 | 0 |
| MAJOR | 21 | 6 | 4 | 11 |
| MINOR | 19 | 2 | 3 | 14 |
| **All** | **44** | **12** | **7** | **25** |

## Table

| ID | Sev | Status | Blocks stage | Evidence / what is missing |
|---|---|---|---|---|
| F01 | BLOCKER | FIXED | — | Grid derived from the Case File: md 95-99, 2251 |
| F02 | BLOCKER | FIXED | — | Unit-agnostic grammar: md 1332-1338; code `backend/ingestion/trade.py` |
| F03 | BLOCKER | FIXED | — | Closed as decision OD-1 (`[DOC_ID, P#, timestamp]` only; row named in words; click-through highlights it): md 1867-1874 |
| F06 | BLOCKER | FIXED | — | Model plan and Odin reserve: md 638-654; hard limits and guard: md 1657-1690 |
| F04 | MAJOR | OPEN | ingestion, Heimdall+Case File | `POST /api/cases` (md 2137) still takes one `pack_path`; no `pack_paths: [base, live]`, so a live-pack case loses the ATL reference sheets |
| F05 | MAJOR | FIXED | — | Verification rule: md 181-185 |
| F07 | MAJOR | OPEN | Thor/Loki+memory, cross-examination, Odin+briefing | No `max_tool_calls_per_agent_step` / `max_model_turns_per_agent_step` in hard limits (md 1657); no `THOR_FAILED`, `LOKI_FAILED`, `ODIN_FAILED`, `WALL_CLOCK_LIMIT` states. D1 now routes "agent failure" to `INCOMPLETE_NO_NEW_EVIDENCE` only for Run 2 |
| F08 | MAJOR | FIXED | — | Sufficiency criteria (a)-(c): md 1970-1976 |
| F09 | MAJOR | FIXED | — | Pre-ruling checks and concession rule: md 1722-1735; REJECTED example: md 1054-1071 |
| F10 | MAJOR | FIXED | — | Canonical metric `net_value_shortfall_pct`: md 1926; one CELL_ESTIMATE per cell |
| F11 | MAJOR | OPEN | Odin+briefing | Baseline (md 1895) is still E5-specific ("July and August 2026"); no YoY primary / pre-event secondary rule |
| F12 | MAJOR | OPEN | Heimdall+Case File, Odin+briefing | Coverage test (md 1978) still lists E5 cells; no generic per-cell direct/substitute/contract test |
| F13 | MAJOR | FIXED | — | Background-only rule: md 1412 |
| F14 | MAJOR | FIXED | — | Source rules 1-5: md 1490; trap rows for ORV-0003/0049/0004: md 463-465 |
| F15 | MAJOR | OPEN | Thor/Loki+memory | Memory record (md 1759) has no `source_doc_ids` / `max_source_pub_date`; post-as-of facts can leak through `case_note` |
| F16 | MAJOR | OPEN | Odin+briefing | Paragraph contract (md 2114) has no number-to-span / `calc_id` rule and no deterministic number validator |
| F17 | MAJOR | PARTIAL | ingestion (doc only) | Implemented and tested (`backend/ingestion/manifest.py`); §14.2 (md 1228) does not state the normalisation rules |
| F18 | MAJOR | PARTIAL | ingestion (doc only) | Implemented and tested (`backend/ingestion/encoding.py`: NUL-share UTF-16 guess, cp1252 fallback); §14.3 TXT (md 1241-1252) still lists BOM-only decoding |
| F19 | MAJOR | PARTIAL | ingestion (doc only) | Implemented and tested (`trade.py` `parse_fixed_tables`); §14.6 (md 1343) still one sentence, no delimiter/column-mapping/`TRADE_TABLE_UNPARSED` rule |
| F20 | MAJOR | OPEN | dashboard | API (md 2135) has no `/feed`, `/case-file`, `/trace`, `/api/packs`, `/api/budget` |
| F21 | MAJOR | OPEN | logging, cost ledger+cache | Replay (md 2190) does not say it uses `DeterministicMockProvider` with recorded responses; no `REPLAY_DIVERGED` |
| F22 | MAJOR | OPEN | Heimdall+Case File | Event mapping (md 1437) still says "exactly one clear best match" with no score threshold |
| F23 | MAJOR | OPEN | Heimdall+Case File | No rule for a question with no sector or country; "known route countries" (md 1423) undefined |
| F31 | MAJOR | OPEN | Odin+briefing, cost ledger+cache | `max_output_tokens_per_call: 1500` (md 1668) for every role; Odin rulings and briefing can truncate |
| F41 | MAJOR | PARTIAL | ingestion (doc only) | Synthetic unseen pack exists (`tests/fixtures/synthetic_pack.py`, 53 tests pass); §29 tests (md 2632) do not describe it, and it has no question/event-mapping part (that waits on Heimdall) |
| F24 | MINOR | OPEN | Heimdall+Case File, Thor/Loki+memory | "Typical arguments" (md 212) not marked as E5-only illustrations kept out of prompts |
| F25 | MINOR | PARTIAL | cross-examination, Odin+briefing | Ruling `decision` enum defined (md 1054); `case_status`, `cell_status`, `claim_status` enums still missing |
| F26 | MINOR | OPEN | logging | No trace-event vocabulary in §12.8 (md 1075); example still uses `event_id` |
| F27 | MINOR | OPEN | cross-examination | No Defence/Concession JSON schema next to 12.6 (md 1014) |
| F28 | MINOR | OPEN | cross-examination | Thor/Loki tools (md 1550) have no Case File read path, and the "runtime injects the Case File" rule is absent |
| F29 | MINOR | OPEN | Heimdall+Case File | `map_question_to_event` is still an LLM tool (md 1541), not `trial/event_mapping.py` |
| F30 | MINOR | OPEN | cost ledger+cache, Thor/Loki+memory | Search caps (md 1663) still allow Run 1 to starve Run 2; no `SEARCH_LIMIT_REACHED` |
| F32 | MINOR | OPEN | cost ledger+cache (diagram only) | Edge still `BUDGET -->|case cap reached| SUFF` (md 551 = mmd:54) |
| F33 | MINOR | OPEN | Heimdall+Case File (doc only) | Trap table (md 449) still labels ORV-0013 "Official correction" |
| F34 | MINOR | PARTIAL | ingestion (doc only) | Rule implemented in code (last unmasked paragraph without terminal punctuation, or strict prefix of a same-title twin); doc states it only for tables (md 1351) |
| F35 | MINOR | OPEN | ingestion, Heimdall+Case File | No "manifest RELIABILITY is authoritative" / `OUTLET_NOT_IN_GUIDE` rule (ranking at md 1464) |
| F36 | MINOR | FIXED | — | "Never derive value from volume using reference price sheets": md 1936 |
| F37 | MINOR | OPEN | logging | `created_at` examples (md 1050, 1071) still use the simulated date |
| F38 | MINOR | OPEN | cost ledger+cache | Two ledger paths (md 1105, 2989), no snapshot rule |
| F39 | MINOR | FIXED | — | Superseded by D1: the unreachable "max_runs reached" branch was replaced by "limit or cap reached before Run 2 searches" (md 1627) |
| F40 | MINOR | PARTIAL | ingestion (doc only) | Code masks TITLE and header values (tested); §26 injection rule (md 2351) still says "paragraph line" only |
| F42 | MINOR | OPEN | ingestion, Heimdall+Case File | Pipeline step "build correction/contradiction relations" (md 1222) still undefined |
| F43 | MINOR | OPEN | Odin+briefing | No statement that the folder tree (md 674) is aspirational, that the evidence graph is a `relations` list, or that sensitivity is one table |
| F44 | MINOR | OPEN | cross-examination, Odin+briefing (diagram only) | No agent-failure edges in the diagram; waits on F07's states (§25 agent failures at md 2310) |

## Open or partial MAJORs by stage

| Stage | Findings |
|---|---|
| ingestion | F04, F17, F18, F19, F41 (F17-F19 and F41 are doc updates; the code is done) |
| Heimdall+Case File | F04, F12, F22, F23 |
| Thor/Loki+memory | F07, F15 |
| cross-examination | F07 |
| Odin+briefing | F07, F11, F12, F16, F31 |
| cost ledger+cache | F21, F31 |
| dashboard | F20 |
| logging | F21 |
