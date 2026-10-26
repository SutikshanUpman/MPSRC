"""Claim validation for Thor and Loki (Stage 2 B3, B4; SYSTEM_ARCHITECTURE 12.5, 14.6, 15, 17, 20, 22).

A submitted claim list is valid only if every rule below holds. Any problem
counts as a schema failure: the agent is asked again, and after
max_model_retries_per_call it is FAILED (THOR_FAILED / LOKI_FAILED).

1. Each claim matches CLAIM_SCHEMA; ids are unique and belong to the agent.
2. Exactly one CELL_ESTIMATE per assigned cell; SUPPORTING claims in the whole
   round (earlier batches included) <= max_supporting_claims_per_side_per_round.
3. Every citation resolves (validate_citation), is inside the case scope, and was
   retrieved by this agent in this case (its own tool log). Every claim cites at
   least one span; a CELL_ESTIMATE without a range cites the result set of the
   search the agent ran for that cell (every cell gets one, Stage 3 A2).
4. Every calc_id is one of this agent's calc records for the same cell; an
   estimate's low/high equal the referenced calc fields.
5. Every number in claim_text, mechanism and assumptions has a number_ref: a calc
   field with that value, or a cited span whose text contains it. Skipped as in
   section 22 (Number provenance): citation brackets, document IDs and row keys,
   OD-1 table and row names, and calendar dates.
6. An ESTIMATED cell cites at least one case-event document (EVENT_ID NONE alone
   never supports a number). A cell with no documented flow carries no range.
7. No masked placeholder or raw masked line appears in any claim text.
8. A Loki ESTIMATED claim names its substitution or mitigation mechanism.
9. A claim that cites a repeated row (sensitivity_row) names its flag (14.6).
10. An ESTIMATED cell reports value and volume change and the implied unit price
    (secondary_metrics), equal to the calc record (Stage 3 A5).
"""
import re

from .. import guards
from ..casefile.schema import CLAIM_SCHEMA
from ..ingestion.quality import MASK_PLACEHOLDER
from ..llm.provider import validate_schema
from ..provenance.citations import parse_citations, validate_citation
from ..ingestion.trade import MONTHS
from .calc import SECONDARY_FIELDS, field

NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?![\w])")
_MONTH = r"(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
NUMBER_SKIP = [re.compile(p, re.I) for p in (
    r"\[[^\]]*\]",                                          # citation brackets
    r"\b[A-Z]{2,}-\d+(?:\|\d{4}-\d{2}(?:#\d+)?)?",          # document IDs and row keys
    r"\b(?:calc|claim|mem)-[\w-]+",                         # calc, claim and memory IDs
    r"\b(?:table|row)\s+[A-Z]?\d+\b",                        # OD-1 table and row names
    # A bare year: Runemark writes every quantity of 1,000 or more with commas ("263,000 tonnes"), so a bare 19xx/20xx with no
    # unit is a year ("2025 vs 2026"), not a figure. Part of an ISO date or of a comma number it is left to the rules above/below.
    r"(?<![\d,.\-])(?:19|20)\d{2}(?![\d,.]|-\d)(?!\s*(?:%|percent|tonnes?|tons?|usd|million|billion|k\b))",
    r"\btier\s+[1-5]\b",                                    # a reliability tier is a label from the Case File, not a figure
    r"\b\d{4}-\d{2}(?:-\d{2})?\b",                          # ISO dates and months
    r"\b\d{1,2}\s+" + _MONTH + r"(?:\s+\d{4})?\b",          # 4 June (2031)
    r"\b" + _MONTH + r"\s+\d{1,2}(?:,\s*\d{4})?\b",         # June 4(, 2031)
    r"\b" + _MONTH + r"\s+\d{4}\b")]                        # June 2031
REPEAT_FLAGS = ("TRADE_ROW_REPEATED_VALUES", "TRADE_ROW_DUPLICATE")


def number_tokens(text):
    """Numbers that need provenance (section 22, Number provenance, steps 1-2)."""
    for pat in NUMBER_SKIP:
        text = pat.sub(" ", text or "")
    return NUMBER.findall(text)


def _norm_num(s):
    return s.replace(",", "")


def masked_raw_lines(corpus):
    return sorted({hit.strip() for rec in corpus.records.values() for m in rec["masked_lines"]
                   for hit in m["raw"] if len(hit.strip()) >= 8})


def validate_claims(agent, claims, assigned_cells, tools, cf, corpus, config, masked_lines, prior=()):
    """Round 1 submit. `prior` = this side's claims already accepted in earlier batches of the round."""
    problems = []
    if not isinstance(claims, list):
        return ["claims must be a list"]
    seen_ids, estimates = {c["claim_id"] for c in prior}, {}
    supporting = sum(1 for c in prior if c["claim_type"] == "SUPPORTING")
    for i, c in enumerate(claims):
        where = f"claims[{i}]"
        errs = validate_schema(c, CLAIM_SCHEMA, where)
        if errs:
            problems += errs
            continue
        if c["claim_id"] in seen_ids:
            problems.append(f"{where}: duplicate claim_id {c['claim_id']}")
        seen_ids.add(c["claim_id"])
        if c["supersedes"] is not None:
            problems.append(f"{where}: a round-1 claim supersedes nothing")
        if c["claim_type"] == "CELL_ESTIMATE":
            estimates.setdefault((c["country"], c["sector"]), []).append(c)
        else:
            supporting += 1
        problems += check_claim(where, agent, c, tools, cf, corpus, masked_lines)
    # 2. counts
    for cell in assigned_cells:
        n = len(estimates.get(cell, []))
        if n != 1:
            problems.append(f"cell {cell}: {n} CELL_ESTIMATE claims (exactly one required)")
    for cell in estimates:
        if cell not in assigned_cells:
            problems.append(f"cell {cell}: CELL_ESTIMATE for a cell not assigned in this batch")
    cap = config["max_supporting_claims_per_side_per_round"]
    if supporting > cap:
        problems.append(f"{supporting} SUPPORTING claims in this round exceed max_supporting_claims_per_side_per_round={cap}")
    return problems


def check_citations(where, agent, citations, tools, cf, corpus):
    """Rule 3 for any list of citations (claims, challenges, responses)."""
    problems = []
    for cit in citations:
        parsed = parse_citations(cit)
        if len(parsed) != 1:
            problems.append(f"{where}: unparseable citation {cit}")
            continue
        issues = validate_citation(parsed[0], corpus, cf["as_of_date"])
        if issues:
            problems.append(f"{where}: citation {cit} invalid: {issues}")
        if parsed[0]["doc_id"] not in tools.index.eligible_ids:
            problems.append(f"{where}: citation {cit} is outside the case scope")
        if cit not in tools.retrieved:
            problems.append(f"{where}: citation {cit} was not retrieved by {agent}")
    return problems


def has_masked_text(text, masked_lines):
    return MASK_PLACEHOLDER in text or any(line in text for line in masked_lines)


def check_claim(where, agent, c, tools, cf, corpus, masked_lines):
    """Rules 1 and 3-9 for one schema-valid claim (round 1 submits and round-2 revisions)."""
    problems = []
    if c["agent"] != agent or not c["claim_id"].startswith(f"claim-{agent}-"):
        problems.append(f"{where}: claim belongs to {c['agent']}")
    cell = (c["country"], c["sector"])
    # 3. citations (A2: a no-flow estimate cites the result set of the cell's search)
    if not c["citations"]:
        problems.append(f"{where}: a claim needs at least one citation")
    problems += check_citations(where, agent, c["citations"], tools, cf, corpus)
    # 4. calc ids and estimate refs
    calcs = {}
    for cid in c["calc_ids"]:
        rec = tools.calc_by_id(cid)
        if rec is None:
            problems.append(f"{where}: unknown calc_id {cid}")
        elif (rec["country"], rec["sector"]) != cell:
            problems.append(f"{where}: calc_id {cid} is for another cell")
        else:
            calcs[cid] = rec
    if c["claim_type"] == "CELL_ESTIMATE":
        problems += _check_estimate(where, c, calcs, agent)
    elif c["secondary_metrics"] is not None:
        problems.append(f"{where}: secondary_metrics belong on a CELL_ESTIMATE")
    # 5. numbers
    problems += _check_numbers(where, c, calcs, tools)
    # 9. repeated rows named
    problems += _check_flag_named(where, c, tools)
    # 7. masked text
    if has_masked_text(" ".join([c["claim_text"], c["mechanism"] or ""] + c["assumptions"]), masked_lines):
        problems.append(f"{where}: claim text contains masked document text")
    # 6. a numeric cell needs a case-event citation
    problems += check_case_event_support([c], corpus, cf["event_id"])
    # FINAL BUILD phase 2: quote, entity and injection guards; abstain rule
    problems += guards.text_guards(where, [c["claim_text"], c["mechanism"] or ""] + c["assumptions"], c["citations"], cf,
                                   corpus, masked_lines)
    problems += guards.abstain_guard(where, c)
    return problems


def _check_estimate(where, c, calcs, agent):
    problems = []
    if not calcs:
        return [f"{where}: CELL_ESTIMATE needs a calc_id"]
    status = c["estimate_status"]
    if status == "ESTIMATED":
        est = c["estimate"]
        if est is None:
            return [f"{where}: ESTIMATED claim without an estimate"]
        for side in ("low", "high"):
            ref = est[f"{side}_ref"]
            rec = calcs.get(ref["calc_id"])
            try:
                value = field(rec, ref["field"]) if rec else None
            except (KeyError, TypeError):
                value = None
            if value is None or float(value) != float(est[side]):
                problems.append(f"{where}: estimate.{side} does not match {ref['calc_id']}:{ref['field']}")
        if est["low"] > est["high"]:
            problems.append(f"{where}: estimate low > high")
        if not any(rec["status"] == "OK" for rec in calcs.values()):
            problems.append(f"{where}: ESTIMATED claim but no calc record has status OK")
        if agent == "loki" and not (c["mechanism"] or "").strip():
            problems.append(f"{where}: Loki estimate must name a substitution or mitigation mechanism")
        problems += _check_secondary(where, c, calcs)
    else:
        if c["estimate"] is not None:
            problems.append(f"{where}: {status} claim must not carry a range")
        if c["secondary_metrics"] is not None:
            problems.append(f"{where}: {status} claim must not carry secondary metrics")
        if not any(rec["status"] == status for rec in calcs.values()):
            problems.append(f"{where}: estimate_status {status} does not match the calc record")
    return problems


def _check_secondary(where, c, calcs):
    """A5: value (amount, %), volume (amount, %) and unit price before/after, each equal to the calc record's
    passes.<pass>.direct field. Required when the calc has a year-on-year pass; null for a proxy-only baseline."""
    sm = c["secondary_metrics"]
    yoy = [r for r in calcs.values() if (r["passes"].get("with_flagged") or {}).get("status") == "OK"]
    if sm is None:
        return [f"{where}: ESTIMATED claim needs secondary_metrics (value, volume, unit price)"] if yoy else []
    rec = calcs.get(sm["calc_id"])
    if rec is None:
        return [f"{where}: secondary_metrics.calc_id {sm['calc_id']} is not one of the claim's calc_ids"]
    problems = []
    for name in SECONDARY_FIELDS + ("currency", "volume_unit"):
        try:
            expected = field(rec, f"passes.{sm['pass']}.direct.{name}")
        except (KeyError, TypeError):
            return [f"{where}: secondary_metrics.pass {sm['pass']!r} has no direct-route figures"]
        if sm[name] != expected and not (isinstance(expected, float) and sm[name] is not None
                                          and round(float(sm[name]), 2) == round(expected, 2)):
            problems.append(f"{where}: secondary_metrics.{name} does not match {sm['calc_id']}")
    return problems


def _check_numbers(where, c, calcs, tools):
    problems = []
    refs = {}
    for ref in c["number_refs"]:
        refs.setdefault(_norm_num(ref["value"]), []).append(ref)
        if "calc_id" in ref:
            rec = calcs.get(ref["calc_id"])
            try:
                value = field(rec, ref["field"]) if rec else None
            except (KeyError, TypeError):
                value = None
            # a percentage in prose is a magnitude ("fell by 60.3%" for a field of -60.3): the direction is in the words
            if value is None or round(abs(float(value)), 1) != round(abs(float(_norm_num(ref["value"]))), 1):
                problems.append(f"{where}: number {ref['value']} does not match {ref.get('calc_id')}:{ref.get('field')}")
        elif "citation" in ref:
            span = tools.retrieved.get(ref["citation"])
            if span is None or _norm_num(ref["value"]) not in {_norm_num(t) for t in NUMBER.findall(span["text"])}:
                problems.append(f"{where}: number {ref['value']} is not in the cited span {ref['citation']}")
            elif ref["citation"] not in c["citations"]:
                problems.append(f"{where}: number_ref citation {ref['citation']} is not among the claim's citations")
        else:
            problems.append(f"{where}: number_ref {ref['value']} has neither calc_id nor citation")
    fields = [("claim_text", c["claim_text"]), ("mechanism", c["mechanism"])]
    fields += [(f"assumptions[{j}]", a) for j, a in enumerate(c["assumptions"])]
    for name, text in fields:
        for token in number_tokens(text):
            if _norm_num(token) not in refs:
                problems.append(f"{where}: number {token} in {name} has no span or calc_id")
    return problems


def _check_flag_named(where, c, tools):
    """Section 14.6: an agent citing a flagged repeated row (any row it retrieved) names the flag."""
    cited = set(c["citations"])
    flags = sorted({f for r in tools.rows_seen.values() if r["sensitivity_row"] and r["citation"]["text"] in cited
                    for f in ([x for x in r["flags"] if x in REPEAT_FLAGS] or REPEAT_FLAGS[:1])})
    text = " ".join([c["claim_text"], c["mechanism"] or ""] + c["assumptions"])
    missing = [f for f in flags if f not in text]
    return [f"{where}: cites a repeated row but does not name its flag {missing}"] if missing else []


def cites_case_event(claim, corpus, event_id):
    return any(corpus.records[p["doc_id"]]["event_id"] == event_id
               for cit in claim["citations"] for p in parse_citations(cit) if p["doc_id"] in corpus.records)


def check_case_event_support(claims, corpus, event_id):
    """Rule 6 (needs the corpus): an ESTIMATED cell must cite a case-event document."""
    return [f"{c['claim_id']}: numeric cell supported only by EVENT_ID NONE documents"
            for c in claims if c.get("claim_type") == "CELL_ESTIMATE" and c.get("estimate_status") == "ESTIMATED"
            and not cites_case_event(c, corpus, event_id)]
