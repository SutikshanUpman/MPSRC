# Final architecture review

**Reviewed:** `docs/SYSTEM_ARCHITECTURE.md` (2,862 lines) and `docs/architecture.mmd` (78 lines), checked against the PS PDF and the dev_pack_E5 corpus.
**Method:** heading index plus targeted reads, then corpus greps. No LLM calls, and nothing edited except this file.
**Result:** 44 findings: 4 BLOCKER, 21 MAJOR, 19 MINOR. All 10 checks were completed.

Line numbers refer to `SYSTEM_ARCHITECTURE.md` unless they are prefixed `mmd:`.

## A. Findings

| ID | Sev | Chk | Location | Problem | Exact fix text |
|---|---|---|---|---|---|
| F01 | BLOCKER | 5,10 | 2083-2090; 2356; 2510 | Exposure table rows are hard-coded as `Midgard / Wheat … Tolan / Maize`. A live pack with other countries or sectors would show the wrong grid, which fails acceptance 6/7. | Replace the Rows block with: "Rows = every `target_countries × target_sectors` cell in the Case File, in question order. Never hard-code rows. For E5 this yields Midgard/Tolan × Wheat/Maize." Change Person 3's exit criterion to "Exposure table has one row per Case File cell". |
| F02 | BLOCKER | 5 | 1271 | The prose row grammar hard-codes `USD <x>M` and `tonnes`. Live sectors priced in other units (ATL-0007 lists LNG in MMBtu, chips in units, index-based goods) or in `USD 1.2B` would parse to zero rows, and no numbers would be citable. | "Match `In <Month> <Year>, the value was <CUR> <number><scale?> and the volume was <number> <unit words>`, where scale ∈ {K, M, B, bn} (normalised to an absolute amount) and unit is any word sequence before the full stop. Store `value_currency`, `volume_unit` and the raw sentence. A row that matches neither grammar is `TRADE_ROW_INVALID`, never dropped silently." |
| F03 | BLOCKER | 1,5,8 | 1276; 1750; 1754-1765 | No citation form is defined for real fixed-layout table rows, which have no `[Pn]`. PS §4.2 says trade rows are identified by table ID plus row number. The validator only knows P# locators, so new-pack numbers would fail their own citation check. | Add to §20: "Fixed-table rows are cited `[DOC_ID, R<row>, timestamp]`, e.g. `[XYZ-0007, R5, 2027-03-02 10:00]`. The source viewer shows the table's own table ID next to the row. The validator accepts `P<n>` or `R<n>` locators, resolves `R<n>` against `native_row_number`, and still checks `DOC_ID` against the manifest." Update 12.3 so `citation.locator` is either "P5" or "R5". |
| F04 | MAJOR | 1,5 | 1981; 794 | `POST /api/cases` takes a single `pack_path`. A new-pack case would lose the ATL reference sheets (tiers, routes, country profiles), which ship only in dev_pack_E5, and the base corpus. | "`pack_paths: [base_runemark, new_pack]`. The index always contains the base Runemark pack plus any live packs. A `doc_id` collision across packs is a `HASH_MISMATCH`-class integrity error, quarantined." |
| F05 | MAJOR | 1,2,8 | 163-176; 1512 | Nothing says how Heimdall decides an event is "real". The PS plants rumours of events that never happened, so a question premised on ORV-0010 ("port gone") would map to E5 and proceed. | Add to §5.1: "Verification rule: the event (and the question's premise) is VERIFIED only if at least one Tier 1-2, non-retracted, in-scope document dated on or before as_of asserts it, and no later Tier 1-2 document corrects it. If only Tier 3-4 or retracted documents support it, the result is `EVENT_REJECTED` with the reason and the citations. Premise words in the question (destroyed, closed, banned) are checked separately from the event." |
| F06 | BLOCKER | 6,7 | 616-632; 1576-1598; 1552 | No model is named. Using Sonnet 5.5 for every agent puts one case at about $0.78, over the $0.50 cap (see section F). The guard then stops billable work, but `INCOMPLETE_BRIEFING` needs an Odin call, so the case ends with no briefing. | "Model plan: Heimdall, Thor and Loki use `claude-haiku-5-5` at effort `low`. Odin uses `claude-sonnet-5-5`. At case start the guard reserves `odin_briefing_reserve_usd: 0.10` that only Odin's final ruling and briefing may spend. If even that is unavailable, the runtime renders a deterministic template briefing from the ruling ledger with no model call. Lower `max_claims_per_side_per_round` to 6, with exactly one estimate claim per cell." |
| F07 | MAJOR | 7 | 1566-1604; 2149-2170; 2220-2230 | Several limits leave undefined states. There is no cap on model↔tool turns inside one agent step (`get_document` and `get_trade_rows` are unlimited). Exhausting retries, failing output validation and the 900 s wall clock all lead nowhere in the state machine, and §25's Thor/Loki/Odin failure messages have no states. | Add limits `max_tool_calls_per_agent_step: 6` and `max_model_turns_per_agent_step: 4`. Add states `THOR_FAILED`, `LOKI_FAILED` (continue, recording the other side as "unchallenged"), `ODIN_FAILED` (go to `INCOMPLETE_AGENT_FAILURE`, template briefing, never COMPLETE) and `WALL_CLOCK_LIMIT` (same as an Odin failure). "An output that fails validation counts as one model retry. After `max_model_retries_per_call` the agent is FAILED." |
| F08 | MAJOR | 1,7 | 1522-1530 | Run 2 only fires on INSUFFICIENT. On a well-covered live pack, Odin may never send the case back, which fails acceptance 8. | Add to §21: "The sufficiency check returns INSUFFICIENT when any cell (a) has no direct-flow evidence, (b) rests on a single evidence family, or (c) contains a CONTESTED claim whose conflict cites no Tier 1-2 resolution. Each gap lists targeted queries." These are genuine criteria that real packs almost always trip. |
| F09 | MAJOR | 1 | 2315; 2505; 995-1015 | Acceptance 5 (at least one claim rejected or conceded) is asserted but nothing makes it happen, and the ruling schema has no REJECTED example. | "Deterministic pre-ruling checks REJECT any claim whose only support is Tier 4, background-only (F13), post-as-of, an invalid citation, or a damaged-only family. Thor and Loki prompts: 'If a challenge cites a later Tier 1-2 document that contradicts your claim, CONCEDE or QUALIFY.' Ruling `decision` ∈ {ACCEPTED, QUALIFIED, REJECTED}." |
| F10 | MAJOR | 1,4 | 101; 956; 1774; 1804-1808; 2095 | There is no canonical exposure metric. The Case File, claim, Odin record and §21 use four different metric names. Nothing says how many Thor claims become one per-cell "Thor range", yet range accuracy is scored on the Thor, Loki and Odin ranges. | "Canonical cell metric: `net_value_shortfall_pct` = net shortfall in trade value against baseline over the post-event months, in percent. `value_shortfall_usd` and `volume_shortfall` are secondary. Thor and Loki must each submit exactly one `CELL_ESTIMATE` claim per cell (low/high in the canonical metric). Those claims are the Thor and Loki ranges. Supporting claims carry no range." |
| F11 | MAJOR | 2,5 | 1771-1779 | The baseline is E5-specific ("July and August 2026") and ambiguous. The ORV-0012 index (100 = pre-agreement normal) and ORV-0024 (corridor at about 95%) imply different baselines, and new packs have different months. | "Baseline is derived from route-level trade rows only. Primary = the same months one year earlier (YoY; the notes carry both years). Secondary = the mean of the pre-event months, where event month = date of the first Tier 1-2 verification document. Record both and use the primary for the canonical metric. A port or loading index is a cross-check only, never the baseline." |
| F12 | MAJOR | 5 | 1840-1847 | The coverage test is written for E5 ("Tolan / Maize, Vanir→Midgard"). | "For each Case File cell, Heimdall tests (1) a direct origin→destination flow for the event's origin, (2) substitute flows into the destination for the same sector, (3) contract or delay evidence. A missing item becomes an `evidence_gap` with ≥2 queries. E5 example: Tolan/Maize, Vanir→Midgard maize." |
| F13 | MAJOR | 2,8 | 1329-1332 | Fix A put every `EVENT_ID: NONE` document in scope, including the PS's "looks related but belongs to no event" bait. ORV-0039 (summer rail paths, Jun 2026) is Loki bait, ORV-0011 (full store, Apr 2026) is supply bait, and ORV-0025 (fee rise, "not bulk grain") is Thor bait. | "NONE documents carry `BACKGROUND_ONLY`. They may support reference facts (tiers, routes, country import profiles) but never an event-impact claim or a numeric cell on their own. Such claims are rejected by the F09 check. Every exposure cell must cite at least one case-event document." This also protects the PS's citation score ("cite the final-round pack"). |
| F14 | MAJOR | 2,8 | 430-452; 1378-1400 | Source-hygiene rules exist only as prose in the trap table. Tier 4 documents, interested-party statements (ORV-0004 "no damage", ORV-0021) and a superseded Tier 1 forecast (ORV-0003 "renewal expected", 2026-08-18, missing from the trap table) have no deterministic handling. | Add §15 "Source rules": "(1) A claim supported only by Tier 4 cannot be ESTABLISHED. (2) `company_statement` sources establish facts only about the issuer's own operations. (3) A later Tier 1-2 document on the same subject supersedes an earlier one (ORV-0016 supersedes ORV-0003 and ORV-0043). (4) ESTABLISHED needs ≥1 Tier 1-2 family or ≥2 independent Tier 3 families." Add ORV-0003, ORV-0049 and ORV-0004 to the §8 trap table. |
| F15 | MAJOR | 8 | 1660-1670 | Persistent `case_note` memory can leak information from after the as-of date. A case with a later as_of writes a note from ORV-0041 (2027-04-09), and a later 2027-01-25 case loads it. | "Each `case_note` stores `source_doc_ids` and `max_source_pub_date`. It is loaded only if `max_source_pub_date ≤ case.as_of_date`. Lessons must not contain document facts." |
| F16 | MAJOR | 8 | 1754-1765; 1949-1958 | No rule ties each briefing number to its source. Validation step 5 ("cited text supports the statement") has no method. | "Every number in a briefing paragraph must either appear in a cited span's text or reference a `calc_id` in the exposure calculation record, whose inputs are cited trade rows. A deterministic validator extracts numbers per paragraph and fails any that are unmatched. No LLM check." |
| F17 | MAJOR | 2,5 | 1170-1179 | Manifest normalisation is unspecified. ATL/WLD entries have string RELIABILITY plus FORMAT and LANGUAGE; ORV entries have integer RELIABILITY, lowercase duplicate keys and no FORMAT. Code reading `FORMAT` would raise a KeyError. | Add to §14.2: "Normalise every entry: upper-case keys win, coerce `RELIABILITY` to int, infer `FORMAT` from the file extension, compare lowercase duplicates and flag `METADATA_CONFLICT` on mismatch, and tolerate missing optional fields. Live manifests may use either schema." |
| F18 | MAJOR | 2,5 | 1185-1196 | Decoding covers BOM-marked UTF-16 only. PS §4.5 promises "badly encoded" documents in live packs: UTF-16 without a BOM, cp1252. | "Per section: if ≥20% of bytes are NUL, try UTF-16-LE then UTF-16-BE and choose the decode with the most printable ASCII. If UTF-8 fails, try cp1252 and flag `MALFORMED_ENCODING`. Always record the decoder used." |
| F19 | MAJOR | 5 | 1276 | The fixed-layout table parser is one sentence long. There is no sample in E5, so the live format is unknown. | "Header: `key: value` lines until the first line containing ≥3 delimiter-separated tokens. Detect the delimiter (pipe, tab, comma, or 2+ spaces) from the column line. Map columns by name (row, month/period, value, volume, unit), case-insensitively. If parsing fails: `TRADE_TABLE_UNPARSED`, keep the raw text searchable, and continue." |
| F20 | MAJOR | 3,10 | 1969-2034; 2045; 2050-2060 | Several UI needs have no endpoint: the live feed replayed from documents (FR7.1), the trace viewer, the Case File panel (demo step 3), the pack selector and budget status. | Add `GET /api/cases/{id}/feed` (eligible documents sorted by PUB_DATE+PUB_TIME, ≤ as_of, with flags), `GET /api/cases/{id}/case-file`, `GET /api/cases/{id}/trace?agent=&run=&type=`, `GET /api/packs` and `GET /api/budget`. |
| F21 | MAJOR | 6,1 | 2022-2034; 2511 | Replay is "deterministic", but LLM outputs are not. If replay re-calls the model it costs money and won't reproduce. | "Replay re-runs the runtime with `DeterministicMockProvider` serving the recorded responses from the trace (keyed by input_hash). Zero billable calls. A hash mismatch is reported as REPLAY_DIVERGED." |
| F22 | MAJOR | 7,5 | 1344-1354 | "Exactly one clear best match" has no threshold, so a live question can be falsely rejected and the whole round is lost. | "Score = matched entities (word-boundary) against the manifest event name/ID ×3 plus against titles ×1. Accept if top ≥ 3 and top ≥ 2 × second; otherwise reject, listing the top 3 candidates and their scores." |
| F23 | MAJOR | 5 | 1337; 89-100 | It is undefined what happens when the question names no sector or country, and "known route countries" is never defined. | "If the question names no sectors, derive them from the event's trade rows that touch the target countries. If it names no countries, derive destinations from the event's trade rows. Route countries = every origin and destination in the event's trade rows." |
| F31 | MAJOR | 6,4 | 1577 | `max_output_tokens_per_call: 1500` counts adaptive-thinking tokens as output. Odin's rulings (~16 claims) and the briefing will truncate, producing invalid JSON and a failure. | "Per-role caps: Heimdall/Thor/Loki 2000; Odin rulings 6000; Odin briefing 6000. The worst-case reservation uses the role cap." |
| F41 | MAJOR | 5,9 | 2460-2512 | Every test is E5. Nothing exercises a pack the team has never seen. | Add "Unseen-pack fixture: synthetic pack with a different event, countries and sector (non-tonne unit), one PS fixed-layout table, one cut-off table, one body duplicate, one BOM-less UTF-16 document, and a question with no sector. Assert: event mapped, grid derived, rows parsed and flagged, all citations resolve." |
| F24 | MINOR | 5 | 201-242 | "Typical arguments" are E5 specifics (rail, Vanir). If they are pasted into prompts they bias the live round. | "Prompts are event-agnostic. The §5.2/5.3 lists are E5 illustrations and must not be copied into prompts." |
| F25 | MINOR | 3,4 | 973; 1001-1003; 1552; 1917 | Enums are undefined: claim `status`, ruling `decision`, run/case completion status, cell status. | Add to §12: `case_status ∈ {COMPLETE, COMPLETE_WITH_REJECTION, INCOMPLETE_BUDGET_LIMIT, INCOMPLETE_AGENT_FAILURE, INCOMPLETE_NO_NEW_EVIDENCE}`; `cell_status ∈ {QUANTIFIED, INSUFFICIENT_EVIDENCE}`; `claim_status ∈ {SUBMITTED, DEFENDED, QUALIFIED, CONCEDED, WITHDRAWN}`. |
| F26 | MINOR | 3,4 | 1017-1041 | There is no trace-event vocabulary, although NFR4 lists 15 loggable actions. The example still uses `event_id` instead of `event_scope`. | List the event types in §12.8 (CASE_CREATED … BRIEFING_GENERATED, plus MEMORY_READ/WRITE, BUDGET_*, SEARCH_*). Fix the example filter to `event_scope`. |
| F27 | MINOR | 3 | 1454-1466; 2454-2458 | `submit_defence` and `concede_claim` have no JSON schema, and the contracts list lacks challenge, defence, exposure-cell, ledger and memory schemas. | Add a §12.6b Defence/Concession JSON (`response_type`, `new_evidence_refs`, `narrowed_claim`) and the missing schema files. |
| F28 | MINOR | 3 | 1454-1470 | Thor and Loki have no tool to read the Case File or the opponent's claims, yet Round 2 needs them. | "The runtime injects the current Case File sections (masked) into every agent call. No read tool is needed." |
| F29 | MINOR | 3,6 | 1445 | `map_question_to_event` is listed as an LLM tool, but the mapping is deterministic. | Move it to the runtime as `trial/event_mapping.py`. Heimdall receives the result. |
| F30 | MINOR | 4,7 | 1571-1572 | 3 agents × 8 searches × 2 runs = 48, above the total of 32, so Run 1 can starve Run 2. Hitting the cap has no defined effect. | "`max_total_searches_per_run: 16`. On the cap, the tool returns `SEARCH_LIMIT_REACHED` and the agent must answer with the evidence it already has." |
| F32 | MINOR | 3 | mmd:54 | The budget can run out mid-round, but the diagram only shows "case cap reached → SUFF". | Label it `BUDGET -->|cap reached at any step| SUFF`. |
| F33 | MINOR | 2 | 438 | ORV-0013 is labelled "Official correction", but it is Raven Wire, Tier 2. | "Wire-service correction (Tier 2)". |
| F34 | MINOR | 2 | 448 | There is no rule for detecting truncation. | "TRUNCATED if the last paragraph lacks terminal punctuation, or if the body is a strict prefix of a same-title twin." |
| F35 | MINOR | 2 | 1378-1400 | Tier source of truth is unstated. Vantro, Corvan, Anchor Marine and Ravik government are not in ATL-0012. | "The manifest `RELIABILITY` is authoritative. ATL-0012 only adds descriptors. An outlet missing from it is flagged `OUTLET_NOT_IN_GUIDE`." |
| F36 | MINOR | 2 | 1800-1810 | The ATL-0007 price bands ($220-320/t wheat) sit below the trade-note implied prices ($350-445/t). | "Never derive value from volume using ATL-0007. Use it only to flag implausible rows." |
| F37 | MINOR | 4 | 1013; 1027; 1662 | Simulated-clock dates (2027-01-25) and wall-clock dates are mixed in `created_at` fields. | "`created_at` is wall-clock UTC. The simulated date lives only in `as_of_date`." |
| F38 | MINOR | 4 | 1047; 2828 | There are two ledger paths (`data/budget-ledger.json` and the run-folder copy). | "The run-folder `budget-ledger.json` is a per-case snapshot of the global ledger." |
| F39 | MINOR | 4,7 | 1532 | "max_runs reached" after Run 1 can never happen when `max_runs` is 2. | Keep it as a guard, but add the comment "reachable only if max_runs=1". |
| F40 | MINOR | 8 | 2194 | The injection scan covers paragraph lines only. Titles and header values are not scanned. | "Scan every text field, including TITLE and header values." |
| F42 | MINOR | 2 | 1162; 436-438 | It is unspecified who builds correction and contradiction relations, and how. | "Ingestion pre-links `SOURCE_TYPE=correction` documents and titles starting 'Correction:'. Heimdall's verification call outputs the final `CORRECTS` and `CONTRADICTS` edges, with citations." |
| F43 | MINOR | 9 | 642-822; 1700-1733; 1890-1902 | The scope implied by the folder tree (~70 modules), the 10-node/10-edge evidence graph and the sensitivity table goes beyond 24 hours. | "24h build: the evidence graph is a `relations` list, and sensitivity is a single deterministic table. The rest of the tree is aspirational." |
| F44 | MINOR | 3 | 2149-2170 vs mmd | The diagram shows no agent-failure path. | Add `THOR -.->|failed| SUFF` and similar edges once the F07 states exist. |


## B. Requirement coverage (check 1)

| Req | Status | Where / gap |
|---|---|---|
| FR1.1 Case File with as-of date | PASS | §3 YAML 84-110; `AS_OF_DATE_RESOLVED` 1499 |
| FR1.2 Gather all formats | PASS | §14.1-14.6 (live-round gaps F02, F17-F19) |
| FR1.3 Verify; reject with reason | ISSUE | Mapping reject at 1351 is fine; "is it real" rule missing (F05) |
| FR1.4 Re-search | PASS | `HEIMDALL_RESEARCHING` targets `evidence_gaps` |
| FR2.1-2.3 Thor | PASS / ISSUE | §5.2, §18; the per-cell high estimate is undefined (F10) |
| FR3.1-3.3 Loki | PASS / ISSUE | §5.3, §18; same gap (F10) |
| FR4.1 Rulings + fact/inference | PASS | 12.7 `claim_kind`; enums missing (F25) |
| FR4.2 E/C/C classification | PASS | 12.7 |
| FR4.3 Sufficiency, says what is missing | PASS / ISSUE | §21 coverage; E5-specific (F12) and may never fire (F08) |
| FR4.4 Briefing from rulings only | PASS | §22 1908 |
| FR5.1 Flow | PASS | §17, mmd |
| FR5.2 Parallel round 1 | PASS | §17; lock serialises only the ledger step |
| FR5.3 Each side attacks one claim | PASS | §18 |
| FR5.4 ≥2 runs, new evidence, hard limits | ISSUE | D1 (section C), F07, F08 |
| FR6 Private lasting memory; share only the Case File | PASS / ISSUE | §19, §3; post-as-of leak (F15) |
| FR7.1 Question box + live feed from documents | ISSUE | No feed endpoint or replay order (F20) |
| FR7.2 Trial view | PASS | Page 3 |
| FR7.3 Exposure low/high per country × sector | ISSUE | Rows hard-coded (F01) |
| FR7.4 Click-through to document / trade row | ISSUE | Fixed-table row locator missing (F03) |
| FR8.1-8.3 Findings, exposure + outlook, citations with timestamps | PASS / ISSUE | §22; number provenance (F16) |
| NFR1 Role, prompt, tools; no planner | PASS | §16, agents/prompts |
| NFR2 Grounding, facts vs inference, off-Runemark | PASS / ISSUE | 363; source rules not deterministic (F13, F14) |
| NFR3 Survive damage; one-side failure; never claim complete | ISSUE | Failure states missing (F07); encodings (F18) |
| NFR4 Log claims, queries, items, memory, rulings | PASS / MINOR | 381-399; event vocabulary (F26) |
| NFR5 Limits on rounds, runs, tool calls, tokens; no repeats | ISSUE | No per-step tool-call cap (F07); tokens bounded via USD + caps (F31) |
| NFR6 Save Case File, as-of, rulings per run | PASS | §36, NFR6 414-426; replay (F21) |
| AC1 Ingest PDF/TXT/DOCX incl. live docs, Case File, trade tables, event real | ISSUE | F02, F03, F04, F05, F19 |
| AC2 Hybrid search, ≥2 metadata filters | PASS | 1323-1340 (as-of + event scope) |
| AC3 Thor and Loki search and submit | PASS | §16, Person 2 exit 2312 |
| AC4 ≥1 cross-examination | PASS | §18 |
| AC5 All claims ruled; ≥1 rejected or conceded | ISSUE | No mechanism (F09) |
| AC6 Briefing E/C/C, exposure bounds, timestamped citations, outlook | PASS / ISSUE | §22; F10, F16 |
| AC7 Dashboard question, feed, trial, exposure, click-through | ISSUE | F01, F20 |
| AC8 Sent back once; Run 2 brings new evidence | ISSUE | F08 + D1 |
| AC9 Lasting memory with a logged changed action | PASS | §19 1681-1697 |
| AC10 Damaged-doc failure handled; limits on rounds/runs/retries | PASS / ISSUE | §25; F07 |
| 3.4 Public repo, README, .env.example | PASS | §31 2601-2609, §27 |
| 3.4 Demo + saved logs of one two-run case | PASS | §36 |
| 3.4 Diagram you can explain | PASS | mmd = md §9 (identical, verified by script) |
| Eval: citation validity | ISSUE | F03, F13 (must cite the new pack) |
| Eval: range accuracy | ISSUE | F10, F11 |
| Eval: calibration | PASS / weak | Odin range from accepted evidence; no width rule |
| Eval: trap handling | ISSUE | F05, F13, F14 |
| Eval: debate quality | PASS | §18; F09 |
| Eval: reliability | ISSUE | F07, F17, F18 |
| Eval: reproducibility | ISSUE | F21 |
| Eval: briefing & UI | PASS / ISSUE | F01, F20 |

## C. D1 replacement text (proposed, not applied)

**Check against AC8 and FR5.4.** D1 is compatible with "a second run must bring new evidence" only if Run 2 must retrieve at least one evidence family that Run 1 did not, counted across all cells. A cell can resolve as INSUFFICIENT_EVIDENCE without that. For E5 this is met naturally: Run 2's targeted maize searches surface families that Run 1 never retrieved (ATL-0010, ORV-0031, ORV-0021 P5). If Run 2 brings no new family, the case can still be COMPLETE for the user, but this case must not be claimed as the AC8 demonstration.

**Replace md 1522-1552** (the state-machine tail plus the `INCOMPLETE_BRIEFING` paragraph) with:

```text
SUFFICIENCY_CHECK
  ├── SUFFICIENT → BRIEFING_GENERATION → COMPLETE
  └── INSUFFICIENT → RESEARCH_REQUESTED   (Odin lists evidence_gaps, ≥2 targeted queries each)
          ↓
     RUN_COUNTER_CHECK / BUDGET_CHECK
     ├── limit or cap reached before Run 2 searches → INCOMPLETE_NO_NEW_EVIDENCE → INCOMPLETE_BRIEFING
     └── within limits
          ↓
RUN_2_STARTED → HEIMDALL_RESEARCHING → ROUND_1_STARTED → ROUND_2_STARTED → ODIN_FINAL_RULING
  ↓
FINAL_SUFFICIENCY_CHECK
  ├── SUFFICIENT → BRIEFING_GENERATION → COMPLETE
  ├── GAPS_SEARCHED_PROPERLY → cells RESOLVED_INSUFFICIENT → BRIEFING_GENERATION → COMPLETE
  └── Run 2 stopped early (budget, limit, agent failure) → INCOMPLETE_NO_NEW_EVIDENCE → INCOMPLETE_BRIEFING
```

"A gap is **searched properly** when every targeted query Odin listed for it was executed in Run 2, within event scope and the as-of gate, and the results were reviewed by Heimdall. Each such query is logged with its result document IDs. A searched-properly gap with no eligible evidence becomes `INSUFFICIENT_EVIDENCE` (low/high null, with the queries attached). It is a resolved finding, not a failure, and the briefing is COMPLETE with the cell flagged.

`INCOMPLETE_NO_NEW_EVIDENCE` is used only when Run 2 stopped before its targeted searches ran (budget cap, run or search limit, wall clock, agent failure). Odin then publishes an `INCOMPLETE_BRIEFING` labelled INCOMPLETE; if no Odin budget remains, it is a template briefing.

Independently of status, the run record stores `run2_new_evidence_families: [ids]`. AC8/FR5.4 are demonstrated only when that list is non-empty. If it is empty, the case may still be COMPLETE, but the UI and trace show 'Run 2 found no new evidence' and the case must not be submitted as the two-run demonstration."

**Replace md 1602** with: "See the FINAL_SUFFICIENCY_CHECK rules above. `INCOMPLETE_NO_NEW_EVIDENCE` means only that Run 2 stopped before its targeted searches ran."

**Replace md 2507 (E2E 9)** with: "9. Run 2 executes every targeted query and `run2_new_evidence_families` is non-empty. Cells still without evidence are `INSUFFICIENT_EVIDENCE` and the case status is COMPLETE."

**Replace md 1856-1861** with fields `"status": "INSUFFICIENT_EVIDENCE"`, `"resolution": "RESOLVED_AFTER_TARGETED_SEARCH"`, `"targeted_queries": [...]`, `"run2_new_evidence_families": [...]`.

**Replace the mmd/md diagram edges** `SUFF -->|run 2 still insufficient or limit reached| INCOMPLETE[...]` with:
`SUFF -->|gaps searched, none found: cell flagged| BRIEF` and `SUFF -->|stopped early on budget or limits| INCOMPLETE[Incomplete briefing<br/>labelled INCOMPLETE]`.

## D. Must fix before coding (BLOCKERs, in order)

1. **F06 Model plan + Odin budget reserve.** This sets every cost number and decides whether a briefing exists when the cap is hit. Freeze it in Phase 0.
2. **F03 Citation locator for fixed tables (`R<n>`).** This is part of the citation contract the validator, API and UI all depend on.
3. **F02 Generic trade-row grammar (currency, scale, unit).** Without it, live non-tonnage packs produce no numbers.
4. **F01 Exposure grid derived from the Case File.** A one-line contract change, but the UI and E2E tests are built on it.

## E. Safe to start the ingestion layer now?

**Yes.** None of the BLOCKERs change the ingestion contract except F02 and F03, which live inside the trade parser and citation resolver. Fold them, plus F17, F18, F19 and F34, into Person 1's work as it is written. Tracks that can start in parallel today:
- **P1 Evidence:** manifest normalisation, extractors, flags, injection scan, dedupe families, trade parsers, BM25 with filters, citation resolver.
- **P2 Runtime:** contracts and enums (F10, F25), AnthropicProvider, budget guard (F06), state machine with failure states (F07), all against `DeterministicMockProvider`. No billable calls yet.
- **P3 UI/API:** FastAPI skeleton with the F20 endpoints serving fixture JSON, plus the single-page UI (grid from the Case File, F01).

Agent prompts and live model calls wait until D1, F05, F08-F10 and F13-F14 are written into the doc.

---

## Appendix: per-check notes

### Check 2: corpus traps (PASS = specific enough to code)

| Trap | Where handled | Status |
|---|---|---|
| ORV-0029/0030 sector mislabel | §15 sector policy 1356; 14.6 step 4 | PASS |
| ORV-0023 empty (twin ORV-0031) | EMPTY_DOCUMENT; family rule 1258 | PASS |
| ORV-0048 cut off (twin ORV-0024) | TRUNCATED_DOCUMENT 448; 1258 | ISSUE: no detection rule (F34) |
| ORV-0007 mixed encoding | 1185-1196 | PASS (BOM-less: F18) |
| ORV-0006/0040 duplicates | 14.5 | PASS |
| ORV-0020 P7 injection | 2190-2199 | PASS (titles: F40) |
| ORV-0014/0036/0041 future-dated | as-of gate 1505; 1323 | PASS |
| ORV-0043/0015 vs ORV-0013/0016 | §8 chain 458-471 | PASS / ISSUE: relation builder (F42), ORV-0013 label (F33), ORV-0003 missing (F14) |
| Tier 4 ORV-0010/0026/0028 | §8 prose only | ISSUE (F14) |
| EVENT_ID NONE documents | Scope 1329 | ISSUE: ORV-0011/0025/0039 citable (F13) |
| Corvan vs Orvan | 1308 | PASS |
| Interested party ORV-0004 | Not handled | ISSUE (F14) |
| Repeated value+volume rows | 14.6 table | PASS |
| ATL-0007 reference prices | Not handled | ISSUE (F36) |
| Baseline (ORV-0012 index vs ORV-0024 ~95%) | 1779 | ISSUE (F11) |
| No Tolan maize / no Vanir→Midgard maize note | §21 1836-1866 | PASS (E5-specific: F12; D1) |
| Sources missing from ATL-0012 | Not handled | ISSUE (F35) |
| Manifest two schemas | Not handled | ISSUE (F17) |
| E5 prose notes vs PS fixed tables | 14.6 | ISSUE (F02, F03, F19) |

### Check 3: file × file

- **mmd vs md §9:** identical (script comparison). 33 nodes, none dangling, subgraph closed.
- **Diagram vs state machine:** the diagram has no agent-failure or wall-clock paths (F07, F44), and budget is drawn only at SUFF (F32). The rest matches.
- **Tools vs schemas:** defence and concession have no schema (F27). Thor and Loki have no read path (F28). `map_question_to_event` has no module (F29). `calculate_exposure(accepted_evidence)` has undefined inputs (F10, F11).
- **API vs UI:** feed, trace, case file, packs and budget have no endpoint (F20). `GET /api/runs/{run_id}` has no response shape. `span_id` ("ORV-0046:P4") repeats the doc ID inside the path (MINOR, part of F26).
- **Field-name drift:** `span_id` (12.5-12.7) vs `paragraph` (12.3 citation); four metric names (F10).

### Check 4: section × section

The numbers that appear more than once agree with each other ($4.00 / $2.50 / $0.50; runs 2; rounds 1; retries 2; wall clock 900). The disagreements and undefined terms are F10, F25, F26, F30, F31, F37, F38 and F39. Top-k (`"limit": 12`) appears only in an example and is not among the hard limits.

### Check 5: live round, a brand-new pack run in my head

These break or degrade, worst first: grid rows (F01); non-tonne units (F02); fixed-table citations and parsing (F03, F19); no ATL reference sheets loaded (F04); E5 baseline months (F11); E5 coverage list (F12); question without a sector (F23); event-mapping threshold (F22); BOM-less encoding (F18); schema variant (F17); E5 arguments in prompts (F24). Cut-off tables and body duplicates are handled (14.5, 14.6).

### Check 6: one full two-run case vs budget

**Prices assumed:** list rates from the Claude API reference, cached 2026-10-06. These are assumptions; verify them before use. Haiku 5.5 is $0.10 in / $0.50 out per million tokens; Sonnet 5.5 is $2 / $10. Adaptive-thinking tokens bill as output; I assumed +50% on visible output.

| Step | Calls | Input tok | Output tok (incl. thinking) |
|---|---|---|---|
| Run 1: Heimdall verify | 1 | 8k | 1.5k |
| Run 1: Thor + Loki query plan + claims | 4 | 28k | 6k |
| Run 1: challenges + defences | 4 | 28k | 6k |
| Run 1: Odin rulings + sufficiency | 1 | 15k | 4.5k |
| Run 2: Heimdall re-search | 1 | 6k | 1.2k |
| Run 2: Thor + Loki | 4 | 28k | 6k |
| Run 2: challenges + defences | 4 | 28k | 6k |
| Run 2: Odin final ruling | 1 | 18k | 4.5k |
| Odin briefing | 1 | 12k | 4.5k |
| **Total** | **21** | **~171k** | **~40k** |

- **All Sonnet 5.5:** ≈ $0.34 + $0.40 = **$0.74 per case. Does not fit the $0.50 cap.** Five cases ≈ $3.70, which exceeds the $2.50 reserve and almost the whole project.
- **F06 plan (Haiku 5.5 for Heimdall, Thor and Loki; Sonnet 5.5 for Odin's 3 calls):** Odin ≈ 45k in / 13.5k out ≈ $0.23; the rest ≈ $0.03. **≈ $0.26 per case. Fits.** Five cases ≈ $1.30, within $2.50.
- **Risk:** if agents run naive tool loops that resend context on every search (8 searches × 3 agents × 2 runs × ~8k), that adds ~384k input: +$0.77 on Sonnet, +$0.04 on Haiku. Use the query-plan pattern (one call proposes queries, the runtime executes them, a second call writes claims), together with F07's per-step caps.
- **Development budget:** $1.50 is about 5 full cases. Use the mock provider and replay (F21) for everything else.

### Check 7: loops × limits

| Loop | Limit | When hit | Status |
|---|---|---|---|
| Runs | max_runs 2 | COMPLETE / INCOMPLETE | PASS |
| Cross-exam rounds | 1 | n/a | PASS |
| Searches | 8 per agent per run, 32 per case | Undefined | ISSUE (F30) |
| Model↔tool turns within an agent step | **None** | n/a | ISSUE (F07) |
| Model retries / output validation | 2 | No FAILED state | ISSUE (F07) |
| Tool retries | 2 | Error result to agent | PASS |
| Wall clock | 900 s | Undefined state | ISSUE (F07) |
| Budget | USD caps | Needs an Odin call to finish | ISSUE (F06) |
| Clarification | None (reject instead) | n/a | PASS (F22 threshold) |
| Ingestion per file | try/except → quarantine | Continue | PASS |
| Identical query | Cache key | Cached result | PASS |

### Check 8: trust × data flow

Raw text goes through extraction, the injection scan (masked for agents, raw kept), the as-of gate, the index, the UNTRUSTED envelope, the agents, then the Case File sections, Odin's rulings and the briefing.

- **Unmasked injection:** closed, except titles and header fields (F40).
- **Post-as-of documents:** closed in the index, but open through memory (F15).
- **Tier 4 or background documents as fact:** open (F13, F14).
- **Uncited numbers:** open (F16).
- **Briefing from rulings only:** stated (1908), but the input set should be pinned: "generator input = ruling ledger + calc records + cited spans; never raw claim or challenge text".
- **Citations resolve in the manifest:** yes for documents; fixed-table rows are open (F03).

### Check 9: 24-hour feasibility (3 people, ~18-20 working hours each)

| # | Task (dependency order) | Owner | h | Cut? |
|---|---|---|---|---|
| 0 | Contracts, enums, Case File JSON, F06 model plan | All | 2 | No |
| 1 | Manifest normalise + hash + extractors (TXT/PDF/DOCX, encodings) | P1 | 4 | No |
| 2 | Flags, injection scan, dedupe families | P1 | 2 | No |
| 3 | Trade parsers (prose + fixed) + damage flags | P1 | 3 | No |
| 4 | BM25 + filters + ranking + cache + citation resolver | P1 | 3 | Local embeddings: cut |
| 5 | Exposure calculator (moved from P2) | P1 | 3 | Sensitivity table: cut to one table |
| 6 | Provider + budget guard + ledger | P2 | 2 | DB reservations: cut |
| 7 | State machine incl. failure states, event mapping | P2 | 3 | No |
| 8 | Four agent prompts + structured outputs + cross-exam | P2 | 6 | No |
| 9 | Odin rulings, sufficiency, coverage matrix | P2 | 3 | No |
| 10 | Memory (lessons + case notes) + replay | P2 | 3 | No |
| 11 | FastAPI endpoints + SSE | P3 | 3 | No |
| 12 | Single-page UI (intake, feed, trial, exposure, briefing, source drawer, trace) | P3 | 8 | Trace filters: minimal |
| 13 | README, .env.example, diagram talk, demo script | P3 | 2 | No |
| 14 | Unseen-pack fixture (F41) + E5 E2E + saved two-run logs | P1+P3 | 4 | No |

No task is multi-day **if** the §10 minimal profile is followed. Postgres, pgvector, Next.js, the full §11 tree, the evidence graph and the three-person plan as written are multi-day, so cut them (F43). Person 2 is the critical path at about 20 hours, which is why the exposure calculator moves to Person 1.

### Check 10: demo × judges

| Demo element | Backed by | Status |
|---|---|---|
| Question box | POST /api/cases | PASS |
| Live feed replayed from corpus | None | ISSUE (F20) |
| Trial view | GET /api/runs/{id} (shape undefined) | ISSUE / MINOR |
| Exposure table, low/high per cell | GET /api/runs/{id}/exposure | ISSUE (F01, F10) |
| Click-through to source | GET /api/sources/{doc}/spans/{span} | PASS (rows: F03) |
| Briefing E/C/C | GET /api/cases/{id}/briefing, §22 | PASS |
| Outlook with assumptions | §22 sections 8-9 | PASS |
| Case File panel, trace viewer, memory change | None / trace only | ISSUE (F20) |
