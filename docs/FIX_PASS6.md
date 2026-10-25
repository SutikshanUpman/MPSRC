# Fix pass 6: verdicts

**Scope:** four items requested after pass 5: D1, OD-1 quotes, the repeated-row rule, and the §14.5 wording.
**Files edited:** `docs/SYSTEM_ARCHITECTURE.md`, `docs/architecture.mmd`, `backend/ingestion/trade.py`, `backend/ingestion/pipeline.py`, `tests/test_ingestion_e5.py`, `tests/test_ingestion_synthetic.py`, `tests/fixtures/synthetic_pack.py`. The corpus was not touched.
**Method:** grep plus line-range reads, plain edits, PS text read with the local PDF extractor. No LLM calls.

Line numbers are for `SYSTEM_ARCHITECTURE.md` after this pass unless a file is named. Pass 7 inserted lines, so pass-6 numbers after md 1867 may be off by a few lines; `docs/STATUS_PASS7.md` has current numbers.

## Summary

| Item | Verdict | Evidence |
|---|---|---|
| 1. D1 | FIXED | md 1627-1643, 1651, 1702, 1996-2007, 2078-2080, 2101, 2326, 2475, 2664; md 554-555 = mmd 57-58 |
| 2. OD-1 PS quotes | FIXED; **OD-1 CLOSED in pass 7** | This file, section OD-1; decision at md 1867-1874 |
| 3. Repeated rows | DEVIATED (adds a case (d)) | md 1353-1366, 2052-2063; `trade.py:46-50`, `trade.py:169`, `trade.py:459`, `trade.py:487`, `trade.py:495`; `pipeline.py:232`, `pipeline.py:298`; tests below |
| 4. §14.5 wording | FIXED | md 1319 |

**Tests:** `python tests/run_tests.py` → 53 passed, 0 failed, 0 skipped.

## 1. D1: insufficient cells after a proper Run 2 search

**Verdict: FIXED.** The review's Section C replacement text is applied.

- **State machine** (md 1627-1637). `RUN_COUNTER_CHECK / BUDGET_CHECK` ends in `INCOMPLETE_NO_NEW_EVIDENCE` only if a limit or cap is hit before the Run 2 searches. `FINAL_SUFFICIENCY_CHECK` now has three exits: `SUFFICIENT`, `GAPS_SEARCHED_PROPERLY → cells RESOLVED_INSUFFICIENT → COMPLETE`, and "Run 2 stopped early → `INCOMPLETE_NO_NEW_EVIDENCE`".
- **"Searched properly"** (md 1639) uses the review's wording: every targeted query Odin listed was run in Run 2, inside event scope and the as-of gate, and Heimdall reviewed the results; each query is logged with its result document IDs. Odin sends the case back once.
- **INCOMPLETE only for early stops** (md 1641, 1702, 2326): `INCOMPLETE_NO_NEW_EVIDENCE` is used only when Run 2 stopped before its targeted searches ran (budget, run or search limit, wall clock, agent failure).
- **AC8 kept** (md 1643, 1651, 2475, 2664): `run2_new_evidence_families` is always recorded. E2E 9 requires it to be non-empty, so AC8 is still demonstrated by Run 2 bringing at least one new family overall. A case with an empty list may be COMPLETE but must not be submitted as the two-run demonstration.
- **Cell record** (md 1996-2007): `resolution: RESOLVED_AFTER_TARGETED_SEARCH`, `targeted_queries`, `run2_new_evidence_families`; the old `new_evidence_found_in_run_2` field is gone.
- **Briefing format** (md 2078-2080, 2101): the header carries COMPLETE or INCOMPLETE (INCOMPLETE only for early stops), the list of flagged cells, and the "Run 2 found no new evidence" notice; the exposure table shows "Insufficient evidence" with the queries, never zero.
- **Diagram** (md 554-555, mmd 57-58): the edge `SUFF -->|run 2 still insufficient or limit reached| INCOMPLETE` is replaced by `SUFF -->|gaps searched, none found: cell flagged| BRIEF` and `SUFF -->|stopped early on budget or limits| INCOMPLETE[Incomplete briefing<br/>labelled INCOMPLETE]`. The md diagram and `architecture.mmd` were compared by script after the edit and are **identical**.

One addition to the review text: the run record stores the stop reason, `INCOMPLETE_BUDGET_LIMIT` when the budget guard stopped Run 2, so the budget state from pass 5 (F06) still has a place.

## OD-1: what the PS says about citing table rows

**Status: CLOSED (decided by the user, pass 7).** `[DOC_ID, P#, timestamp]` is the only bracketed citation format. A table row is named in plain words in the sentence right before the citation ("Table T2, row 5"), and the dashboard click-through highlights that row. Tables without `[Pn]` keep the `SYNTHETIC_PARAGRAPH` numbering. Applied in `SYSTEM_ARCHITECTURE.md` (decision OD-1 at md 1867-1874; 14.6 at md 1345; validator md 1884; paragraph contract `row_refs` md 2121; source-span API md 2171-2174; dashboard Page 5 md 2268) and in the diagram's source-viewer node (md 575 = mmd 78). The quotes and reading below are kept as the record of why.

### Verbatim quotes

Page numbers are the PDF's physical pages (6 in total). Line breaks and hyphen splits from PDF extraction were joined; the words are unchanged.

| # | Page | Section | Quote |
|---|---|---|---|
| Q1 | 5 | §4.2 Format and Access, "Trade table layout" | "Every trade table file starts with a short header (table ID, country pair, sector, unit, period, event ID). Then comes one line of column names, then one row per month. The row number is the first column. A trade row is identified by its table ID and row number. Citations and click-through use these IDs." |
| Q2 | 5 | §4.2 Format and Access | "Every document has a permanent ID. Citations and click-through use these IDs." |
| Q3 | 5 | §4.2 Format and Access | "The organizers check every citation in a briefing against the manifest." |
| Q4 | 3 | §3.1 Functional Requirements, FR8 | "FR8.3 (Citations): Inline citations with Runemark document IDs and timestamps, and a source list." |
| Q5 | 2 | §3.1 Functional Requirements, FR7 | "FR7.4 (Click-through): A click from any claim to the Runemark document or trade table row behind it." |
| Q6 | 3 | §3.2 Non-Functional Requirements, NFR2 | "Every citation must resolve to a real document in Runemark. Sources from outside Runemark must be labelled as off-Runemark." |
| Q7 | 4 | §3.3 Minimum Acceptance Criteria, item 6 | "The briefing separates Established, Contested and Conceded, and has an exposure table with low and high bounds, citations with timestamps, and an outlook with assumptions." |
| Q8 | 6 | §5 How Submissions Are Evaluated, "Citation validity" | "the share of citations that resolve to real documents in the manifest. Briefings that cite nothing from the final round packs are penalized." |

The PS never uses the strings `[Pn]`, `P#` or "paragraph". The paragraph-level requirement comes from the dev-pack README ("inline paragraph-level citations"), not from the PS.

### Reading

- **What the validator checks.** Q3, Q6 and Q8 are the only statements about checking. All three check citations against the **manifest** and count citations that "resolve to real documents". The manifest lists documents, not rows or paragraphs, so the stated check works at document level: the `DOC_ID` must exist in the manifest (and, from the simulated-clock rule, be dated on or before the as-of date). Nothing in the PS says the organisers check a paragraph or row locator.
- **What a citation must contain.** Q4 and Q7 require document IDs and timestamps. Q1 adds that for trade rows, "citations and click-through use" the table ID and row number. Q1 is the only text that ties a citation to a row, and it names table ID + row number as the identifiers, not a paragraph.
- **Is the table ID a manifest ID?** The PS does not say whether the table ID in the table header is the same string as the file's manifest `DOC_ID`. E5 has no fixed-layout table, so this cannot be checked before the final round. If they differ, a citation that uses only the table ID would not "resolve to a real document in the manifest" (Q6, Q8).
- **Click-through.** Q5 needs a click to reach the row. That is a UI requirement and is already met by the source drawer, which shows the table ID and `native_row_number`.
- **Conflict.** Q1 says row citations use table ID + row number; the project rule says the bracketed citation is only `[DOC_ID, P#, timestamp]`. A row in a table without `[Pn]` has no real `P#`.

### Recommendation

Keep `[DOC_ID, P#, timestamp]` as the only bracketed format (option A, the current interim), and **put the table ID and row number in the sentence text right before the bracket**, for example: "Velka→Brenn LNG fell to EUR 31.0M in December (table T-0077, row 6) [SYN-0001, P1, 2031-01-15 09:00]."

- The bracket always carries a manifest `DOC_ID` and a timestamp, which is what Q3, Q4, Q6, Q7 and Q8 check and score.
- The row identifiers from Q1 are still visible in every row citation, so a reader or judge can find the row, and Q5 is met by the drawer.
- The citation parser and validator stay unchanged.

Revisit when the first final-round pack is opened: if its table ID equals the manifest `DOC_ID` and the tables carry `[Pn]` labels, nothing changes; if the tables have no `[Pn]` and the OC's examples cite rows directly, option B (a row locator) may score better and needs your decision.

## 3. Repeated rows

**Verdict: DEVIATED.** The rule is changed as asked, but the E5 data needs a fourth case: ten of the 14 flagged rows fit none of (a), (b) or (c).

### New rule (docs)

md 1357-1366 (§14.6) and md 2052-2063 (§21 "Repeated-row sensitivity"): a repeated row is flagged, kept visible to agents with its flag, and used. Exposure is computed twice, with and without the flagged rows. The reported low is the lower of the two lows and the reported high is the higher of the two highs, so the difference widens the range. The record stores both results and `repeat_sensitivity_pct`. Rows flagged missing, bad-number, invalid or truncated are still excluded from both passes. This fits PS §4.5 (page 5): "Systems must report these rows and must not use them silently". The rows are used, but never silently.

| Case | Definition | Use |
|---|---|---|
| (a) | Same month and year twice inside one document | Both kept; second row key gets `#n`; "with" pass counts a month once (or tries each copy if numbers differ), "without" pass leaves the month out |
| (b) | Same value and volume in a different year | "With" uses both; "without" drops both |
| (c) | Same route, month, value and volume in two documents | Counted once, never summed; same family = one source, different families = corroboration; no flag |
| (d) | Same value and volume in two different months of the same year, inside one document | As (b) |

### Ingestion changes (flags unchanged)

- `trade.py:46-50`: `TRADE_ROW_REPEATED_VALUES` and `TRADE_ROW_DUPLICATE` moved out of `BLOCKING_FLAGS` into `SENSITIVITY_FLAGS`. Repeated rows now have `usable_for_arithmetic: true` and `sensitivity_row: true`.
- `trade.py:169`, `trade.py:459`: new fields `sensitivity_row`, `repeat_cases`, `repeat_months`, `cross_doc_matches`; case labels a/b/d per document.
- `trade.py:487`: a repeated month (case a) keeps both rows addressable with a `#n` row-key suffix.
- `pipeline.py:232`, `pipeline.py:298`: case (c) is detected across documents and recorded in `cross_doc_matches` with `same_family`. **No new flag is added.**
- Tests: `tests/test_ingestion_e5.py:191` (all 14 E5 rows usable, sensitivity-marked, case counts); `tests/test_ingestion_synthetic.py:142` (broken rows still excluded, repeated rows kept), `:161` (case a), `:168` (case c). The synthetic fixture gained a same-month repeat (`synthetic_pack.py:104`) and a shared trade sentence in the TXT/DOCX duplicate pair (`synthetic_pack.py:62`).

### The 14 E5 flagged rows

All 14 carry only `TRADE_ROW_REPEATED_VALUES`. No E5 row has a repeated month (case a), and no row is repeated in another document (case c).

| # | Row key | Para | Value / volume | Repeats | Case |
|---|---|---|---|---|---|
| 1 | ORV-0019\|2026-10 | P5 | USD 36.4M / 91,000 t | 2026-11 | (d) |
| 2 | ORV-0019\|2026-11 | P6 | USD 36.4M / 91,000 t | 2026-10 | (d) |
| 3 | ORV-0019\|2025-07 | P8 | USD 42.8M / 107,000 t | 2025-09 | (d) |
| 4 | ORV-0019\|2025-09 | P10 | USD 42.8M / 107,000 t | 2025-07 | (d) |
| 5 | ORV-0019\|2025-10 | P11 | USD 39.6M / 99,000 t | 2025-11 | (d) |
| 6 | ORV-0019\|2025-11 | P12 | USD 39.6M / 99,000 t | 2025-10 | (d) |
| 7 | ORV-0027\|2026-09 | P4 | USD 31.5M / 84,000 t | 2025-07 | (b) |
| 8 | ORV-0027\|2025-07 | P8 | USD 31.5M / 84,000 t | 2026-09 | (b) |
| 9 | ORV-0029\|2026-07 | P2 | USD 72.9M / 187,000 t | 2026-08 | (d) |
| 10 | ORV-0029\|2026-08 | P3 | USD 72.9M / 187,000 t | 2026-07 | (d) |
| 11 | ORV-0029\|2026-11 | P6 | USD 32.5M / 73,000 t | 2026-12 | (d) |
| 12 | ORV-0029\|2026-12 | P7 | USD 32.5M / 73,000 t | 2026-11 | (d) |
| 13 | ORV-0044\|2026-09 | P4 | USD 21.1M / 57,000 t | 2025-07 | (b) |
| 14 | ORV-0044\|2025-07 | P8 | USD 21.1M / 57,000 t | 2026-09 | (b) |

Routes: ORV-0019 Orvan→Asgard wheat; ORV-0027 Vanir→Midgard wheat; ORV-0029 Orvan→Asgard maize; ORV-0044 Vanir→Tolan wheat.

## 4. §14.5 wording

**Verdict: FIXED.** md 1319: `ORV-0007`/`ORV-0047` were removed from the damaged/clean twin examples. The sentence now says that once `ORV-0007` is decoded, the two bodies are identical, so body-hash dedupe puts them in one family exactly like `ORV-0006`/`ORV-0040`. This matches the ingestion output: both records have the same `body_hash` and carry `CONTENT_HASH_DUPLICATE`.
