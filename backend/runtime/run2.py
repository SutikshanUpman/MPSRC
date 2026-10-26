"""Run 2: the send-back (SYSTEM_ARCHITECTURE section 17 Run 2; FINAL BUILD 1.3).

After Odin's first ruling the runtime checks sufficiency cell by cell. A cell is sufficient when Odin gave it a
range and Heimdall's coverage test left no evidence gap. Every other cell goes back ONCE, with a gap list:

  1. Heimdall re-searches the gaps with queries not used in Run 1 (deterministic, no model call).
  2. Thor and Loki update only the gap cells (a new Thor/Loki step with run=2); each new CELL_ESTIMATE supersedes
     the side's Run-1 estimate for that cell; every claim passes the same guards as Round 1.
  3. Odin rules again on the whole ledger.

A cell still without a quantified range afterwards is INSUFFICIENT_EVIDENCE (D1): the briefing is COMPLETE with the
cell flagged. `run2_new_evidence_families` is what Heimdall's Run-2 searches found that nobody had retrieved in
Run 1; when it is empty the run record says why. It is never padded.
"""
import json

from ..agents import counsel
from ..agents.claims import check_claim
from ..agents.normalize import normalize_claims
from ..casefile.schema import CLAIM_SCHEMA
from ..llm.provider import canonical, validate_schema
from ..provenance.citations import format_citation
from ..search.bm25 import mentions
from ..runtime.budget import BudgetExceeded

SIDES = counsel.SIDES


def family_of(corpus, doc_id):
    rec = corpus.records[doc_id]
    return rec["evidence_family_id"] or doc_id


def sufficiency(cf, cells):
    """The gap list: one entry per cell that needs evidence."""
    gaps = []
    for cell in cells:
        if cell["status"] == "INCOMPLETE_BUDGET_LIMIT":
            continue
        key = (cell["country"], cell["sector"])
        eg = [g for g in cf["evidence_gaps"] if (g["country"], g["sector"]) == key]
        if cell["status"] == "INSUFFICIENT_EVIDENCE" or eg:
            gaps.append({"country": key[0], "sector": key[1], "reason": cell["reason"] or "COVERAGE_GAP",
                         "missing": sorted({g["missing"] for g in eg}), "queries": [q for g in eg for q in g["queries"]]})
    return gaps


def fresh_queries(cf, gap, used):
    origins = " ".join((cf["manifest_scope"] or {}).get("event_origins", []))
    c, s = gap["country"], gap["sector"]
    pool = list(gap["queries"]) + [f"{c} {s} supply disruption", f"{origins} {c} {s} trade".strip(), f"{c} {s} shipments"]
    out = []
    for q in pool:
        if q not in used and q not in out:
            out.append(q)
    return out[:3]


def heimdall_research(cf, gaps, sides, trace, corpus, index):
    """Step 1. Returns (queries by cell, new evidence families, hits by cell)."""
    used = {e["query"] for a in SIDES for e in sides[a].tools.search_log}
    used |= {c["query"] for c in (cf["evidence_packet"] or {}).get("cells", [])}
    seen = set((cf["evidence_packet"] or {}).get("families_seen", []))
    for a in SIDES:
        for cit in sides[a].tools.retrieved:
            doc = cit.split(",")[0].strip("[ ")
            if doc in corpus.records:
                seen.add(family_of(corpus, doc))
    queries, hits_by_cell, new, new_spans = {}, {}, {}, {}
    for gap in gaps:
        key = f"{gap['country']}|{gap['sector']}"
        queries[key] = fresh_queries(cf, gap, used)
        hits_by_cell[key], new_spans[key] = [], []
        for q in queries[key]:
            # Two passes: the cell's destination country as a filter, and no country filter (a substitute route
            # runs through a third country, so its documents are not filed under the cell's country). The second
            # pass keeps only paragraphs that name the cell's country: relevance by text, not by luck.
            hits = index.search_docs(q, countries=[gap["country"]], sectors=[gap["sector"]], limit=5)
            wide = [h for h in index.search_docs(q, countries=None, sectors=[gap["sector"]], limit=8)
                    if mentions(f"{h['title']} {h['text']}", gap["country"])]
            trace.emit("heimdall", "SEARCH_COMPLETED", {"query": q, "run": 2, "filters": {
                "event_scope": cf["event_scope"], "published_before_or_on": cf["as_of_date"], "countries": [gap["country"]]},
                "result_doc_ids": [h["doc_id"] for h in hits], "unfiltered_country_hits": [h["doc_id"] for h in wide]})
            for h in hits + [w for w in wide if w["doc_id"] not in {x["doc_id"] for x in hits}]:
                rec = corpus.records[h["doc_id"]]
                span = {"doc_id": h["doc_id"], "paragraph": h["paragraph"], "title": h["title"], "text": h["text"],
                        "citation": format_citation(h["doc_id"], h["paragraph"], rec["pub_date"], rec["pub_time"]),
                        "tier": h["reliability"], "context_only": h["context_only"], "event_id": h["event_id"],
                        "source_type": h["source_type"], "evidence_family_id": h["evidence_family_id"]}
                hits_by_cell[key].append(span)
                fam = family_of(corpus, h["doc_id"])
                if fam not in seen and not h["context_only"] and h["event_id"] == cf["event_id"]:
                    new.setdefault(fam, []).append(span["citation"])
                    if span["citation"] not in {x["citation"] for x in new_spans[key]}:
                        new_spans[key].append(span)
    run2_view.new_spans = new_spans
    return queries, sorted(new), hits_by_cell, new


def run2_view(side, snapshot, gaps, queries, config, current):
    cells = [{"country": g["country"], "sector": g["sector"], "coverage": next(
        (c["status"] for c in snapshot["coverage"] if (c["country"], c["sector"]) == (g["country"], g["sector"])), None)}
        for g in gaps]
    mine = [c for c in snapshot["claim_ledger"] if c["agent"] == side.agent]
    return {"task": "run_2_claims", "agent": side.agent, "side": counsel.STANCE[side.agent], "run": 2, "round": 1,
            "event_id": snapshot["event_id"], "event_name": snapshot["event_name"], "as_of_date": snapshot["as_of_date"],
            "event_origins": snapshot["manifest_scope"]["event_origins"],
            "verification_citations": [c["citation"] for c in snapshot["event_verification"]["citations"]],
            "premise_check": snapshot["premise_check"]["status"], "cells": cells,
            "gaps": [{k: g[k] for k in ("country", "sector", "reason", "missing")} for g in gaps],
            "gap_queries": queries, "supersedes": current,
            "new_evidence": {k: v for k, v in getattr(run2_view, "new_spans", {}).items()}, "claims_so_far": len(mine), "supporting_so_far": 0,
            "run1_citations": sorted({c for x in mine for c in x["citations"]}),
            "limits": dict({k: config[k] for k in ("max_tool_calls_per_agent_step", "max_model_turns_per_agent_step",
                                                   "max_supporting_claims_per_side_per_round", "max_searches_per_agent_per_run")},
                           **config.caps(side.agent)),
            "memory": []}


def validate_run2(agent, claims, gaps, current, tools, cf, corpus, config, masked, run1_cites, prior_ids):
    problems = []
    if not isinstance(claims, list):
        return ["claims must be a list"]
    want = {(g["country"], g["sector"]) for g in gaps}
    estimates, supporting, seen = {}, 0, set(prior_ids)
    for i, c in enumerate(claims):
        where = f"claims[{i}]"
        errs = validate_schema(c, CLAIM_SCHEMA, where)
        if errs:
            problems += errs
            continue
        if c["claim_id"] in seen:
            problems.append(f"{where}: duplicate claim_id {c['claim_id']}")
        seen.add(c["claim_id"])
        if c["run"] != 2:
            problems.append(f"{where}: a Run-2 claim has run 2")
        cell = (c["country"], c["sector"])
        if cell not in want:
            problems.append(f"{where}: cell {cell} is not on the gap list")
        if c["claim_type"] == "CELL_ESTIMATE":
            estimates.setdefault(cell, []).append(c)
            if c["supersedes"] != current.get(f"{cell[0]}|{cell[1]}"):
                problems.append(f"{where}: the update must supersede {current.get(f'{cell[0]}|{cell[1]}')}")
        else:
            supporting += 1
            if c["supersedes"] is not None:
                problems.append(f"{where}: a SUPPORTING claim supersedes nothing")
            if not set(c["citations"]) - set(run1_cites):
                problems.append(f"{where}: a Run-2 SUPPORTING claim must cite evidence not cited in Run 1")
        problems += check_claim(where, agent, c, tools, cf, corpus, masked)
    for cell in want:
        if len(estimates.get(cell, [])) != 1:
            problems.append(f"cell {cell}: {len(estimates.get(cell, []))} CELL_ESTIMATE claims (exactly one required)")
    if supporting > config["max_supporting_claims_per_side_per_round"]:
        problems.append("too many SUPPORTING claims")
    return problems


def run_step2(side, snapshot, gaps, queries, current, corpus, provider, guard, config, masked, run1_cites):
    side.steps += 1
    side.tools.begin_step()
    cells = [(g["country"], g["sector"]) for g in gaps]
    side.trace.emit(side.agent, "AGENT_STEP_STARTED", {"cells": [list(c) for c in cells], "run": 2})
    view = run2_view(side, snapshot, gaps, queries, config, current)
    messages = [{"role": "system", "content": counsel.load_prompt(side.agent, 1, run_number=2)},
                {"role": "user", "content": canonical(view)}]
    prior_ids = {c["claim_id"] for c in snapshot["claim_ledger"] if c["agent"] == side.agent}

    def on_tools(out, turn):
        return [side.tools.execute(c) for c in out.get("tool_calls", [])]

    def on_submit(out, turn):
        out["claims"] = normalize_claims(out.get("claims", []), side.agent, 2, 1, side.tools, supersedes=current)
        problems = validate_run2(side.agent, out.get("claims", []), gaps, current, side.tools, snapshot, corpus, config,
                                 masked, run1_cites, prior_ids)
        return problems + [f"cell {c}: no executed search by {side.agent} in this case" for c in cells
                           if not counsel.cell_searched(side.tools, c)]

    out, turn, retries = counsel.model_loop(side, messages, provider, guard, config, on_tools, on_submit)
    side.trace.emit(side.agent, "CLAIMS_SUBMITTED", {"claim_ids": [c["claim_id"] for c in out["claims"]], "turn": turn, "run": 2})
    side.trace.emit(side.agent, "AGENT_STEP_COMPLETED", {"turns": turn, "retries": retries, "run": 2})
    return out["claims"], out.get("memory_writes", [])


def run_second_run(cf, cells, gaps, sides, provider, config, trace, guard, memory_root=None):
    """Steps 1 and 2. Mutates cf (claim_ledger, calc_ledger, run_status) and returns the run-2 record."""
    corpus, index = sides[SIDES[0]].tools.corpus, sides[SIDES[0]].tools.index
    from ..agents.claims import masked_raw_lines
    masked = masked_raw_lines(corpus)
    trace.emit("runtime", "ODIN_SENT_BACK", {"gaps": [{k: g[k] for k in ("country", "sector", "reason", "missing")} for g in gaps]})
    trace.emit("runtime", "RUN_2_STARTED", {"cells": [[g["country"], g["sector"]] for g in gaps]})
    queries, new_families, hits_by_cell, new = heimdall_research(cf, gaps, sides, trace, corpus, index)
    trace.emit("heimdall", "RUN_2_NEW_EVIDENCE", {"families": new_families, "citations": {k: v[:3] for k, v in new.items()}})
    reason = None
    if not new_families:
        reason = ("Heimdall's targeted searches returned only documents already retrieved in Run 1, background material, or "
                  "nothing for the gap cells.")
    for a in SIDES:                                   # Heimdall hands its new evidence to both sides; it is citable
        for spans in run2_view.new_spans.values():
            for sp in spans:
                sides[a].tools._saw(sp["citation"], {"doc_id": sp["doc_id"], "paragraph": sp["paragraph"], "text": sp["text"]})
    snapshot = json.loads(json.dumps(cf))
    current_by_agent = {a: {} for a in SIDES}
    for c in cf["claim_ledger"]:
        if c["claim_type"] == "CELL_ESTIMATE" and c["status"] == "submitted":
            current_by_agent[c["agent"]][f"{c['country']}|{c['sector']}"] = c["claim_id"]
    stop_reason, failures = None, []
    new_claims = {}
    total_cap = config.get("max_total_searches_per_case")
    for a in SIDES:
        s = sides[a]
        s.tools.run_number, s.tools.round = 2, 3
        s.tools.searches = 0
        s.trace = type(s.trace)(cf["case_id"]).for_side()
        s.tools.trace = s.trace
        used = sum(sides[b].tools.search_total() for b in SIDES)
        s.tools.search_cap = config["max_searches_per_agent_per_run"] if not total_cap else \
            max(0, min(config["max_searches_per_agent_per_run"], total_cap - used))
        s.status = "OK" if s.failure is None else s.status
    for agent in SIDES:
        side = sides[agent]
        if side.status != "OK":
            continue
        run1_cites = {c for x in cf["claim_ledger"] if x["agent"] == agent for c in x["citations"]}
        try:
            claims, writes = run_step2(side, snapshot, gaps, queries, current_by_agent[agent], corpus, provider, guard, config, masked, run1_cites)
            new_claims[agent] = claims
            counsel._write_memory(side, writes, snapshot, corpus)
        except counsel.StepFailed as e:
            side.status = f"{agent.upper()}_FAILED"
            side.failure = {"reason": e.reason, "problems": e.problems[:20], "step": side.steps, "run": 2, "round": 1,
                            "attempts": side.retries, "last_error": (e.problems or [e.reason])[0]}
            failures.append(dict(side.failure, agent=agent, state=side.status))
            side.trace.emit("runtime", "AGENT_FAILED", {"agent": agent, "state": side.status, **side.failure}, "WARNING")
        except BudgetExceeded as e:
            stop_reason = "INCOMPLETE_BUDGET_LIMIT"
            side.trace.emit("runtime", "BUDGET_CAP_REACHED", {"agent": agent, "detail": str(e)}, "WARNING")
    for agent in SIDES:
        for e in sides[agent].trace.events:
            trace.emit(e["actor"], e["event_type"], e["payload"], e["level"])
    ledger = {c["claim_id"]: c for c in cf["claim_ledger"]}
    for agent, claims in new_claims.items():
        for c in claims:
            if c["supersedes"] and c["supersedes"] in ledger:
                old = ledger[c["supersedes"]]
                old["status"], old["superseded_by"] = "superseded", c["claim_id"]
                trace.emit("runtime", "CLAIM_SUPERSEDED", {"claim_id": old["claim_id"], "superseded_by": c["claim_id"], "challenge_id": None, "run": 2})
            cf["claim_ledger"].append(dict(c, superseded_by=None))
    cf["calc_ledger"] = [r for a in SIDES for r in sides[a].tools.calcs]
    record = {"run_number": 2, "state": "RUN_2_COMPLETED", "stop_reason": stop_reason, "integrity_warnings": [],
              "quarantined_documents": [], "llm_calls": len(guard.calls), "gaps": gaps, "queries_by_cell": queries,
              "run2_new_evidence_families": new_families, "run2_new_evidence_citations": {k: v[:3] for k, v in new.items()},
              "run2_no_evidence_reason": reason, "agent_failures": failures,
              "updated_claims": {a: [c["claim_id"] for c in cl] for a, cl in new_claims.items()}}
    cf["run_status"].append(record)
    cf["run_status"][0]["llm_calls"] = len(guard.calls)
    trace.emit("runtime", "RUN_2_COMPLETED", {"new_evidence_families": new_families, "failures": [f["agent"] for f in failures],
                                              "updated": record["updated_claims"]})
    return record
