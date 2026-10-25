# Trial of the Nine Realms: supply chain disruption impact analyzer

Four agents work through a disruption question about a fictional trade world. **Heimdall** opens and verifies the case, **Thor** and **Loki** argue high and limited exposure and cross-examine each other, and **Odin** judges, sends the case back once, and writes the briefing.
Every claim is grounded in a document pack and cited as `[DOC_ID, P#, timestamp]`; nothing dated after the case's as-of date is used.
The output is a low/high exposure range per country x sector cell (percent, value and volume), a cited briefing (Established / Contested / Conceded), and a full trace.

```
question -> Heimdall (Case File) -> Round 1 (Thor | Loki) -> Round 2 (cross-examination) -> Odin rules
         -> sufficiency check -> send back ONCE -> Run 2 (Heimdall re-search, Thor/Loki update gap cells) -> Odin rules again
         -> briefing (guarded) + trap report + run record
```

Architecture diagram: [docs/architecture.mmd](docs/architecture.mmd) (Mermaid). Explanation: [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md). Data shapes: [docs/CONTRACTS.md](docs/CONTRACTS.md). What was built and how it is checked: [docs/BUILD_FINAL.md](docs/BUILD_FINAL.md).

## Setup

Python 3.12, standard library only (no `pip install`). Put the document pack at the repo root as `dev_pack_E5/` (it holds `manifest.json`, `hashes.sha256` and `docs/`), or set `RAGNAROK_PACK_DIR`. The pack is read-only and is not committed.

```sh
python tests/run_tests.py          # the whole suite; no model call, no network
```

## Run a case

```sh
# Mock provider: rule-based stand-ins for every agent, deterministic, $0
python scripts/run_case.py --pack dev_pack_E5 --question "As of 25 January 2027, how exposed are Midgard and Tolan to the end of the Orvan corridor agreement? Give a low and high range for wheat and maize imports."

# The demo: the E5 sample question, then a second case that shares private memory (shows a logged DECISION_CHANGED)
python scripts/run_case.py --demo                 # writes data/runs/demo_E5/ and data/runs/demo_E5_memory/

# Replay a recorded case at $0, byte-identical (also the way the dashboard shows a "live" case)
python scripts/run_case.py --provider replay --from demo_E5
```

Each case writes `data/runs/<case_id>/`: `case_file.json`, `claim_ledger.json`, `calc_ledger.json` (with "why this number" explanations), `cross_examination.json`, `rulings.json`, `briefing.json` + `briefing.md`, `trap_report.json`, `run_record.json` (inputs hashed, spend, which acceptance criteria it shows), `events.jsonl`, `search_log.jsonl`, `llm_calls.jsonl` (every model call, recorded before use). Private memory persists per agent in `data/memory/<agent>/` (`--memory-dir` to change it). Any pack with the same layout works with no code change: `tests/test_final.py` runs a synthetic pack end to end.

### Live run: the budget owner only, once

There is **one** $4 key for everything; $2.50 is the untouchable final-round reserve, the per-case cap is $0.50, and Odin's briefing reserve is derived from the token caps and protected by the budget guard. Model prices in `config/runtime_config.json` are **unverified** until the budget owner checks them and sets `"prices_verified": true`. Copy `.env.example` to `.env` (never commit it) and then:

```sh
python scripts/live_check.py                                   # 1. dry run: models, caps, worst case, ledger; makes NO call
LIVE=1 BUDGET_OWNER=<name> python scripts/run_case.py --provider anthropic --pack dev_pack_E5 --question "<question>"   # 2. the live run
python scripts/export_logs.py <case_id>                        # 3. copy the case to logs/ for the submission
```

The provider refuses unless `LIVE=1`, `BUDGET_OWNER` and verified prices are all set. The project ledger (`data/ledger.json`) refuses a live run when spend so far plus one case's worst case would pass $1.50 (`--final-round` raises the ceiling to $4.00). The live run is a one-shot: afterwards the demo and the dashboard use **replay** only.

## Dashboard

`python scripts/run_case.py --demo` once, then `python server.py` serves the dashboard on `http://127.0.0.1:8000` (override with `HOST`/`PORT`): question box, live feed, trial view, exposure table, click-through to sources, briefing, trap report. It runs the mock or replay provider only and never makes a live call. See `docs/DASHBOARD.md`.

## Folder layout

| Path | What |
|---|---|
| `backend/ingestion`, `search`, `provenance` | PDF/TXT/DOCX ingestion, trade-table parsing, local BM25 with metadata filters, citation validation |
| `backend/agents` | Heimdall, Thor/Loki (Round 1, calc tool), cross-examination, Odin, mock policies |
| `backend/guards` | The hallucination guardrails |
| `backend/runtime` | Config, budget guard, project ledger, Run 2, orchestrator |
| `backend/briefing` | Briefing builder and gate, trap report, "why this number" |
| `backend/llm` | Provider boundary: mock, live (stdlib `urllib`), recording, replay |
| `prompts/` | Live-path prompts: `thor.md`, `loki.md` (round 1, round 2, run 2), `odin.md`, `odin_briefing.md` |
| `config/runtime_config.json` | Limits, token caps, models, prices (UNVERIFIED) |
| `logs/` | Saved logs of a full two-run case (committed) |
| `docs/` | **Architecture and spec.** `dev_pack_E5/docs/` is the corpus; do not confuse the two |
| `tests/` | `run_tests.py` and the test files; `tests/fixtures/` builds synthetic packs |

## Design choices

- **Hybrid search = local BM25 + four metadata filters.** Paragraph-level BM25 (no embeddings, no external index) with mandatory filters (as-of date and event scope) plus country, tier, source-type and sector-boost filters. No vector service is needed, results are deterministic and every hit is a citable span. Sector is a ranking boost, never a filter.
- **Deterministic Heimdall.** Event mapping, as-of resolution, verification, coverage and the cell plan are rules; a model is called only as a stance fallback when the rules are inconclusive.
- **Odin is rules first.** Pre-ruling checks reject tier-4-only claims, post-as-of or out-of-scope or unretrieved citations, background-only numeric support and quotes that are not verbatim; interested-party claims are qualified. The model rules only on the claims the rules left open and can never add a fact (its rationale goes through the same guards, else the rules stand).
- **Guardrails** (`backend/guards`): structured output with unknown fields rejected, citation guard, quote guard, number guard (agents never do arithmetic; every number maps to a span or a calc id), entity/date guard, injection guard, abstain rule, briefing gate. A failed output is a schema failure: retry, then `AGENT_FAILED`.
- **D1.** A cell with no documented flow is `INSUFFICIENT_EVIDENCE` after Run 2, flagged with its targeted queries; the briefing is still COMPLETE. It is never read as zero.
- **OD-1.** A table row is cited by its paragraph `[DOC_ID, P#, timestamp]` and traced through `row_refs` (doc, table id, row number).
- **Record / replay.** Every model call is written to `llm_calls.jsonl` before its output is used; `--provider replay` re-runs the case from those records and reproduces the same briefing hash.
- **Fallbacks** (each logged as `FALLBACK_*`): retry with backoff, one JSON repair, deterministic Odin and a template briefing, budget stop with `INCOMPLETE_BUDGET_LIMIT`, `EVENT_UNVERIFIED` with no numbers, unparsed trade table, ingestion flags for odd packs.

## Known limitations

- The agents have only run on the **mock** provider here. Their prompts and the live provider are tested against a stubbed transport, not against the real API; the budget owner's live run is the first real test.
- Model prices and token caps are unverified starting values.
- Search is lexical (BM25). Paraphrases that share no word with the query can be missed; Heimdall's Run-2 re-search widens by sector and by text mention of the country to compensate.
- Run 2 can legitimately find no new evidence; the run record then says why (`run2_no_evidence_reason`) instead of pretending.
- There is no external web lookup (`docs/EXTERNAL_LOOKUP.md` explains why it is off).
