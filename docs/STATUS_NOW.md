# Status now (read-only audit, 2026-10-26)

Zero LLM/API calls. `.env` not read, `runemark_map.png` not opened. Pipeline runs wrote only to the session scratchpad.

## 1. Baseline

| Item | Fact |
|---|---|
| Branch / HEAD | `main` / `823ccc6` "Stage 1-3: heimdall, casefile, agents, memory, runtime, cross-exam, docs pass 8" |
| Last 5 commits | `823ccc6` Stage 1-3, `6c6d061` Revert "Ap", `d2a623d` Ap, `9b28fd7` AP, `d24b43b` Docs pass 6 and 7 |
| `git status --short` | 2 untracked entries only: `server.py`, `web/` (dashboard draft). Everything else is committed (nothing pushed; origin = SutikshanUpman/MPSRC) |
| Tests | `PASSED 164  FAILED 0  SKIPPED 0` |
| Build reports present | `BUILD_STAGE1.md`, `BUILD_STAGE2.md`, `BUILD_STAGE3.md`, `FIX_PASS8.md`, `AUDIT_BASELINE.md`, `CONTRACTS.md`, `STATUS_PASS8.md` (also `FIX_PASS5/6`, `STATUS_PASS7`, `REVIEW_FINAL`). **No `BUILD_STAGE4/5`, no `DASHBOARD.md`** |

Code that exists: Heimdall (`backend/agents/heimdall.py`), Thor/Loki Round 1 (`counsel.py`), Round 2 (`cross_exam.py`), calc tool, private memory (`backend/memory/store.py`), budget guard (`backend/runtime/budget.py`), config, mock provider. **Code that does not exist: Odin (ruling, send-back, briefing), Run 2, live provider calls.** `grep -i odin backend/ server.py scripts/` finds nothing in code, only in memory/budget role names.

## 2. Acceptance criteria

| AC | Verdict | Evidence | Missing |
|---|---|---|---|
| AC1 ingest + Case File + trade tables + event verified | **DONE** | `backend/ingestion/{extractors,pipeline,trade}.py`; `heimdall.py:278-375` (event verification); Case File `backend/casefile/`; `test_ingestion_e5.py`, `test_heimdall_e5.py`; E5 run: `OPEN event=E5 as_of=2027-01-25`, 4 cells | none |
| AC2 hybrid search, >= 2 metadata filters | **PARTIAL** | `backend/search/bm25.py:57,83` filters: countries, max_tier, tiers, source_types (as-of and event are mandatory build-time filters); `agents/tools.py:74` | It is BM25 only. No semantic/vector half, so "hybrid" is not met. Add a cheap dense or fuzzy/TF-IDF second ranker and fuse (RRF), or state the deviation |
| AC3 Thor/Loki evidence-backed claims from own queries | **DONE (mock)** | `counsel.py:279 run_round1`; per-agent `search_log.jsonl`; E5 run: 8 CELL_ESTIMATE claims with citations | Never run with a real model; the mock policy (`mock_policy.py`) is rule-based. Prompts exist (`prompts/thor.md`, `loki.md`) but are untested live |
| AC4 at least one cross-examination | **DONE (mock)** | `cross_exam.py:275 run_round2`; `test_stage3.py`; E5 run: `cross_examination.json`, 5 responses | none for mock |
| AC5 Odin rules on every claim; >= 1 rejected/conceded | **PARTIAL** | Concessions exist: E5 run has 1 `CONCEDE`, 2 `QUALIFY`, 1 `DEFEND` | **Odin does not exist.** No ruling schema code, no rejected claim. `BUILD_STAGE3.md:134`: "Odin rulings arrive in Stage 4" |
| AC6 briefing (Established/Contested/Conceded, low/high exposure, timestamped citations, outlook) | **NOT STARTED** | no `Established`/`Contested` string anywhere in `backend/`; `run_case.py` ends at Round 2 and prints per-cell ranges | Briefing generator, sections, outlook, citation timestamps |
| AC7 dashboard | **PARTIAL** | `server.py` + `web/` (untracked). Section 5 | live feed, click-through to source, Odin/briefing/Run 2 views, exposure table across both runs |
| AC8 Odin sends back once; Run 2 brings new evidence | **NOT STARTED** | `max_runs: 2` in config only; tools carry a `run_number` arg (`tools.py:28`) | Odin send-back decision, Run 2 loop, new-evidence check |
| AC9 private memory + a logged action it changed | **DONE (mock)** | `memory/store.py` (owner-only, as-of hide); `test_stage2.py:291 test_seeded_memory_changes_a_decision`; `counsel.py:133 _log_decisions` writes `DECISION_CHANGED` | In the plain E5 run 0 `DECISION_CHANGED` events (memory starts empty). Odin memory not wired. Needs a real two-case demo (case A writes, case B changes a decision) |
| AC10 damaged doc no crash + hard limits | **DONE** (limits: partly unverifiable live) | `pipeline.py:79,293` `UNREADABLE_FILE`, `test_ingestion_e5.py:40,75`, `test_ingestion_synthetic.py:142`; limits in `config/runtime_config.json` (`max_runs 2`, `max_cross_examination_rounds 1`, searches, retries, wall clock 900 s); `BudgetGuard` | Retries and wall-clock enforcement exist only against the mock; the Run-count and round limits cannot be exercised until Run 2 exists |

## 3. Submission items (PS 3.4)

| Item | Verdict | Evidence |
|---|---|---|
| Public repo | **PARTIAL** | Remote `github.com/SutikshanUpman/MPSRC` exists; visibility not checked; HEAD `823ccc6` is not confirmed pushed |
| README | **PARTIAL** | `README.md` has layout, corpus placing, running. No overview, no architecture link, no demo steps, no two-run instructions |
| `.env.example` | **NOT STARTED** | `.env.example` does not exist (`.gitignore` already allows it via `!.env.example`) |
| Working demo | **PARTIAL** | Mock pipeline works to Round 2; dashboard starts. No Odin/briefing/Run 2; no live path |
| Saved logs of one full two-run case | **NOT STARTED** | `data/runs/` is gitignored and empty; no full case exists |
| Architecture diagram + explanation | **DONE** | `docs/architecture.mmd` (matches the mermaid block in `SYSTEM_ARCHITECTURE.md`), `docs/SYSTEM_ARCHITECTURE.md`. Known diagram nit: F32 label |

## 4. Pipeline check (mock provider, `scripts/run_case.py`)

`run_case.py` flags: `--pack --base --question --provider {mock,anthropic} --config --out --memory-dir --heimdall-only --round1-only`. Stages run: Heimdall, Round 1, Round 2. **Nothing after Round 2.**

| Run | Result |
|---|---|
| E5 sample question, `dev_pack_E5` | Ran to the end of Round 2, exit 0. `OPEN event=E5 as_of=2027-01-25`. Cells: Midgard/Wheat COVERED, Midgard/Maize PARTIAL, Tolan/Wheat COVERED, Tolan/Maize NO_DIRECT_FLOW. Thor and Loki each give 4 estimates (e.g. Midgard/Wheat Thor 57.6..57.7 %, Loki 54.8..57.7 %; Tolan/Maize NO_DOCUMENTED_FLOW). Round 2: 1 CONCEDE, 2 QUALIFY, 1 DEFEND. Writes: `case_file.json`, `claim_ledger.json`, `calc_ledger.json`, `cross_examination.json`, `search_log.jsonl`, `provider_calls.jsonl`, `events.jsonl`. No error. No ruling, briefing, or run 2 file |
| Synthetic pack (`tests/fixtures/synthetic_pack.py`, event E9) with the E5 question | `EVENT_REJECTED` (`REJECTED_NO_MATCH`), correct: wrong question for that pack |
| Same pack, matching question ("Brenn ... Velka canal closure ... LNG") | Ran through Round 2, exit 0. Both sides give `NO_BASELINE` for Brenn/LNG; cell is PARTIAL. No error, but nothing substantive to argue |

First stop in both: the script ends after Round 2 by design (no Odin code). No crash.

## 5. Dashboard

| Question | Answer |
|---|---|
| Starts? | Yes. `python server.py --port 8765` serves `/` and `/api/health` |
| Bind address | **`0.0.0.0` by default** (`server.py:294,313`). Must default to `127.0.0.1` before any commit/demo on a shared network. Pre-existing note in `CLEANUP_REPORT.md` |
| Endpoints | `GET /api/health`, `/api/corpus/stats`, `/api/corpus/docs`, `/api/corpus/doc/<id>`; `POST /api/heimdall/open-case`, `/api/case/run`, `/api/heimdall/test` |
| What it shows | Title "Trial of the Nine Realms". Question box with run button; Heimdall metrics (as-of, cells), question entity resolution, verified citations table, exposure-cells matrix and evidence gaps, Thor vs Loki arguments, a range matrix, "Re-Run Round 1" |
| `/api/case/run` | Runs Heimdall + **Round 1 only** (no Round 2, no Odin), returns the whole result in one response; mock or `anthropic` provider selectable |
| AC7 parts | Question box: **yes**. Live feed: **no** (single blocking POST, no polling/SSE, `events` returned at the end). Trial view: **partial** (Round 1 only). Exposure table: **yes** (Round 1 ranges, no final low/high). Click-through to source: **partial** (corpus doc endpoint exists; not checked that every citation links to it) |

## 6. Budget / live readiness

| Item | State |
|---|---|
| Live provider path | **No.** `backend/llm/provider.py`: `AnthropicProvider.complete` raises `LiveCallsDisabled` ("not wired in Stage 1"). Constructor also needs `live.enabled` and `live.budget_owner` in config. No SDK/HTTP call anywhere |
| Cost ledger | Partial. `BudgetGuard` + `provider_calls.jsonl` (mock) record usage and cost estimates. The architecture's "Stage 5" full ledger is not built |
| Budget guard | **Yes** (`budget.py`): per-case cap 0.50, project cap 4.00, final-round reserve 2.50, `can_afford` checks, covered by `test_provider_budget.py` |
| Odin reserve | **Yes** in logic: `odin_briefing_reserve_usd` derived in `config.py:62`, enforced in `budget.py:27,36-41`. Odin itself absent, so the reserve is protecting nothing yet |
| `.env.example` | **Missing** |
| Prices | **Still UNVERIFIED** (`runtime_config.json`: `prices_usd_per_million_tokens` listed in `_tunable_unverified`; Haiku 0.10/0.50, Sonnet 2.00/10.00; models `claude-haiku-5-5`, `claude-sonnet-5-5`). Verify against the provider price page before the live run; also all token caps are unverified starting values |

## 7. Open findings that affect the final round

Source: `STATUS_PASS8.md`, `BUILD_STAGE1-3.md`, `FIX_PASS8.md`. Cosmetic/doc-only items skipped (F17-F19, F24, F33, F34, F37, F40-F43).

| ID | Item | Why it matters |
|---|---|---|
| F20 (MAJOR, OPEN) | Dashboard API has no `/feed`, `/case-file`, `/trace`, `/api/packs`, `/api/budget` | AC7 live feed |
| F21 (MAJOR, OPEN) | Replay not defined (mock provider with recorded responses; no `REPLAY_DIVERGED`) | Saved logs / reproducible demo |
| F25 (PARTIAL) | `case_status`, `claim_status` enums missing | Odin rulings need them |
| F28 (OPEN) | Thor/Loki have no Case File read path; "runtime injects Case File" rule absent | Live prompts |
| F29 (OPEN) | `map_question_to_event` still described as an LLM tool; code is deterministic | Doc mismatch only if graded on spec |
| F30 (OPEN) | Run 1 can starve Run 2 of searches (`max_total_searches_per_case 32`, 8 per agent per run); no `SEARCH_LIMIT_REACHED` | AC8 |
| F27 (OPEN) | No Defence/Concession JSON schema in the spec (code has it) | Spec consistency |
| F35 (OPEN) | No "manifest RELIABILITY is authoritative" rule | Source ranking in briefing |
| `BUILD_STAGE1` open question | Stance detection is a lexicon; first candidate for a Haiku call if a live/unseen pack misfires | Unseen-pack robustness |
| `FIX_PASS8` | A question with > 6 cells cannot satisfy one CELL_ESTIMATE per cell under `max_claims_per_side_per_round: 6` | Unseen question with many countries/sectors |
| `FIX_PASS8` B2 | Wall-clock deviation still awaits approval | AC10 |
| Observed | Synthetic pack run gives `NO_BASELINE` for both sides; unseen-pack baseline handling is thin | Unseen-pack round |

## 8. Remaining work, ranked (about 3 hours, two people)

Split: **Person A = back end (new files `backend/agents/odin.py`, `backend/runtime/run2.py`, `backend/briefing/`, `scripts/run_case.py`)**; **Person B = UI + live + docs (`server.py`, `web/`, `backend/llm/provider.py`, `.env.example`, `README.md`, `config/runtime_config.json`, `docs/`)**. No shared files except `run_case.py` (A only) and `config/runtime_config.json` (B only; A asks B for new keys).

| # | What | Why (AC/score) | Size | Files | Owner |
|---|---|---|---|---|---|
| 1 | **Odin ruling**: rule on every claim (accept / reject / concede-accepted / needs-evidence), mock responder first, schema per `CONTRACTS.md` md 1037 | AC5, gate for AC6/AC8 | M | `backend/agents/odin.py` (new), `backend/agents/mock_policy.py` (add Odin responder), `tests/test_odin.py` (new) | A |
| 2 | **Send-back + Run 2**: Odin returns the case once with named gaps; Thor/Loki re-run with remaining search budget and must cite new docs; enforce `max_runs` | AC8, AC10 | L | `backend/runtime/run2.py` (new), `backend/agents/counsel.py` (read-only reuse; touch only if needed, A owns it) | A |
| 3 | **Briefing**: Established / Contested / Conceded, low/high per cell, timestamped citations, next-quarter outlook; write `briefing.json` + `.md` | AC6, biggest scoring gap | M | `backend/briefing/` (new), `scripts/run_case.py` (wire Odin, run 2, briefing, outputs) | A |
| 4 | **Live provider**: implement `AnthropicProvider.complete` (SDK, schema-validated JSON output, usage into ledger), `.env` loading by name only, verify prices, set `live.enabled` | Needed to claim real agents (AC3/AC4 with a real model); score for working demo | M | `backend/llm/provider.py`, `config/runtime_config.json`, `.env.example` (new), `tests/test_provider_budget.py` | B |
| 5 | **Dashboard completion**: bind `127.0.0.1`; call the whole pipeline (Round 2, Odin, Run 2, briefing); live feed via polling a `/api/case/<id>/feed` of `events.jsonl`; exposure table with final range; click citation -> doc | AC7 | L | `server.py`, `web/app.js`, `web/index.html`, `web/style.css` | B (after #3 contract is fixed, first against saved JSON) |
| 6 | **Submission set**: README overview + demo steps, `.env.example`, push, check repo is public, one saved two-run case log under a committed `demo_logs/` folder (not gitignored `data/runs/`) | PS 3.4 items; cheap points | S | `README.md`, `.env.example`, `demo_logs/` | B (log after A finishes #3) |
| 7 | **Run the live case once** under the budget guard (E5), keep logs; check cost vs `per_case_cap_usd` | Evidence for the demo and real-model AC3/AC4/AC9 | S-M | none (run only), config values | B, then both |
| 8 | **Hybrid search**: add a second ranker (e.g. TF-IDF/char n-gram or small embedding) and fuse with BM25 | AC2 "hybrid" | M | `backend/search/bm25.py` -> new `backend/search/hybrid.py`, `agents/tools.py` one call site | A if time, else state deviation in README |
| 9 | AC9 demo: two cases on one memory dir showing a logged `DECISION_CHANGED` | AC9 evidence | S | `scripts/` (new `demo_memory.py`) | either |
| 10 | Unseen-pack robustness: baseline handling for `NO_BASELINE`, > 6 cells cap | Unseen final question | M | `heimdall.py`, `counsel.py`, config | A, after #1-3 |

**Safe to skip if time runs out:** #8 (document as deviation), #10, #9 (the existing unit test covers the mechanism), all doc-only findings (F17-F19, F24, F26, F27, F29, F32-F34, F37, F38, F40-F43), F21 replay.

**Do not skip:** #1, #2, #3 (three ACs are NOT STARTED or blocked on them), #4 and #7 (nothing has been run on a real model), #6.
