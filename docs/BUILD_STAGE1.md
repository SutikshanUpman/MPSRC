# Build Stage 1: provider boundary, Heimdall and the Case File

Scope: Stage 1 of the build. Mock provider only: **zero live LLM or API calls**, no API client imported anywhere, `.env` not read, no git commands. Stdlib only, so no new dependency. `md` = `docs/SYSTEM_ARCHITECTURE.md`.

**Tests:** `python tests/run_tests.py` → `PASSED 89  FAILED 0  SKIPPED 0` (the 53 earlier tests plus 36 new ones).

## Step 0: spec sections read

| Topic | Spec location |
|---|---|
| Heimdall role, inputs/outputs, required and forbidden behaviour | md 148-194 |
| Verification rule and premise check | md 182-186 |
| Case File schema, `exposure_cells` | md 76-122 (`exposure_cells` md 95) |
| E5 traps and the expected verification chain | md 443-486 |
| Model boundary, `DeterministicMockProvider` | md 629-641 |
| Model plan, unverified prices | md 643-663 |
| Normalised document JSON (`relations`) | md 885-930 |
| Trace-event JSON | md 1080 |
| Content dedup (`normalized_body_sha256`) | md 1310 |
| Metadata filters, background-only rule | md 1409-1436 |
| Event mapping (F22) | md 1438-1457 |
| Default scope / manifest scope (F23) | md 1459-1480 |
| Sector trap policy, ranking | md 1482-1528 |
| Source rules (supersede = rule 3), edge types `CORRECTS` / `RETRACTS` (F33) | md 1530-1538, md 1990-2003 |
| Heimdall tools | md 1577-1588 |
| As-of resolution | md 1635 |
| Run record fields (`stop_reason`, `run2_new_evidence_families`) | md 1681-1683 |
| Hard limits, per-role caps | md 1725-1758 |
| Tunable values table | md 1760-1777 |
| Budget guard, derived `odin_briefing_reserve_usd` | md 1781-1797 |
| Budget stop rules, cell budget rule | md 1801-1839 |
| Citation format / validation | md 2005, md 2034 |
| Coverage test (F12) | md 2144-2158 |
| `pack_paths`, collision rule (F04) | md 2330-2355 |
| Hash mismatch = quarantined | md 2508 |

Existing APIs reused, not duplicated: `ingest_pack`, `case_scope`, `Corpus` (`backend/ingestion/pipeline.py:23, 263, 306`); `CaseIndex.search_docs`, `mentions`, `tokenize` (`backend/search/bm25.py:19-133`); `format_citation`, `validate_citation`, `parse_citations` (`backend/provenance/citations.py`); `parse_month` (`backend/ingestion/trade.py:90`). Agents see only masked text (`text_masked`, `agent_title`), as `agent_view` does.

## Which steps use the LLM

**None in Stage 1.** Every Heimdall step has a deterministic rule in the spec, or one I wrote here: the mapping score, the Tier 1-2 verification rule, source rule 3 (supersede), the premise-word list, coverage checks, and cell ranking. That keeps the cost at $0 and the output byte-for-byte reproducible.

The one fuzzy step is **stance detection**: does a document assert or deny the event? It uses a generic cue lexicon. It is the first candidate for a Haiku call through `BudgetGuard.call` if live packs show it misfiring (see the open questions). The provider and guard path is built and tested so that call can be added without new plumbing.

## Files built

| File | What |
|---|---|
| `config/runtime_config.json` | The md §17 config block as JSON, every TUNABLE, UNVERIFIED key in one place (`_tunable_unverified`); `live.enabled=false`, `live.budget_owner=""` |
| `backend/runtime/config.py` | Loader; derives `odin_briefing_reserve_usd` and `htl_minimum_usd`; live-case startup check; rejects a hand-set reserve |
| `backend/llm/provider.py` | `Provider`, `DeterministicMockProvider` (call log), `AnthropicProvider` (raises), mini JSON-schema validator |
| `backend/runtime/budget.py` | `BudgetGuard`: usage recording, next-batch projection, reserve protection, `call()` wrapper |
| `backend/runtime/cells.py` | Cell ranking, batching, re-projection before each batch, `INCOMPLETE_BUDGET_LIMIT` marking |
| `backend/runtime/trace.py` | Append-only JSONL trace |
| `backend/ingestion/packs.py` | `load_packs(pack_paths)`: merge + Pass 8b collision rule |
| `backend/casefile/schema.py`, `model.py` | Case File JSON schema, build, validate on write, serialise, `stable_json` |
| `backend/agents/heimdall.py` | Heimdall steps a-h and `open_case` |
| `scripts/run_case.py` | Runner → `data/runs/<case_id>/case_file.json` + `events.jsonl` |
| `tests/test_heimdall_e5.py`, `tests/test_heimdall_synthetic.py`, `tests/test_provider_budget.py` | 36 new tests (picked up by `run_tests.py` discovery) |
| `tests/fixtures/synthetic_pack.py` | Extended with `build_live()`: event E10, re-shipped identical SYN-0014, re-shipped changed SYN-0004 |
| `.gitignore` | Added `data/runs/` |

## Spec → code map

| Spec | Code |
|---|---|
| Config block, derived reserve, live-case check (md 1725-1813) | `backend/runtime/config.py:55-80`; `config/runtime_config.json` |
| Model boundary (md 629-641) | `backend/llm/provider.py:99-165` |
| Budget guard, reserve slices (md 1781-1813) | `backend/runtime/budget.py:35-94` |
| Cell budget rule (md 1820-1839) + manager's next-batch decision | `backend/runtime/cells.py:13-50`; `heimdall.py:473` (`cell_plan`) |
| As-of from the question, manifest fallback (md 1635) | `heimdall.py:101` (`parse_as_of`), `open_case` |
| Countries and sectors from manifest values (no fixed list) | `heimdall.py:117` (`vocabulary`) |
| Event mapping (md 1438-1457) | `heimdall.py:162` (`map_event`) |
| Manifest scope + defaults + assumptions (md 1459-1480) | `heimdall.py:195` (`manifest_scope`), `heimdall.py:225` (`resolve_targets`) |
| `pack_paths` + collision rule (md 2342-2353) | `backend/ingestion/packs.py:23` |
| Hash mismatch quarantined (md 2508) | `heimdall.py:524` |
| Verification rule, corrections, supersede (md 182-186, 1530-1538) | `heimdall.py:278` (`stance_of`), `heimdall.py:318` (`verify_event`) |
| Premise check (md 186) | `heimdall.py:377` (`premise_check`) |
| Coverage test + evidence gaps (md 2144-2158) | `heimdall.py:428` (`coverage_test`), `evidence_gaps` |
| Initial evidence packet | `heimdall.py:490` (`evidence_packet`), rationale `heimdall.py:73` |
| Case File (md 76-122) | `backend/casefile/schema.py`, `backend/casefile/model.py` |
| Run record (md 1681-1683) | `heimdall.py:539` (`run_status[0]`: `stop_reason`, `integrity_warnings`, `pack_merges`, `quarantined_documents`, `llm_calls`) |

## Verdicts

| Item | Verdict | Evidence | Note |
|---|---|---|---|
| 1 Provider | DONE | `provider.py:112-165`; tests `test_provider_budget.py` (`Providers`) | The mock gives the same output for the same input, and every call is logged (role, model, input hash, token estimates; optional JSONL). The model for each role comes from config. `AnthropicProvider` raises `LiveCallsDisabled` unless `live.enabled` is true and `live.budget_owner` is non-empty. Even then, `complete()` raises in Stage 1: the live call arrives with the full ledger (Stage 5). No test sets the flags, and a test asserts `anthropic` is never imported. |
| 2 Config | DEVIATED (format only) | `config/runtime_config.json`, `config.py:91` | JSON instead of the spec's YAML, because stdlib has no YAML parser and no dependency was approved. Keys and values mirror md 1725-1777. The reserve is derived: **$0.108 + $0.092 = $0.200**; `htl_minimum_usd` = **$0.0528**; live-case check passes (tested). |
| 3 Budget (minimal) | DEVIATED (manager decision) | `budget.py:55-69`, `cells.py:30` | Projection = spend so far + worst case of the **next batch only**, re-projected after every batch, as the manager decided. Spec md 1826-1832 still describes a once-per-run projection, so the spec text needs updating. The reserve is protected: other roles stop at cap − reserve; the final ruling cannot touch the briefing's slice (tested). The persisted ledger and project-headroom commits are Stage 5. |
| 4a Parse question | DONE | `heimdall.py:101, 117, 135` | As-of in ISO, "25 January 2027" or "January 25, 2027" forms. Names come only from manifest `COUNTRY`/`SECTOR` values and trade rows (word-boundary match). |
| 4b Event mapping | DONE | `heimdall.py:162` | Accept only if top ≥ 3 and ≥ 2x runner-up. Otherwise `event_mapping.decision = REJECTED_AMBIGUOUS_EVENT` (or `REJECTED_NO_MATCH`) with the top 3 candidates, and the case gets `status: EVENT_REJECTED`. |
| 4c Scope + cells | DEVIATED (event origins) | `heimdall.py:195-250`, `cells.py` | Defaults, assumptions, ranking and batching follow the spec. **Deviation:** md 1466 defines event origins as "every origin in the scope trade rows". That would make a substitute route (an E5 example: Vanir) an event origin and break the direct/substitute split. Origins are instead the scope-row origins named in the manifest event name, falling back to the origin with the most rows. This needs a spec update. |
| 4d `pack_paths` | DONE | `packs.py:23` | Same body hash → merged (INFO `PACK_DOC_ID_DUPLICATE`). Different body → the later (live) copy is indexed, the earlier copy is quarantined, and `INTEGRITY_WARNING` (both raw and body hashes) goes into `run_status[0].integrity_warnings`. The case always starts. |
| 4e Event verification | DONE (heuristic, see the open questions) | `heimdall.py:278-375` | Only case-event documents (never `NONE`) in the as-of gate, excluding company statements (source rule 2). Stance comes from generic cue words in sentences naming a subject term, with negation ("not renewed") and counterfactual ("had expected") handling and a margin of at least 2. A correction corrects its own outlet's earlier report; any later Tier 1-2 opposite-stance document supersedes (rule 3). Citations are one per evidence family, via `format_citation`. |
| 4f Premise check | DONE | `heimdall.py:377` | Premise words (destroyed, sunk, closed, banned, blocked, famine) must appear, un-negated, in a current Tier 1-2 sentence. Otherwise `REJECTED_PREMISE` with citations (the established event plus any low-tier claims), and the case continues. The status name follows this stage's brief; spec md 186 says `premise_check: REJECTED`. |
| 4g Coverage | DONE | `heimdall.py:428-470` | `direct_flow` / `substitute_flow` / `contract_delay` → `COVERED` / `PARTIAL` / `NO_DIRECT_FLOW`. Each failed check becomes an evidence gap with 2 queries. |
| 4h Evidence packet | DONE | `heimdall.py:73, 490` | One generic query and top-k = 3 per cell (`evidence_packet_top_k_per_cell`, TUNABLE), collapsed by family, masked text only. It is narrow on purpose: nothing targets substitute, contract or delay evidence, so Run 2's targeted gap queries can bring new families (AC8). `families_seen` is recorded so Run 2 can compute `run2_new_evidence_families`. |
| 5 Case File | DONE | `casefile/schema.py`, `model.py:42-63` | Spec field names kept, Heimdall outputs added; `additionalProperties: false`. Validated on every write. Every doc-derived item must carry `doc_id` and a citation matching `[DOC_ID, P#, timestamp]`. Volatile fields are only `case_id` and `created_at`. |
| 6 Runner | DONE | `scripts/run_case.py` | `--pack`, `--base`, `--question`, `--provider mock`; writes `case_file.json` and `events.jsonl` (LF). |
| Tests | DONE | 3 new files, 36 tests | All the requested cases, plus guard, re-projection and hash-mismatch tests. |
| Grep checks | DONE | see below | |

Counts: **DONE 10, DEVIATED 3** (2, 3, 4c), **PARTIAL 0**, out of 13 build items. The tests and grep checks are also done.

## Grep checks

- No `ATL-`/`ORV-`/`WLD-` IDs, E5 country or sector names, or E5 months in any new non-test code (`backend/`, `scripts/`, `config/`). The only hits under `backend/` are pre-existing: docstring examples in `backend/search/bm25.py:5-6, 24` (`Orvan`/`Corvan`), a period example in `backend/ingestion/trade.py:332`, and the generic month-name table at `trade.py:24-27`. None is used as data.
- No import of `anthropic`, `requests`, `httpx`, `urllib`, `http.client` or `socket` in `backend/`, `scripts/` or `tests/`. `AnthropicProvider` raises in its constructor and has no client code. Two tests assert `"anthropic" not in sys.modules`.

## Line endings (correction to Pass 8)

A byte-level check (Python, counting `\r` bytes) found CRLF in `tests/test_ingestion_e5.py`, `backend/ingestion/structure.py` and `backend/provenance/citations.py`. These are the three files the Pass 8 Part A script rewrote with `write_text`, which writes CRLF on this Windows Python. The Pass 8 LF check used `grep $'\r'`, which is unreliable in this shell and missed them. All three were converted to LF in this stage. All 49 repo text files now have 0 CR bytes (checked with Python), and the tests still give 89/0/0.

## E5 Case File summary (sample question, mock provider)

- **Event:** E5 "Orvan grain corridor collapse", accepted (score 13, single candidate). As-of 2027-01-25, from the question. Orvan was excluded from the targets as the event origin.
- **Cells (rank order):** Midgard/Wheat, Tolan/Wheat, Midgard/Maize, Tolan/Maize. All are in batch 1 and `PENDING`; the first batch is affordable (worst case $0.0352 against a $0.30 general pool).
- **Verification:** `VERIFIED`, citing `[ORV-0016, P6, 2026-09-10 17:45]` (Tier 1), `[ORV-0013, P2, 2026-09-10 09:10]` (Tier 2) and `[ORV-0034, P1, 2026-09-11 06:20]` (Tier 2).
- **Correction map:** ORV-0043 is corrected by ORV-0013. ORV-0003, ORV-0049 and ORV-0015 are superseded. This matches the chain in md 470-486 with no document ID in code.
- **Premise:** `NO_PREMISE_WORDS`.

| Cell | Coverage | direct | substitute | contract/delay |
|---|---|---|---|---|
| Midgard / Wheat | COVERED | ORV-0009 | ORV-0027 | ORV-0034, ORV-0007, ORV-0047, ORV-0027 |
| Midgard / Maize | PARTIAL | ORV-0030 | none | none |
| Tolan / Wheat | COVERED | ORV-0046 | ORV-0044 | ORV-0007, ORV-0047 |
| Tolan / Maize | NO_DIRECT_FLOW | none | none | none |

There are 5 evidence gaps (Midgard/Maize: substitute, contract; Tolan/Maize: all three), each with 2 queries. The evidence packet holds 12 hits across 9 evidence families.

## Open questions (need a human decision)

1. **Event-origin definition (spec md 1466).** Adopt "origins named in the manifest event name, fallback: the origin with the most rows" in the spec? The current spec wording breaks the direct/substitute split.
2. **Cell projection text (spec md 1826-1832).** Update it to the manager's next-batch-only rule, which the code now follows.
3. **Stance lexicon vs LLM.** Verification uses a deterministic cue lexicon. It is correct on E5 and the synthetic packs, but it needed two generic guards tuned on E5 (counterfactual "had expected", margin ≥ 2). A live pack with unusual phrasing could misread a document. Should a Haiku stance call be added later as a fallback for documents the lexicon scores NEUTRAL? At Haiku's worst case that is about $0.0022 per call (unverified price).
4. **Hash-mismatch quarantine.** Heimdall now enforces md 2508: documents flagged `HASH_MISMATCH` are excluded from the case unless listed in `allow_hash_mismatch_doc_ids`. Ingestion and search alone still return them. Confirm that this is the intended policy.
5. **Cross-pack evidence families.** These are computed per pack, so the same body under different IDs in two packs counts as two families. Same-ID duplicates are merged.
6. **Premise status name.** `REJECTED_PREMISE` (this brief) or `REJECTED` (spec md 186)? Pick one and align the spec.
