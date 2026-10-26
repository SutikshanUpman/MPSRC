# Merging AdverSI into the Trial of the Nine Realms

`adversi-main` (MIT, Yash Jindal; its licence is in `ui/LICENSES/adversi-MIT.txt`) is a separate implementation of the same problem statement: a React console, a FastAPI server and its own Python agents. This repository's engine was built and tested independently. The two were merged along one seam: **AdverSI's console is the face, this repository's engine is the brain.**

## What came from where

| Part | From | Notes |
|---|---|---|
| Visual design: typography, Norse palette, light and dark theme, ornaments, agent portraits, Runemark map plate, range plot, ruling ledger, source drawer | AdverSI (`ui/`) | Kept as designed |
| Screens: welcome, "how it works", case console (Briefing, Case File, Runemark map, Document feed, Trial, Exposure, Audit), live feed, source drawer | AdverSI | Re-wired to the engine's data |
| Trial engine: Heimdall, Thor, Loki, Odin, cross-examination, Run 2, calc tool, guardrails, memory, budget, record/replay | This repository (`backend/`) | Unchanged by the merge |
| The API contract the console reads: `/api/meta`, `/api/runs`, `/api/runs/<id>`, `/events`, `/feed`, `/sources/<id>` | AdverSI's contract, implemented in `server.py` (stdlib) + `backend/runtime/trial_view.py` | The FastAPI server is not used |
| Trial record (`trial-2`): Case File, one entry per run, briefing, exposure rows, memory audit | AdverSI's shape, extended | `trial_view.trial_result` maps the engine's files onto it |

## What was changed in AdverSI

- **Names follow the problem statement.** "Althing", "Runemark Tribunal", "AdverSI", "workspace", "hands", "judge", "advocates", "court", "round" became *Trial of the Nine Realms*, *Ragnarok Trial Console*, *the console*, *agents*, *Odin*, *Thor and Loki*, *run*. Tabs: Briefing, Case File, Runemark map, Document feed, Trial, Exposure, Audit. Run I / Run II, Case File, Cross-examination, Rulings, Established / Contested / Conceded / Rejected, `INSUFFICIENT_EVIDENCE` are the problem statement's terms.
- **Trial only.** The generic modes (simple, debate, jury, ...), their result view, claim graph and the terms/privacy boilerplate were removed: they are not part of the problem statement.
- **Exposure is a range with a status.** A cell with no evidence after Run II shows "Insufficient evidence" and its targeted queries, never a number. Each row shows Odin's value range, the net-shortfall percent, the volume range, and opens "why this range" and "why this number" (formula, baseline rule, the input rows, with and without repeated rows).
- **Claims show their life**: superseded or withdrawn claims, the claim they update, the kind of each challenge, who decided each ruling (rules or model).
- **Run II** shows the new evidence families Heimdall found, or the reason it found none.
- **Audit** shows the acceptance evidence of the run (send-back, new evidence, concessions, memory decisions, briefing hash), the trap report, the private-memory audit, and a **Replay at $0** button.
- **The live feed** reads this engine's own event names (`ODIN_SENT_BACK`, `RUN_2_NEW_EVIDENCE`, `DECISION_CHANGED`, `FALLBACK_*`, ...).
- **A run starts from the console on a model you choose** (Ollama or Claude), as in AdverSI's provider and model picker. Keys stay in the server's environment; metered providers keep the budget owner's switches, per-case cap and ledger.

## What was changed in this repository for the merge

- `server.py` now serves the AdverSI API contract (stdlib only) and the built console from `web/`. A run started from the console runs in a thread and its events appear in the live feed as the engine writes them (`TraceLog.on_emit`).
- `backend/runtime/trial_view.py` (new): the case's files -> the console's record; the as-of document feed; click-through to a document, a paragraph (`DOC:P#`) or a trade row (`DOC|YYYY-MM`).
- `backend/llm/` gained the Ollama provider (and Claude as before) and `factory.py` (provider + model -> configured run); the rule-based stand-ins used by the test suite moved to `tests/fakes/` and the product no longer offers them.
- `ui/` (new): the console's source. `web/` is its production build, committed, so running the project needs no node.
- `orchestrator.run_full_case(on_event=...)`, `TraceLog.on_emit`: live events. `memory_before/` in each case: a replay starts from the same private memory.

## What was not merged

AdverSI's own Python engine (`src/adversi`: async providers, status policy, SQLite trial memory, evaluation harness, CLI) is not used: this repository's engine already implements each of those ideas for the problem statement (typed claims, deterministic rulings and status rules, private memory, guardrails, replay), is covered by tests, and runs on the standard library alone. Its `adversi-main (2)/` folder and zip stay untouched and untracked.

## Rebuilding the console

```sh
cd ui
npm install        # once
npm run build      # writes ../web
```
