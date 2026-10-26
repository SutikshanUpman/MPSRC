"""Round 1 for Thor and Loki (SYSTEM_ARCHITECTURE 5.2, 5.3, 16, 17, 19; Stage 2 B1-B8).

Both sides work from one frozen snapshot of the Case File and never see each
other's claims, tools, trace or memory. Each side's events are buffered and the
results are merged in a fixed order (thor, then loki), so the execution order
cannot change the ledgers. Cells are taken batch by batch from the cell plan;
the budget guard re-projects before every batch (cells.next_batch).

An agent step is a loop of model turns through BudgetGuard.call:
  {"action": "tools", "tool_calls": [...]}  -> the runtime runs the tools
  {"action": "submit", "claims": [...], "memory_writes": [...]} -> validated
A submit that fails validation (backend/agents/claims.py) counts as one model
retry; after max_model_retries_per_call, or at max_model_turns_per_agent_step,
the side is FAILED (THOR_FAILED / LOKI_FAILED) and the trial continues with the
other side (section 17, Agent failure and wall-clock states).

Memory: each side reads only its own store (as-of hide rule applied, hides
logged), reports any memory-driven decision, and the runtime logs it as
DECISION_CHANGED only if the memory entry was really read and the change is
visible in that turn's tool calls.
"""
import copy
import json
import re
from pathlib import Path

from ..casefile import model as casefile
from ..ingestion.packs import load_packs
from ..llm.provider import ProviderUnavailable, SchemaError, canonical, is_billable, message_tokens
from ..memory.store import MemoryStore
from ..runtime import cells as cellrules
from ..runtime.budget import BudgetExceeded, BudgetGuard
from ..runtime.trace import TraceLog
from ..search.bm25 import CaseIndex
from .claims import masked_raw_lines, validate_claims
from .normalize import normalize_claims
from .tools import AgentTools

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"
SIDES = ("thor", "loki")
STANCE = {"thor": "HIGH exposure (strongest defensible high case)", "loki": "LIMITED exposure (strongest defensible limited case)"}

TURN_SCHEMA = {
    "type": "object", "required": ["action"],
    "properties": {
        "action": {"type": "string", "enum": ["tools", "submit"]},
        "tool_calls": {"type": "array", "items": {
            "type": "object", "required": ["tool", "args"],
            "properties": {"tool": {"type": "string", "enum": ["search", "get_document", "get_trade_rows", "calc"]},
                           "args": {"type": "object"}}}},
        "claims": {"type": "array"},
        "challenges": {"type": "array"},
        "responses": {"type": "array"},
        "memory_writes": {"type": "array", "items": {"type": "object", "required": ["key", "kind", "value", "source_doc_ids"]}},
        "memory_decisions": {"type": "array", "items": {"type": "object", "required": ["memory_id", "kind", "before", "after"]}},
    },
}


def load_prompt(agent, round_number, run_number=1):
    """The agent's prompt with only this round's section (marked <!-- round:N --> ... <!-- /round:N -->). The Run-2
    section (<!-- run:2 --> ... <!-- /run:2 -->) is added only for the send-back run."""
    text = (PROMPTS / f"{agent}.md").read_text(encoding="utf-8")
    for n in (1, 2):
        if n != round_number:
            text = re.sub(rf"<!-- round:{n} -->.*?<!-- /round:{n} -->\n?", "", text, flags=re.S)
    if run_number != 2:
        text = re.sub(r"<!-- run:2 -->.*?<!-- /run:2 -->\n?", "", text, flags=re.S)
    return re.sub(r"<!-- /?(?:round|run):\d -->\n?", "", text)


class Side:
    def __init__(self, agent, snapshot, corpus, index, config, memory_root):
        self.agent = agent
        self.trace = TraceLog(snapshot["case_id"]).for_side()
        self.tools = AgentTools(agent, snapshot, corpus, index, config, self.trace)
        self.claims, self.status, self.failure = [], "OK", None
        self.steps = self.turns = self.retries = 0
        self.decisions, self.memory_written = [], []
        self.store = MemoryStore(memory_root, agent, agent) if memory_root else None
        self.visible, self.hidden = ([], []) if self.store is None else self.store.read_for_case(snapshot["as_of_date"], snapshot["event_id"])
        for e in self.hidden:
            self.trace.emit(agent, "MEMORY_HIDDEN", {"memory_id": e["memory_id"], "max_source_pub_date": e["max_source_pub_date"],
                                                     "case_as_of": snapshot["as_of_date"]})
        self.trace.emit(agent, "MEMORY_READ", {"memory_ids": [e["memory_id"] for e in self.visible],
                                               "hidden_ids": [e["memory_id"] for e in self.hidden]})


def case_view(side, snapshot, cells, config):
    """Everything the model sees at the start of a step. No case_id or clock, so the input is reproducible."""
    cov = {(c["country"], c["sector"]): c["status"] for c in snapshot["coverage"]}
    return {
        "task": "round_1_claims", "agent": side.agent, "side": STANCE[side.agent], "run": 1, "round": 1,
        "event_id": snapshot["event_id"], "event_name": snapshot["event_name"], "as_of_date": snapshot["as_of_date"],
        "event_origins": snapshot["manifest_scope"]["event_origins"],
        "verification_citations": [c["citation"] for c in snapshot["event_verification"]["citations"]],
        "premise_check": snapshot["premise_check"]["status"],
        "cells": [{"country": c, "sector": s, "coverage": cov.get((c, s))} for c, s in cells],
        "claims_so_far": len(side.claims),
        "supporting_so_far": sum(1 for c in side.claims if c["claim_type"] == "SUPPORTING"),
        "limits": dict({k: config[k] for k in ("max_tool_calls_per_agent_step", "max_model_turns_per_agent_step",
                                               "max_supporting_claims_per_side_per_round", "max_searches_per_agent_per_run")},
                       **config.caps(side.agent)),
        "memory": [{"memory_id": e["memory_id"], "key": e["key"], "kind": e["kind"], "value": e["value"]} for e in side.visible],
    }


def cell_searched(tools, cell):
    """An executed (not cached) search by this agent in this case filtered to the cell's country, boosting its sector."""
    return any(not e["cache_hit"] and cell[0] in e["filters"]["countries"] and cell[1] in e["filters"]["sector_boost"]
               for e in tools.search_log)


def _skip_overrides(side, out, cells, turn):
    """Stage 3 A2: memory may skip or rewrite a query, but every assigned cell keeps at least one executed search.
    A QUERY_SKIPPED that would leave its cell with none (in this case, this turn included) is overridden: the
    skipped query runs anyway and MEMORY_SKIP_OVERRIDDEN is logged. Returns (extra tool calls, overridden ids)."""
    planned = {(tuple(c["args"].get("countries") or []), tuple(c["args"].get("sectors") or []))
               for c in out.get("tool_calls", []) if c.get("tool") == "search"}
    extra, overridden = [], set()
    for d in out.get("memory_decisions", []):
        cell = tuple(d.get("cell") or ())
        if d["kind"] != "QUERY_SKIPPED" or cell not in cells or cell_searched(side.tools, cell):
            continue
        if any(cell[0] in cs and cell[1] in ss for cs, ss in planned):
            continue
        call = {"tool": "search", "args": {"query": d["before"], "countries": [cell[0]], "sectors": [cell[1]], "limit": 5}}
        extra.append(call)
        overridden.add(d["memory_id"])
        side.trace.emit("runtime", "MEMORY_SKIP_OVERRIDDEN", {"agent": side.agent, "memory_id": d["memory_id"],
                                                              "cell": list(cell), "query": d["before"], "turn": turn,
                                                              "reason": "the cell would have no executed search"})
    return extra, overridden


def _log_decisions(side, out, turn, overridden=()):
    visible = {e["memory_id"] for e in side.visible}
    queries = {c["args"].get("query") for c in out.get("tool_calls", []) if c.get("tool") == "search"}
    for d in out.get("memory_decisions", []):
        if d["memory_id"] in overridden:
            side.decisions.append(dict(d, turn=turn, verified=False, overridden=True))
            continue
        verified = d["memory_id"] in visible and (
            (d["kind"] == "QUERY_REWRITTEN" and d["after"] in queries and d["before"] not in queries)
            or (d["kind"] == "QUERY_SKIPPED" and d["before"] not in queries))
        entry = dict(d, turn=turn, verified=verified)
        side.decisions.append(entry)
        side.trace.emit(side.agent, "DECISION_CHANGED" if verified else "DECISION_UNVERIFIED", entry,
                        "INFO" if verified else "WARNING")


def fit_input(side, messages, config):
    """F07: a prompt over the role's input cap is rebuilt once without the oldest tool results, one result at a time
    (the newest tool-result message is kept whole); if it is still over, it is not sent and the turn counts as a
    failed attempt. A dropped result leaves a stub naming the tool, so the agent can fetch it again."""
    cap = config.caps(side.agent)["max_input_tokens"]
    size = message_tokens(messages)
    if size <= cap:
        return messages, None
    rebuilt, dropped = list(messages), 0
    results = [i for i, m in enumerate(rebuilt) if m["role"] == "user" and m["content"].startswith('{"tool_results"')]
    for i in results[:-1]:
        items = json.loads(rebuilt[i]["content"])["tool_results"]
        for j, item in enumerate(items):
            if item.get("dropped"):
                continue
            items[j] = {"tool": item.get("tool"), "args": item.get("args"), "dropped": "input cap"}
            rebuilt[i] = {"role": "user", "content": canonical({"tool_results": items})}
            dropped += 1
            if message_tokens(rebuilt) <= cap:
                break
        if message_tokens(rebuilt) <= cap:
            break
    after = message_tokens(rebuilt)
    side.trace.emit(side.agent, "INPUT_REBUILT", {"input_tokens_before": size, "input_tokens_after": after, "cap": cap,
                                                  "dropped_tool_results": dropped}, "WARNING")
    if after > cap:
        return rebuilt, f"INPUT_CAP_EXCEEDED: about {after} input tokens > max_input_tokens {cap} after the rebuild"
    return rebuilt, None


def _hints(problems):
    """What the model should do about the validator's messages, in plain steps (a small model does not infer the tool order)."""
    text = " ".join(problems)
    hints = []
    if "must narrow the range inside" in text:
        hints.append("A range whose low equals its high is a single point and cannot be narrowed: keep its numbers and qualify the "
                     "wording (a caveat or a narrower scope), or DEFEND with new evidence, or CONCEDE.")
    if "new round-2 calc_id" in text:
        hints.append("A QUALIFY that changes a range needs fresh arithmetic: call `calc` now (in this round) for that cell, then point "
                     "the revised estimate's low_ref/high_ref at the new calc id. If you will not recalculate, DEFEND with new "
                     "evidence instead, or CONCEDE.")
    elif "calc_id" in text or "does not match" in text:
        hints.append("A CELL_ESTIMATE rests on the calc tool: call `calc` for each cell first, then set calc_ids to the ids it returns "
                     "(like calc-r1-thor-01) and low_ref/high_ref to its fields. Do not type trade figures yourself.")
    if "citation" in text:
        hints.append("Cite only documents your search or get_document returned, each as one bracket [DOC_ID, P#, timestamp].")
    if "CELL_ESTIMATE claims" in text:
        hints.append("Submit exactly one CELL_ESTIMATE for every cell in your batch: run `calc` for the cells still missing one, then submit all together.")
    return hints or ["Fix each problem and submit again."]


def model_loop(side, messages, provider, guard, config, on_tools, on_submit):
    """One agent step (F07): model turns through the guard; tool turns run tools, a submit is validated.
    `on_tools(out, turn)` returns the tool results; `on_submit(out, turn)` returns problems (empty = accepted).
    A failed validation, an over-cap prompt or a schema error is one retry; the step fails at
    max_model_retries_per_call or at max_model_turns_per_agent_step. Returns (out, turn, retries)."""
    retries, problems = 0, []
    for turn in range(1, config["max_model_turns_per_agent_step"] + 1):
        side.turns += 1
        messages, over_cap = fit_input(side, messages, config)
        if over_cap:
            out, problems = None, [over_cap]
        else:
            try:
                out = guard.call(provider, side.agent, messages, TURN_SCHEMA)["output"]
            except SchemaError as e:
                out, problems = None, [f"output does not match the turn schema: {e}"]
            except ProviderUnavailable as e:
                out, problems = None, [f"FALLBACK_LLM_RETRY: {e}"]
        if out is not None:
            messages.append({"role": "assistant", "content": canonical(out)})
            try:
                if out["action"] == "tools":
                    messages.append({"role": "user", "content": canonical({"tool_results": on_tools(out, turn)})})
                    continue
                problems = on_submit(out, turn)
            except Exception as e:                    # what a model wrote is untrusted: a bad shape is a failed attempt, never a crash
                problems = [f"your output could not be processed ({type(e).__name__}: {e}); follow the output schema exactly"]
            if not problems:
                return out, turn, retries
        retries += 1
        side.retries += 1
        side.trace.emit(side.agent, "CLAIM_VALIDATION_FAILED", {"attempt": retries, "problems": problems[:20]}, "WARNING")
        if retries > config["max_model_retries_per_call"]:
            raise StepFailed(f"validation failed {retries} times (max_model_retries_per_call="
                             f"{config['max_model_retries_per_call']})", problems)
        messages.append({"role": "user", "content": canonical({"validation_errors": problems, "what_to_do": _hints(problems)})})
    raise StepFailed(f"no valid output within max_model_turns_per_agent_step={config['max_model_turns_per_agent_step']}", problems)


def run_step(side, snapshot, cells, corpus, provider, guard, config, masked):
    side.steps += 1
    side.tools.begin_step()
    side.trace.emit(side.agent, "AGENT_STEP_STARTED", {"cells": [[c, s] for c, s in cells]})
    messages = [{"role": "system", "content": load_prompt(side.agent, 1)},
                {"role": "user", "content": canonical(case_view(side, snapshot, cells, config))}]

    def on_tools(out, turn):
        extra, overridden = _skip_overrides(side, out, cells, turn)
        _log_decisions(side, out, turn, overridden)
        results = [side.tools.execute(c) for c in out.get("tool_calls", [])]
        return results + [dict(side.tools.execute(c), runtime_override="MEMORY_SKIP_OVERRIDDEN") for c in extra]

    def on_submit(out, turn):
        _log_decisions(side, out, turn)
        out["claims"] = normalize_claims(out.get("claims", []), side.agent, 1, 1, side.tools,
                                         taken={c["claim_id"] for c in side.claims})     # the runtime fills the paperwork
        problems = validate_claims(side.agent, out.get("claims", []), set(cells), side.tools, snapshot, corpus, config,
                                   masked, prior=side.claims)
        return problems + [f"cell {c}: no executed search by {side.agent} in this case (every cell needs one)"
                           for c in cells if not cell_searched(side.tools, c)]

    out, turn, retries = model_loop(side, messages, provider, guard, config, on_tools, on_submit)
    claims = out.get("claims", [])
    side.trace.emit(side.agent, "CLAIMS_SUBMITTED", {"claim_ids": [c["claim_id"] for c in claims], "turn": turn})
    side.trace.emit(side.agent, "AGENT_STEP_COMPLETED", {"turns": turn, "retries": retries})
    return claims, out.get("memory_writes", [])


class StepFailed(RuntimeError):
    def __init__(self, reason, problems):
        super().__init__(reason)
        self.reason, self.problems = reason, problems


def _write_memory(side, writes, snapshot, corpus):
    if side.store is None:
        return
    retrieved_docs = {v["doc_id"] for v in side.tools.retrieved.values()}
    pub_dates = {d: r["pub_date"] for d, r in corpus.records.items()}
    for w in writes:
        doc_ids = [d for d in w["source_doc_ids"] if d in retrieved_docs]
        value = w["value"]
        if not isinstance(value, dict):                    # a memory value is an object; a plain note becomes one
            value = {"note": str(value)}
        if w["kind"] == "case_note":
            value = dict(value, event_id=snapshot["event_id"])     # a case note belongs to the event it was written for
        entry = side.store.write(w["key"], w["kind"], value, doc_ids, pub_dates, snapshot["as_of_date"],
                                 snapshot["case_id"])
        if entry:
            side.memory_written.append(entry["memory_id"])
            side.trace.emit(side.agent, "MEMORY_WRITTEN", {"memory_id": entry["memory_id"], "key": entry["key"],
                                                           "source_doc_ids": entry["source_doc_ids"],
                                                           "max_source_pub_date": entry["max_source_pub_date"],
                                                           "written_as_of": entry["written_as_of"]})


def _resize_batches(cf, sides, snapshot, config, trace):
    """Stage 3 A4: fewer cells per step when a step's projected input would pass batch_input_target_share of the
    role's input cap. The projection is the step's fixed part (prompt + case view) plus per-cell estimates."""
    base = max(message_tokens([{"role": "system", "content": load_prompt(a, 1)},
                               {"role": "user", "content": canonical(case_view(sides[a], snapshot, [], config))}])
               for a in SIDES)
    cap = min(config.caps(a)["max_input_tokens"] for a in SIDES)
    resized, projections = cellrules.resize_batches(cf["cell_plan"], base, cap, config["batch_input_target_share"],
                                                    config["max_cells_per_agent_step"], config["batch_token_estimates"])
    cf["budget_projection"]["batch_input_projection"] = projections
    if resized:
        trace.emit("runtime", "BATCH_RESIZED", {"max_cells_per_agent_step": config["max_cells_per_agent_step"],
                                                "input_cap": cap, "target_share": config["batch_input_target_share"],
                                                "fixed_tokens": base, "batches": projections})


def run_round1(cf, provider, config, trace, memory_root=None, order=SIDES, guard=None):
    """Run Round 1 on an OPEN Case File. Returns {agent: Side}. Mutates cf (claim_ledger, calc_ledger, cell_plan, run_status)."""
    corpus, _, _ = load_packs(cf["pack_paths"])
    allow = tuple(config.get("allow_hash_mismatch_doc_ids") or ())
    index = CaseIndex(corpus, cf["as_of_date"], cf["event_id"], allow_hash_mismatch=allow)
    masked = masked_raw_lines(corpus)
    guard = guard or BudgetGuard(config, billable=is_billable(provider))
    snapshot = copy.deepcopy(cf)
    trace.emit("runtime", "ROUND_1_STARTED", {"sides": list(SIDES), "cells": len(cf["exposure_cells"])})
    sides = {a: Side(a, snapshot, corpus, index, config, memory_root) for a in SIDES}
    _resize_batches(cf, sides, snapshot, config, trace)
    stop_reason = None
    while True:
        number, batch = cellrules.next_batch(cf["cell_plan"], guard)
        if number is None:
            if any(c["cell_status"] == cellrules.BUDGET_LIMIT for c in cf["cell_plan"]):
                stop_reason = "INCOMPLETE_BUDGET_LIMIT"
            break
        cells = [(c["country"], c["sector"]) for c in batch]
        for agent in order:
            side = sides[agent]
            if side.status != "OK":
                continue
            try:
                claims, writes = run_step(side, snapshot, cells, corpus, provider, guard, config, masked)
                side.claims += claims
                _write_memory(side, writes, snapshot, corpus)
            except StepFailed as e:
                calls = [c for c in guard.calls if c["role"] == agent]
                side.status = f"{agent.upper()}_FAILED"
                side.failure = {"reason": e.reason, "problems": e.problems[:20], "step": side.steps, "run": 1, "round": 1,
                                "attempts": side.retries, "last_error": (e.problems or [e.reason])[0],
                                "input_tokens": sum(c["input_tokens"] for c in calls),
                                "output_tokens": sum(c["output_tokens"] for c in calls),
                                "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
                                "shadow_cost_usd": round(sum(c["shadow_cost_usd"] for c in calls), 6)}
                side.trace.emit("runtime", "AGENT_FAILED", {"agent": agent, "state": side.status, **side.failure}, "WARNING")
            except BudgetExceeded as e:
                stop_reason = "INCOMPLETE_BUDGET_LIMIT"
                side.trace.emit("runtime", "BUDGET_CAP_REACHED", {"agent": agent, "detail": str(e)}, "WARNING")
        if stop_reason:
            for c in cf["cell_plan"]:
                if c["cell_status"] == cellrules.PENDING:
                    c["cell_status"] = cellrules.BUDGET_LIMIT
            break
        cellrules.mark(cf["cell_plan"], number, cellrules.ASSESSED)

    for agent in SIDES:                      # fixed merge order: execution order cannot change the ledgers
        for e in sides[agent].trace.events:
            trace.emit(e["actor"], e["event_type"], e["payload"], e["level"])
    log_shared_queries(sides, trace, set())
    cf["claim_ledger"] = [dict(c, superseded_by=None) for a in SIDES for c in sides[a].claims]
    cf["calc_ledger"] = [r for a in SIDES for r in sides[a].tools.calcs]
    run = cf["run_status"][0]
    run["state"] = "ROUND_1_COMPLETED"
    run["stop_reason"] = run["stop_reason"] or stop_reason
    run["round_1"] = {"agents": {a: _side_summary(sides[a], guard) for a in SIDES},
                      "agent_failures": [{"agent": a, "state": sides[a].status, **sides[a].failure}
                                         for a in SIDES if sides[a].failure]}
    run["llm_calls"] = len(guard.calls)
    trace.emit("runtime", "ROUND_1_COMPLETED", {"claims": len(cf["claim_ledger"]), "calcs": len(cf["calc_ledger"]),
                                                "failures": [a for a in SIDES if sides[a].failure]})
    casefile.validate(cf)
    return sides


def log_shared_queries(sides, trace, reported):
    """Spec md 1556 (Stage 3 A3): caches are per agent, so an identical query run by both agents runs twice.
    That is expected: log it once at INFO. `reported` holds keys already logged (rounds 1 and 2)."""
    executed = {a: {(e["query"], json.dumps(e["filters"], sort_keys=True)) for e in sides[a].tools.search_log
                    if not e["cache_hit"]} for a in SIDES}
    for query, filters in sorted(executed[SIDES[0]] & executed[SIDES[1]] - reported):
        reported.add((query, filters))
        trace.emit("runtime", "SEARCH_SHARED_QUERY", {"query": query, "filters": json.loads(filters), "agents": list(SIDES)})


def _side_summary(side, guard):
    calls = [c for c in guard.calls if c["role"] == side.agent]
    return {"status": side.status, "steps": side.steps, "turns": side.turns, "retries": side.retries,
            "tool_calls": side.tools.tool_calls, "searches": side.tools.searches, "cache_hits": side.tools.cache_hits,
            "claims": len(side.claims), "calcs": len(side.tools.calcs),
            "memory_read": [e["memory_id"] for e in side.visible], "memory_hidden": [e["memory_id"] for e in side.hidden],
            "memory_written": side.memory_written, "decisions_changed": [d for d in side.decisions if d["verified"]],
            "model_calls": len(calls), "input_tokens_est": sum(c["input_tokens"] for c in calls),
            "output_tokens_est": sum(c["output_tokens"] for c in calls),
            "shadow_cost_usd": round(sum(c["shadow_cost_usd"] for c in calls), 6), "failure": side.failure}
