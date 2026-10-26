# Project review against the Problem Statement

Reviewed on 2026-10-26, against the working copy of `main` (HEAD `7697003`) **plus 14 uncommitted changes** (13 changed files and the new `backend/briefing/dispute.py`). The uncommitted fixes are from the live test-case session; nothing here has been pushed.

How this review was done:
- The Problem Statement (PS) was read in full. It is **not** at `docs/PS.pdf`. The copy used is `C:\Users\paree\Downloads\Trial of the Nine Realms PS.pdf` (6 pages).
- The code was checked directly. Where a report (a `docs/*.md` file) says something the code does not show, this review says so.
- No AI model was called. No `.env` file was read.

Live checks:

| Check | Result |
|---|---|
| `python tests/run_tests.py` | Last line: **`PASSED 265  FAILED 0  SKIPPED 0`** |
| E5 sample question, mock provider (a stand-in that gives fixed answers, so no AI model is called) | **Ran to the end.** Briefing `COMPLETE`. 23 rulings: 16 Established, 6 Contested, 1 Conceded; 1 claim rejected. 5 cross-examinations. Odin sent the case back, and Run 2 found 2 new evidence families. 14 files written. No error. Memory changed 0 decisions (a first case has no memory to use). |
| Server plus headless browser (a browser with no window, driven by a script) | All AC7 parts render: question box, document feed, trial view, exposure table, citation buttons. The click-through address returns the document or the trade row. |

Details of the live checks:
- **The mock is not a command-line option any more.** `scripts/run_case.py --help` offers only `ollama`, `anthropic` and `replay`. The mock was removed from the product earlier and now lives only in `tests/fakes/`. The run above used that test mock through `run_case.main()`, with all output written outside the repo.
- **Files the mock run wrote:** `briefing.json`, `briefing.md`, `calc_ledger.json`, `case_file.json`, `claim_ledger.json`, `config.json`, `cross_examination.json`, `events.jsonl`, `llm_calls.jsonl`, `provider_calls.jsonl`, `rulings.json`, `run_record.json`, `search_log.jsonl`, `trap_report.json`.
- **Server test setup:** a separate copy on port 8010, pointed at the mock run, with no API key.
- **What the browser test could not do:** it can only read the drawn page, not click. So the click-through was checked by calling the same address the button calls (`ui/src/api.ts:47`), not by a real mouse click.
- **Real Claude runs from today** (in `data/runs`, not committed):
  - **Q2 run (`run-e6d0c56d70`):** briefing `COMPLETE`. It had cross-examination, a send-back and new evidence in Run 2, but **0** rejected or conceded rulings and **0** memory-changed decisions.
  - **Q1 run (`run-8501ff2178`):** `INCOMPLETE`, because 3 agent steps failed. It had **1** rejected claim.

### Update after the review (same day)

Fixed and tested (268 tests pass), all uncommitted:
- **Odin's own rulings now count.** In both live runs below, Odin's AI ruled after Run 1 and after Run 2 (`MODEL_ON_OPEN_CLAIMS`). Before, a guard threw his answer away every time (see §7).
- **Q1 on Claude is now COMPLETE:** `run-5e2966af0b`, $0.16, 0 lines removed by the validator.
- **Q2 on Claude is still INCOMPLETE:** `run-c7e02dea08`, $0.16. Loki got through cross-examination this time. Thor failed, because he kept a draft revision that no QUALIFY named. Such a leftover draft is now set aside and logged (`REVISION_SET_ASIDE`) instead of failing the step. That fix has not been run live yet.
- **Budget bug:** the final-round switch raised the ledger's ceiling but not the run's guard, so one Q2 attempt stopped before any agent ran. Also, free runs (Ollama, the mock) were being stopped by what paid runs had spent. Both are fixed in `backend/runtime/orchestrator.py`, with a test.
- **Console label:** Run II showed "SUFFICIENT" while listing missing evidence. It now says "run limit reached · gaps flagged" when gaps remain after the last run.
- **Spend:** the project ledger is at about $1.53. Further Claude runs need the final-round setting.

---

## 1. The PS in 6 lines

1. One event (a strike, a ban, an attack) can hurt trade in many countries, and experts argue about how badly.
2. Build a "court case" of four AI agents. Heimdall opens and checks the case, Thor argues the damage is high, Loki argues it is limited, and Odin judges every claim and writes the briefing.
3. Everything must come from Runemark, the organisers' invented set of news files and trade tables. Every claim needs a document ID, and nothing dated after the question's date may be used.
4. The two sides must really search, attack each other's claims, defend with new evidence or give in. The judge may send the case back for a second run.
5. The output is a dashboard and a briefing: what is certain, what is disputed, and a low-to-high damage range per country and sector, all clickable back to sources.
6. In the final round the organisers hand over five new event packs, and the system must take a live question on each with no code changes. It is scored from saved logs on citation validity, whether the true damage falls inside the ranges, how narrow those ranges are, trap handling, debate quality, reliability and reproducibility.

---

## 2. Is agentic AI really needed here?

**Honest answer: partly.**

Much of the job is better done by fixed rules (deterministic: same input, same output, every time). Examples:
- reading files
- checking dates
- doing the sums
- checking that every citation is real

We do all of those with rules, and that is the right choice, because a model can invent a number or a citation and a rule cannot.

What a fixed pipeline cannot do well is the part the PS cares about most: two sides who choose their own searches, find evidence the other side missed, and either defend a claim with new evidence or give in. That is open-ended work where the next step depends on what was just found. That is where agents add real value, and it is also why the PS asks for them.

**Where the agents add real value in our code:**

| What happens | Where |
|---|---|
| Each side picks its own search queries and documents, and only what it retrieved itself may be cited. | `backend/agents/tools.py:79` (search), `backend/agents/claims.py:120-121` (a citation must be one this agent retrieved) |
| Cross-examination: each side must attack 1 to 3 of the other's claims, with a citation of its own. | `backend/agents/cross_exam.py:111-112`, `:135` |
| Defence: DEFEND only counts with new evidence found in Round 2. Otherwise the side must QUALIFY (narrow its claim) or CONCEDE. | `backend/agents/cross_exam.py:8` (rules), `validate_responses` |
| A concession and a rejection happened. | Mock E5 run: 1 Conceded, 1 Rejected. Live Claude Q1 run `run-8501ff2178`: 1 Rejected. |
| Send-back: Odin finds gaps, Heimdall searches again, and Run 2 must bring new evidence. | `backend/runtime/run2.py:34` (`sufficiency`), `:59` (`heimdall_research`). Live Claude Q2: 5 new evidence families. |
| Memory changes a decision in a later case. | `backend/agents/counsel.py:149` (`DECISION_CHANGED`), test `test_ac9_second_case_changes_a_decision_because_of_memory`. **Proven with the mock only.** |

**Where we deliberately use fixed rules instead (and why):**

| Rule-based part | Why not a model |
|---|---|
| Heimdall: reading files, the as-of date gate, event check, retractions, premise check (`backend/agents/heimdall.py:314, 388, 592`) | Whether an event is real must be the same answer every time, and must be checkable. |
| All arithmetic: the calc tool (`backend/agents/calc.py`) | Models get sums wrong. Every number in the output must point to a calc field or a cited sentence. |
| Odin's first pass on every claim: `rule_claims` (`backend/agents/odin.py:129`) | Clear-cut rulings (bad citation, out of date, number mismatch) need no judgement. The model is asked only about claims the rules leave open (`model_pass`, `odin.py:225`). |
| The checks on every output (`backend/guards/__init__.py`) | They catch made-up numbers, citations, quotes and names. |
| The dispute check (`backend/briefing/dispute.py`, uncommitted) | It compares a named party's figure with independent records. |

**Where the AI model is used:**
- Thor and Loki: searching, writing claims, challenging and answering.
- Odin: ruling only on open claims, and writing the briefing text.
- Heimdall: only a small fallback that sorts documents the rules could not classify (`heimdall.py:543`).

**Where it is not used:** reading files, dates, sums, citation checks, the premise and dispute checks, the exposure table, and the trap report.

---

## 3. Tech stack

Only things that are really in the repo.

| Tool / library | Where | Why chosen |
|---|---|---|
| Python 3.12, standard library only (no pip packages for the backend) | `backend/`, `scripts/`, `server.py` | Nothing to install. It runs the same everywhere, including the judges' machine. |
| Own PDF / DOCX / TXT readers | `backend/ingestion/extractors.py` | The PS requires all three formats. Written by hand so no external library is needed. |
| Own trade-table and trade-note parser | `backend/ingestion/trade.py` | The PS says teams must parse the text tables themselves. |
| BM25 keyword search (a standard way to rank documents by matching words) with metadata filters | `backend/search/bm25.py` | Fast, local, explainable, no external index. Filters: as-of date, event, country, tier, source type. |
| Ollama (runs a free AI model on this computer) through its web API | `backend/llm/provider.py` (`OllamaProvider`) | Free local runs. No key. |
| Anthropic Claude through the Messages API | `backend/llm/provider.py` (`AnthropicProvider`), `backend/llm/factory.py` | The stronger, paid model for live runs. Haiku 5.5 for the agents, Sonnet 5.5 for Odin. |
| Record and replay of every model call | `backend/llm/provider.py` (`RecordingProvider`, `ReplayProvider` at line 394) | Any case can be re-run for $0 and gives the same briefing (`test_determinism_and_replay_at_zero_dollars`). |
| Budget guard and spend ledger | `backend/runtime/budget.py`, `backend/runtime/ledger.py`, `config/runtime_config.json` | Hard money limits per case and per project, with money kept back for Odin. |
| Built-in Python web server | `server.py` | Serves the dashboard and its data. No web framework to install. |
| React 18, React Router, TypeScript, Vite (front-end build tool) | `ui/` (source), `web/` (built, committed) | The dashboard. Built once, then served as plain files. |
| Docker, docker-compose, Render config | `Dockerfile`, `Dockerfile.with-pack`, `docker-compose.yml`, `render.yaml` | Deploying the console. |
| Mermaid diagram (text that draws a diagram) | `docs/architecture.mmd` | The required architecture diagram. |
| Python `unittest` with a mock model | `tests/`, `tests/fakes/` | 265 tests, no model calls. |

---

## 4. What we built: question to briefing in 10 steps

1. **The user asks a question** in the dashboard or on the command line. → `server.py` (`POST /api/runs`), `scripts/run_case.py`
2. **Read the pack.** Every PDF, DOCX and TXT file is read. Damaged files get a status (EMPTY, TRUNCATED and so on) instead of crashing, and instruction-like lines are masked. → `backend/ingestion/pipeline.py`, `extractors.py`, `trade.py`, `packs.py`
3. **Heimdall opens the Case File.** He finds the as-of date and which event the question is about, then keeps only documents dated on or before that date and belonging to that event. → `backend/agents/heimdall.py:101` (`parse_as_of`), `:162` (`map_event`), `:592` (`open_case`)
4. **Heimdall checks the event is real.** He looks for corrections and retractions, and checks words in the question like "destroyed" or "famine" against trusted documents. → `heimdall.py:314` (`verify_event`), `:388` (`premise_check`)
5. **Round 1:** Thor and Loki each search, read documents and trade rows, run the calc tool, and submit claims with citations. They both work from the same frozen copy of the Case File and cannot see each other's claims. → `backend/agents/counsel.py` (`run_round1`), `backend/agents/tools.py`, `backend/agents/calc.py`
6. **Every claim is checked** for citations, numbers, quotes, names and hidden instructions. A failing claim goes back to the agent with the reasons. → `backend/agents/claims.py`, `backend/guards/__init__.py`, `backend/agents/normalize.py`
7. **Round 2 (cross-examination):** each side challenges the other, then answers with DEFEND (new evidence), QUALIFY (narrower claim) or CONCEDE. → `backend/agents/cross_exam.py`
8. **Odin rules on every claim.** Rules first, then the model on the claims still open. He marks each as sourced fact or inference, and as Established, Contested, Conceded or Rejected. → `backend/agents/odin.py:129` (`rule_claims`), `:225` (`model_pass`)
9. **Sufficiency check.** If cells are missing evidence, Odin sends the case back once. Heimdall searches again, Run 2 must bring new evidence, and Odin rules again. → `backend/runtime/run2.py:34, :59`
10. **The briefing is built and checked.** It has a summary, the Established / Contested / Conceded sections, the exposure table, an outlook, and sources. Every line goes through the checks again, and failing lines are removed and listed. Everything is saved for replay. → `backend/briefing/__init__.py` (`build`, `gate`), `backend/runtime/orchestrator.py`, `backend/runtime/trial_view.py` (what the dashboard shows)

---

## 5. Our extras beyond the PS

| Extra | Really built? | Evidence |
|---|---|---|
| A claim may cite only what that agent retrieved itself | **Yes** | `backend/agents/claims.py:120-121` |
| Number check: every figure must equal a calc field (`calc_id`) or appear in a cited sentence | **Yes** | `backend/guards/__init__.py:89` (`number_guard`), `claims.py` (`_check_numbers`) |
| Quote check: quoted words must appear word for word in the cited text | **Yes** | `guards/__init__.py:78` (`quote_guard`) |
| Name check: no invented country, firm or place names | **Yes** | `guards/__init__.py:144` (`entity_guard`) |
| Honest INSUFFICIENT_EVIDENCE: no range is given when there is no data | **Yes** | `guards/__init__.py:177` (`abstain_guard`). The mock E5 run shows Tolan / Maize as `INSUFFICIENT_EVIDENCE (NO_DOCUMENTED_FLOW)`. |
| Trap report (what was caught: masked instructions, future documents, duplicates, damaged files, rumours, retractions) | **Yes** | `backend/briefing/trap_report.py:13`. `trap_report.json` is written in every run. |
| $0 replay that gives the same briefing | **Yes** | `backend/llm/provider.py:394`, `test_determinism_and_replay_at_zero_dollars` (`tests/test_final.py:140`) |
| Spend ledger and money kept back for Odin | **Yes** | `backend/runtime/budget.py:6-9, 27, 41`, `backend/runtime/ledger.py:46`. It refused a run today when the $1.50 development limit would have been passed. |
| A new pack needs no code changes (tested on made-up packs) | **Yes** | `tests/test_ingestion_synthetic.py` (`SyntheticPack`, 20+ tests), `tests/test_heimdall_synthetic.py` (`test_mock_determinism_on_a_second_pack`) |
| Repeated-row widening only in affected cells: a range is widened only where repeated rows were used | **Yes** | `backend/agents/calc.py:306` (`widened` = repeated rows only). The mock run shows `widened: True` on Midgard / Wheat only. |
| Memory hides facts from after the question's date | **Yes** | `backend/memory/store.py:40` (`read_for_case`), `counsel.py:84` (`MEMORY_HIDDEN`) |
| Premise check (for example "destroyed" is rejected when only a rumour says it) | **Yes** | `heimdall.py:388`, briefing `premise_paragraphs` |
| Dispute check (a named party's figure against independent records) | **Yes, but uncommitted** | `backend/briefing/dispute.py`, test `test_a_named_dispute_is_adjudicated_from_the_documents` |
| "Why this number" calc explanation and range calibration text | **Yes** | `trap_report.py` (`calc_explain`), `backend/briefing/__init__.py` (`calibration`) |

---

## 6. PS criteria table

The marks are strict:
- **DONE** means the code does it and a test or a run shows it.
- **"Mock only"** means it was shown with the stand-in model, not a real one. It counts as DONE only where the PS does not need a real model for it.

### §3.3 Minimum acceptance criteria (the final-round list)

| # | Requirement in plain words | Status | Evidence | What is missing |
|---|---|---|---|---|
| 1 | Read PDF, TXT and DOCX (including new files given live), make the Case File, read trade tables, check the event is real | DONE | E5 pack: 30 PDF, 30 TXT, 16 DOCX all read. `heimdall.py:592` (`open_case`), `:314` (`verify_event`). Live packs through `pack_paths`: `packs.py:1`, `test_doc_id_collision_merges_or_live_wins...` | Nothing |
| 2 | Hybrid search with at least two metadata filters | PARTIAL | `search/bm25.py:57-68, 83`: BM25 plus filters for as-of date, event, country, tier and source type | "Hybrid" usually means keyword plus meaning-based search. We have keyword plus filters only (see §7). |
| 3 | Thor and Loki each make evidence-backed claims from their own searches, searching at least once | DONE | `counsel.py` (a cell with no search by the agent is rejected), `claims.py:120`. Live Claude runs: both sides searched and claimed. | Nothing |
| 4 | At least one cross-examination | DONE | Mock E5: 5. Live Claude Q2 (`run-e6d0c56d70`): 6 challenges and 6 responses. | Nothing |
| 5 | Odin rules on every claim; at least one claim rejected or conceded | PARTIAL | Mock: 1 rejected and 1 conceded (`test_ac5_...`). Live: 1 rejected in `run-8501ff2178` (incomplete run); **0** in the complete live run `run-e6d0c56d70`. | Not reliably shown with a real model |
| 6 | Briefing has Established / Contested / Conceded, an exposure table with low and high, timestamped citations, and an outlook with assumptions | DONE | `briefing/__init__.py` (`build`), `test_ac6_briefing_has_every_part`. Live Q2 briefing COMPLETE with all parts. | Nothing |
| 7 | Dashboard shows a question box, live feed, trial view and exposure table, and click-through works | DONE | Headless-browser check of `/app` and `/app?run=<id>&tab=…` (tabs at `ui/src/components/TrialView.tsx:24`); `/api/runs/<id>/sources/<id>` returns the document or row | A real mouse click was not tested (page render plus address check only) |
| 8 | Odin sends the case back at least once, and Run 2 brings new evidence | DONE | Mock: `sent_back: True`, 2 new families. Live Claude Q2: sent back, 5 new families. `test_ac8_...` | Nothing |
| 9 | Every agent has private, lasting memory, and a log shows memory changing an action | PARTIAL | `memory/store.py:18, 30` (owner-only), `test_thor_cannot_read_loki_memory`, `test_ac9_...` and `test_stage2.py:292, 305` show `DECISION_CHANGED` **with the mock only**. Live runs: `memory_decisions_changed: 0`. | No real-model run shows memory changing a decision |
| 10 | A damaged document is handled without crashing, and rounds, runs and retries have hard limits | DONE | E5 has 1 EMPTY and 1 TRUNCATED file (`test_ingestion_e5.py:36, 40`). Limits at `config/runtime_config.json:20-28` (2 runs, 1 cross-exam round, 6 tool calls a step, retries, a 900-second clock, token caps). | Nothing |

**Count for items 1-10: 7 DONE, 3 PARTIAL, 0 MISSING.**

### Functional requirements

| FR | Plain words | Status | Evidence | Missing |
|---|---|---|---|---|
| FR1.1 | Question becomes a Case File with an as-of date | DONE | `heimdall.py:101, 592` | — |
| FR1.2 | Gather documents and trade data in any format | DONE | `ingestion/pipeline.py`, `extractors.py`, `trade.py` | — |
| FR1.3 | Check the event is real, including retractions and contradictions; say why if not | DONE | `heimdall.py:314` (verify), correction map, `test_unrelated_question_is_no_match`, `test_false_premise_is_recorded...` | — |
| FR1.4 | Heimdall searches again on send-back and does not debate | DONE | `run2.py:59` (`heimdall_research`) | — |
| FR2.1 | Thor builds the high case | DONE | `prompts/thor.md`; Thor's scenarios are the high bounds (`normalize.py`) | — |
| FR2.2 | Every Thor claim has a document ID and a high estimate per country and sector | DONE | `claims.py`, one CELL_ESTIMATE per cell | — |
| FR2.3 | Thor answers attacks with new evidence or concedes | DONE | `cross_exam.py` (DEFEND needs new Round-2 evidence) | — |
| FR3.1 | Loki builds the limited case | DONE | `prompts/loki.md` | — |
| FR3.2 | Every Loki claim has a document ID and a low estimate; no "maybe it will be fine" | DONE | `claims.py`, `guards/__init__.py:177` | — |
| FR3.3 | Loki answers attacks with new evidence or concedes | DONE | `cross_exam.py` | — |
| FR4.1 | Rule on every claim; say sourced fact or inference | DONE | `odin.py:129`; every claim carries `claim_kind` SOURCED_FACT or INFERENCE | — |
| FR4.2 | Sort into Established / Contested / Conceded | DONE | `odin.py`, briefing sections | — |
| FR4.3 | Decide if good enough; if not, say what is missing and send back | DONE | `run2.py:34`, `ODIN_SENT_BACK` event lists the gaps | — |
| FR4.4 | Briefing written from Odin's rulings only | PARTIAL | `briefing/__init__.py` (`build`) uses rulings | The new premise and dispute paragraphs come from Heimdall's rule checks, not Odin rulings. They should be labelled as such or passed through Odin. |
| FR5.1 | Flow: user → Heimdall → Thor and Loki → Odin → briefing or next run | DONE | `orchestrator.py` | — |
| FR5.2 | Thor and Loki submit Round 1 at the same time | DONE | `counsel.py:309-318`: both use one frozen copy and neither sees the other | The code runs them one after the other, not literally in parallel. The effect is the same. |
| FR5.3 | Each side attacks at least one of the other's claims | DONE | `cross_exam.py:111-112` | — |
| FR5.4 | At least 2 runs; Run 2 brings new evidence; hard limits | DONE | `max_runs: 2`; `RUN_2_NEW_EVIDENCE`; limits in config | — |
| FR6.1 | Each agent has its own private, lasting memory; only the Case File is shared | DONE | `memory/store.py:18-30`, `test_thor_cannot_read_loki_memory` | — |
| FR7.1 | Question box and a live news feed replayed from Runemark | PARTIAL | Question box: yes. "Document feed" tab: documents up to the as-of date (`trial_view.py:280`). A live trial-event stream also exists. | The feed is a dated list, not a replay that plays the news in time order |
| FR7.2 | Thor's and Loki's claims side by side, with Odin's rulings | DONE | Trial tab render | — |
| FR7.3 | Exposure view with low and high per country and sector | DONE | Exposure tab (4 rows in the mock run) | — |
| FR7.4 | Click from any claim to the document or trade-table row | DONE | `/sources/<id>` returns a document or row; row payload has `table_id` and `row_id` (`trial_view.py:309-316`) | E5 has no table files, so table ID plus row number was only tested on made-up packs |
| FR8.1 | Executive summary plus Established / Contested / Conceded | DONE | `briefing.md` | — |
| FR8.2 | Exposure table and next-quarter outlook with assumptions | DONE | `briefing/__init__.py:301` | The outlook holds today's range constant. It is not a real forecast, and the text says so. |
| FR8.3 | Inline citations with document IDs and timestamps, and a source list | DONE | `[DOC, P#, date time]` format, `sources()` | — |

### Non-functional requirements

| NFR | Plain words | Status | Evidence | Missing |
|---|---|---|---|---|
| NFR1 | Each agent has a clear role, its own prompt and its own tools; no central planner | PARTIAL | `prompts/thor.md`, `loki.md`, `odin.md`, `odin_briefing.md`; no planner (Odin only judges) | No `prompts/heimdall.md` (his small model prompt is in code, `heimdall.py:553`). Thor and Loki use the same tool set. Odin has no tools. See §7. |
| NFR2 | No claim without a source; facts and inferences kept apart; every citation is real; outside sources labelled | DONE | `claims.py:120`, `guards/__init__.py:47`, `claim_kind` | No outside sources are used at all (`docs/EXTERNAL_LOOKUP.md`: design only, off) |
| NFR3 | No crash on bad files or failed tools; if one side fails, say the other went unchallenged; never claim complete when not | PARTIAL | No crash: tests plus today's runs (failed model calls recovered). Completeness: `briefing/__init__.py:176-179` marks INCOMPLETE on any agent failure. | The console says it: "No challenge was entered against this side this run. Its claims stand as argued, not as tested." (`ui/src/components/TrialView.tsx:679-680, 860-863`). **The briefing file (`briefing.md`) does not.** |
| NFR4 | Log every claim, query, retrieved item, memory use and ruling | DONE | `backend/contracts.py:100-126` (`CLAIMS_SUBMITTED`, `SEARCH_EXECUTED`, `DOCUMENT_RETRIEVED`, `MEMORY_READ`, `ODIN_RULED` …), `events.jsonl` | — |
| NFR5 | Hard limits; never send the same search or tool call twice | PARTIAL | Limits: config. Repeat search: served from cache and logged `SEARCH_CACHE_HIT` (`tools.py:7-9, 79-89`) | Repeated `get_document`, `get_trade_rows` and `calc` calls are not blocked or cached |
| NFR6 | Save the Case File, as-of date and rulings for every run | DONE | `case_file.json`, `rulings.json`, `run_record.json` per run; replay hash check | — |

### §3.4 What to submit

| Item | Status | Evidence | Missing |
|---|---|---|---|
| Public GitHub repo with README and `.env.example` | PARTIAL | Remote `github.com/SutikshanUpman/MPSRC`; `README.md` and `.env.example` are committed (names only, no keys) | Public visibility not checked. **Today's fixes (14 files) are not committed or pushed.** |
| Working demo, and saved logs of one full case with two runs | PARTIAL | The demo works (console plus a live Claude run). `scripts/export_logs.py` exists. | **No `logs/` folder in the repo.** No exported case yet. |
| Architecture diagram, explained to judges | DONE | `docs/architecture.mmd` (Mermaid; must be drawn for slides) | Its "unchallenged" edge is shown in the console only, not in the saved briefing |

**Reports versus code:**
- `docs/STATUS_NOW.md` is out of date. It says `--provider {mock,anthropic}` and "nothing after Round 2". The code now runs the whole trial and has no mock option.
- `docs/BUILD_FINAL.md` marks AC2 as "DONE as designed". This review marks it PARTIAL.

---

## 7. Specific risks

- **NFR1, own prompt and own tools:** not fully.
  - Thor, Loki and Odin have prompt files.
  - Heimdall has none. He is almost all rules, and his one small model prompt sits in code (`heimdall.py:553`).
  - Thor and Loki use the **same** four tools (search, get_document, get_trade_rows, calc), but each has a separate copy with its own record of what it has read. That is why each may cite only its own finds.
  - Odin has no tools; he reads the Case File.
  - **How to say it honestly:** "Each agent has its own role, prompt and private record. Thor and Loki share a tool kit but cannot see each other's results. Heimdall is mostly rules by design, so the event check cannot be talked into a fake event."
  - Adding `prompts/heimdall.md` is a small fix.
- **AC2, hybrid search:** what we have is keyword ranking (BM25) plus structured filters on the metadata header: date, event, country, tier and source type. There is no meaning-based (embedding) search. The README says this openly (`README.md:80`).
  - **Honest wording:** "hybrid = keyword ranking + metadata filters".
  - If a judge expects keyword plus meaning, this is a gap.
- **PS 4.2, trade row by table ID and row number:** the parser reads them (`ingestion/trade.py:380-407`) and the click-through returns `table_id` and `row_id` (`trial_view.py:309-316`).
  - E5 has no table files. All 98 rows come from prose trade notes, so their `table_id` is empty.
  - The table path is only proven on made-up packs (`test_fixed_table_units_and_synthetic_paragraph`).
  - Row keys in E5 look like `ORV-0009|2025-07` (document plus month), not table plus row.
- **NFR3, "the other side went unchallenged": half built.** (Corrected: the first version of this review searched only the backend and said "not built".)
  - The console marks a side as unchallenged whenever it has claims but none were challenged in that run, which is what happens when the other side fails (`ui/src/components/TrialView.tsx:679-680, 860-863`).
  - The failure itself is recorded (`orchestrator.py:219-223`) and listed under "Run errors" (`trial_view.py:233-235`).
  - The saved briefing (`briefing.md` / `briefing.json`, which the judges score from the logs) never says it.
- **NFR3, never claim complete when not: built.**
  - Any agent failure, stop reason or unassessed cell gives `INCOMPLETE` (`briefing/__init__.py:176-179`).
  - Today's live Q1 run was correctly marked INCOMPLETE.
- **NFR5, no repeated query or tool call: half built.**
  - A repeated search is never run again. It is served from the cache and logged (`SEARCH_CACHE_HIT`).
  - Repeated `get_document`, `get_trade_rows` or `calc` calls are allowed. They are logged, but not stopped.
- **PS 5, cite the final-round pack:** nothing forces the briefing to cite the new pack's documents rather than the base reference documents.
  - In practice the claims are about the event, so they cite event documents. Those will be the live pack's documents, because base documents are background.
  - No test checks this.
- **Off-Runemark sources:** none exist. External lookup is design only and switched off (`docs/EXTERNAL_LOOKUP.md`). Nothing needs labelling.
- **Final round, zero code or index edits for a new pack:** shown by `tests/test_ingestion_synthetic.py` (a generated pack with damaged and odd files) and `tests/test_heimdall_synthetic.py::test_mock_determinism_on_a_second_pack`. The index is built fresh for each case (`search/bm25.py:28-31`), so there is nothing to edit by hand.
- **Found after this review: Odin's own judgement was being thrown away.** In the complete live run (`run-e6d0c56d70`), Odin ruled twice, once per run, as the PS asks. Both times his AI answer was discarded and the fixed rules were used instead (`DETERMINISTIC_FALLBACK`).
  - **Why:** the check on his reasons allowed only numbers that appear in the claim's sentence. Odin quoted the claim's own range ("the no-credit high of 60.3"), which Claude keeps in the estimate fields, not the sentence. On top of that, one failing sentence threw out every ruling in that run.
  - **Fixed** (`backend/agents/odin.py`, `model_pass`): Odin may now quote the claim's own range and its referenced figures. A failing ruling falls back alone, and the others stand. Test: `test_odin_may_quote_the_claims_own_range_and_one_bad_ruling_does_not_sink_the_rest`.
- **Extra risk found today: real-model reliability.** With Claude, agent steps still sometimes fail (answers cut off at the output limit, bookkeeping mistakes in Round 2). Of today's two final live runs, one was COMPLETE and one INCOMPLETE. Most of these were fixed today, but the fixes are uncommitted and only the Q2 run used most of them.
- **Extra risk: budget.** The development ledger stands at **$1.05 of $1.50**. The next Claude run needs the final-round setting (`FINAL_ROUND=1`), which uses the reserve.

---

## 8. Top 5 fixes that would raise the score most

| # | Fix | Size | Files | Or say honestly? |
|---|---|---|---|---|
| 1 | **Commit and push today's fixes, and export one full two-run case into `logs/`.** It is a required submission item, and today's live-run fixes exist only on this machine. | S | the 14 changed files; `scripts/export_logs.py` → `logs/case_<id>/` | No, must be done |
| 2 | **Make live runs finish COMPLETE reliably.** Stop answers being cut off (fewer cells per step for Claude, or a bigger output limit), and run one clean case on each test question. This directly affects range accuracy, debate quality and reliability scores. | M | `backend/llm/factory.py`, `prompts/thor.md`, `prompts/loki.md`, `backend/agents/counsel.py` | Partly: "every failure is caught and the briefing says INCOMPLETE" is true and can be shown |
| 3 | **Say "the other side went unchallenged" in the saved briefing** when Thor or Loki fails. The console already says it; the briefing file, which is scored from the logs, does not. | S | `backend/briefing/__init__.py`, a test | No, small and named in the PS |
| 4 | **Show AC5 and AC9 with a real model:** run two cases back to back on Claude so memory from the first changes a decision in the second, and keep the run where a claim is rejected or conceded. | S (mostly running, about $0.40) | none, or a short demo script; needs `FINAL_ROUND=1` | Yes, for now: "proven by tests with the mock; the code path is the same" |
| 5 | **Close the NFR1 and NFR5 gaps:** add `prompts/heimdall.md` (move the in-code prompt there), and block or cache repeated `get_document` / `get_trade_rows` / `calc` calls. Label premise and dispute paragraphs as "Heimdall verification" so FR4.4 (briefing from Odin's rulings) stays true. | S–M | `prompts/heimdall.md`, `backend/agents/heimdall.py`, `backend/agents/tools.py`, `backend/briefing/__init__.py` | Hybrid search (AC2) is better **said honestly** than rebuilt now: "keyword ranking + metadata filters, no embeddings, by choice: local, explainable, no external index" |
