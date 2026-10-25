# Trial of the Nine Realms: supply chain disruption impact analyzer

Four agents work through a disruption question about a fictional trade world: Heimdall opens and verifies the case, Thor and Loki argue high and limited exposure, and Odin judges.
Every claim is grounded in a document pack and cited as `[DOC_ID, P#, timestamp]`, and nothing dated after the case's as-of date is used.
The output is a low/high exposure range per country × sector cell, with a cited briefing.

## Folder layout

| Path | What |
|---|---|
| `backend/` | Python code: `ingestion/`, `search/`, `provenance/`, `agents/`, `casefile/`, `llm/`, `runtime/`, `contracts.py` |
| `config/runtime_config.json` | Limits, token caps, model names and prices. All values are tunable, and prices are unverified |
| `prompts/` | Live-path system prompts for Thor and Loki (`thor.md`, `loki.md`), one section per round; not sent anywhere while the provider is the mock |
| `scripts/` | `run_case.py` (Heimdall, Round 1, then Round 2 cross-examination for Thor and Loki), `ingest_pack.py` (dump normalised records) |
| `tests/` | `run_tests.py` and the test files; `tests/fixtures/` builds synthetic packs |
| `docs/` | **Architecture docs (editable).** Start with `docs/SYSTEM_ARCHITECTURE.md`; `docs/CONTRACTS.md` has the data shapes |
| `dev_pack_E5/` | **The document corpus (read-only, not committed).** `dev_pack_E5/docs/` holds the corpus documents; don't confuse it with the architecture `docs/` above |
| `data/` | Generated output (`normalized/`, `runs/`, `memory/`), not committed |

## Placing the corpus

Put the pack folder at the repo root as `dev_pack_E5/`, containing `manifest.json`, `hashes.sha256` and `docs/`. To keep it elsewhere, set `RAGNAROK_PACK_DIR` to its path. Never edit files inside the pack.

## Running

```sh
python tests/run_tests.py
python scripts/run_case.py --pack dev_pack_E5 --question "<your question>"
```

`run_case.py` writes `data/runs/<case_id>/` (`case_file.json`, `claim_ledger.json`, `calc_ledger.json`, `cross_examination.json`, `search_log.jsonl`, `provider_calls.jsonl`, `events.jsonl`) and keeps each agent's private memory in `data/memory/<agent>/` across cases (`--memory-dir` to change it).

The provider is the deterministic mock by default, so no model is called and nothing is billed. Live calls stay disabled unless the config enables them and names a budget owner. API keys live in `.env`; never commit it (`.gitignore` excludes it).
