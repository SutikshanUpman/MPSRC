# Baseline audit: 4 external review points against the current repo

Each check was run against the repo as it stands after Stage 1. The Stage 2 brief (Thor, Loki, memory) was interrupted before any change, so nothing from it exists. No LLM or API calls were made, `.env` was not read, no git commands were run, and the corpus was only read (hash check). `md` = `docs/SYSTEM_ARCHITECTURE.md`.

**Tests:** before the audit `PASSED 89  FAILED 0  SKIPPED 0`; after it `PASSED 97  FAILED 0  SKIPPED 0` (8 new tests in `tests/test_contracts.py`).

| Check | Found | Evidence | Action taken | Verdict after |
|---|---|---|---|---|
| R1a one corpus copy | EXISTS-OK | `find` over the whole outer folder: the only `manifest.json` / `hashes.sha256` are in `dev_pack_E5/` | none | OK |
| R1b `03_Ragnarok` | EXISTS-OK | `grep -rn "03_Ragnarok"` (excluding `dev_pack_E5/`): one hit, `docs/FIX_PASS8.md:9`, which is the Pass 8 report describing the old fix. None in code, tests or scripts; `tests/test_ingestion_e5.py:16` uses `RAGNAROK_PACK_DIR`, else `ROOT/dev_pack_E5` | none (the report is history) | OK |
| R1c `.gitignore` | EXISTS-BROKEN | `data/memory/` missing; the other 9 required lines were present | added `data/memory/` (`.gitignore:10`) | FIXED |
| R1d `__pycache__` / `*.pyc` | EXISTS-BROKEN | 11 `__pycache__` dirs and 38 `.pyc` files outside `dev_pack_E5/` | deleted all; deleted again after the final test run (0 left) | FIXED |
| R1e `README.md` | MISSING | no file at repo root | created `README.md`: purpose (3 lines), layout with both docs folders, corpus placement, run commands, mock-by-default and never commit `.env`. No key, prices or E5 answers | FIXED |
| R1f corpus hashes | EXISTS-OK | `sha256sum -c hashes.sha256` inside `dev_pack_E5/` (read-only): 76 listed, 76 OK, 0 mismatches | none | OK |
| R2 F04 | EXISTS-OK | `FIX_PASS8.md` B1 FIXED (revised in 8b); md 2342 (`pack_paths`), md 2348 (collision rule) | none | OK |
| R2 F07 | EXISTS-OK | B2 DEVIATED (partial); md 1734 (per-step limits), md 1685, 1706-1709 (failure states) | none | OK |
| R2 F11 | EXISTS-OK | B3 DEVIATED; md 2056 (primary YoY), md 2065 ("Neither" row) | none | OK |
| R2 F12 | EXISTS-OK | B4 FIXED; md 2144 (per-cell coverage test), md 2154 (feeds Odin) | none | OK |
| R2 F15 | EXISTS-OK | B5 FIXED; md 1920 (`max_source_pub_date`), md 1934 (as-of hide rule) | none | OK |
| R2 F16 | EXISTS-OK | B6 FIXED; md 2305 (`number_refs`), md 2308 (number provenance) | none | OK |
| R2 F22 | EXISTS-OK | B7 FIXED; md 1452 (accept rule), md 1453 (reject with top 3) | none | OK |
| R2 F23 | EXISTS-OK | B8 FIXED; md 1461 (manifest scope), md 107 and 1478 (`scope_assumptions`) | none | OK |
| R2 F31 | EXISTS-OK | B9 FIXED; md 1743 (`token_caps_by_role`), md 1787 (derived reserve), md 1801 (budget stop rules) | none | OK |
| R3a "interim" / "open decision" | EXISTS-OK | `grep -rn -i "interim\|open decision" backend/` → no output | none | OK |
| R3b `citations.py` wording | EXISTS-BROKEN (wording) | The validator is right: `LOCATOR_RE` (`citations.py:12`) rejects any non-`P<n>` locator, as OD-1 intends. But the docstring said table IDs and row numbers "stay internal", which contradicts OD-1 point 2 (md 2028): the row is named in words in the sentence. No "untraceable" or "deferred" wording found | docstring reworded (`citations.py:1-9`): never inside the bracket, named in words, traceable through `row_refs`. No logic change | FIXED |
| R3c row-ref chain | EXISTS-BROKEN (partial) | Trade rows carry `source_doc_id`, `paragraph`, `table_id`, `native_row_number`, `row_key`, `raw_text`, `citation` (`trade.py:163-171`, `:398`, `:407`, `:491`, `:499`). The only Case File row reference (coverage evidence, `heimdall.py:412`) carried `doc_id` + citation + `row_key` but not `table_id` / `native_row_number` / `paragraph`. `calc_id` inputs and claims don't exist (Stage 2 not built) | coverage trade-row evidence now carries `paragraph`, `source_layout`, `table_id`, `native_row_number` (`heimdall.py:412-416`); chain written up in `docs/CONTRACTS.md` (OD-1 row-reference chain) | FIXED for the built links; calc → claim → briefing → source-span API → UI marked TODO in `CONTRACTS.md` |
| R3d chain test | MISSING | no test | `tests/test_contracts.py` `OD1RowChain`. E5 prose row (ORV-0009, 2026-07): ingestion → Case File row ref → the bracket validates, and the ref resolves to the exact row text inside P2. Synthetic tables: SYN-0002 (row numbers, no table ID) through the Case File; SYN-0001 T-0077 row 5 at the ingestion → citation level (that doc is hash-mismatch-quarantined from cases); the table ID never appears in the bracket | FIXED |
| R4a no UI code | EXISTS-OK | `find` for `*.html`, `*.js`, `*.ts(x)`, `*.jsx`, `*.css`, `*.vue`, `package.json` outside `dev_pack_E5/`: none | none | OK |
| R4b `docs/CONTRACTS.md` | MISSING | no contracts doc; only the Case File had a schema (`casefile/schema.py:33`) | wrote `docs/CONTRACTS.md` and `backend/contracts.py` (trade row, row ref, provider call, budget entry, trace event + per-type payload keys, search log entry; Case File parts reuse `CASE_FILE_SCHEMA`). Each has a file:line and a real, shortened mock-E5 example | DEVIATED (partial): calc record, claim / CELL_ESTIMATE and memory entry were listed as existing but don't exist yet (Stage 2 interrupted), so they are marked PENDING (Stage 2) with spec refs, as are cross-exam, rulings, briefing and source-span API (Stage 3/4) |
| R4c contract test | MISSING | none | `tests/test_contracts.py` `ContractsOnMockE5Run`: validates the mock E5 `case_file.json`, every `events.jsonl` line, every E5 and synthetic trade row, the row refs, and the provider and budget records. It also fails if the Case File field list or event-type list in `CONTRACTS.md` drifts from the code | FIXED |

## Totals

22 checks: **14 already OK** (R1a, R1b, R1f, all 9 R2 items, R3a, R4a), **8 fixed now** (R1c, R1d, R1e, R3b, R3c, R3d, R4b, R4c). **Still open:** the Stage 2 links of the row-ref chain (`calc_id` inputs, claims) and the Stage 3/4 structures, all tracked as PENDING/TODO in `docs/CONTRACTS.md`.

## Verify

- Tests: `PASSED 97  FAILED 0  SKIPPED 0` (89 before; the count did not drop).
- Line endings: a byte-level Python check of 54 repo text files outside `dev_pack_E5/` found 0 CR bytes.
- `__pycache__` / `*.pyc`: 0 left after the final cleanup.

## Needs a human decision

1. **Tables without a `TABLE_ID` header.** Example: synthetic SYN-0002, a table inside `[P2]`. Its rows get `table_id: null` but keep their row numbers. OD-1 says the sentence names the row "using the table's own table ID", so such a row has nothing to name. Proposal: name it by position, e.g. "the table in P2, row 1", and allow `row_refs.table_id: null` in that case. Not changed in this pass because it touches closed decision OD-1.
2. **Stage 2 resumption.** The interrupted Stage 2 brief also contained Stage 1 fixes (spec sync, hash mismatch moved into `case_scope()`, cross-pack dedupe, a verification fallback), and none of it was applied. Say whether to resume that brief as written.
