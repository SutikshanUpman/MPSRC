"""Odin: rulings on every claim (SYSTEM_ARCHITECTURE 12.7, 18; FINAL BUILD 1.1-1.2).

Order, always:
  1. Deterministic pre-ruling checks on every claim (reason codes below). A claim that fails is REJECTED
     (`rejected_by: PRE_RULING_CHECK`) or QUALIFIED; no later step may overturn it.
  2. Deterministic rules for the rest: ACCEPTED / QUALIFIED / REJECTED, SOURCED_FACT vs INFERENCE, and a finding
     classification ESTABLISHED / CONTESTED / CONCEDED (REJECTED for a rejected claim).
  3. Only the claims the rules left open (classification CONTESTED, not pre-rejected) may go to the model
     (`odin_ruling`, Sonnet). The model can change a decision and write a rationale; it can never add a fact:
     its rationale is checked by the quote, entity, number and injection guards against the claim's own material.
     Any failure (budget, provider, schema, guard) falls back to the deterministic ruling (FALLBACK_ODIN_RULES).

The Odin range of a cell comes from the accepted, current CELL_ESTIMATEs of both sides and their calc records
(value and volume through the same scenario field), never from a model.
"""
import re

from .. import guards
from ..llm.provider import ProviderError, canonical, validate_schema
from ..provenance.citations import parse_citations, validate_citation
from ..runtime.budget import BudgetExceeded
from .claims import number_tokens

DECISIONS = ["ACCEPTED", "QUALIFIED", "REJECTED"]
CLASSIFICATIONS = ["ESTABLISHED", "CONTESTED", "CONCEDED", "REJECTED"]
DAMAGED_FLAGS = {"TRUNCATED_DOCUMENT", "EMPTY_DOCUMENT", "UNREADABLE_FILE"}

RULING_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["ruling_id", "claim_id", "run", "agent", "country", "sector", "classification", "claim_kind", "decision",
                 "rationale", "supporting_refs", "conflicting_refs", "confidence", "created_at", "decided_by"],
    "properties": {
        "ruling_id": {"type": "string", "pattern": r"^ruling-odin-\d{3}$"},
        "claim_id": {"type": "string", "pattern": r"^claim-(thor|loki)-\d{3}$"},
        "run": {"type": "integer"}, "agent": {"type": "string", "enum": ["thor", "loki"]},
        "country": {"type": "string"}, "sector": {"type": "string"},
        "classification": {"type": "string", "enum": CLASSIFICATIONS},
        "claim_kind": {"type": "string", "enum": ["SOURCED_FACT", "INFERENCE"]},
        "decision": {"type": "string", "enum": DECISIONS},
        "rejected_by": {"type": "string", "enum": ["PRE_RULING_CHECK", "CONCESSION", "ODIN"]},
        "rejection_reasons": {"type": "array", "items": {"type": "string"}},
        "qualification_reasons": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
        "supporting_refs": {"type": "array", "items": {"type": "object", "required": ["doc_id", "span_id"],
                                                       "properties": {"doc_id": {"type": "string"}, "span_id": {"type": "string"}}}},
        "conflicting_refs": {"type": "array", "items": {"type": "object", "required": ["doc_id", "span_id"],
                                                        "properties": {"doc_id": {"type": "string"}, "span_id": {"type": "string"}}}},
        "claim_status": {"type": "string"}, "superseded_by": {"type": ["string", "null"]},
        "confidence": {"type": "number"}, "created_at": {"type": "string"},
        "decided_by": {"type": "string", "enum": ["RULES", "MODEL"]},
    },
}

# What the model may return for the open claims: a decision and a rationale, nothing else.
ODIN_OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["rulings"],
    "properties": {"rulings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["claim_id", "decision", "rationale", "confidence"],
        "properties": {"claim_id": {"type": "string", "pattern": r"^claim-(thor|loki)-\d{3}$"},
                       "decision": {"type": "string", "enum": DECISIONS}, "rationale": {"type": "string"},
                       "confidence": {"type": "number"}}}}},
}


def _span_ref(cit):
    p = parse_citations(cit)[0]
    return {"doc_id": p["doc_id"], "span_id": f"{p['doc_id']}:{p['paragraph']}"}


def _docs(claim, corpus):
    out = []
    for cit in claim["citations"]:
        for p in parse_citations(cit):
            if p["doc_id"] in corpus.records:
                out.append(corpus.records[p["doc_id"]])
    return out


def _is_numeric(claim):
    return claim["estimate_status"] == "ESTIMATED" or bool(number_tokens(claim["claim_text"]))


def pre_ruling(claim, cf, corpus, eligible_ids, retrieved, masked):
    """Returns (rejection reason codes, qualification reason codes)."""
    reject, qualify = [], []
    docs = _docs(claim, corpus)
    for cit in claim["citations"]:
        parsed = parse_citations(cit)
        if len(parsed) != 1:
            reject.append("INVALID_CITATION")
            continue
        issues = validate_citation(parsed[0], corpus, cf["as_of_date"])
        if "POST_AS_OF" in issues:
            reject.append("POST_AS_OF_CITATION")
        if [i for i in issues if i != "POST_AS_OF"]:
            reject.append("INVALID_CITATION")
        doc = parsed[0]["doc_id"]
        if doc not in eligible_ids:
            rec = corpus.records.get(doc)
            reject.append("HASH_MISMATCH" if rec and "HASH_MISMATCH" in rec["flags"] else "OUT_OF_CASE_SCOPE")
        elif cit not in retrieved:
            reject.append("NOT_RETRIEVED_BY_CLAIMANT")
    if docs and all(d["reliability"] == 4 for d in docs):
        reject.append("ONLY_TIER_4_SUPPORT")
    if docs and _is_numeric(claim) and all(d["background_only"] for d in docs) and claim["estimate_status"] in (None, "ESTIMATED"):
        reject.append("ONLY_BACKGROUND_SUPPORT")
    if docs and all(d["status"] in ("FAILED", "EMPTY", "TRUNCATED") or DAMAGED_FLAGS & set(d["flags"]) for d in docs) \
            and claim["estimate_status"] in (None, "ESTIMATED"):
        reject.append("ONLY_DAMAGED_FAMILY")
    if guards.quote_guard("claim", [claim["claim_text"]], claim["citations"], corpus):
        reject.append("QUOTE_NOT_VERBATIM")
    if docs and all(d["source_type"] == "company_statement" for d in docs):
        qualify.append("COMPANY_STATEMENT_OVERREACH")
    return sorted(set(reject)), sorted(set(qualify))


def _overlap(a, b):
    return a is not None and b is not None and a["low"] <= b["high"] and b["low"] <= a["high"]


def _current_estimates(claims):
    out = {}
    for c in claims:
        if c["claim_type"] == "CELL_ESTIMATE" and c["status"] == "submitted":
            out.setdefault((c["country"], c["sector"]), []).append(c)
    return out


def rule_claims(cf, corpus, sides, eligible_ids, masked, first_number=1):
    """Deterministic rulings (steps 1 and 2) for every claim in the ledger. Returns the ruling list."""
    claims = cf["claim_ledger"]
    current = _current_estimates(claims)
    xe = {}
    for e in cf["cross_examination"]:
        xe.setdefault(e["target_claim_id"], []).append(e)
    rulings = []
    for i, c in enumerate(claims):
        retrieved = sides[c["agent"]].tools.retrieved
        reject, qualify = pre_ruling(c, cf, corpus, eligible_ids, retrieved, masked)
        kind = c["claim_kind"]
        r = {"ruling_id": f"ruling-odin-{first_number + i:03d}", "claim_id": c["claim_id"], "run": c["run"],
             "agent": c["agent"], "country": c["country"], "sector": c["sector"], "claim_kind": kind,
             "claim_status": c["status"], "superseded_by": c.get("superseded_by"),
             "supporting_refs": [_span_ref(x) for x in c["citations"] if parse_citations(x)],
             "conflicting_refs": [], "created_at": f"{cf['as_of_date']}T00:00:00Z", "decided_by": "RULES"}
        challenges = xe.get(c["claim_id"], [])
        rivals = [x for x in current.get((c["country"], c["sector"]), []) if x["agent"] != c["agent"]]
        if reject:
            r.update(classification="REJECTED", decision="REJECTED", rejected_by="PRE_RULING_CHECK", rejection_reasons=reject,
                     rationale=f"Pre-ruling check failed: {', '.join(reject)}; Odin may not overturn it.", confidence=0.95)
        elif c["status"] == "withdrawn":
            ch = challenges[0] if challenges else None
            why = (ch["response"] or {}).get("reason") if ch and ch.get("response") else None
            r.update(classification="CONCEDED", decision="REJECTED", rejected_by="CONCESSION",
                     rejection_reasons=["CONCEDED_BY_AUTHOR"],
                     rationale=f"The author conceded this claim after a {ch['challenge_kind']} challenge: {why}"
                     if ch else "The author withdrew this claim.", confidence=0.9)
        elif c["status"] == "superseded":
            ch = challenges[0] if challenges else None
            r.update(classification="CONTESTED", decision="QUALIFIED",
                     qualification_reasons=["NARROWED_AFTER_CHALLENGE"],
                     rationale=f"Narrowed by {c['superseded_by']} after a "
                     f"{ch['challenge_kind'] if ch else 'challenge'}; the revised claim stands in its place.", confidence=0.7)
        else:
            defended = [x for x in challenges if x.get("response") and x["response"]["response_type"] == "DEFEND"]
            unanswered = [x for x in challenges if not x.get("response")]
            est = c["estimate"]
            opp = next((x["estimate"] for x in rivals if x["estimate"]), None)
            if c["claim_type"] == "CELL_ESTIMATE" and c["estimate_status"] == "ESTIMATED":
                agree = _overlap(est, opp)
                classification = "CONTESTED" if (defended or unanswered or not agree) else "ESTABLISHED"
                reasons = list(qualify)
                calc_ids = c["calc_ids"]
                recs = [x for x in cf["calc_ledger"] if x["calc_id"] in calc_ids]
                if any(x["baseline_conflict"] or x["widened"] for x in recs):
                    reasons.append("RANGE_WIDENED_BY_FLAGGED_ROWS")
                if c["supersedes"]:
                    reasons.append("REVISED_CLAIM")
                decision = "QUALIFIED" if reasons or classification == "CONTESTED" else "ACCEPTED"
                why = ("The two sides' ranges overlap" if agree else "The opposing range does not overlap this one"
                       if opp else "The other side gives no range for this cell")
                if defended:
                    why += f"; the challenge {defended[0]['challenge_id']} was defended, not resolved"
                r.update(classification=classification, decision=decision, rationale=why + ".",
                         confidence=0.85 if classification == "ESTABLISHED" else 0.6)
                if reasons:
                    r["qualification_reasons"] = reasons
            elif c["claim_type"] == "CELL_ESTIMATE":
                same = [x for x in rivals if x["estimate_status"] == c["estimate_status"]]
                r.update(classification="ESTABLISHED" if same or not rivals else "CONTESTED", decision="ACCEPTED",
                         rationale=f"{c['estimate_status']}: no range is given, and none is invented.", confidence=0.8)
            else:
                reasons = list(qualify)
                classification = "CONTESTED" if (defended or unanswered or qualify) else "ESTABLISHED"
                r.update(classification=classification, decision="QUALIFIED" if reasons else "ACCEPTED",
                         rationale=("Interested-party statement: valid for its own operations only." if qualify
                                    else "Supported by cited Tier 1-2 material and checked calc inputs."),
                         confidence=0.65 if reasons else 0.85)
                if reasons:
                    r["qualification_reasons"] = reasons
            for x in rivals:
                r["conflicting_refs"] += [_span_ref(cit) for cit in x["citations"] if parse_citations(cit)][:3] \
                    if r["classification"] == "CONTESTED" else []
        rulings.append(r)
    return rulings


def odin_view(cf, rulings):
    """What the model sees: only the open claims, with their text, calc numbers and the challenge record."""
    xe = {}
    for e in cf["cross_examination"]:
        xe.setdefault(e["target_claim_id"], []).append({"challenge_kind": e["challenge_kind"],
                                                         "challenge_text": e["challenge_text"],
                                                         "response_type": (e["response"] or {}).get("response_type")})
    by_id = {c["claim_id"]: c for c in cf["claim_ledger"]}
    open_ = [r for r in rulings if r["classification"] == "CONTESTED" and r["decision"] != "REJECTED"
             and r["claim_status"] == "submitted"]
    return {"task": "odin_ruling", "as_of_date": cf["as_of_date"], "event_id": cf["event_id"], "event_name": cf["event_name"],
            "open_claims": [{"claim_id": r["claim_id"], "agent": r["agent"], "cell": [r["country"], r["sector"]],
                             "claim_text": by_id[r["claim_id"]]["claim_text"], "default_decision": r["decision"],
                             "default_rationale": r["rationale"], "challenges": xe.get(r["claim_id"], []),
                             "estimate": by_id[r["claim_id"]]["estimate"]} for r in open_]}


def model_pass(cf, rulings, provider, guard, trace, corpus, masked, final_ruling=False):
    """Step 3. Mutates `rulings` in place for the claims the model rules on; returns the mode label."""
    view = odin_view(cf, rulings)
    if not view["open_claims"]:
        return "RULES_ONLY"
    messages = [{"role": "system", "content": ODIN_PROMPT()}, {"role": "user", "content": canonical(view)}]
    try:
        out = guard.call(provider, "odin_ruling", messages, ODIN_OUTPUT_SCHEMA, final_ruling=final_ruling)["output"]
    except (BudgetExceeded, ProviderError) as e:
        trace.emit("runtime", "FALLBACK_ODIN_RULES", {"reason": type(e).__name__, "detail": str(e)[:200]}, "WARNING")
        return "DETERMINISTIC_FALLBACK"
    allowed = {c["claim_id"]: c for c in view["open_claims"]}
    by_claim = {r["claim_id"]: r for r in rulings}
    problems = []
    for item in out["rulings"]:
        c = allowed.get(item["claim_id"])
        if c is None:
            problems.append(f"{item['claim_id']}: not an open claim")
            continue
        claim = next(x for x in cf["claim_ledger"] if x["claim_id"] == item["claim_id"])
        where = item["claim_id"]
        problems += guards.entity_guard(where, [item["rationale"]], cf, corpus, claim["citations"])
        problems += guards.injection_guard(where, [item["rationale"]], masked)
        problems += guards.quote_guard(where, [item["rationale"]], claim["citations"], corpus)
        allowed_numbers = {t.replace(",", "") for t in number_tokens(claim["claim_text"] + " " + c["default_rationale"])}
        for t in number_tokens(item["rationale"]):
            if t.replace(",", "") not in allowed_numbers:
                problems.append(f"{where}: number {t} in the rationale is not in the claim")
        if not 0 <= item["confidence"] <= 1:
            problems.append(f"{where}: confidence outside 0-1")
    if problems:
        trace.emit("runtime", "FALLBACK_ODIN_RULES", {"reason": "GUARD_FAILED", "problems": problems[:10]}, "WARNING")
        return "DETERMINISTIC_FALLBACK"
    for item in out["rulings"]:
        r = by_claim[item["claim_id"]]
        r["decided_by"] = "MODEL"
        r["decision"], r["rationale"], r["confidence"] = item["decision"], item["rationale"], item["confidence"]
        if item["decision"] == "REJECTED":
            r.update(classification="REJECTED", rejected_by="ODIN", rejection_reasons=["ODIN_JUDGEMENT"])
    return "MODEL_ON_OPEN_CLAIMS"


def ODIN_PROMPT():
    from pathlib import Path
    return (Path(__file__).resolve().parents[2] / "prompts" / "odin.md").read_text(encoding="utf-8")


# ---------- 1.2: the Odin range per cell ----------

def _val(rec, path):
    v = rec
    for part in path.split("."):
        v = v[part]
    return v


def _scaled(rec, ref_field, family):
    """The value (or volume) figure of the same scenario field: envelope.X.low -> envelope_value.X.low."""
    try:
        return _val(rec, ref_field.replace("envelope.", f"{family}.", 1))
    except (KeyError, TypeError):
        return None


def cell_results(cf, rulings, final=False):
    """One result per exposure cell from the accepted (ACCEPTED / QUALIFIED), current estimates of both sides."""
    ruling = {r["claim_id"]: r for r in rulings}
    calcs = {c["calc_id"]: c for c in cf["calc_ledger"]}
    plan = {(p["country"], p["sector"]): p["cell_status"] for p in cf["cell_plan"]}
    cov = {(p["country"], p["sector"]): p["status"] for p in cf["coverage"]}
    out = []
    for cell in cf["exposure_cells"]:
        key = (cell["country"], cell["sector"])
        mine = [c for c in cf["claim_ledger"] if c["claim_type"] == "CELL_ESTIMATE" and (c["country"], c["sector"]) == key
                and c["status"] == "submitted" and ruling.get(c["claim_id"], {}).get("decision") in ("ACCEPTED", "QUALIFIED")]
        per_side = {a: next((c for c in mine if c["agent"] == a), None) for a in ("thor", "loki")}
        est = [c for c in mine if c["estimate_status"] == "ESTIMATED" and c["estimate"]]
        res = {"country": key[0], "sector": key[1], "coverage": cov.get(key),
               "thor": _side(per_side["thor"]), "loki": _side(per_side["loki"]),
               "claim_ids": [c["claim_id"] for c in mine], "calc_ids": sorted({i for c in mine for i in c["calc_ids"]})}
        if plan.get(key) == "INCOMPLETE_BUDGET_LIMIT":
            res.update(status="INCOMPLETE_BUDGET_LIMIT", odin=None, reason="INCOMPLETE_BUDGET_LIMIT")
        elif est:
            low = min(c["estimate"]["low"] for c in est)
            high = max(c["estimate"]["high"] for c in est)
            odin = {"low": low, "high": high, "unit": "percent",
                    "low_from": _origin(est, "low", low), "high_from": _origin(est, "high", high)}
            for family, name in (("envelope_value", "value"), ("envelope_volume", "volume")):
                los, his = [], []
                for c in est:
                    lr, hr = c["estimate"]["low_ref"], c["estimate"]["high_ref"]
                    rec, rec_h = calcs.get(lr["calc_id"]), calcs.get(hr["calc_id"])
                    lo = _scaled(rec, lr["field"], family) if rec else None
                    hi = _scaled(rec_h, hr["field"], family) if rec_h else None
                    if lo is not None and hi is not None:
                        los.append((lo, {"calc_id": lr["calc_id"], "field": lr["field"].replace("envelope.", family + ".", 1)}))
                        his.append((hi, {"calc_id": hr["calc_id"], "field": hr["field"].replace("envelope.", family + ".", 1)}))
                if los:
                    d = next((x for x in (calcs.get(i) for i in res["calc_ids"]) if x and x["status"] == "OK"), None)
                    direct = (d["passes"].get("with_flagged") or {}).get("direct", {}) if d else {}
                    lo, hi = min(los, key=lambda t: t[0]), max(his, key=lambda t: t[0])
                    odin[name] = {"low": lo[0], "high": hi[0], "low_ref": lo[1], "high_ref": hi[1],
                                  "unit": direct.get("currency") if name == "value" else direct.get("volume_unit")}
            odin["widened"] = any(calcs[i]["widened"] for i in res["calc_ids"] if i in calcs)
            res.update(status="ASSESSED", odin=odin, reason=None)
        else:
            reasons = sorted({c["estimate_status"] for c in mine if c["estimate_status"]})
            res.update(status="INSUFFICIENT_EVIDENCE", odin=None, reason=", ".join(reasons) or "NO_ACCEPTED_ESTIMATE")
        out.append(res)
    return out


def _side(c):
    if c is None:
        return None
    if c["estimate_status"] == "ESTIMATED" and c["estimate"]:
        return {"status": "ESTIMATED", "low": c["estimate"]["low"], "high": c["estimate"]["high"], "claim_id": c["claim_id"]}
    return {"status": c["estimate_status"], "low": None, "high": None, "claim_id": c["claim_id"]}


def _origin(est, which, value):
    return next(c["claim_id"] for c in est if c["estimate"][which] == value)
