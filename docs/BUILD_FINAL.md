# Final build report (session A)

Scope: all phases. Phase 5 (dashboard) was originally session B's; it was not delivered, so it was built in this final pass (`server.py`, `web/`, `docs/DASHBOARD.md`). Phase 8 is design only. **No model call has been made by the build itself**; `.env` was never read or created; no key is in any file. Everything below ran on the mock, replay or stubbed-transport providers.

Test line: see the end of this file (`python tests/run_tests.py`).

## Phases

| Phase | Verdict | Evidence |
|---|---|---|
| 1.1 Odin: pre-ruling checks, rulings, mock + live | DONE | `backend/agents/odin.py:83` `pre_ruling`, `:129` `rule_claims`, `:225` `model_pass` (model only on open claims; guards on its rationale), mock `mock_policy.py` `odin_policy`; tests `OdinPreRulingChecks`, `OdinModelAndFallbacks` |
| 1.2 Odin range per cell (accepted estimates + calc records, value and volume, widening only where flagged, no number for no-flow cells) | DONE | `odin.py:289` `cell_results`; `E5EndToEnd.test_ac6...`, `test_odin_never_puts_a_number...` |
| 1.3 Send-back once, Run 2, `run2_new_evidence_families` | DONE | `backend/runtime/run2.py:33` `sufficiency`, `:58` `heimdall_research`, `:183` `run_second_run`; E5 run: 2 new families, recorded honestly (`run2_no_evidence_reason` is set when empty); `test_ac8...` |
| 1.4 Briefing from rulings only | DONE | `backend/briefing/__init__.py:110` `build`, `:278` `gate`, `:366` `render_markdown`; `briefing.json` + `briefing.md` |
| 1.5 `run_case.py` runs the whole case; `--demo` | DONE | `scripts/run_case.py`; writes `data/runs/demo_E5/` and `demo_E5_memory/` |
| 1.6 Tests: E5 end to end, Tolan/Maize, synthetic, determinism | DONE | `tests/test_final.py` `E5EndToEnd`, `SyntheticEndToEnd` |
| 1.7 `prompts/odin.md`, schema drift test, contracts | DONE | `prompts/odin.md`, `prompts/odin_briefing.md`; `OdinPromptAndContracts`; `docs/CONTRACTS.md` "Final build"; `backend/contracts.py` |
| 2 Guardrails (2.1-2.9) | DONE | `backend/guards/__init__.py`; wired into `claims.check_claim` (every Thor/Loki claim, Round 1, Round 2 revisions, Run 2), `odin.model_pass`, `briefing.gate`; `GuardsRejectBadOutput` (one negative test per guard) |
| 3.1 Live provider (urllib, key from env at call time, three gates) | DONE, **never executed** | `backend/llm/provider.py:193` `AnthropicProvider`; `LiveProviderAndLedger`, `LiveTransportFallbacks` (stubbed transport) |
| 3.2 Record-everything + replay at $0 | DONE | `provider.py:270` `RecordingProvider`, `:319` `ReplayProvider`; `test_determinism_and_replay_at_zero_dollars` (byte-identical case file, ledgers, rulings, briefing) |
| 3.3 Project ledger | DONE | `backend/runtime/ledger.py`; dev ceiling 1.50, `--final-round` 4.00; spend in `run_record.json` |
| 3.4 `export_logs.py`, committed `logs/` | DONE | `scripts/export_logs.py`; `logs/case_*` (mock two-run cases; **replace with the live case after the budget owner's run**) |
| 3.5 `.env.example`, `prices_verified: false` | DONE | `.env.example`, `config/runtime_config.json` |
| 3.6 `live_check.py` | DONE | `scripts/live_check.py` (no call, no key read) |
| 4.1-4.7 Fallbacks | DONE (4.5 and 4.6 see notes) | table below |
| 5 Dashboard (5.1-5.5) | DONE, then rebuilt on AdverSI's console | `server.py` (127.0.0.1, `web/` only, traversal refused, mock/replay only), `backend/runtime/trial_view.py`, `ui/` + `web/` (AdverSI's React console, renamed to the problem statement, see `docs/MERGE_ADVERSI.md`), `docs/DASHBOARD.md`, `docs/screenshots/`, `tests/test_server.py` |
| 6.1 Demo data + memory demo | DONE | `--demo`; `MemoryAcrossCases` shows a verified `DECISION_CHANGED` in a second case |
| 6.2 `export_logs.py` on the two-run case; synthetic end to end | DONE | `logs/`, `SyntheticEndToEnd` |
| 7.1 Trap Report | DONE | `backend/briefing/trap_report.py:13`; `trap_report.json` (12 trap types, from the corpus, Case File and trace; no pack-specific code) |
| 7.2 "Why this number" | DONE | `trap_report.py:75` `calc_explain` (in every calc record of `calc_ledger.json`) |
| 7.3 Calibration note per cell | DONE | `briefing/__init__.py:70` `calibration` (structured) and `calibration_sentence` |
| 7.4 Reproducibility proof | DONE | `run_record.json` `input_hashes` (pack manifests and hash lists, config, every prompt); replay reproduces the briefing hash |
| 8 External lookup | DESIGN ONLY | `docs/EXTERNAL_LOOKUP.md` |

## Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 ingest PDF/TXT/DOCX, Case File, trade tables, event verified | DONE | `backend/ingestion/`, `heimdall.py`; `test_ingestion_*`, `test_heimdall_*` |
| AC2 hybrid search with >= 2 metadata filters | DONE as designed | local BM25 + mandatory as-of and event-scope filters + country, tier, source-type filters, sector boost (`backend/search/bm25.py:57,83`); there is no vector half by design (README, "Design choices") |
| AC3 Thor and Loki submit evidence-backed claims from their own queries | DONE (mock) | `counsel.py`, `search_log.jsonl`; **not yet exercised on a real model** |
| AC4 at least one cross-examination | DONE (mock) | `cross_exam.py`; E5: 5 challenges (1 CONCEDE, 2 QUALIFY, 2 DEFEND) |
| AC5 Odin rules on every claim; >= 1 rejected or conceded | DONE | `rulings.json`: one ruling per claim; E5 has a CONCEDED/REJECTED ruling from a real concession (`test_ac5...`) and pre-ruling rejections are covered by `OdinPreRulingChecks` |
| AC6 briefing: Established/Contested/Conceded, exposure, timestamped citations, outlook | DONE | `briefing.md`; `test_ac6...` |
| AC7 dashboard: question box, live feed, trial view, exposure table, click-through | DONE | `docs/DASHBOARD.md`; screenshots in `docs/screenshots/`; `tests/test_server.py` |
| AC8 Odin sends the case back once; Run 2 brings new evidence | DONE | `E5EndToEnd.test_ac8...` (run_status[1], `run2_new_evidence_families` non-empty on E5) |
| AC9 private lasting memory + a logged action it changed | DONE | `backend/memory/store.py`; `MemoryAcrossCases` (second case, `DECISION_CHANGED`, `verified: true`) |
| AC10 damaged document handled + hard limits | DONE | `trap_report.json` `DAMAGED_DOCUMENT`; `max_runs 2`, one cross-exam round, search/tool/turn/retry caps, wall-clock config, per-case and project caps (`config/runtime_config.json`, `budget.py`, `ledger.py`) |

## Guardrails (`backend/guards/`)

| Guard | What it rejects |
|---|---|
| `schema_guard` (2.1) | non-JSON or schema-breaking output, unknown fields (`additionalProperties: false`); temperature 0 on the live path |
| `citation_guard` (2.2) | a citation that does not resolve, is out of case scope, is dated after the as-of date or was not retrieved by the author |
| `quote_guard` (2.3) | quoted text that is not an exact (whitespace-normalised) substring of a cited masked span |
| `number_guard`, `range_guard` (2.4) | a number with no calc field or cited span, low > high, a wrong unit; agents never do arithmetic |
| `entity_guard` (2.5) | a capitalised name that is neither in the Case File nor in the cited spans |
| `injection_guard` (2.6) | masked document text reappearing, instruction-like text in an output |
| `abstain_guard` (2.7) | a range on a NO_DOCUMENTED_FLOW / NO_BASELINE / MIXED_UNITS cell |
| briefing gate (2.8) | failing paragraphs are removed and listed under "Removed by validator"; the header counts removed numbers |

## Fallbacks (each is a `FALLBACK_*` event in `events.jsonl`)

| Case | Behaviour | Test |
|---|---|---|
| 4.1 live call error or timeout | backoff, at most 2 retries (`FALLBACK_LLM_RETRY`), then the agent is failed (F07), the case goes on | `LiveTransportFallbacks` |
| 4.2 invalid JSON | one repair (`FALLBACK_JSON_REPAIR`), then a schema failure and retry | `test_invalid_json_gets_one_repair_attempt` |
| 4.3 Odin failure or reserve exhausted | deterministic rules (`FALLBACK_ODIN_RULES`), template briefing (`FALLBACK_BRIEFING_TEMPLATE`), both labelled in the header | `OdinModelAndFallbacks` |
| 4.4 budget cap hit | trial stops, Odin briefs from what exists, `INCOMPLETE_BUDGET_LIMIT`, briefing INCOMPLETE | `test_a_cap_too_small...` |
| 4.5 event verification inconclusive | existing stance fallback; if it fails the case ends as `EVENT_UNVERIFIED` with a briefing that carries no exposure numbers (`FALLBACK_EVENT_UNVERIFIED`). **Deviation:** the agents do not run on an unverified event, because Heimdall's Case File schema has no unverified-but-open state | `test_event_verification_inconclusive...` |
| 4.6 trade table unparsed | cells use other evidence (existing behaviour); the table is listed with `FALLBACK_TRADE_TABLE_UNPARSED`. No synthetic pack triggers `TRADE_TABLE_UNPARSED`, so only the generic path is exercised | code path only |
| 4.7 unknown pack layout | ingested with flags, never a crash; missing `hashes.sha256` gives `HASH_NOT_LISTED` | `test_missing_hashes_file_is_ingested_with_flags` |

## Novelty

Trap Report, "Why this number" (`calc_explain`), per-cell calibration, reproducibility proof (hashed inputs and replay), record/replay at $0, project ledger with a development ceiling, one negative test per guardrail.

## Not done / limits

- The live provider and the agents' real prompts have not run against the real API. The budget owner's one live run is the first real test.
- Prices are unverified; `prices_verified` is `false`, so the provider refuses to start.
- Run 2's Heimdall re-search is lexical and text-based; on a different pack it may legitimately find nothing (the record then says why).
- 4.5 deviation and 4.6 coverage above.
- The dashboard's live feed replays a finished case's event log; a run started from the page finishes in about a second, so there is no mid-run streaming.

## Exact test line

`python tests/run_tests.py` -> `PASSED 224  FAILED 0  SKIPPED 0` (baseline before this build: `PASSED 164  FAILED 0  SKIPPED 0`).

Note: the Trap Report lists tier-4 claims only when an agent cites one; the mock agents never do, so `TIER_4_REJECTED` is 0 on E5 (the rule itself is tested in `OdinPreRulingChecks.test_tier_4_only`).

## Update: real providers, mock removed from the product

- The rule-based stand-ins for the agents (and the deterministic provider) moved from `backend/` to `tests/fakes/`; the CLI, the console and the README no longer offer a mock. The test suite still uses them, because it must run without a model.
- New providers (stdlib `urllib`): `OllamaProvider` (native `/api/chat`, JSON schema as `format`, `num_ctx`, free), `AnthropicProvider` (as before). `backend/llm/factory.py` turns `{provider, model, odin_model, base_url}` into a configured run; `tests/test_providers_real.py` exercises all three against a local stub HTTP server.
- The console and `scripts/run_case.py --provider ollama|anthropic|replay --model ...` start runs on the chosen model. The committed example logs, the `/demo` page and the example screenshots were produced by the fake and were removed: replace them with a real run (`scripts/export_logs.py`).
- **Not yet exercised against a real model.** The three providers and the agents' prompts have only met a stub server. A small local model may fail the output guards; the agent is then marked failed (F07) and the briefing is INCOMPLETE rather than wrong.

- The model choice was then narrowed to **Ollama and Claude** (one dropdown in the console); the OpenAI-compatible provider was removed.
