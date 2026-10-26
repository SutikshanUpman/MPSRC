"""Deterministic round-2 policy for the mock Thor and Loki (Stage 3 B4; never a live model).

Challenges come from checks on the opponent's round-1 ledger, in this priority order (one per target claim,
then by claim id, at most max_challenges_per_side_per_round):
  0 POST_AS_OF          a cited document is dated after the as-of date
  1 INTERESTED_PARTY    a SUPPORTING claim cites only company statements
  2 SOURCE_TIER         a SUPPORTING claim cites only Tier 3-4 documents
  3 BACKGROUND_ONLY     a SUPPORTING claim with numbers cites only EVENT_ID NONE documents
  4 INFERENCE_AS_FACT   a SOURCED_FACT that rests on a calc_id
  5 EVIDENCE_MISREAD    a quoted SOURCED_FACT whose sentence carries more of the challenger's cues than the claimant's
  6 ASSUMPTION_ATTACK   an estimate's substitute or mitigation assumption, against evidence the challenger retrieved:
                          Thor -> Loki full credit: a Tier 1-2 span saying the substitute is limited;
                          Loki -> Thor no credit:   the substitute trade rows behind Thor's own calc;
                          Loki -> Thor (no substitute flow): a Tier 1-2 contract or delayed-delivery span for the cell
  7 BASELINE_CHOICE     Thor -> Loki: an origin-wide index (base 100) for the post-event months; not a route
                          cross-check (spec md 2070), so offered as inference
  8 SINGLE_SOURCE       fallback, only when no rule above fires: a SUPPORTING claim or a no-range estimate that
                          rests on one evidence family (md 1327: a family counts as one source)
Responses come from whether a rebuttal exists in the corpus:
  DEFEND  when a span the side retrieves in round 2, not cited in its round 1, answers the challenge
          (substitute limited / substitute delivered / index scope caveat / delay already in the observed rows /
          an independent Tier 1-2 corroboration of a challenged fact);
  QUALIFY an estimate without such a rebuttal, or one challenged by a later Tier 1-2 document (concession rule,
          md 1866): narrowed through a new calc toward the challenger's scenario;
  QUALIFY a SINGLE_SOURCE claim without independent corroboration: restated as uncorroborated, lower confidence;
  CONCEDE a SUPPORTING claim without a rebuttal (or one the challenge proves misread): withdrawn.
Same messages in -> same output.
"""
import json
import re

from backend.search.bm25 import mentions
from backend.agents import calc as calc_mod
from backend.agents.claims import number_tokens
from backend.agents.heimdall import CONTRACT_CUES, SUBSTITUTE_CUES

LIMIT_CUES = re.compile(r"\b(?:limited|cannot|small compared|smaller than|not a full|partial|only part|not enough)\b", re.I)
GROWTH_CUES = re.compile(r"\b(?:more|increas\w*|grew|growing|rose|larger|higher|additional)\b", re.I)
SCOPE_CAVEAT = re.compile(r"\b(?:covers all|cover all|not only|all (?:\w+ ){0,3}loaded|all routes|every route)\b", re.I)
PRIORITY = ["POST_AS_OF", "INTERESTED_PARTY", "SOURCE_TIER", "BACKGROUND_ONLY", "INFERENCE_AS_FACT", "EVIDENCE_MISREAD",
            "ASSUMPTION_ATTACK", "BASELINE_CHOICE", "SINGLE_SOURCE"]
FACT_MAX_TIER = 2
SCENARIOS = {"thor": ("envelope.half_credit.low", "envelope.no_credit.high"),
             "loki": ("envelope.full_credit.low", "envelope.half_credit.high")}
# The narrower scenario a side moves to when it must QUALIFY: toward the challenger's view.
QUALIFIED = {"thor": ("envelope.half_credit.low", "envelope.half_credit.high"),
             "loki": ("envelope.half_credit.low", "envelope.half_credit.high")}


def _payloads(messages):
    return [json.loads(m["content"]) for m in messages if m["role"] == "user"]


def _results(messages):
    return [r for p in _payloads(messages)[1:] for r in p.get("tool_results", [])]


def _tool_turns(messages):
    return sum(1 for m in messages if m["role"] == "assistant" and json.loads(m["content"]).get("action") == "tools")


def _fmt(x):
    return f"{x:.1f}"


def _get(rec, path):
    return calc_mod.field(rec, path)


def _spans(results):
    """Every span returned by search or get_document, in order, with its metadata."""
    out = []
    for r in results:
        res = r.get("result")
        if r["tool"] == "search" and isinstance(res, list):
            out += res
        elif r["tool"] == "get_document" and isinstance(res, dict) and "paragraphs" in res:
            out += [dict(p, doc_id=res["doc_id"], title=res["title"], tier=res["tier"], event_id=res["event_id"],
                         source_type=res["source_type"], context_only=res["context_only"], pub_date=res["pub_date"],
                         whole_document=not r["args"].get("paragraphs"))
                    for p in res["paragraphs"]]
    return out


def _sentence(text, cue):
    for s in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())):
        if cue.search(s) and len(s) <= 300 and "[MASKED" not in s:
            return s
    return None


def _strong(span, view):
    return (span.get("event_id") == view["event_id"] and not span.get("context_only")
            and span.get("tier") is not None and span["tier"] <= FACT_MAX_TIER and span.get("source_type") != "company_statement")


def _quote_refs(sentence, citation):
    return [{"value": t, "citation": citation} for t in dict.fromkeys(number_tokens(sentence))]


def round2_policy(role, messages, schema):
    view = _payloads(messages)[0]
    if view["task"] == "round_2_challenge":
        return _challenge(role, view, messages)
    return _respond(role, view, messages)


# ---------- A. challenges ----------

def _estimates(view):
    return [c for c in view["opponent_claims"] if c["claim_type"] == "CELL_ESTIMATE" and c["estimate_status"] == "ESTIMATED"]


def _challenge(role, view, messages):
    turns, results = _tool_turns(messages), _results(messages)
    origins = " ".join(view["event_origins"])
    if turns == 0:
        calls = []
        for c in _source_candidates(role, view):            # retrieve the opponent's cited span to cite it ourselves
            doc, para = c["citations"][0].strip("[]").split(", ")[:2]
            calls.append({"tool": "get_document", "args": {"doc_id": doc, "paragraphs": [para]}})
        if role == "thor":
            calls.append({"tool": "search", "args": {"query": f"{origins} substitute rail capacity limited", "limit": 5}})
            calls.append({"tool": "search", "args": {"query": f"{origins} port loading index normal", "limit": 5}})
        else:
            for c in _estimates(view):
                calc = view["opponent_calcs"][c["calc_ids"][0]]
                if calc["passes"]["with_flagged"].get("substitute_offset", 0) <= 0:
                    calls.append({"tool": "search", "args": {"query": f"{c['country']} {c['sector']} delayed delivery contract terms",
                                                             "countries": [c["country"]], "sectors": [c["sector"]], "limit": 5}})
        return {"action": "tools", "tool_calls": calls[:view["limits"]["max_tool_calls_per_agent_step"]]}
    if turns == 1 and role == "thor":
        ranked = sorted({(s.get("tier") or 9, s["doc_id"]) for s in _spans(results)
                         if "index" in s["text"].lower() and s["event_id"] == view["event_id"]})
        docs = [d for _, d in ranked][:2]
        if docs:
            return {"action": "tools", "tool_calls": [{"tool": "get_document", "args": {"doc_id": d}} for d in docs]}
    return {"action": "submit", "challenges": _pick(role, view, results)}


def _source_candidates(role, view):
    return [c for c in view["opponent_claims"] if c["claim_type"] == "SUPPORTING" and _source_kind(role, view, c)]


def _source_kind(role, view, c):
    meta = [view["cited_sources"].get(cit) or {} for cit in c["citations"]]
    if any((m.get("pub_date") or "") > view["as_of_date"] for m in meta):
        return "POST_AS_OF"
    if meta and all(m.get("source_type") == "company_statement" for m in meta):
        return "INTERESTED_PARTY"
    if meta and all((m.get("tier") or 9) >= 3 for m in meta):
        return "SOURCE_TIER"
    if meta and all(m.get("event_id") == "NONE" for m in meta) and number_tokens(c["claim_text"]):
        return "BACKGROUND_ONLY"
    if c["claim_kind"] == "SOURCED_FACT" and (c["calc_ids"] or any("calc_id" in r for r in c["number_refs"])):
        return "INFERENCE_AS_FACT"
    if c["claim_kind"] == "SOURCED_FACT" and '"' in c["claim_text"]:
        from .mock_policy import LOSS_CUES, MITIGATION_CUES
        quote = c["claim_text"].split('"')[1]
        mine, theirs = (LOSS_CUES, MITIGATION_CUES) if role == "thor" else (MITIGATION_CUES, LOSS_CUES)
        if len(mine.findall(quote)) > len(theirs.findall(quote)):
            return "EVIDENCE_MISREAD"
    return None


def _pick(role, view, results):
    spans = _spans(results)
    found = []
    for c in view["opponent_claims"]:
        kind = _source_kind(role, view, c) if c["claim_type"] == "SUPPORTING" else None
        if kind:
            found.append((kind, c, _source_challenge(role, view, c, kind)))
    for c in _estimates(view):
        ch = _assumption_challenge(role, view, c, spans) or (_baseline_challenge(view, c, spans) if role == "thor" else None)
        if ch:
            found.append((ch[0], c, ch[1]))
    found = [f for f in found if f[2]]
    if not found:                            # fallback: the weakest support, one evidence family
        for c in view["opponent_claims"]:
            families = {(view["cited_sources"].get(x) or {}).get("evidence_family_id") for x in c["citations"]}
            if len(families) == 1 and (c["claim_type"] == "SUPPORTING" or c["estimate"] is None):
                found.append(("SINGLE_SOURCE", c, {"challenge_text": f"{c['claim_id']} rests on a single source (one "
                                                                     f"evidence family), so it is not corroborated.",
                                                   "citations": c["citations"][:1], "number_refs": []}))
    found.sort(key=lambda f: (PRIORITY.index(f[0]), f[1]["claim_id"]))
    chosen, targets = [], set()
    for kind, c, body in found:
        if c["claim_id"] in targets or len(chosen) >= view["limits"]["max_challenges_per_side_per_round"]:
            continue
        targets.add(c["claim_id"])
        chosen.append(dict({"challenge_id": f"challenge-{role}-{len(chosen) + 1:03d}", "challenger": role,
                            "target_agent": view["opponent"], "target_claim_id": c["claim_id"], "challenge_kind": kind,
                            "run": 1, "round": 2, "required_response": "DEFEND_QUALIFY_OR_CONCEDE"}, **body))
    return [{k: ch[k] for k in ("challenge_id", "challenger", "target_agent", "target_claim_id", "challenge_kind",
                                "challenge_text", "citations", "number_refs", "run", "round", "required_response")}
            for ch in chosen]


def _source_challenge(role, view, c, kind):
    why = {"POST_AS_OF": "cites a document dated after the as-of date",
           "INTERESTED_PARTY": "rests only on a company statement, an interested party under the source rules",
           "SOURCE_TIER": "rests only on low-tier documents (tier three or four)",
           "BACKGROUND_ONLY": "states numbers supported only by background (EVENT_ID NONE) documents",
           "INFERENCE_AS_FACT": "is tagged SOURCED_FACT but rests on a calculation, so it is an inference",
           "EVIDENCE_MISREAD": "quotes a sentence that mostly supports the other side's case"}[kind]
    return {"challenge_text": f"{c['claim_id']} {why}.", "citations": c["citations"][:1], "number_refs": []}


def _assumption_challenge(role, view, c, spans):
    calc = view["opponent_calcs"][c["calc_ids"][0]]
    p = calc["passes"]["with_flagged"]
    offset = p.get("substitute_offset", 0) if p.get("status") == "OK" else 0
    cell = f"{c['country']} {c['sector']}"
    if role == "thor" and offset > 0 and c["estimate"]["low_ref"]["field"].startswith("envelope.full_credit"):
        for s in spans:
            subs = calc["substitute_origins"]
            if _strong(s, view) and SUBSTITUTE_CUES.search(s["text"]) and LIMIT_CUES.search(s["text"]) and \
                    (mentions(s["text"], c["country"]) or any(mentions(s["text"], o) for o in subs)):
                low = c["estimate"]["low"]
                return "ASSUMPTION_ATTACK", {
                    "challenge_text": (f"{c['claim_id']} credits documented substitute growth in full (low {_fmt(low)}% for "
                                       f"{cell}), but the cited source says the substitute supply is limited."),
                    "citations": [s["citation"]],
                    "number_refs": [{"value": _fmt(low), "calc_id": c["calc_ids"][0], "field": c["estimate"]["low_ref"]["field"]}]}
    if role == "loki" and offset > 0 and c["estimate"]["high_ref"]["field"] == "envelope.no_credit.high":
        high, growth = c["estimate"]["high"], p["substitute"]["value_change_pct"]
        return "ASSUMPTION_ATTACK", {
            "challenge_text": (f"{c['claim_id']} sets its high ({_fmt(high)}%) for {cell} with no credit for substitutes, "
                               f"although the substitute routes behind its own calc grew {_fmt(growth)}% in value (cited rows)."),
            "citations": calc["input_citations"]["substitute"][:2],
            "number_refs": [{"value": _fmt(high), "calc_id": c["calc_ids"][0], "field": "envelope.no_credit.high"},
                            {"value": _fmt(growth), "calc_id": c["calc_ids"][0],
                             "field": "passes.with_flagged.substitute.value_change_pct"}]}
    if role == "loki" and offset <= 0:
        for s in spans:
            names = mentions(s["text"], c["country"]) or (mentions(s["title"], c["country"]) and mentions(s["title"], c["sector"]))
            sentence = _sentence(s["text"], CONTRACT_CUES)
            if _strong(s, view) and names and sentence:
                return "ASSUMPTION_ATTACK", {
                    "challenge_text": (f"{c['claim_id']} credits no mitigation for {cell}, but a cited source documents "
                                       f"contract or delayed-delivery terms: \"{sentence}\""),
                    "citations": [s["citation"]], "number_refs": _quote_refs(sentence, s["citation"])}
    return None


def _baseline_challenge(view, c, spans):
    """Thor: an origin-wide index (base 100) for post-event months, deeper than the opponent's high."""
    calc = view["opponent_calcs"][c["calc_ids"][0]]
    months = calc["passes"]["with_flagged"].get("paired_months") or []
    by_doc = {}
    for s in spans:
        if s.get("whole_document") and s.get("event_id") == view["event_id"]:
            by_doc.setdefault(s["doc_id"], []).append(s)
    best = None
    for doc, paras in sorted(by_doc.items()):
        body = " ".join(p["text"] for p in paras)
        if not calc_mod.INDEX_BASE.search(body) or not any(mentions(body, o) for o in view["event_origins"]):
            continue
        levels = []
        for p in paras:
            for sentence in re.split(r"(?<=[.!?])\s+", " ".join(p["text"].split())):
                named = [m for m in calc_mod._months_in(sentence, p["pub_date"]) if m in months]
                found = [lv for kind, lv in calc_mod._levels_in(sentence, True) if kind == "index"]
                if len(found) == 1 and len(named) == 1 and not calc_mod.HEDGE.search(sentence):
                    levels.append((named[0], found[0], p["citation"]))
        if levels:
            key = (paras[0]["tier"] or 9, tuple(-ord(x) for x in paras[0]["pub_date"]), doc)
            if best is None or key < best[0]:
                base = next(p["citation"] for p in paras if calc_mod.INDEX_BASE.search(p["text"]))
                best = (key, sorted(set(levels)), base)
    if best is None:
        return None
    levels, base = best[1], best[2]
    deeper = all(100 - lv > c["estimate"]["high"] + view["limits"]["baseline_crosscheck_tolerance_pct_points"]
                 for _, lv, _ in levels)
    if not deeper:
        return None
    shown = ", ".join(f"{lv:g}" for _, lv, _ in levels)
    cites = list(dict.fromkeys([base] + [cit for _, _, cit in levels]))
    refs = [{"value": "100", "citation": base}] + [{"value": f"{lv:g}", "citation": cit} for _, lv, cit in levels]
    return "BASELINE_CHOICE", {
        "challenge_text": (f"{c['claim_id']}: the origin's port-wide index (normal 100) read {shown} in the post-event "
                           f"months (cited), a loss deeper than its high of {_fmt(c['estimate']['high'])}% for "
                           f"{c['country']} {c['sector']}. It is not a route cross-check; it is offered as an inference."),
        "citations": cites,
        "number_refs": refs + [{"value": _fmt(c["estimate"]["high"]), "calc_id": c["calc_ids"][0],
                                "field": c["estimate"]["high_ref"]["field"]}]}


# ---------- B. responses ----------

def _respond(role, view, messages):
    turns, results = _tool_turns(messages), _results(messages)
    claims = {c["claim_id"]: c for c in view["my_claims"]}
    if turns == 0:
        calls = []
        for ch in view["challenges"]:
            c = claims[ch["target_claim_id"]]
            calls += _rebuttal_calls(role, view, ch, c)
        return {"action": "tools", "tool_calls": list({canonical_key(x): x for x in calls}.values())}
    plan = [(ch, claims[ch["target_claim_id"]], _rebuttal(role, view, ch, claims[ch["target_claim_id"]], _spans(results)))
            for ch in view["challenges"]]
    qualify = [(ch, c) for ch, c, reb in plan if reb is None and c["claim_type"] == "CELL_ESTIMATE" and c["estimate"]]
    calcs = [r for r in results if r["tool"] == "calc" and isinstance(r.get("result"), list)]
    if qualify and not calcs:
        cells = []
        for _, c in qualify:
            v = view["my_calcs"][c["calc_ids"][0]]
            cells.append({"country": c["country"], "sector": c["sector"], "direct_row_keys": v["direct_row_keys"],
                          "substitute_row_keys": v["substitute_row_keys"]})
        return {"action": "tools", "tool_calls": [{"tool": "calc", "args": {"cells": cells}}]}
    new_calcs = {(r["country"], r["sector"]): r for res in calcs for r in res["result"] if "calc_id" in r}
    responses, revised, n = [], [], view["claims_so_far"]
    for i, (ch, c, reb) in enumerate(plan, 1):
        rid = f"response-{role}-{i:03d}"
        base = {"response_id": rid, "responder": role, "challenge_id": ch["challenge_id"], "target_claim_id": c["claim_id"],
                "number_refs": [], "revised_claim_id": None, "reason": None, "new_evidence": []}
        if reb is not None:
            responses.append(dict(base, response_type="DEFEND", response_text=reb["text"], citations=reb["citations"],
                                  new_evidence=reb["new"], number_refs=reb["refs"]))
        elif ch["challenge_kind"] == "SINGLE_SOURCE" or (c["claim_type"] == "CELL_ESTIMATE" and not c["estimate"]):
            n += 1
            new = _uncorroborated(c, f"claim-{role}-{n:03d}", ch)
            revised.append(new)
            responses.append(dict(base, response_type="QUALIFY", revised_claim_id=new["claim_id"], citations=[],
                                  response_text=(f"{c['claim_id']} is restated as {new['claim_id']}: it rests on one "
                                                 f"source and no independent corroboration was found.")))
        elif c["claim_type"] == "CELL_ESTIMATE":
            n += 1
            new = _qualified(role, c, new_calcs[(c["country"], c["sector"])], f"claim-{role}-{n:03d}", ch)
            revised.append(new)
            responses.append(dict(base, response_type="QUALIFY", revised_claim_id=new["claim_id"], citations=[],
                                  response_text=(f"{c['claim_id']} is narrowed to {_fmt(new['estimate']['low'])}% to "
                                                 f"{_fmt(new['estimate']['high'])}% as {new['claim_id']}: no new evidence "
                                                 f"answers {ch['challenge_id']}."),
                                  number_refs=[{"value": _fmt(new["estimate"][k]), "calc_id": new["calc_ids"][0],
                                                "field": new["estimate"][f"{k}_ref"]["field"]} for k in ("low", "high")]))
        else:
            responses.append(dict(base, response_type="CONCEDE", citations=[],
                                  response_text=f"{c['claim_id']} is withdrawn.",
                                  reason=f"No independent top-tier evidence answers {ch['challenge_kind']} ({ch['challenge_id']})."))
    order = ["response_id", "responder", "challenge_id", "target_claim_id", "response_type", "response_text", "citations",
             "new_evidence", "number_refs", "revised_claim_id", "reason"]
    return {"action": "submit", "responses": [{k: r[k] for k in order} for r in responses], "claims": revised}


def canonical_key(call):
    return json.dumps(call, sort_keys=True)


def _later_tier12(view, ch, c):
    """Concession rule (md 1866): the challenge cites a Tier 1-2 document later than everything the claim cites."""
    mine = max((m or {}).get("pub_date") or "" for m in [view["cited_sources"].get(x) for x in c["citations"]] or [None])
    theirs = [view["cited_sources"].get(x) or {} for x in ch["citations"]]
    return any((m.get("tier") or 9) <= 2 and (m.get("pub_date") or "") > mine for m in theirs) if mine else False


def _rebuttal_calls(role, view, ch, c):
    cell = f"{c['country']} {c['sector']}"
    kind = ch["challenge_kind"]
    filters = {"countries": [c["country"]], "sectors": [c["sector"]], "limit": 5}
    if kind == "BASELINE_CHOICE":
        return [{"tool": "get_document", "args": {"doc_id": ch["citations"][0].strip("[]").split(", ")[0]}}]
    if kind == "ASSUMPTION_ATTACK" and role == "thor":
        if CONTRACT_CUES.search(ch["challenge_text"]):
            return [{"tool": "get_document", "args": {"doc_id": x.strip("[]").split(", ")[0],
                                                       "paragraphs": [x.strip("[]").split(", ")[1]]}} for x in ch["citations"]]
        return [{"tool": "search", "args": {"query": f"{' '.join(view['event_origins'])} substitute rail capacity limited",
                                            "limit": 5}}]
    if kind == "ASSUMPTION_ATTACK":
        return [{"tool": "search", "args": dict(filters, query=f"{cell} substitute supply arrivals increase")}]
    quote = c["claim_text"].split('"')[1] if '"' in c["claim_text"] else c["claim_text"]
    words = [w for w in re.findall(r"[A-Za-z]+", quote) if len(w) > 3][:8]
    return [{"tool": "search", "args": dict(filters, query=" ".join(words))}]


def _rebuttal(role, view, ch, c, spans):
    """A DEFEND body {text, citations, new, refs} when a rebuttal exists, else None."""
    if _later_tier12(view, ch, c):
        return None
    old = set(view["my_round1_citations"])
    fresh = [s for s in spans if s["citation"] not in old]
    kind = ch["challenge_kind"]
    if kind == "BASELINE_CHOICE":
        for s in fresh:
            sentence = _sentence(s["text"], SCOPE_CAVEAT)
            if sentence and s["doc_id"] == ch["citations"][0].strip("[]").split(", ")[0]:
                return _defend(c, s, sentence, "the cited index is port-wide, so it is not a measure of this route")
        return None
    if kind == "ASSUMPTION_ATTACK" and role == "thor" and CONTRACT_CUES.search(ch["challenge_text"]):
        own_docs = {x.strip("[]").split(", ")[0] for x in c["citations"]}
        for s in fresh:
            sentence = _sentence(s["text"], CONTRACT_CUES)
            if sentence and s["doc_id"] in own_docs:
                return _defend(c, s, sentence, "those cargoes are already inside the observed post-event rows of the same note")
        return None
    if kind == "ASSUMPTION_ATTACK" and role == "thor":
        for s in fresh:
            if _strong(s, view) and SUBSTITUTE_CUES.search(s["text"]) and LIMIT_CUES.search(s["text"]) and \
                    mentions(s["text"], c["country"]):
                sentence = _sentence(s["text"], LIMIT_CUES)
                if sentence:
                    return _defend(c, s, sentence, "substitute supply is limited, so a no-credit high is a defensible bound")
        return None
    if kind == "ASSUMPTION_ATTACK":
        for s in fresh:
            sentence = _sentence(s["text"], GROWTH_CUES)
            if _strong(s, view) and sentence and SUBSTITUTE_CUES.search(s["text"]) and mentions(sentence, c["country"]):
                return _defend(c, s, sentence, "substitute supply did reach the market, as credited")
        return None
    if kind == "SINGLE_SOURCE":
        mine = {(view["cited_sources"].get(x) or {}).get("evidence_family_id") for x in c["citations"]}
        from .mock_policy import LOSS_CUES, MITIGATION_CUES
        cue = LOSS_CUES if role == "thor" else MITIGATION_CUES
        for s in fresh:
            sentence = _sentence(s["text"], cue)
            if _strong(s, view) and sentence and s.get("evidence_family_id") not in mine and \
                    mentions(s["text"], c["country"]) and mentions(s["text"], c["sector"]):
                return _defend(c, s, sentence, "an independent source corroborates it")
        return None
    if kind in ("INTERESTED_PARTY", "SOURCE_TIER", "BACKGROUND_ONLY"):
        cue = re.compile("|".join(re.escape(w) for w in re.findall(r"[A-Za-z]{5,}", c["claim_text"])[:6]), re.I)
        for s in fresh:
            sentence = _sentence(s["text"], cue)
            if _strong(s, view) and sentence and mentions(sentence, c["country"]):
                return _defend(c, s, sentence, "an independent Tier 1-2 source says the same")
    return None


def _defend(c, s, sentence, why):
    return {"text": f"{c['claim_id']} stands: {why}. A source it did not cite before states: \"{sentence}\"",
            "citations": [s["citation"]], "new": [s["citation"]], "refs": _quote_refs(sentence, s["citation"])}


def _uncorroborated(c, claim_id, ch):
    """QUALIFY without new numbers: the same claim, restated as resting on one source, at lower confidence."""
    from .mock_policy import ORDER
    new = dict(c, claim_id=claim_id, round=2, supersedes=c["claim_id"], status="submitted",
               claim_text=f"On a single, uncorroborated source: {c['claim_text']}",
               assumptions=c["assumptions"] + [f"Rests on one evidence family; not corroborated ({ch['challenge_id']})"],
               confidence=round(c["confidence"] * 0.8, 2))
    return {k: new[k] for k in ORDER}


def _qualified(role, c, calc, claim_id, ch):
    low_f, high_f = QUALIFIED[role]
    low, high = _get(calc, low_f), _get(calc, high_f)
    from .mock_policy import secondary_metrics, ORDER
    text = (f"{role.capitalize()} narrows its {c['country']} {c['sector']} estimate to {_fmt(low)}% to {_fmt(high)}% "
            f"(half of the documented substitute growth credited) after {ch['challenge_id']}.")
    new = dict(c, claim_id=claim_id, round=2, claim_text=text, calc_ids=[calc["calc_id"]], supersedes=c["claim_id"],
               estimate={"low": low, "high": high, "unit": "percent", "low_ref": {"calc_id": calc["calc_id"], "field": low_f},
                         "high_ref": {"calc_id": calc["calc_id"], "field": high_f}},
               number_refs=[{"value": _fmt(low), "calc_id": calc["calc_id"], "field": low_f},
                            {"value": _fmt(high), "calc_id": calc["calc_id"], "field": high_f}],
               assumptions=c["assumptions"] + [f"Revised in cross-examination after {ch['challenge_id']} ({ch['challenge_kind']})"],
               secondary_metrics=secondary_metrics(calc), status="submitted")
    return {k: new[k] for k in ORDER}
