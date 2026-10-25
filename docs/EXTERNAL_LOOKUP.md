# External web lookup: design only, OFF

Status: **not implemented.** This note describes an adapter that could be added for real-world cases. It is disabled by default (`EXTERNAL_LOOKUP=0`) and stays that way for this hackathon.

## Why it is off here

The corpus is the only allowed evidence. Every claim, ruling and briefing line must carry a `[DOC_ID, P#, timestamp]` citation that resolves in the case scope, is dated on or before the as-of date and was retrieved by the claimant. A web page has no manifest entry, no tier, no hash and no stable paragraph id, so any citation to it would fail citation validity (`guards.citation_guard`, `odin.pre_ruling`: `INVALID_CITATION`, `OUT_OF_CASE_SCOPE`). Allowing it would also break the as-of gate, which is what keeps the trial reproducible: a live page can change or post-date the question.

## Rules if it were ever enabled

1. **Switch.** `EXTERNAL_LOOKUP=1` in the environment and `external_lookup.enabled` in the runtime config, both set by the budget owner. Default 0.
2. **Label.** Every result is tagged `EXTERNAL` with its URL, fetch time and a content hash. It never receives a tier, a `doc_id` or a `P#`.
3. **Not evidence.** An EXTERNAL result is never cited by a claim, never counts in a ruling, never feeds a calc record or an exposure range, and never appears in the briefing's findings, exposure table or citations. The pre-ruling checks reject any citation that is not a corpus span, so this is enforced, not promised.
4. **Where it shows.** Only in a separate "Outside context" panel of the dashboard and an "Outside context" appendix of the briefing, each item marked EXTERNAL and not verified. Nothing in that panel is used by the trial.
5. **Cost.** Every lookup is counted in the project ledger (`data/ledger.json`) and in the case's budget guard like a model call, under its own role, and obeys the per-case cap and the final-round reserve. A lookup that does not fit is skipped and logged as `FALLBACK_EXTERNAL_LOOKUP_SKIPPED`.
6. **Injection.** Fetched text goes through the same masking as a document (`backend/ingestion/quality.py`) before anyone reads it, and is stored hashed in the run record, so a replay shows the same outside context.
7. **Replay.** Lookup results are recorded in `llm_calls.jsonl`-style records and replayed from there; a replay never touches the network.

## Where it would plug in

A new `backend/runtime/external.py` returning `[{label: "EXTERNAL", url, fetched_at, sha256, text}]`, called by the orchestrator after the briefing is built and written to `external_context.json`. No agent tool, no ruling, no guard would change.
