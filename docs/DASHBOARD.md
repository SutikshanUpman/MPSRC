# Dashboard

`python server.py` (standard library only) serves `web/` and a JSON API over the saved cases in `data/runs/` on **127.0.0.1:8000**. Override with `--host/--port` or the `HOST`/`PORT` environment variables. It runs the **mock** or **replay** provider only: there is no way to start a live model call from the page or the API (`POST /api/cases` with `provider: anthropic` is refused). Live runs are the budget owner's, from the command line.

To see something first: `python scripts/run_case.py --demo`, then open `http://127.0.0.1:8000/`.

## Screens (AC7)

| Tab | What it shows | Source |
|---|---|---|
| Question box (top) | Type a question and run it on the mock provider ($0), or pick a saved case. "Replay at $0" re-runs the saved case from its recorded model calls and says whether the briefing hash matches | `POST /api/cases` |
| Live feed | `events.jsonl` replayed in time order with Play / Pause / Rewind and a speed control; warnings are highlighted | `GET /api/cases/<id>/events` |
| Trial | One card per cell: Thor and Loki side by side, each claim with Odin's ruling chip and rationale beside it, the challenge and response under the claim it targets, superseded claims dimmed with a link to their revision | Case File, `rulings.json` |
| Exposure | The table from the briefing (Thor, Loki, Odin range, Odin value, Odin volume, status). `INSUFFICIENT_EVIDENCE` and `NO_DOCUMENTED_FLOW` are shown as such, never as zero. Each cell opens "why this range" (calibration), its citations, its table rows and a "Why this number" drill-down (formula, baseline rule, inputs, with and without repeated rows) | `briefing.json`, `calc_ledger.json` |
| Briefing | `briefing.md` rendered, header chips (COMPLETE / INCOMPLETE, flagged cells, numbers removed by the validator) | `briefing.md` |
| Traps & numbers | Trap report (12 trap types with their evidence) and the acceptance evidence of the run | `trap_report.json`, `run_record.json` |
| Header | Cost meter: spend (or the estimate at configured prices for a mock run) against the per-case cap and the $4 project cap | `run_record.json`, `config.json` |

**Click-through:** every `[DOC_ID, P#, timestamp]` on every tab opens the source drawer with the masked paragraph, its header metadata (tier, source type, date, flags, event) and the other paragraphs of the document. A table row named by a `row_ref` (`table_id`, `native_row_number` or row key) is highlighted in the paragraph.

A file that does not exist yet (for example no trap report) shows a "Pending" panel; the page never crashes on it. Deep links: `/#case=demo_E5&tab=exposure&source=ORV-0009:P4`.

## API

| Request | Returns |
|---|---|
| `GET /api/health` | `{ok, cases, providers}` |
| `GET /api/cases` | saved cases, newest first (id, question, status, provider, briefing completion and hash, spend, acceptance evidence) |
| `GET /api/cases/<id>` | `run_record`, `case_file`, `rulings`, `briefing`, `briefing_md`, `trap_report`, `claims`, `calcs`, `cross_examination`, `search_log`, `config`; a missing file is `null` |
| `GET /api/cases/<id>/events` | the event log as a list |
| `GET /api/source?doc_id=&p=[&table_id=&row=][&case=]` | masked paragraph text, header metadata, the highlighted row text |
| `POST /api/cases` | `{question, provider: "mock"}` runs a case; `{provider: "replay", from: "<id>"}` replays one; anything else is refused |

## Safety

Only files inside `web/` are served and a case id is one directory name under `data/runs/` (no `..`, no separators); both are tested. Every string from the API is inserted with `textContent`, never as HTML. A replay starts from the memory snapshot the original case started from (`data/runs/<id>/memory_before/`), so it reproduces the original.

## Screenshots

`docs/screenshots/` (Edge headless, the `demo_E5` case): `feed.png`, `trial.png`, `exposure.png`, `briefing.png`, `insight.png`, `source.png`.
