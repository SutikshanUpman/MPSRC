"""Deterministic mock policies used by DeterministicMockProvider (tests, CI, demos; never a live model).

- heimdall: stance classification for the verification fallback. A broader
  generic keyword policy standing in for Haiku; it proves the plumbing, not
  Haiku's accuracy.
- thor / loki: a rule-based Round 1 policy that uses only what the runtime
  sends (case view, visible private memory, tool results):
    turn 1  get_trade_rows for the batch + one search per cell
    turn 2  calc per cell (direct rows = event-origin routes, substitute rows = other routes)
    turn 3  submit claims (+ memory notes about searches that found nothing useful)
  Thor takes the high-exposure scenarios of each calc record, Loki the limited ones.
  Memory: a visible note that a query found nothing useful for this event and
  cell makes the policy rewrite that query (or skip it if the rewrite also
  failed before) and report the decision.
Same messages in -> same output; no randomness, no clock.
"""
import json
import re

from ..ingestion.quality import MASK_PLACEHOLDER
from ..llm.provider import canonical, estimate_tokens, skeleton
from ..search.bm25 import mentions
from .claims import number_tokens
from .calc import SECONDARY_FIELDS
from .heimdall import CONTRACT_CUES, SUBSTITUTE_CUES

STOPPAGE = re.compile(r"\b(?:stop(?:s|ped|page)?|withdr[ae]w\w*|barr(?:ed|ing)|bans?|banned|prohibit\w*|no longer|idle|"
                      r"cease[sd]?|clos(?:ed|ure)|halt\w*|suspend\w*|blockad\w*|ended|expir\w*|cut off)\b", re.I)
REVERSAL = re.compile(r"\b(?:resum\w*|reopen\w*|restor\w*|allowed again|lifted|renew\w*)\b", re.I)
# Thor quotes loss, delay or contract evidence; Loki quotes substitute supply (SUBSTITUTE_CUES).
LOSS_CUES = re.compile(r"\b(?:fell|fall(?:en|ing|s)?|drop\w*|declin\w*|below|lower|loss|lost|shortfall|stopped|"
                       r"halt\w*|delay\w*|deferr\w*|backlog\w*|contract\w*)\b", re.I)
# Loki's mitigation evidence: substitutes, and contracts or delayed delivery (md 248-249).
MITIGATION_CUES = re.compile(SUBSTITUTE_CUES.pattern + "|" + CONTRACT_CUES.pattern, re.I)
FACT_MAX_TIER = 2                     # quoted facts come from Tier 1-2 documents only
OUTPUT_MARGIN = 0.9                   # share of max_output_tokens the submit turn may fill
KIND_NOUN = {"news": "news report", "gov_notice": "government notice"}

QUERIES = {
    "thor": [("t1", "{origins} {country} {sector} disruption delays shortfall"), ("t2", "{country} {sector} imports disruption")],
    "loki": [("l1", "{country} {sector} alternative supply rail substitute"), ("l2", "{country} {sector} suppliers contracts")],
}
SCENARIOS = {  # (low field, high field) in a calc record
    "thor": ("envelope.half_credit.low", "envelope.no_credit.high"),
    "loki": ("envelope.full_credit.low", "envelope.half_credit.high"),
}


def _user_payloads(messages):
    return [json.loads(m["content"]) for m in messages if m["role"] == "user"]


# ---------- heimdall: stance ----------

def heimdall_policy(role, messages, schema):
    payload = _user_payloads(messages)[-1]
    if payload.get("task") != "stance_classification":
        return skeleton(schema)
    units = [("title", payload["title"])] + [(p["id"], p["text"]) for p in payload["paragraphs"]]
    scores = {pid: (len(STOPPAGE.findall(t)), len(REVERSAL.findall(t))) for pid, t in units}
    a, d = sum(s[0] for s in scores.values()), sum(s[1] for s in scores.values())
    stance = "ASSERTS" if a > d else "DENIES" if d > a else "NEUTRAL"
    idx = 0 if stance != "DENIES" else 1
    paras = [(pid, s) for pid, s in scores.items() if pid != "title"]
    best = max(paras, key=lambda kv: (kv[1][idx], -int(kv[0][1:])), default=("P1", (0, 0)))[0]
    return {"stance": stance, "paragraph": best,
            "reason": f"mock keyword policy: {a} stoppage cue(s), {d} reversal cue(s)"}


# ---------- thor / loki: Round 1 ----------

def counsel_policy(role, messages, schema):
    payloads = _user_payloads(messages)
    view = payloads[0]
    if view["task"].startswith("round_2"):
        from .mock_round2 import round2_policy
        return round2_policy(role, messages, schema)
    results = [r for p in payloads[1:] for r in p.get("tool_results", [])]
    rows = [r for r in results if r["tool"] == "get_trade_rows" and "result" in r]
    calcs = [r for r in results if r["tool"] == "calc" and "result" in r]
    # Newest results decide the turn, so a prompt rebuilt without the oldest tool results (input cap) still
    # moves forward: calc results -> submit, trade rows -> calc, nothing yet -> retrieve.
    if calcs:
        # If the rebuild dropped a cell's search results, fetch them again first: the identical search is a
        # cache hit, so nothing is searched twice. Done once per step.
        missing = [c for c in view["cells"] if not _searches_for(results, c)]
        if missing and not any(json.loads(m["content"]).get("refetch") for m in messages if m["role"] == "assistant"):
            again = [c for c in _turn_retrieve(role, dict(view, cells=missing))["tool_calls"] if c["tool"] == "search"]
            if again:
                return {"action": "tools", "tool_calls": again, "refetch": True}
        return _turn_submit(role, view, results, calcs[-1]["result"])
    if rows:
        return _turn_calc(rows[-1]["result"])
    return _turn_retrieve(role, view)


def _query(role, template, view, cell):
    return template.format(origins=" ".join(view["event_origins"]), country=cell["country"], sector=cell["sector"]).strip()


def _noted(view, cell, template_id):
    for m in view["memory"]:
        v = m["value"]
        if (m["key"] == "unproductive_query" and v.get("event_id") == view["event_id"] and v.get("country") == cell["country"]
                and v.get("sector") == cell["sector"] and v.get("template") == template_id):
            return m
    return None


def _turn_retrieve(role, view):
    calls = [{"tool": "get_trade_rows", "args": {"cells": view["cells"]}}]
    decisions = []
    if view.get("gap_queries"):               # Run 2: Heimdall's fresh queries for the gap cells
        # The step allows few tool calls (rows + calc + searches): each cell gets one country-filtered search first
        # (every cell needs one), then unfiltered and further searches are shared round-robin up to the allowance.
        room = max(len(view["cells"]), view["limits"]["max_tool_calls_per_agent_step"] - 2)
        per_cell = []
        for cell in view["cells"]:
            qs = view["gap_queries"].get(f"{cell['country']}|{cell['sector']}", [])
            plan = []
            for i, q in enumerate(qs[:2]):
                plan.append((q, [cell["country"]], 5))
                plan.append((q, [], 8))
            per_cell.append((cell, plan))
        for rank in range(4):
            for cell, plan in per_cell:
                if rank < len(plan) and room > 0:
                    q, countries, limit = plan[rank]
                    calls.append({"tool": "search", "args": {"query": q, "countries": countries,
                                                             "sectors": [cell["sector"]], "limit": limit}})
                    room -= 1
        return {"action": "tools", "tool_calls": calls, "memory_decisions": []}
    (first_id, first_t), (alt_id, alt_t) = QUERIES[role]
    for cell in view["cells"]:
        planned = _query(role, first_t, view, cell)
        note = _noted(view, cell, first_id)
        if note is None:
            query = planned
        else:
            alt_note = _noted(view, cell, alt_id)
            alt = _query(role, alt_t, view, cell)
            if alt_note is None:
                query = alt
                decisions.append({"memory_id": note["memory_id"], "kind": "QUERY_REWRITTEN", "cell": [cell["country"], cell["sector"]],
                                  "before": planned, "after": alt})
            else:
                query = None
                decisions.append({"memory_id": alt_note["memory_id"], "kind": "QUERY_SKIPPED", "cell": [cell["country"], cell["sector"]],
                                  "before": alt, "after": None})
        if query:
            calls.append({"tool": "search", "args": {"query": query, "countries": [cell["country"]],
                                                     "sectors": [cell["sector"]], "limit": 5}})
    return {"action": "tools", "tool_calls": calls, "memory_decisions": decisions}


def _turn_calc(row_result):
    cells = []
    for cell in row_result:
        usable = [r for r in cell["rows"] if r["usable_for_arithmetic"]]
        cells.append({"country": cell["country"], "sector": cell["sector"],
                      "direct_row_keys": [r["row_key"] for r in usable if r["role"] == "direct"],
                      "substitute_row_keys": [r["row_key"] for r in usable if r["role"] == "substitute"]})
    return {"action": "tools", "tool_calls": [{"tool": "calc", "args": {"cells": cells}}]}


def _fmt(x):
    return f"{x:.1f}"


def _searches_for(results, cell):
    out = []
    for r in results:
        if r["tool"] == "search" and isinstance(r.get("result"), list) and r["args"].get("countries") == [cell["country"]] \
                and r["args"].get("sectors") == [cell["sector"]]:
            out.append(r)
    return out


def _useful(span, view, cell):
    text = f"{span['title']} {span['text']}"
    return (span["event_id"] == view["event_id"] and not span["context_only"]
            and mentions(text, cell["country"]) and mentions(text, cell["sector"]))


def _turn_submit(role, view, results, calc_records):
    by_cell = {(c["country"], c["sector"]): c for c in calc_records if "calc_id" in c}
    n = view["claims_so_far"]
    claims, supporting, text_facts = [], [], []

    def next_id():
        nonlocal n
        n += 1
        return f"claim-{role}-{n:03d}"

    for cell in view["cells"]:
        key = (cell["country"], cell["sector"])
        rec = by_cell.get(key)
        if rec is None:
            continue
        row_cites = rec["input_citations"]["direct"] + rec["input_citations"]["substitute"]
        cell_spans = _cell_spans(results, view, cell)
        if view["run"] == 2:                  # a Run-2 fact must come from evidence not cited in Run 1
            cell_spans += view.get("new_evidence", {}).get(f"{cell['country']}|{cell['sector']}", [])
            cell_spans = [s for s in cell_spans if s["citation"] not in view["run1_citations"]]
        base = {"agent": role, "run": view["run"], "round": view["round"], "country": cell["country"], "sector": cell["sector"],
                "calc_ids": [rec["calc_id"]], "status": "submitted", "secondary_metrics": None, "supersedes": None}
        if rec["status"] == "OK":
            low_f, high_f = SCENARIOS[role]
            low, high = _value(rec, low_f), _value(rec, high_f)
            sub_origins = rec["substitute_origins"]
            offset = rec["passes"]["with_flagged"].get("substitute_offset", 0)
            if role == "thor":
                text = (f"Thor estimates a net value shortfall of {_fmt(low)}% to {_fmt(high)}% for {cell['country']} "
                        f"{cell['sector']} imports, crediting at most half of the documented substitute growth.")
                mechanism = None
                assumptions = [_basis_note(rec), "At most half of documented substitute growth replaces lost direct-route value"]
            else:
                text = (f"Loki estimates a net value shortfall of {_fmt(low)}% to {_fmt(high)}% for {cell['country']} "
                        f"{cell['sector']} imports, crediting documented substitute growth in full.")
                mechanism = (f"Documented substitute routes from {', '.join(sub_origins)} into {cell['country']} "
                             f"(trade rows) offset part of the direct-route loss." if offset > 0 else
                             "No documented substitute growth; the estimate credits nothing beyond the direct-route record.")
                assumptions = [_basis_note(rec), "Documented substitute growth fully replaces lost direct-route value"]
            claims.append(dict(base, claim_id=next_id(), claim_type="CELL_ESTIMATE", claim_kind="INFERENCE",
                               metric="net_value_shortfall_pct", estimate_status="ESTIMATED",
                               estimate={"low": low, "high": high, "unit": "percent",
                                         "low_ref": {"calc_id": rec["calc_id"], "field": low_f},
                                         "high_ref": {"calc_id": rec["calc_id"], "field": high_f}},
                               claim_text=text,
                               number_refs=[{"value": _fmt(low), "calc_id": rec["calc_id"], "field": low_f},
                                            {"value": _fmt(high), "calc_id": rec["calc_id"], "field": high_f}],
                               citations=_cites(row_cites + [x["citation"] for x in rec["crosscheck_refs"]]),
                               mechanism=mechanism,
                               assumptions=assumptions + _calc_assumptions(rec, cell),
                               confidence=0.5 if rec["baseline_flags"] else 0.6 if rec["widened"] else 0.7,
                               secondary_metrics=secondary_metrics(rec)))
            supporting.append(_calc_fact(role, base, rec, cell))
        else:
            checked = _cites(s["citation"] for r in _searches_for(results, cell) for s in r["result"])
            reason = {"NO_DOCUMENTED_FLOW": f"No trade row from {' and '.join(view['event_origins'])} into {cell['country']} "
                                            f"for {cell['sector']} is documented in the case scope; the search for this cell "
                                            f"(cited results, background documents as context only) found none, "
                                            f"so no range is given.",
                      "NO_BASELINE": f"Direct-route rows for {cell['country']} {cell['sector']} cannot be paired with the same "
                                     f"months a year earlier, so no range is given.",
                      "MIXED_UNITS": f"Direct-route rows for {cell['country']} {cell['sector']} mix currencies, so no range is given."}
            claims.append(dict(base, claim_id=next_id(), claim_type="CELL_ESTIMATE", claim_kind="INFERENCE",
                               metric="net_value_shortfall_pct", estimate_status=rec["status"], estimate=None,
                               claim_text=reason[rec["status"]], number_refs=[],
                               citations=_cites(row_cites) if row_cites else checked,
                               mechanism=None, assumptions=["A missing flow is never read as zero exposure or filled with another cell's rate"],
                               confidence=0.5))
        fact = _sourced_fact(role, base, view, cell, cell_spans)
        if fact:
            text_facts.append(fact)
    # Supporting claims go in while the round allowance lasts and the output stays inside the role's
    # max_output_tokens (with a margin): a live model would be cut off at the cap.
    if view["run"] == 2:
        supporting = []
        for c in claims:
            if c["claim_type"] == "CELL_ESTIMATE":
                c["supersedes"] = view["supersedes"].get(f"{c['country']}|{c['sector']}")
    notes = _memory_notes(role, view, results)
    budget = int(view["limits"]["max_output_tokens"] * OUTPUT_MARGIN)
    room = view["limits"]["max_supporting_claims_per_side_per_round"] - view["supporting_so_far"]
    for s in text_facts[:1] + [x for x in supporting if x] + text_facts[1:]:     # one quoted fact first
        if room <= 0:
            break
        trial = claims + [dict(s, claim_id=f"claim-{role}-{n + 1:03d}")]
        if estimate_tokens(canonical(_submission(trial, notes))) > budget:
            continue
        s["claim_id"] = next_id()
        claims.append(s)
        room -= 1
    return _submission(claims, notes)


def _submission(claims, notes):
    return {"action": "submit", "claims": [_order(c) for c in claims], "memory_writes": notes}


def _value(rec, path):
    value = rec
    for part in path.split("."):
        value = value[part]
    return value


def _cites(citations):
    return list(dict.fromkeys(citations))


def _basis_note(rec):
    if rec["baseline_basis"] == "CROSS_CHECK_ONLY":
        return "Baseline = post-event flow divided by the cited level of normal (F11 cross-check only)"
    return "Baseline = the same months one year earlier on the same route (F11 primary rule)"


def _cell_spans(results, view, cell):
    """Spans this side retrieved by searching for the cell, one per evidence family, in result order."""
    out, families = [], set()
    for r in _searches_for(results, cell):
        for span in r["result"]:
            fam = span["evidence_family_id"] or span["doc_id"]
            if fam not in families and mentions(f"{span['title']} {span['text']}", cell["country"]):
                families.add(fam)
                out.append(span)
    return out


def _flag_note(flagged, country):
    if not flagged:
        return []
    flags = sorted({f for r in flagged for f in (r.get("flags") or ["TRADE_ROW_REPEATED_VALUES"])})
    where = ", ".join(f"{r['origin']} to {country} {r['month']}" for r in flagged)
    return [f"Rows flagged {' and '.join(flags)} ({where}) are used in one pass and left out in the other; "
            f"the range covers both passes"]


def _calc_assumptions(rec, cell):
    notes = _flag_note(rec["flagged_inputs"], cell["country"])
    if rec["crosscheck"] == "AGREE":
        notes.append("The F11 cross-check level (cited) agrees with the trade-row baseline within the configured tolerance")
    elif rec["crosscheck"] == "CONFLICT":
        notes.append("BASELINE_CONFLICT: the F11 cross-check level (cited) disagrees with the trade-row baseline; "
                     "the range also covers a pass with the baseline scaled to the cross-check")
    elif rec["crosscheck"] == "CROSS_CHECK_ONLY":
        notes.append("BASELINE_PROXY: no prior-year rows; the baseline is implied from the cited level of normal")
    return notes


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())) if s]


def _sourced_fact(role, base, view, cell, spans):
    """Quote one retrieved Tier 1-2 case-event sentence about the cell: loss, delay or contract evidence for Thor,
    substitute supply for Loki. Interested parties (company statements) come last, then by tier."""
    cue = LOSS_CUES if role == "thor" else MITIGATION_CUES
    ranked = sorted((s for s in spans if _useful(s, view, cell) and cue.search(s["text"])
                     and s["tier"] is not None and s["tier"] <= FACT_MAX_TIER),
                    key=lambda s: (s["source_type"] == "company_statement", s["tier"] if s["tier"] is not None else 9))
    for span in ranked:
        for sentence in _sentences(span["text"]):
            names_cell = mentions(sentence, cell["country"]) or (mentions(span["title"], cell["country"])
                                                                 and mentions(span["title"], cell["sector"]))
            if cue.search(sentence) and names_cell and MASK_PLACEHOLDER not in sentence and len(sentence) <= 300:
                kind = KIND_NOUN.get(span["source_type"], (span["source_type"] or "document").replace("_", " "))
                refs = [{"value": t, "citation": span["citation"]} for t in dict.fromkeys(number_tokens(sentence))]
                return dict(base, calc_ids=[], claim_type="SUPPORTING", claim_kind="SOURCED_FACT", metric=None,
                            estimate_status=None, estimate=None, claim_text=f'A {kind} states: "{sentence}"',
                            number_refs=refs, citations=[span["citation"]],
                            mechanism=None if role == "thor" else f"Mitigation named in the cited {kind}",
                            assumptions=[], confidence=0.5 if span["source_type"] == "company_statement" else 0.7)
    return None


def _calc_fact(role, base, rec, cell):
    p = rec["passes"]["with_flagged"]
    cid = rec["calc_id"]
    if p["status"] != "OK":                 # e.g. a cross-check-only baseline: no year-on-year flows to state
        return None
    if role == "thor":
        v, w, n = p["direct"]["value_change_pct"], p["direct"]["volume_change_pct"], p["paired_month_count"]
        if v is None or w is None:
            return None
        return dict(base, claim_type="SUPPORTING", claim_kind="INFERENCE", metric=None, estimate_status=None, estimate=None,
                    claim_text=(f"Direct-route value for {cell['country']} {cell['sector']} imports changed by {_fmt(v)}% and "
                                f"volume by {_fmt(w)}% against the same months one year earlier ({n} paired months)."),
                    number_refs=[{"value": _fmt(v), "calc_id": cid, "field": "passes.with_flagged.direct.value_change_pct"},
                                 {"value": _fmt(w), "calc_id": cid, "field": "passes.with_flagged.direct.volume_change_pct"},
                                 {"value": str(n), "calc_id": cid, "field": "passes.with_flagged.paired_month_count"}],
                    citations=rec["input_citations"]["direct"], mechanism=None,
                    assumptions=_flag_note([r for r in rec["flagged_inputs"] if r["origin"] not in rec["substitute_origins"]],
                                           cell["country"]), confidence=0.8)
    v = p["substitute"]["value_change_pct"]
    if v is None or p["substitute_offset"] <= 0:
        return None
    return dict(base, claim_type="SUPPORTING", claim_kind="INFERENCE", metric=None, estimate_status=None, estimate=None,
                claim_text=(f"Substitute routes into {cell['country']} for {cell['sector']} changed by {_fmt(v)}% in value over "
                            f"the same paired months, offsetting part of the direct-route loss."),
                number_refs=[{"value": _fmt(v), "calc_id": cid, "field": "passes.with_flagged.substitute.value_change_pct"}],
                citations=rec["input_citations"]["substitute"],
                mechanism="Documented substitute routes (trade rows)",
                assumptions=_flag_note([r for r in rec["flagged_inputs"] if r["origin"] in rec["substitute_origins"]],
                                       cell["country"]), confidence=0.7)


ORDER = ["claim_id", "agent", "run", "round", "claim_type", "claim_kind", "country", "sector", "metric", "estimate_status",
         "estimate", "claim_text", "number_refs", "calc_ids", "citations", "mechanism", "assumptions", "confidence", "status",
         "secondary_metrics", "supersedes"]


def secondary_metrics(rec):
    """A5: value and volume change and implied unit price, copied from the calc's year-on-year pass."""
    p = rec["passes"].get("with_flagged") or {}
    if p.get("status") != "OK":
        return None
    d = p["direct"]
    return dict({"calc_id": rec["calc_id"], "pass": "with_flagged", "currency": d["currency"], "volume_unit": d["volume_unit"]},
                **{f: d[f] for f in SECONDARY_FIELDS})


def _order(c):
    return {k: c[k] for k in ORDER}


def _memory_notes(role, view, results):
    notes = []
    templates = dict(QUERIES[role])
    for cell in view["cells"]:
        for r in _searches_for(results, cell):
            query = r["args"]["query"]
            tid = next((t for t, tpl in templates.items() if _query(role, tpl, view, cell) == query), None)
            if tid is None or any(_useful(s, view, cell) for s in r["result"]):
                continue
            notes.append({"key": "unproductive_query", "kind": "case_note",
                          "value": {"event_id": view["event_id"], "country": cell["country"], "sector": cell["sector"],
                                    "template": tid, "query": query},
                          "source_doc_ids": sorted({s["doc_id"] for s in r["result"]})})
    return notes


def odin_policy(role, messages, schema):
    """Mock Odin: keeps the runtime's default decision and rationale for every open claim. Deterministic."""
    view = _user_payloads(messages)[-1]
    return {"rulings": [{"claim_id": c["claim_id"], "decision": c["default_decision"], "rationale": c["default_rationale"],
                         "confidence": 0.6} for c in view.get("open_claims", [])]}


def briefing_policy(role, messages, schema):
    """Mock briefing writer: returns the template narrative the runtime sent as `template`."""
    view = _user_payloads(messages)[-1]
    return view["template"]


def default_responders():
    return {"heimdall": heimdall_policy, "thor": counsel_policy, "loki": counsel_policy, "odin_ruling": odin_policy,
            "odin_briefing": briefing_policy}
