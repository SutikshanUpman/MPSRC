"""Round 2: cross-examination (SYSTEM_ARCHITECTURE 18, md 1850-1897; Stage 3 B1-B4).

Two phases. In each, both sides work from one frozen snapshot, so the execution order cannot change the output.
  A. challenge: each side reads the other side's round-1 ledger through the masked Case File (claims, calc
     views, cited-source metadata; never the other side's memory, tools or trace) and files between 1 and
     max_challenges_per_side_per_round challenges, at most one per target claim, each with its own citations.
  B. respond: each side answers every challenge against it:
       DEFEND  new evidence: at least one cited span it retrieved in round 2 and did not cite in round 1;
       QUALIFY a revised claim that supersedes the target and is narrower (a CELL_ESTIMATE range inside the
               original one); a new round-2 calc_id when its numbers change;
       CONCEDE a SUPPORTING claim withdrawn with a reason (an estimate cannot be withdrawn: every cell keeps one).
Any rule violation is a failed attempt (F07). A side whose phase step fails is <AGENT>_FAILED for round 2: its
challenges or answers are missing, and a challenge left unanswered keeps `response: null`.
"""
import copy
import json

from ..casefile import model as casefile
from ..casefile.schema import CHALLENGE_SCHEMA, CLAIM_SCHEMA, RESPONSE_SCHEMA
from ..llm.provider import canonical, validate_schema
from ..provenance.citations import parse_citations
from ..runtime.budget import BudgetExceeded
from ..runtime.trace import TraceLog
from .calc import agent_view, field
from .claims import NUMBER, _norm_num, check_citations, check_claim, has_masked_text, masked_raw_lines, number_tokens
from .counsel import SIDES, STANCE, StepFailed, load_prompt, log_shared_queries, model_loop

OTHER = {"thor": "loki", "loki": "thor"}


def source_meta(corpus, citation):
    parsed = parse_citations(citation)
    rec = corpus.records.get(parsed[0]["doc_id"]) if len(parsed) == 1 else None
    if rec is None:
        return None
    return {"doc_id": rec["doc_id"], "tier": rec["reliability"], "source_type": rec["source_type"],
            "event_id": rec["event_id"], "pub_date": rec["pub_date"], "context_only": rec["background_only"],
            "evidence_family_id": rec["evidence_family_id"] or rec["doc_id"]}


def _round1_claims(cf, agent):
    return [c for c in cf["claim_ledger"] if c["agent"] == agent and c["round"] == 1]


def _calc_views(cf, claims):
    ids = {cid for c in claims for cid in c["calc_ids"]}
    return {r["calc_id"]: agent_view(r) for r in cf["calc_ledger"] if r["calc_id"] in ids}


def _common(side, snapshot, config, task):
    return {"task": task, "agent": side.agent, "side": STANCE[side.agent], "run": 1, "round": 2,
            "event_id": snapshot["event_id"], "event_name": snapshot["event_name"], "as_of_date": snapshot["as_of_date"],
            "event_origins": snapshot["manifest_scope"]["event_origins"],
            "limits": dict({k: config[k] for k in ("max_tool_calls_per_agent_step", "max_model_turns_per_agent_step",
                                                    "max_challenges_per_side_per_round", "max_searches_per_agent_per_run",
                                                    "baseline_crosscheck_tolerance_pct_points")},
                           **config.caps(side.agent))}


def challenge_view(side, snapshot, corpus, config):
    """The masked Case File as the challenger sees it: the opponent's round-1 ledger only."""
    claims = _round1_claims(snapshot, OTHER[side.agent])
    cited = sorted({cit for c in claims for cit in c["citations"]})
    return dict(_common(side, snapshot, config, "round_2_challenge"), opponent=OTHER[side.agent], opponent_claims=claims,
                opponent_calcs=_calc_views(snapshot, claims), cited_sources={c: source_meta(corpus, c) for c in cited})


def response_view(side, snapshot, challenges, corpus, config):
    mine = {c["claim_id"]: c for c in snapshot["claim_ledger"] if c["agent"] == side.agent}
    targets = [mine[ch["target_claim_id"]] for ch in challenges]
    cited = sorted({cit for ch in challenges for cit in ch["citations"]} | {cit for c in targets for cit in c["citations"]})
    return dict(_common(side, snapshot, config, "round_2_response"), challenges=challenges, my_claims=targets,
                my_calcs=_calc_views(snapshot, targets), cited_sources={c: source_meta(corpus, c) for c in cited},
                my_round1_citations=sorted({cit for c in _round1_claims(snapshot, side.agent) for cit in c["citations"]}),
                claims_so_far=len(mine))


def _check_text_numbers(where, texts, number_refs, citations, calcs, tools):
    """Every number in the texts has a number_ref to a calc field (any calc in the Case File) or to a whole number
    in one of the item's own cited spans (section 22)."""
    problems, refs = [], set()
    for ref in number_refs:
        refs.add(_norm_num(ref["value"]))
        if "calc_id" in ref:
            try:
                value = field(calcs[ref["calc_id"]], ref["field"])
            except (KeyError, TypeError):
                value = None
            if value is None or round(float(value), 1) != round(float(_norm_num(ref["value"])), 1):
                problems.append(f"{where}: number {ref['value']} does not match {ref.get('calc_id')}:{ref.get('field')}")
        elif "citation" in ref:
            span = tools.retrieved.get(ref["citation"])
            if span is None or ref["citation"] not in citations or \
                    _norm_num(ref["value"]) not in {_norm_num(t) for t in NUMBER.findall(span["text"])}:
                problems.append(f"{where}: number {ref['value']} is not in a cited span {ref['citation']}")
        else:
            problems.append(f"{where}: number_ref {ref['value']} has neither calc_id nor citation")
    for text in texts:
        for token in number_tokens(text):
            if _norm_num(token) not in refs:
                problems.append(f"{where}: number {token} has no span or calc_id")
    return problems


def validate_challenges(agent, challenges, snapshot, tools, corpus, config, masked):
    problems = []
    if not isinstance(challenges, list):
        return ["challenges must be a list"]
    cap = config["max_challenges_per_side_per_round"]
    if not 1 <= len(challenges) <= cap:
        problems.append(f"{len(challenges)} challenges: at least 1 and at most max_challenges_per_side_per_round={cap}")
    targets = {c["claim_id"] for c in _round1_claims(snapshot, OTHER[agent])}
    calcs = {r["calc_id"]: r for r in snapshot["calc_ledger"]}
    seen_ids, seen_targets = set(), set()
    for i, ch in enumerate(challenges):
        where = f"challenges[{i}]"
        errs = validate_schema(ch, CHALLENGE_SCHEMA, where)
        if errs:
            problems += errs
            continue
        if ch["challenger"] != agent or ch["target_agent"] != OTHER[agent] or not ch["challenge_id"].startswith(f"challenge-{agent}-"):
            problems.append(f"{where}: challenger/target agent mismatch")
        if ch["challenge_id"] in seen_ids:
            problems.append(f"{where}: duplicate challenge_id")
        seen_ids.add(ch["challenge_id"])
        if ch["target_claim_id"] not in targets:
            problems.append(f"{where}: {ch['target_claim_id']} is not a round-1 claim of {OTHER[agent]}")
        if ch["target_claim_id"] in seen_targets:
            problems.append(f"{where}: {ch['target_claim_id']} is already challenged")
        seen_targets.add(ch["target_claim_id"])
        if (ch["run"], ch["round"]) != (1, 2):
            problems.append(f"{where}: a challenge belongs to run 1, round 2")
        if not ch["citations"]:
            problems.append(f"{where}: a challenge needs at least one citation of its own")
        problems += check_citations(where, agent, ch["citations"], tools, snapshot, corpus)
        problems += _check_text_numbers(where, [ch["challenge_text"]], ch["number_refs"], ch["citations"], calcs, tools)
        if has_masked_text(ch["challenge_text"], masked):
            problems.append(f"{where}: challenge text contains masked document text")
    return problems


def validate_responses(agent, out, challenges, snapshot, tools, corpus, config, masked):
    """B2. Returns problems; the revised claims are out['claims'] (each must be named by a QUALIFY)."""
    responses, revised = out.get("responses", []), out.get("claims", [])
    if not isinstance(responses, list) or not isinstance(revised, list):
        return ["responses and claims must be lists"]
    problems = []
    ledger = {c["claim_id"]: c for c in snapshot["claim_ledger"]}
    round1_cites = {cit for c in _round1_claims(snapshot, agent) for cit in c["citations"]}
    new_round2 = tools.retrieved_in(2)
    round2_calcs = {r["calc_id"] for r in tools.calcs if r.get("round") == 2}
    calcs = {r["calc_id"]: r for r in snapshot["calc_ledger"] + tools.calcs}
    by_id = {}
    for i, c in enumerate(revised):
        where = f"claims[{i}]"
        errs = validate_schema(c, CLAIM_SCHEMA, where)
        if errs:
            problems += errs
            continue
        if c["claim_id"] in ledger or c["claim_id"] in by_id:
            problems.append(f"{where}: claim_id {c['claim_id']} is already used")
        if (c["run"], c["round"]) != (1, 2):
            problems.append(f"{where}: a revised claim belongs to run 1, round 2")
        problems += check_claim(where, agent, c, tools, snapshot, corpus, masked)
        by_id[c["claim_id"]] = c
    answered, used = set(), set()
    expected = {ch["challenge_id"]: ch for ch in challenges}
    for i, r in enumerate(responses):
        where = f"responses[{i}]"
        errs = validate_schema(r, RESPONSE_SCHEMA, where)
        if errs:
            problems += errs
            continue
        ch = expected.get(r["challenge_id"])
        if ch is None:
            problems.append(f"{where}: {r['challenge_id']} is not a challenge against {agent}")
            continue
        if r["challenge_id"] in answered:
            problems.append(f"{where}: {r['challenge_id']} answered twice")
        answered.add(r["challenge_id"])
        if r["responder"] != agent or not r["response_id"].startswith(f"response-{agent}-") or \
                r["target_claim_id"] != ch["target_claim_id"]:
            problems.append(f"{where}: responder or target does not match the challenge")
        problems += check_citations(where, agent, r["citations"], tools, snapshot, corpus)
        problems += _check_text_numbers(where, [r["response_text"], r["reason"] or ""], r["number_refs"], r["citations"],
                                        calcs, tools)
        if has_masked_text(" ".join([r["response_text"], r["reason"] or ""]), masked):
            problems.append(f"{where}: response text contains masked document text")
        target = ledger[ch["target_claim_id"]]
        kind = r["response_type"]
        if kind == "DEFEND":
            if not r["new_evidence"]:
                problems.append(f"{where}: DEFEND needs new evidence (a span retrieved in round 2, not cited in round 1)")
            for cit in r["new_evidence"]:
                if cit not in r["citations"]:
                    problems.append(f"{where}: new evidence {cit} is not among the response's citations")
                if cit in round1_cites:
                    problems.append(f"{where}: {cit} was already cited in round 1, so it is not new evidence")
                if cit not in new_round2:
                    problems.append(f"{where}: {cit} was not retrieved by {agent} in round 2")
        elif kind == "QUALIFY":
            new = by_id.get(r["revised_claim_id"])
            if new is None:
                problems.append(f"{where}: QUALIFY needs revised_claim_id naming a revised claim in this submission")
                continue
            used.add(new["claim_id"])
            problems += _check_revision(where, new, target, round2_calcs)
        else:
            if target["claim_type"] == "CELL_ESTIMATE":
                problems.append(f"{where}: a CELL_ESTIMATE cannot be conceded (every cell keeps one): QUALIFY it")
            if not (r["reason"] or "").strip():
                problems.append(f"{where}: CONCEDE needs an explicit reason")
        if kind != "QUALIFY" and r["revised_claim_id"] is not None:
            problems.append(f"{where}: only a QUALIFY names a revised claim")
    for cid in expected:
        if cid not in answered:
            problems.append(f"{cid}: no response (every challenge needs DEFEND, QUALIFY or CONCEDE)")
    for cid in by_id:
        if cid not in used:
            problems.append(f"{cid}: a round-2 claim must be the revision named by a QUALIFY")
    return problems


def _check_revision(where, new, target, round2_calcs):
    problems = []
    if new["supersedes"] != target["claim_id"]:
        problems.append(f"{where}: the revised claim must supersede {target['claim_id']}")
    if (new["claim_type"], new["country"], new["sector"]) != (target["claim_type"], target["country"], target["sector"]):
        problems.append(f"{where}: the revised claim must keep the target's type and cell")
    if target["claim_type"] == "CELL_ESTIMATE" and target["estimate"] and new["estimate"]:
        old, est = target["estimate"], new["estimate"]
        if not (old["low"] <= est["low"] <= est["high"] <= old["high"]) or (est["low"], est["high"]) == (old["low"], old["high"]):
            problems.append(f"{where}: QUALIFY must narrow the range inside [{old['low']}, {old['high']}]")
        if not set(new["calc_ids"]) & round2_calcs:
            problems.append(f"{where}: changed numbers need a new round-2 calc_id")
    elif new["claim_text"] == target["claim_text"]:
        problems.append(f"{where}: QUALIFY must change the claim")
    return problems


def _new_trace(side, case_id):
    side.trace = TraceLog(case_id).for_side()
    side.tools.trace = side.trace


def _merge(trace, sides, agents):
    for agent in SIDES:                      # fixed merge order, as in round 1
        if agent in agents:
            for e in sides[agent].trace.events:
                trace.emit(e["actor"], e["event_type"], e["payload"], e["level"])


def _phase_step(side, view, task, provider, guard, config, on_submit):
    side.steps += 1
    side.tools.begin_step()
    side.trace.emit(side.agent, "AGENT_STEP_STARTED", {"cells": [], "task": task})
    messages = [{"role": "system", "content": load_prompt(side.agent, 2)}, {"role": "user", "content": canonical(view)}]
    out, turn, retries = model_loop(side, messages, provider, guard, config,
                                    lambda o, t: [side.tools.execute(c) for c in o.get("tool_calls", [])], on_submit)
    side.trace.emit(side.agent, "AGENT_STEP_COMPLETED", {"turns": turn, "retries": retries, "task": task})
    return out


def _fail(side, phase, e, guard):
    calls = [c for c in guard.calls if c["role"] == side.agent]
    side.r2_status = f"{side.agent.upper()}_FAILED"
    side.r2_failure = {"reason": e.reason, "problems": e.problems[:20], "step": side.steps, "run": 1, "round": 2,
                       "phase": phase, "attempts": side.retries, "last_error": (e.problems or [e.reason])[0],
                       "input_tokens": sum(c["input_tokens"] for c in calls), "output_tokens": sum(c["output_tokens"] for c in calls),
                       "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
                       "shadow_cost_usd": round(sum(c["shadow_cost_usd"] for c in calls), 6)}
    side.trace.emit("runtime", "AGENT_FAILED", {"agent": side.agent, "state": side.r2_status, **side.r2_failure}, "WARNING")


def run_round2(cf, sides, provider, config, trace, guard, order=SIDES):
    """Round 2 on a Case File after Round 1 (`sides` from run_round1). Mutates cf: cross_examination, claim_ledger
    (round-2 revisions appended, superseded / withdrawn statuses), calc_ledger, run_status[0].round_2."""
    corpus = sides[SIDES[0]].tools.corpus
    masked = masked_raw_lines(corpus)
    snapshot = copy.deepcopy(cf)
    active = [a for a in SIDES if sides[a].status == "OK" and _round1_claims(cf, a)]
    trace.emit("runtime", "ROUND_2_STARTED", {"sides": active})
    for a in SIDES:
        side = sides[a]
        side.r2_status, side.r2_failure, side.challenges, side.responses, side.revised = "OK", None, [], [], []
        side.r2_start = {"steps": side.steps, "turns": side.turns, "retries": side.retries, "tool_calls": side.tools.tool_calls,
                         "searches": side.tools.searches, "cache_hits": side.tools.cache_hits, "calls": len(guard.calls)}
        side.tools.round = 2
        _new_trace(side, cf["case_id"])
    stop_reason = None

    # A. challenges (both from the same snapshot)
    for agent in order:
        side = sides[agent]
        if agent not in active or OTHER[agent] not in active:
            continue
        view = challenge_view(side, snapshot, corpus, config)
        try:
            out = _phase_step(side, view, "challenge", provider, guard, config,
                              lambda o, t: validate_challenges(agent, o.get("challenges", []), snapshot, side.tools, corpus,
                                                               config, masked))
            side.challenges = out["challenges"]
            side.trace.emit(agent, "CHALLENGES_SUBMITTED", {"challenge_ids": [c["challenge_id"] for c in side.challenges],
                                                            "targets": [c["target_claim_id"] for c in side.challenges],
                                                            "kinds": [c["challenge_kind"] for c in side.challenges]})
        except StepFailed as e:
            _fail(side, "challenge", e, guard)
        except BudgetExceeded as e:
            stop_reason = "INCOMPLETE_BUDGET_LIMIT"
            side.trace.emit("runtime", "BUDGET_CAP_REACHED", {"agent": agent, "detail": str(e)}, "WARNING")
    _merge(trace, sides, SIDES)

    # B. responses (both from the snapshot after phase A)
    against = {a: [c for b in SIDES for c in sides[b].challenges if c["target_agent"] == a] for a in SIDES}
    for a in SIDES:
        _new_trace(sides[a], cf["case_id"])
    for agent in order:
        side = sides[agent]
        if not against[agent] or side.r2_status != "OK" or stop_reason:
            continue
        view = response_view(side, snapshot, against[agent], corpus, config)
        try:
            out = _phase_step(side, view, "response", provider, guard, config,
                              lambda o, t: validate_responses(agent, o, against[agent], snapshot, side.tools, corpus,
                                                              config, masked))
            side.responses, side.revised = out.get("responses", []), out.get("claims", [])
            side.trace.emit(agent, "RESPONSES_SUBMITTED", {"response_ids": [r["response_id"] for r in side.responses],
                                                           "types": [r["response_type"] for r in side.responses],
                                                           "revised_claim_ids": [c["claim_id"] for c in side.revised]})
        except StepFailed as e:
            _fail(side, "response", e, guard)
        except BudgetExceeded as e:
            stop_reason = "INCOMPLETE_BUDGET_LIMIT"
            side.trace.emit("runtime", "BUDGET_CAP_REACHED", {"agent": agent, "detail": str(e)}, "WARNING")
    _merge(trace, sides, SIDES)

    log_shared_queries(sides, trace, {(e["payload"]["query"], json.dumps(e["payload"]["filters"], sort_keys=True))
                                      for e in trace.of_type("SEARCH_SHARED_QUERY")})
    _apply(cf, sides, trace)
    run = cf["run_status"][0]
    run["state"] = "ROUND_2_COMPLETED"
    run["stop_reason"] = run["stop_reason"] or stop_reason
    run["round_2"] = {"agents": {a: _summary(sides[a], guard) for a in SIDES},
                      "agent_failures": [dict(sides[a].r2_failure, agent=a, state=sides[a].r2_status)
                                         for a in SIDES if sides[a].r2_failure],
                      "concessions": sum(r["response_type"] == "CONCEDE" for a in SIDES for r in sides[a].responses),
                      "qualifications": sum(r["response_type"] == "QUALIFY" for a in SIDES for r in sides[a].responses),
                      "unanswered": [x["challenge_id"] for x in cf["cross_examination"] if x["response"] is None]}
    run["llm_calls"] = len(guard.calls)
    trace.emit("runtime", "ROUND_2_COMPLETED", {"challenges": len(cf["cross_examination"]),
                                                "responses": sum(len(sides[a].responses) for a in SIDES),
                                                "revised_claims": sum(len(sides[a].revised) for a in SIDES),
                                                "failures": [a for a in SIDES if sides[a].r2_failure]})
    casefile.validate(cf)
    return sides


def _apply(cf, sides, trace):
    """B3: round-2 revisions supersede their targets (both kept, linked both ways); concessions withdraw."""
    responses = {r["challenge_id"]: r for a in SIDES for r in sides[a].responses}
    cf["cross_examination"] = [dict(ch, response=responses.get(ch["challenge_id"])) for a in SIDES for ch in sides[a].challenges]
    ledger = {c["claim_id"]: c for c in cf["claim_ledger"]}
    for a in SIDES:
        for r in sides[a].responses:
            target = ledger[r["target_claim_id"]]
            if r["response_type"] == "QUALIFY":
                target["status"], target["superseded_by"] = "superseded", r["revised_claim_id"]
                trace.emit("runtime", "CLAIM_SUPERSEDED", {"claim_id": target["claim_id"], "superseded_by": r["revised_claim_id"],
                                                           "challenge_id": r["challenge_id"]})
            elif r["response_type"] == "CONCEDE":
                target["status"] = "withdrawn"
                trace.emit("runtime", "CLAIM_CONCEDED", {"claim_id": target["claim_id"], "challenge_id": r["challenge_id"],
                                                         "reason": r["reason"]})
    cf["claim_ledger"] += [dict(c, superseded_by=None) for a in SIDES for c in sides[a].revised]
    cf["calc_ledger"] = [r for a in SIDES for r in sides[a].tools.calcs]


def _summary(side, guard):
    s0 = side.r2_start
    calls = [c for c in guard.calls[s0["calls"]:] if c["role"] == side.agent]
    return {"status": side.r2_status, "steps": side.steps - s0["steps"], "turns": side.turns - s0["turns"],
            "retries": side.retries - s0["retries"], "tool_calls": side.tools.tool_calls - s0["tool_calls"],
            "searches": side.tools.searches - s0["searches"], "cache_hits": side.tools.cache_hits - s0["cache_hits"],
            "challenges": [c["challenge_id"] for c in side.challenges],
            "responses": {t: sum(r["response_type"] == t for r in side.responses) for t in ("DEFEND", "QUALIFY", "CONCEDE")},
            "revised_claims": [c["claim_id"] for c in side.revised], "model_calls": len(calls),
            "input_tokens_est": sum(c["input_tokens"] for c in calls), "output_tokens_est": sum(c["output_tokens"] for c in calls),
            "shadow_cost_usd": round(sum(c["shadow_cost_usd"] for c in calls), 6), "failure": side.r2_failure}
