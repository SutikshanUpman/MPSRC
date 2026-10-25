# Build Stage 3: Stage 2 fixes and cross-examination (round 2)

Scope: Part A (manager decisions on Stage 2) and Part B (round 2: challenges, DEFEND / QUALIFY / CONCEDE, revised ledgers). **Mock provider only: zero live LLM or API calls.** `.env` was not read or printed, no git command was run, nothing under `dev_pack_E5/` was edited, and `runemark_map.png` was never opened. `md` = `docs/SYSTEM_ARCHITECTURE.md`, read by grep and line range only. Prices and caps are config values, TUNABLE and UNVERIFIED.

**Tests:** `python tests/run_tests.py` → `PASSED 164  FAILED 0  SKIPPED 0`. The baseline of 138 is still all passing (some Stage 2 assertions were updated for the new behaviour, listed under A2 and A4). New tests: 24 in `tests/test_stage3.py` and 2 in `tests/test_contracts.py`.

## Step 0: spec sections read

| Topic | Spec location |
|---|---|
| Challenge JSON (`challenge_kind`, `required_response`, `response`) | md 1019-1036 |
| Ruling JSON (Odin, Stage 4) | md 1037 |
| Cross-examination protocol: round 1 independent, round 2 steps, DEFEND / QUALIFY / CONCEDE | md 1848-1863 |
| Concession rule (prompt sentence) | md 1864 |
| Deterministic pre-ruling checks (reason codes used as challenge types) | md 1866-1877 |
| What the record must preserve; "no fake debate" | md 1879-1893 |
| State machine `ROUND_2_STARTED`, `*_CHALLENGED_*`, `*_DEFENDED_OR_CONCEDED` | md 1653-1658 |
| FR2.3 / FR3.3 defence, FR5.3 each side attacks at least one claim | md 299, 307, 324 |
| Tools (`challenge_claim`, `submit_defence`, `concede_claim`), append-only Case File sections | md 1573, md 1590-1600 |
| Round limit `max_cross_examination_rounds: 1` | md 1729 |
| Agent step and retry on schema failure (F07) | md 1685-1711 |
| Evidence family = one source (new-evidence and single-source rules) | md 1327 |
| Search cache (A3), cross-check scope (A1) | md 1540-1563, md 2068-2070 |
| Review gaps closed here: F27 (defence/concession schema), F28 (no read path for round 2) | `docs/REVIEW_FINAL.md` rows F27, F28 |

The spec defines no list of challenge types: the md 1019 example has only `ASSUMPTION_ATTACK`. The set used here is the brief's list, plus `EVIDENCE_MISREAD`, `ASSUMPTION_ATTACK` and `SINGLE_SOURCE` (see B1).

## Part A: Stage 2 fixes

| Item | Verdict | Evidence | Note |
|---|---|---|---|
| A1 cross-check scope | DONE | Spec md 2068 (rule) and md 2070 (E5 example rewritten); code unchanged (`calc.py:172` `find_crosschecks`) | A port-wide index is not a calc cross-check. Agents may cite it as an inference, and Thor does in round 2 (`BASELINE_CHOICE`). The old md 2070 sentence ("the port index … are cross-checks only") contradicted the decision and was replaced. |
| A2 every cell gets a search | DONE | `counsel.py:105` `cell_searched`, `counsel.py:111` `_skip_overrides`; submit backstop in `run_step` (`counsel.py:213`); no-flow citations `mock_policy.py` (`checked`, result set of the cell's search); rule 3 `claims.py:126` `check_claim` | A memory `QUERY_SKIPPED` that would leave a cell without an executed search is overridden: the skipped query runs and `MEMORY_SKIP_OVERRIDDEN` is logged (no `DECISION_CHANGED`). A submit with an unsearched cell is rejected. No-flow estimates now cite the search's full result set, background documents included as context, and the empty-citation exception is gone. Test: `test_a2_memory_cannot_leave_a_cell_unsearched` (Thor seeded with notes for both Tolan/Maize templates: the override fires, "Tolan Maize imports disruption" runs, and the estimate cites its spans). **Changed behaviour:** AC9 case 3 used to show a `QUERY_SKIPPED`; it now shows the override. Case 2's `QUERY_REWRITTEN` remains the AC9 demonstration. |
| A3 cache per agent | DONE | Spec md 1556-1563; `counsel.py:345` `log_shared_queries` (called after round 1 and round 2) | Caches stay per agent. An identical query run by both agents is logged once as `SEARCH_SHARED_QUERY` at INFO, never as an error. It is computed after the fixed-order merge, so it does not depend on order. Test: `test_a3_identical_queries_by_both_agents_are_logged_at_info`. E5: no shared query (the templates differ). |
| A4 adaptive batch | DONE | `cells.py:53` `cell_input_tokens`, `cells.py:59` `resize_batches`; `counsel.py:263` `_resize_batches`; config `batch_input_target_share: 0.8`, `batch_token_estimates` (TUNABLE); calibration hook `budget.py:72-86`, `budget.py:89` | Cells per step = `max_cells_per_agent_step`, reduced when the projected input of a step (fixed prompt + view, plus per-cell row, search, calc-view and turn-output estimates) passes 80% of the role's input cap. `BATCH_RESIZED` is logged with the projections. **E5:** 4 cells → batches [Midgard/Wheat, Tolan/Wheat] (projected 8,455 tokens) and [Midgard/Maize, Tolan/Maize] (6,215), target 9,600. The largest actual call is 10,108 tokens, under the 12,000 cap. Batch 1's last turn measured 9,346 (Thor) and 9,545 (Loki) against the 8,455 projected, so the per-cell constants run 10-13% low; the 20% headroom covered it. Calibration hook: a billable usage record stores `observed_chars_per_token` per model in the guard ledger (`guard.chars_per_token`, `observed_chars_per_token(model)`). Mock calls never do. Not used by any estimate yet (test `test_a4_calibration_hook_records_live_usage_only`). Related fix: `fit_input` now drops the oldest tool results one at a time, and the mock re-fetches dropped search results from its cache. |
| A5 value and volume | DONE | `calc.py:78` `_unit_price`, `calc.py:82` `_flow`; per-scenario `scenario_values` / `scenario_volumes`, `envelope_value` / `envelope_volume` (`calc.py:297`); claim `secondary_metrics` (`schema.py:38`, check `claims.py:197`) | Every calc pass reports value change (currency and %), volume change (unit and %) and implied unit price before and after. Every `ESTIMATED` `CELL_ESTIMATE` carries `secondary_metrics` equal to the calc record's `passes.with_flagged.direct` (a validation rule); other claims carry `null`. **The headline range stays `net_value_shortfall_pct`**: the net shortfall in trade value against the same months one year earlier, in percent (md 2091-2093). The USD and tonne columns below are the same scenario fields in `envelope_value` / `envelope_volume`. |
| A6 Midgard/Maize evidence | DONE (finding: yes) | Classifier fix `heimdall.py:430` `_route_is_cell`, `heimdall.py:435` `_para_items`; test `test_a6_route_note_paragraphs_count_for_their_own_cell_only` | See A6 below. |
| A7 other editors | DONE (report only) | Timestamps | See A7 below. |

### A6 finding

**Yes.** `[ORV-0030, P14]` (Tier 1 trade note "Orvan to Midgard, maize") reads: *"The October volume held up longer than the wheat routes because a share of the maize trade was on delayed delivery terms."* That is delayed-delivery evidence, but Stage 1 coverage marked Midgard/Maize `contract_delay` as missing.

**Why it was missed:** `_para_items` counted a cue paragraph only if the paragraph itself named both the cell's country and its sector. In a route note, only the header ("Route: Orvan to Midgard, maize") names the route; P14 says "maize" but not "Midgard". (`ORV-0029 P14`, "no long-term contract cover", is on the Orvan → Asgard maize note, which feeds no E5 cell.)

**Generic fix:** a paragraph also counts when the document's own parsed route is the cell (route destination = cell country and route sector = cell sector). A mention of another sector inside such a note (P14's "wheat routes") does not make it count for that other cell. The test asserts that no ORV-0030 paragraph appears in Midgard/Wheat.

**New coverage:** Midgard/Maize `contract_delay` passes with `[ORV-0030, P14]`. The status stays `PARTIAL` because no substitute flow is documented. Evidence gaps go from 5 to 4. Midgard/Wheat also gains `[ORV-0027, P14]` from its own Vanir → Midgard wheat note.

**Ranges:** unchanged. The calc reads trade rows only, and those cargoes are already inside the observed post-event rows. Round 2 shows this: Loki challenges Thor's maize estimate with P14, and Thor DEFENDs because the delay is in the same note's observed rows.

### A7 finding

- No file in the tree had a modification time after my Stage 2 report (`docs/BUILD_STAGE2.md`, 2026-10-25 23:28:31) when this stage began (23:35). All 81 files under `dev_pack_E5/` still carry the unpack time, 2026-10-25 16:31.
- Files written 2026-10-25 18:05-18:26, before my Stage 2 session started, were the pre-existing Stage 2 draft. That session already reported them: `tools.py`, `calc.py`, `claims.py`, `counsel.py`, `mock_policy.py`, `memory/store.py`, `contracts.py`, `test_stage2.py`, `prompts/`, `docs/CONTRACTS.md`, and also `docs/FIX_PASS8.md` (18:26).
- **No outside edit is detectable since then.** Timestamps cannot attribute authorship (no git), so this rules out later edits only, not who made the earlier ones.

## Part B: verdicts

| Item | Verdict | Evidence | Note |
|---|---|---|---|
| B1 challenges | DONE (1 addition) | Views `cross_exam.py:60` `challenge_view`; validation `cross_exam.py:105`; schema `schema.py:85`; kinds `schema.py:80`; config `max_challenges_per_side_per_round: 3` (TUNABLE) | Each side gets the other's round-1 ledger through the masked Case File: claims, calc agent views, cited-source metadata. It never gets the other's memory, tools or trace (test `test_round_2_view_never_carries_the_opponents_memory`). This also closes F28 (the runtime injects the Case File). Between 1 and 3 challenges per side, one per target, only on round-1 claims, each with citations the challenger retrieved. **Addition:** `SINGLE_SOURCE` (a claim resting on one evidence family, md 1327) is a lowest-priority fallback the mock uses only when no other rule fires. Without it the synthetic packs, which have no stronger weakness, could not meet "at least one challenge per side". |
| B2 responses | DONE | `cross_exam.py:142` `validate_responses`, `cross_exam.py:224` `_check_revision`; retrieval rounds `tools.py` (`_saw`, `retrieved_in`); schema `schema.py:97` | **DEFEND** needs `new_evidence`: spans retrieved by the responder in round 2 (not via a cache hit of a round-1 search) and not cited in its round 1. **QUALIFY** names a revised claim: `supersedes` = target, a range inside the original, and a round-2 calc if numbers change. **CONCEDE** needs a reason and applies to SUPPORTING claims only. A violation is a failed attempt (F07, `model_loop` `counsel.py:179`). Tests: `test_defend_without_new_evidence_is_rejected` (LOKI_FAILED, challenge left `response: null`), `test_an_estimate_cannot_be_conceded`. |
| B3 revised ledgers | DONE | `cross_exam.py:358` `_apply`; `LEDGER_CLAIM_SCHEMA` `schema.py:75` | Round-2 claims are appended. The target gets `status: superseded` and `superseded_by`; a conceded claim becomes `withdrawn`. Both are kept, each cell keeps exactly one current (`submitted`) estimate per side, and `CLAIM_SUPERSEDED` / `CLAIM_CONCEDED` are logged. |
| B4 mock policy | DONE | `backend/agents/mock_round2.py` (rules in the module docstring; `_pick` :166, `_rebuttal` :377) | Challenges come from checks on the opponent's ledger, in fixed priority. Responses come from whether a rebuttal span exists in the corpus. Nothing is scripted by ID: E5 IDs appear only in tests. Round 2 runs in two phases (challenge, respond), each from one frozen snapshot with buffered per-side traces merged thor-then-loki, so execution order cannot change the output (test: both orders give identical ledgers). |
| B5 prompts | DONE | `prompts/thor.md`, `prompts/loki.md`; `counsel.py:60` `load_prompt(agent, round)` | One file per agent with `<!-- round:1 -->` / `<!-- round:2 -->` sections; the runtime sends only the current round's section, so round-1 input stays inside the cap. The round-2 section covers both steps, the response rules and the concession sentence verbatim (md 1864), with schemas for `turn`, `claim`, `challenge` and `response`. The drift test (`test_round_2_schema_block_matches_the_code`) compares the round-2 block with the code and checks that no E5 name is in either round. |
| B6 runner | DONE | `scripts/run_case.py:57` | Heimdall → round 1 → round 2 (`--round1-only` / `--heimdall-only` stop early). It adds `cross_examination.json`; ledgers and `events.jsonl` are LF. |
| B7 contracts | DONE | `docs/CONTRACTS.md` (status table, claim and calc sections, new "Round 2" section with real E5 examples); `contracts.py` event types; `test_contracts.py` `test_round_2_structures`, `OD1RowChain.test_chain_through_a_revised_claim` | The row chain runs from revised claim `claim-thor-010` through `calc-r1-thor-05` (round 2) to the trade rows: each ref resolves and its bracket validates. New trace events: `ROUND_2_STARTED`, `CHALLENGES_SUBMITTED`, `RESPONSES_SUBMITTED`, `CLAIM_SUPERSEDED`, `CLAIM_CONCEDED`, `ROUND_2_COMPLETED`, `BATCH_RESIZED`, `MEMORY_SKIP_OVERRIDDEN`, `SEARCH_SHARED_QUERY`. |

Counts: **Part A: DONE 7. Part B: DONE 7** (B1 with one addition, `SINGLE_SOURCE`). **PARTIAL 0, DEVIATED 0.**

## E5 per cell: round 1 vs round 2

Net value shortfall over the four paired post-event months (2026-09 to 2026-12, against the same months of 2025). % is the headline metric; USD and tonnes are the same scenario fields in `envelope_value` / `envelope_volume`. "=" means unchanged in round 2.

| Cell | Side | Round 1: % / USD / tonnes (claim, calc) | Round 2 |
|---|---|---|---|
| Midgard / Wheat | Thor | 57.6–60.3 / 206.3M–216.2M / 632,000–649,000 (claim-thor-001, calc-r1-thor-01) | **QUALIFY →** 57.6–57.7 / 206.3M–206.9M / 632,000–633,500 (claim-thor-010, calc-r1-thor-05) |
| | Loki | 54.8–57.7 / 196.5M–206.9M / 615,000–633,500 (claim-loki-001, calc-r1-loki-01) | = |
| Tolan / Wheat | Thor | 55.6–60.3 / 88.5M–96.0M / 281,000–295,000 (claim-thor-002, calc-r1-thor-02) | **QUALIFY →** 55.6–55.8 / 88.5M–88.8M / 281,000–282,000 (claim-thor-011, calc-r1-thor-06) |
| | Loki | 50.8–55.8 / 80.9M–88.8M / 267,000–282,000 (claim-loki-002, calc-r1-loki-02) | = |
| Midgard / Maize | Thor | 38.5–38.5 / 128.7M / 374,000 (claim-thor-006, calc-r1-thor-03) | = (DEFEND) |
| | Loki | 38.5–38.5 / 128.7M / 374,000 (claim-loki-007, calc-r1-loki-03) | = (DEFEND) |
| Tolan / Maize | both | NO_DOCUMENTED_FLOW | = (not challenged) |

Observed direct-route change (`secondary_metrics`, the same on both sides):

| Cell | Value change | Volume change | Unit price before → after (USD/t) |
|---|---|---|---|
| Midgard / Wheat | −216.2M USD (−60.3%) | −649,000 t (−65.2%) | 360.10 → 410.69 |
| Tolan / Wheat | −96.0M USD (−60.3%) | −295,000 t (−64.8%) | 349.89 → 395.00 |
| Midgard / Maize | −128.7M USD (−38.5%) | −374,000 t (−42.5%) | 380.00 → 406.52 |

Volume fell further than value on every cell because the implied unit price rose. Thor's revised ranges are still not below Loki's.

## E5 challenges and responses

| Challenge | Kind | Target | Why it was raised (rule) | Response | Why (rule) |
|---|---|---|---|---|---|
| challenge-thor-001 | INTERESTED_PARTY | claim-loki-006 (SUPPORTING, Tolan/Wheat: quote of ORV-0042, a company statement) | Every citation is a `company_statement` | **CONCEDE** (withdrawn) | Loki's corroboration search found no independent Tier 1-2 span |
| challenge-thor-002 | BASELINE_CHOICE | claim-loki-007 (Midgard/Maize estimate) | ORV-0012 (Tier 1 port index, normal 100) reads 40, 38, 32 for Sep-Nov; every reading implies a loss above Loki's high of 38.5% + 5. Cited as inference (A1) | **DEFEND**, new evidence `[ORV-0012, P7]` | The index's own document says it "covers all grain loaded at the port, not only the routes covered by the monthly trade notes" (scope caveat, not cited in round 1) |
| challenge-loki-001 | ASSUMPTION_ATTACK | claim-thor-001 (Midgard/Wheat) | Thor's high is `no_credit` although its own calc shows substitute value +15.6% (`[ORV-0027, P5]`) | **QUALIFY** → claim-thor-010 | Thor found no new Tier 1-2 span limiting the credited substitute (see below) |
| challenge-loki-002 | ASSUMPTION_ATTACK | claim-thor-002 (Tolan/Wheat) | Same rule, substitute +18.1% (`[ORV-0044, P5]`) | **QUALIFY** → claim-thor-011 | Same |
| challenge-loki-003 | ASSUMPTION_ATTACK | claim-thor-006 (Midgard/Maize) | No substitute flow, but a Tier 1 span documents delayed-delivery terms (`[ORV-0030, P14]`, the A6 find) | **DEFEND**, new evidence `[ORV-0030, P14]` | The paragraph is in the same note as Thor's direct rows, so the delayed cargoes are already in the observed flow |

**Natural QUALIFY and CONCEDE: yes** (2 QUALIFY, 1 CONCEDE). The concession meets AC5 "at least one claim conceded" without scripting.

**Why Thor raised no ASSUMPTION_ATTACK on Loki's full-credit wheat estimates.** Thor's search found limiting evidence, but it is all about the Ravik rail link: ORV-0017 P7 and ORV-0024 P5 ("capacity is limited"). None of those spans names the cell country or Vanir, the substitute origin Loki credits, so the rule does not apply rail limits to the Vanir route. ORV-0024 P6 names Vanir, Midgard and Tolan ("the amounts are small compared with Orvan's sea trade") but carries no substitute-mechanism cue. The same search ran again when Thor responded and was served from the cache (round-2 `cache_hits: 1`): no search was executed twice.

## Mock tokens and shadow cost per side (E5)

Tokens are estimated at 4 characters per token; prices are the configured, UNVERIFIED `claude-haiku-5-5` rates. The mock is billed $0.

| Side | Round 1: calls / in / out / USD | Round 2: calls / in / out / USD | Total USD |
|---|---|---|---|
| Thor | 6 / 33,981 / 3,016 / $0.0049 | 6 / 51,324 / 2,036 / $0.0062 | $0.0111 |
| Loki | 6 / 35,023 / 2,874 / $0.0049 | 4 / 27,832 / 817 / $0.0032 | $0.0081 |

There are 22 model calls in the case (Heimdall: 0). Round 1 now has two steps per side because of the A4 batching.

## Checks

- **E5 identifiers in non-test code:** none added (`backend/`, `scripts/`, `config/`, `prompts/`). The only hits are pre-existing docstring examples (`bm25.py:5-6, 24`, `trade.py:332`).
- **No network imports** were added. `AnthropicProvider` still raises; the calibration test uses an in-process fake provider.
- **LF:** 0 CR bytes in all 68 repo text files outside `dev_pack_E5/` (Python byte check).
- **Determinism:** two mock runs and both execution orders give identical claim, calc and cross-examination ledgers. The runner's `claim_ledger.json`, `calc_ledger.json`, `cross_examination.json` and `search_log.jsonl` are byte-identical across runs.

## Needs a human decision

1. **Round-2 budget projection.** The cell budget rule projects one step per side per round per batch (`2 rounds × 4 turns`). Round 2 is in fact two steps per side (challenge, respond), run once over the whole ledger after every batch. The guard still checks every call, so the cap is safe, but the projection undercounts round 2 by one step per side. Options: project round 2 separately before it starts, or count it as 3 steps.
2. **QUALIFY target scenario.** The mock narrows to `half_credit` on both bounds (Thor: 57.6–60.3 → 57.6–57.7). The ranges become almost points. A real model may narrow less, but the rule "a QUALIFY range lies inside the original" allows this. Should a QUALIFY keep a minimum width, or move only the challenged bound?
3. **`SINGLE_SOURCE` challenge kind** (B1): accept it as a spec challenge type, or require a stronger weakness even when none exists? Without it, a clean ledger cannot satisfy "each side challenges at least one claim".
4. **Per-cell token estimates** (`batch_token_estimates`, TUNABLE) ran 10-13% low on E5. Raise them, or replace them with the calibration ratio once live usage exists.
5. Still open: all prices and caps are UNVERIFIED; Odin rulings (and with them the pre-ruling checks of md 1866) arrive in Stage 4.
