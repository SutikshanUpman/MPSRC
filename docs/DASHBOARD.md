# The Trial of the Nine Realms console

`python server.py` (standard library only) serves the console (`web/`, built from `ui/`) and its API on **127.0.0.1:8000**; override with `--host/--port` or `HOST`/`PORT`. The design is AdverSI's, the engine is this repository's ([MERGE_ADVERSI.md](MERGE_ADVERSI.md)). The console runs the **mock** or **replay** provider only: there is no way to start a live model call from the page or the API (`POST /api/runs` with another profile is refused). Live runs are the budget owner's, from the command line.

To see something first: `python scripts/run_case.py --demo`, then open `http://127.0.0.1:8000/app`.

## Pages

| Route | What |
|---|---|
| `/` | Welcome: the four agents (Heimdall, Thor, Loki, Odin), the Runemark map |
| `/how-it-works` | The sequence: Case File, two independent cases, cross-examination, Odin's rulings, the single send-back, the briefing |
| `/demo` | A saved E5 trial, readable without starting anything |
| `/app` | The console |

## The console (AC7)

| Part | What it shows | Data |
|---|---|---|
| Question box | Question, as-of date, Runemark pack; "Start the trial" runs it on the mock provider ($0); "Use the E5 sample question" | `POST /api/runs` |
| Live feed | The trace as the engine writes it (searches, claims, challenges, `ODIN_SENT_BACK`, `RUN_2_NEW_EVIDENCE`, memory decisions, fallbacks), latest first, warnings highlighted | `GET /api/runs/<id>/events?after=N` (polled) |
| Briefing | Executive summary, evidence posture (certified / uncertified), cells flagged INSUFFICIENT_EVIDENCE, lines removed by the validator, the Established / Contested / Conceded / Rejected ledger, next-quarter outlook, assumptions, citations | `briefing.json` |
| Case File | Event, verification, countries and sectors, contradictions and corrections, assumptions, coverage, excluded or damaged documents | `case_file.json` |
| Runemark map | The chart, with each port's documents, claims and exposure rows | feed + record |
| Document feed | The corpus as of the case's date (nothing later is admitted), filterable by source type, quarter and text | `GET /api/runs/<id>/feed` |
| Trial | Run I and Run II: Thor and Loki side by side, each claim with Odin's ruling and rationale, superseded or withdrawn claims marked, cross-examination (challenge kind, defence, concession), Odin's rulings, what the send-back found | record |
| Exposure | Odin's range per cell (value, net-shortfall percent, volume), Thor's ceiling and Loki's floor, confidence, `INSUFFICIENT_EVIDENCE` shown as such. Under it: "why this range" (calibration), the cell's sources and trade rows, and "Why this number" (formula, baseline rule, input rows, with and without repeated rows) | `briefing.json`, `calc_ledger.json` |
| Audit | Acceptance evidence of the run (send-back, new evidence families, concessions, memory decisions, briefing hash), **Replay at $0**, trap report, private-memory audit, usage and cost (a mock run shows $0 and the estimate at configured prices) | `run_record.json`, `trap_report.json`, events |
| Source drawer | Any citation, trade row or document id opens the masked paragraph or row with its tier, source, date and flags | `GET /api/runs/<id>/sources/<id>` |

A file that does not exist (for example no trap report) shows nothing or an empty state; the page does not crash. Deep links: `/app?run=demo_E5&tab=Exposure`.

## API

| Request | Returns |
|---|---|
| `GET /api/health`, `/api/meta` | status and version; the providers (mock, replay, live: CLI only) |
| `GET /api/runs` | saved and running trials, newest first |
| `POST /api/runs` | `{question, as_of_date?, runemark_path?, profile: "mock"}` starts a trial (202); `{profile: "replay", from: "<id>"}` replays one; anything else is refused |
| `GET /api/runs/<id>` | summary and the trial record (`schema_version: trial-2`; `result` is `null` while it runs) |
| `GET /api/runs/<id>/events?after=N` | events after sequence N |
| `GET /api/runs/<id>/feed` | the document archive admitted by the case's as-of date |
| `GET /api/runs/<id>/sources/<id>` | `DOC` (whole document), `DOC:P#` (one paragraph) or `DOC\|YYYY-MM` (a trade row) |

## Safety

Only files inside `web/` are served (console routes fall back to the app); a run id is one directory name under `data/runs/` (no `..`, no separators). Both are tested (`tests/test_server.py`). The console renders every string through React, never as raw HTML. A replay starts from the memory snapshot the original case started from (`data/runs/<id>/memory_before/`), so it reproduces the original.

## Screenshots

`docs/screenshots/` (Edge headless, the `demo_E5` case): `landing.png`, `new-case.png`, `briefing.png`, `case-file.png`, `trial.png`, `exposure.png`, `audit.png`.
