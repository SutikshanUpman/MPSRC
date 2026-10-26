"""Completing the mechanical fields of a claim (before the guards run).

A claim has about twenty fields, and most are bookkeeping that the runtime already knows: who wrote it, which run and round,
`status: submitted`, `supersedes: null`, the metric and unit, the estimate's numbers (they are the calc fields the claim
names), the secondary metrics (copied from the calc record), and the number references for figures that equal a field of the
calc record. A small or hurried model that leaves these out would fail on paperwork, not on substance, so the runtime fills
them in from the agent's own tool results.

What it never fills in: the claim's text, its citations, which calc fields it chose, its confidence beyond a neutral default, or
a number that no calc field or cited span contains. A citation that is not one `[DOC_ID, P#, timestamp]` bracket (for example a
range `P8-13`) is dropped, not guessed. Everything still goes through the same guards afterwards: a made-up number, a citation the
agent did not retrieve, a quote that is not in the span are all rejected exactly as before.
"""
import re

from ..casefile.schema import CITATION_PATTERN
from .calc import SECONDARY_FIELDS, field
from .claims import NUMBER, _norm_num, number_tokens

CITATION = re.compile(CITATION_PATTERN)
NEUTRAL_CONFIDENCE = 0.5
# Thor argues the high bound (at most half the substitute growth credited); Loki the limited bound (substitutes credited in full).
SCENARIOS = {"thor": ("envelope.half_credit.low", "envelope.no_credit.high"),
             "loki": ("envelope.full_credit.low", "envelope.half_credit.high")}


def _leaf_paths(obj, prefix="", depth=0):
    if depth > 5:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaf_paths(v, f"{prefix}.{k}" if prefix else k, depth + 1)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield prefix, obj


def _usable_ref(r):
    """A number reference that names a calc field, or one valid citation. Anything else is dropped; the number it was meant to
    cover then has no source, and the number guard says so."""
    if not isinstance(r, dict) or r.get("value") in (None, ""):
        return False
    if isinstance(r.get("calc_id"), str) and isinstance(r.get("field"), str):
        return True
    return isinstance(r.get("citation"), str) and bool(CITATION.match(r["citation"]))


def _secondary(rec):
    p = (rec.get("passes") or {}).get("with_flagged") or {}
    if p.get("status") != "OK":
        return None
    d = p["direct"]
    return dict({"calc_id": rec["calc_id"], "pass": "with_flagged", "currency": d["currency"], "volume_unit": d["volume_unit"]},
                **{f: d[f] for f in SECONDARY_FIELDS})


def _number_ref_for(token, records):
    """A calc field whose value is this number at one decimal: the figure came from the calc tool."""
    want = round(float(_norm_num(token)), 1)
    for rec in records:
        for path, value in _leaf_paths({k: rec[k] for k in ("envelope", "passes") if k in rec}):
            if round(float(value), 1) == want:
                return {"value": token, "calc_id": rec["calc_id"], "field": path}
    return None


def normalize_claim(c, agent, run, round_, tools, supersedes=None):
    """Returns a completed copy of one submitted claim (a non-dict is returned unchanged, for the schema check to refuse)."""
    if not isinstance(c, dict):
        return c
    c = dict(c)
    est = c.get("estimate") if isinstance(c.get("estimate"), dict) else None
    c.setdefault("agent", agent)
    c.setdefault("run", run)
    c.setdefault("round", round_)
    c.setdefault("status", "submitted")
    if "claim_type" not in c:
        c["claim_type"] = "CELL_ESTIMATE" if (est or c.get("estimate_status")) else "SUPPORTING"
    estimate = c["claim_type"] == "CELL_ESTIMATE"
    if "claim_kind" not in c:
        c["claim_kind"] = "INFERENCE" if estimate or "\"" not in str(c.get("claim_text", "")) else "SOURCED_FACT"
    c.setdefault("metric", "net_value_shortfall_pct" if estimate else None)
    c.setdefault("supersedes", supersedes if estimate else None)
    c.setdefault("confidence", NEUTRAL_CONFIDENCE)
    c.setdefault("mechanism", None)
    for key in ("assumptions", "number_refs", "citations", "calc_ids"):
        if not isinstance(c.get(key), list):
            c[key] = []
    c["citations"] = [x for x in c["citations"] if isinstance(x, str) and CITATION.match(x)]
    c["number_refs"] = [dict(r, value=str(r["value"])) for r in c["number_refs"] if _usable_ref(r)]   # a malformed reference is dropped
    # calc ids named by the estimate's references
    refs = [est[k] for k in ("low_ref", "high_ref") if est and isinstance(est.get(k), dict)] if est else []
    for r in refs:
        if r.get("calc_id") and r["calc_id"] not in c["calc_ids"]:
            c["calc_ids"].append(r["calc_id"])
    if estimate and not c["calc_ids"]:                # a cell estimate rests on that cell's calc record: the latest one this agent ran
        own = [r for r in getattr(tools, "calcs", []) if (r["country"], r["sector"]) == (c.get("country"), c.get("sector"))]
        if own:
            c["calc_ids"].append(own[-1]["calc_id"])
    records = [rec for rec in (tools.calc_by_id(i) for i in c["calc_ids"]) if rec]
    if estimate and records and records[0]["status"] == "OK" and c.get("estimate_status") in (None, "ESTIMATED"):
        # The side's standing scenarios (the prompt's rule): a bound the model left out or set to null is taken from them.
        est = dict(est or {})
        for which, path in zip(("low", "high"), SCENARIOS.get(agent, (None, None))):
            ref = est.get(f"{which}_ref")
            if path and not (isinstance(ref, dict) and ref.get("field")):
                est[f"{which}_ref"] = {"calc_id": records[0]["calc_id"], "field": path}
        refs = [est[k] for k in ("low_ref", "high_ref") if isinstance(est.get(k), dict)]
        c["estimate"] = est
    if estimate:
        by_id = {rec["calc_id"]: rec for rec in records}
        if est and refs and len(refs) == 2:
            values = {}
            for which in ("low", "high"):
                r = est[f"{which}_ref"]
                try:
                    values[which] = field(by_id[r["calc_id"]], r["field"])
                except (KeyError, TypeError):
                    values[which] = None
            if all(v is not None for v in values.values()):
                est = dict(est, low=values["low"], high=values["high"], unit="percent")
                c["estimate"] = est
                c.setdefault("estimate_status", "ESTIMATED")
        elif not est:
            c["estimate"] = None
            if "estimate_status" not in c and records and records[0]["status"] != "OK":
                c["estimate_status"] = records[0]["status"]
        c.setdefault("estimate", None)
        if "secondary_metrics" not in c:
            c["secondary_metrics"] = _secondary(records[0]) if records and c.get("estimate_status") == "ESTIMATED" else None
    else:
        c.setdefault("estimate", None)
        c.setdefault("estimate_status", None)
        c.setdefault("secondary_metrics", None)
    # number references: only for figures that really are a calc field of a calc the claim names
    have = {_norm_num(r["value"]) for r in c["number_refs"] if isinstance(r, dict) and "value" in r}
    texts = [str(c.get("claim_text", "")), str(c.get("mechanism") or "")] + [str(a) for a in c["assumptions"]]
    for text in texts:
        for token in number_tokens(text):
            if _norm_num(token) in have:
                continue
            ref = _number_ref_for(token, records) if NUMBER.fullmatch(token) else None
            if ref:
                c["number_refs"].append(ref)
                have.add(_norm_num(token))
    return c


def normalize_claims(claims, agent, run, round_, tools, supersedes=None):
    """`supersedes`: {"Country|Sector": claim_id} for a Run-2 estimate that was left blank."""
    if not isinstance(claims, list):
        return claims
    out = []
    for c in claims:
        sup = None
        if isinstance(c, dict) and supersedes:
            sup = supersedes.get(f"{c.get('country')}|{c.get('sector')}")
        out.append(normalize_claim(c, agent, run, round_, tools, sup))
    return out
