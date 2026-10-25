# Fix pass 8: housekeeping and Task 1 docs fix

Scope: Part A housekeeping (A1-A3) and the 9 open MAJORs that block agent stages (B1-B9). No LLM or API calls were made, `.env` was not read, and nothing under `dev_pack_E5/` was edited (only `manifest.json` metadata was read, for 4 pub dates). `md` = `docs/SYSTEM_ARCHITECTURE.md`; line numbers are after this pass.

## Verdicts

| Item | Verdict | Evidence | Deviation / note |
|---|---|---|---|
| A1 path fix | FIXED | `tests/test_ingestion_e5.py:16`: `PACK` = `$RAGNAROK_PACK_DIR` if set, else `ROOT / "dev_pack_E5"` (`import os` added at line 2) | A repo-wide grep (excluding `dev_pack_E5/`) found `03_Ragnarok` only in this test. `scripts/ingest_pack.py` has no default pack dir (it is the required `argv[1]`), and its default output `ROOT/data/normalized/<pack>` is already correct, so it was left unchanged. `tools/` has no hits. **Docs: no `03_Ragnarok` mentions remain** in `docs/`. |
| A2 .gitignore | FIXED | `.gitignore` (8 lines, exactly the requested patterns) | No `git init`, commit or push. |
| A3 OD-1 docstrings | FIXED | `backend/ingestion/structure.py:4-6` ("as set by closed decision OD-1"); `backend/provenance/citations.py:3` ("closed decision OD-1") | Wording only. `grep -rn -i "interim\|open decision" backend/` returned nothing once the stale `backend/**/__pycache__` folders were deleted. They still matched because `run_tests.py` does not rewrite bytecode, and they are generated and gitignored. |
| B1 F04 | FIXED (revised in 8b) | Current lines: md 2342 (`pack_paths` in the request), md 2346 (ordered list, base first, `as_of` from the last pack), md 2348-2353 (collision rule), md 2355 (Example (E5)) | **Changed in Pass 8b (manager decision, item 8b-1).** Pass 8 made a collision refuse to start the case, which was a manager error: final-round packs may re-ship reference documents, and no code edits are allowed then. A collision now never stops a case. If the body hashes match, the copies merge into one document (INFO log). If they differ, the live copy wins, the base copy is quarantined, and `INTEGRITY_WARNING` goes into the run record. This is close to the review's original "quarantined" fix, so the row is now FIXED. |
| B2 F07 | DEVIATED (partial) | Hard limits md 1734-1749 (`max_tool_calls_per_agent_step: 6`, `max_model_turns_per_agent_step: 4`, `token_caps_by_role`, `briefing_time_reserve_seconds: 120`); new subsection md 1685-1711 (agent step definition, per-step limits, schema failure = one retry, state table with trigger, next step, run status, briefing and trace event); §25 md 2474 and the paragraph after it point to the states | (1) **Wall clock:** the review said "same as an Odin failure" (template briefing). That conflicts with D1, which lists wall clock as a Run 2 stop that Odin briefs. So the trial stops at `max_wall_clock_seconds - briefing_time_reserve_seconds`, and Odin gets one briefing call in the reserved time, with the template as the fallback. (2) Thor or Loki failure in the final run sets `INCOMPLETE_AGENT_FAILURE`, per NFR3 "partial completion is not successful completion"; a Run 1 failure followed by a clean Run 2 does not. (3) Run 2 precedence keeps D1: a failure before the targeted queries ran gives `INCOMPLETE_NO_NEW_EVIDENCE`. (4) Added a Heimdall-failure sentence (not in F07). (5) The per-role caps include **input** caps (new numbers, see the decisions below). |
| B3 F11 | DEVIATED | md 1999-2017 (event month, post-event months, primary YoY with month pairing, cross-check, 5-row table for agree / disagree / primary only / cross-check only / neither, record fields, Example (E5)); `baseline_basis` and `crosscheck_refs` in the calc record md 2145; claim example assumption md 1003 | Followed this pass's spec (cross-check = pre-event index or "% of normal"), not the review's secondary "mean of pre-event months". When the two disagree, the primary wins as the canonical basis and the range widens to the min/max of two passes, mirroring the repeated-row rule. Added `baseline_crosscheck_tolerance_pct_points` (default 5): a new threshold, so a human must decide it. The E5 "July and August 2026" text was removed, and the E5 claim example's July-August baseline assumption was reworded to match the rule. |
| B4 F12 | FIXED | md 2092-2106: generic coverage table (`direct_flow`, `substitute_flow`, `contract_delay`) over `target_countries x target_sectors`; statuses `COVERED` / `PARTIAL` / `NO_DIRECT_FLOW`; `COVERAGE_TESTED` trace; "Feeds Odin's send-back" md 2102; the E5 cells moved to an Example (E5) line | The sufficiency criteria (a)-(c) are unchanged; `NO_DIRECT_FLOW` maps to (a). |
| B5 F15 | FIXED | md 1868-1870 (fields in the example), md 1873-1882 (field definitions, set by the runtime; as-of hide rule; `MEMORY_HIDDEN` trace), md 1889 (read order) | The hide rule applies to every record (lessons too), not only `case_note`. `written_as_of` is stored for audit only and does not drive the hide. |
| B6 F16 | FIXED | Paragraph contract md 2250-2251 (`calc_refs`, `number_refs`); Number provenance md 2254-2263 (extract, skip list, match rule, on-failure path); citation validation step 5 md 1990; `calc_id` in the calc record md 2134; briefing header "Removed numbers" md 2205 | On failure: one regeneration of the failing paragraphs as an `odin_briefing` call within the remaining reserve (counted as a briefing retry); otherwise the numbers are replaced by "[number removed: no source]" and the paragraph is flagged `UNSOURCED_NUMBER_REMOVED`. |
| B7 F22 | FIXED | md 1445-1457: candidates, score formula, accept rule (`>= 3` and `>= 2x` the runner-up), reject with `NO_MATCH`/`AMBIGUOUS` plus the top 3 candidates and their scores; config keys `event_match_min_score`/`event_match_min_ratio` in the hard limits | Title matches count only documents that passed the as-of gate (mapping runs after `AS_OF_DATE_GATE`). |
| B8 F23 | FIXED | md 1459-1480: precise **manifest scope** definition (scope documents, valid trade rows, route countries, event origins, scope countries and sectors, header fallback), defaulting rules, `max_default_cells`, `NO_SCOPE` rejection, `scope_assumptions` + `SCOPE_DEFAULTED`; Case File field md 107; briefing header md 2204 and "Assumptions and limitations"; "known route countries" replaced in the optional filter | Fallback to manifest `COUNTRY`/`SECTOR` headers when no trade row parses. `max_default_cells` was **removed in Pass 8b** (item 8b-3) and replaced by the cell budget rule. |
| B9 F31 | FIXED | `token_caps_by_role` md 1742-1747 (output: H/T/L 2000, Odin ruling 6000, Odin briefing 6000); worst-case and `briefing_floor` formula md 1764; Budget stop rules md 1779-1789 (role key, startup check, case start, case cap hit, project dev cap hit, project cap hit, briefing refused); §10 reserve paragraph md 658; reserve comment md 1751; ledger fields md 1122, 1132; NFR5 md 421 | Prices are still read from config and still marked unverified; no price was hard-coded. The reserve is protected because only a runtime-tagged `odin_briefing` call may spend `briefing_floor`, and Odin's final ruling may spend only the excess. **Superseded in Pass 8b** (item 8b-2): the reserve is now derived and covers both the final ruling and the briefing. |

Counts (after the Pass 8b revision of B1): **FIXED 10** (A1, A2, A3, B1, B4, B5, B6, B7, B8, B9), **DEVIATED 2** (B2 partial, B3), **PARTIAL 0**.

Line numbers in rows B2-B9 refer to the file after Pass 8; Pass 8b shifted later text. B1 uses current line numbers. `docs/STATUS_PASS8.md` has current line numbers.

## Diagram (F07 → F44)

`docs/architecture.mmd` and the md §9 mermaid block were edited identically: the `RUN → SUFF` label now includes wall clock, and three edges were added (`THOR -.->|failed: Loki unchallenged| ODIN`, `LOKI -.->|failed: Thor unchallenged| ODIN`, `ODIN -.->|failed: template briefing, no model call| INCOMPLETE`; mmd:53, 60-62).

Diff script (scratchpad `diagram_diff.py`, extracts the single ```` ```mermaid ```` block from the md as bytes and compares it with the mmd file):

```text
md block sha256  b26f3edaa96e917a8e3707f9c237ea4044463346d02b8708a01eb07a3668ecb4 3310 bytes
mmd file sha256  b26f3edaa96e917a8e3707f9c237ea4044463346d02b8708a01eb07a3668ecb4 3310 bytes
IDENTICAL
```

F32 (`BUDGET -->|case cap reached| SUFF` label) was not touched and stays open.

## Tests

`python tests/run_tests.py` → **PASSED 53 FAILED 0 SKIPPED 0** (before Part A it errored on the missing pack path). It also gives 53/0/0 with `RAGNAROK_PACK_DIR` set to the pack.

## C2: E5 identifiers in edited text

Every added line containing `ATL-`/`ORV-`/`WLD-`, an E5 country, sector or month sits on or directly under an `Example (E5)` label (md 1455, 1480, 1854, 2017, 2106, 2128, 2283, 2296), or inside the E5 example JSON blocks those labels introduce (memory record, calc record, insufficient-evidence result, create-case request). The memory-record and create-case JSON blocks predate this pass but had no label, so `Example (E5):` was added above each. **No hit falls inside a generic rule.**

## Needs a human decision

1. **Briefing reserve size.** At the configured (unverified) prices, `briefing_floor` = 16,000 input + 6,000 output tokens on the Odin model ≈ $0.092. That leaves only ≈ $0.008 of the $0.10 reserve for Odin's final ruling, so in practice the final ruling is paid from the general pool. Either raise `odin_briefing_reserve_usd` (still inside the $0.50 case cap) or accept this. The startup check refuses to run if the reserve falls below the floor.
2. **New starting values** (all config, not facts): per-role input caps (12k / 12k / 12k / 24k / 16k), `max_default_cells: 4`, `baseline_crosscheck_tolerance_pct_points: 5`, `briefing_time_reserve_seconds: 120`.
3. **Remaining gap, not opened here:** an explicit question with more than 6 cells cannot satisfy "one CELL_ESTIMATE per cell" within `max_claims_per_side_per_round: 6`. `max_default_cells` covers only defaulted scope.
4. The §10 per-case estimate (≈ $0.26) predates the larger output caps. It is an estimate of actual spend and is still marked unverified.

## Stale rows in docs/STATUS_PASS7.md

Not updated in this pass, as instructed. Now stale:

- Rows **F04, F07, F11, F12, F15, F16, F22, F23, F31** (now addressed per the table above) and **F44** (diagram edges now exist).
- The **Counts** table and the **"Open or partial MAJORs by stage"** section (lines 74-85).
- Every md line reference after md line 106, because the text below it shifted. Examples: F03 "md 1867-1874", F21 "md 2190", F28 "md 1550", F32 "md 551", F38 "md 1105, 2989".

---

# Pass 8b: manager decisions on Pass 8 and status refresh

No LLM or API calls; `.env` not read; no git commands; LF line endings kept (0 CR bytes in every edited file). Line numbers are current (`md` = `docs/SYSTEM_ARCHITECTURE.md`).

| Item | Verdict | Evidence | Note |
|---|---|---|---|
| 8b-1 F04 reversal | FIXED | md 2348-2353; B1 row above updated | A collision never stops a case. Same `normalized_body_sha256` → one document (the later pack's copy is kept), `PACK_DOC_ID_DUPLICATE` at INFO. Different body → the live (later) copy is indexed, the base copy is quarantined, and `INTEGRITY_WARNING` (both `raw_file_sha256` and both body hashes) goes into the run record's `integrity_warnings`. Shown in the briefing header (md 2259) and limitations. |
| 8b-2 derived reserve | FIXED | yaml md 1752; formula md 1784-1791; Budget stop rules md 1801-1813 (role key, "which ruling is final", live-case startup check with `htl_minimum_usd`); §10 md 658 | `odin_briefing_reserve_usd = worst_case(odin_ruling) + worst_case(odin_briefing)`, from the role caps and configured prices. **At the current unverified prices: $0.108 + $0.092 = $0.200.** Stated minimum for Heimdall/Thor/Loki: `htl_minimum_usd` = the worst case of one Run 1 with no retries (6 steps x 4 turns x $0.0022 = **$0.0528**). The check passes: $0.200 <= $0.50 - $0.0528 = $0.447. Only Odin's final ruling and the briefing may spend the reserve, and the final ruling cannot touch the briefing's slice. "Live case" = any case that calls a billable provider; mock cases skip the check. |
| 8b-3 cells vs claim cap | FIXED | Key renamed to `max_supporting_claims_per_side_per_round` md 1738; claim rule md 1017; Cell budget rule md 1820-1839; defaulting md 1475; exposure table md 2457-2459; briefing header md 2258 | `CELL_ESTIMATE` claims are outside the cap: exactly one per assessed cell per side. `max_default_cells` is removed, and one rule covers named and defaulted cells. Rank by in-scope trade rows, then event-document mentions (then question order, then alphabetical). Process in batches, project with the guard, and mark cells that don't fit `INCOMPLETE_BUDGET_LIMIT` (Case File `cell_status`, `CELL_BUDGET_PROJECTED` trace, table row "Not assessed: budget limit", briefing header, case labelled INCOMPLETE). A mid-run refusal marks the rest of its batch the same way. **Addition:** `max_cells_per_agent_step: 4` (batching), because "process in that order" needs a mechanism and one Thor/Loki step can't emit unlimited cells within a 2,000-token output cap. At the unverified prices, Run 1 affords about 4 batches (16 cells) at worst case. |
| 8b-4 tunable table | FIXED | Table "Tunable starting values" md 1760-1777; `# TUNABLE, UNVERIFIED` markers in the hard-limits yaml md 1734-1748 | Covers per-step limits, the 120 s briefing time reserve, all per-role token caps, the 5-point baseline tolerance (now also in the yaml, md 1742), event-match thresholds, `max_cells_per_agent_step` and model prices. Derived values (`odin_briefing_reserve_usd`, `htl_minimum_usd`) are listed as not hand-set. |
| 8b-5 STATUS_PASS8 | FIXED | `docs/STATUS_PASS8.md` (new); `docs/STATUS_PASS7.md` untouched | Pass 7 line references were remapped by a `difflib` line map (pass 7 file vs current); rewritten text was re-located by grep. Counts: 22 FIXED / 7 PARTIAL / 15 OPEN (MAJOR: 15 / 4 / 2). Open MAJORs left: F20 (dashboard API), F21 (replay). |
| 8b-6 diagram | FIXED (no change needed) | sha256 below | Items 1-3 did not touch the diagram. `architecture.mmd` is byte-identical to its Pass 8 state, and the md §9 block matches it. |
| 8b-7 verify | FIXED | see below | |

**Diagram check (8b):**

```text
md block sha256  b26f3edaa96e917a8e3707f9c237ea4044463346d02b8708a01eb07a3668ecb4 3310 bytes
mmd file sha256  b26f3edaa96e917a8e3707f9c237ea4044463346d02b8708a01eb07a3668ecb4 3310 bytes
IDENTICAL
```

**Tests:** last line of `python tests/run_tests.py`: `PASSED 53  FAILED 0  SKIPPED 0`

**E5 identifiers in 8b-edited text:** one added line contains E5 terms, md 2459 `Example (E5): the rows are Midgard/Wheat, ...`. It is labelled. It came from moving a pre-existing E5 sentence out of the generic Page 4 rule line. No `ATL-`/`ORV-`/`WLD-` appears in any 8b-added line.

**Pass 8b counts:** FIXED 7 (8b-1 … 8b-7), PARTIAL 0, DEVIATED 0.

## Needs a human decision (replaces the Pass 8 list)

1. Pass 8 item 1 (reserve size) is resolved by the derived reserve. Pass 8 item 3 (more than 6 cells) is resolved by the cell budget rule.
2. **New in 8b:** `max_cells_per_agent_step: 4`, and the batch projection treats every batch as worst case (each of 4 turns at the full input and output cap). That is deliberately conservative, so it may mark cells `INCOMPLETE_BUDGET_LIMIT` that would in fact have fit.
3. Still TUNABLE, UNVERIFIED: every row of the md 1760-1777 table, and all prices. The $0.200 reserve and $0.0528 minimum move with them.
4. B2's wall-clock deviation (a 120 s briefing time reserve instead of an immediate template) is still awaiting explicit approval.