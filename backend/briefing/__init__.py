"""Briefing (SYSTEM_ARCHITECTURE md 2247-2317; FINAL BUILD 1.4, 2.8).

Built from the rulings ONLY (plus the Case File and calc records they point at): executive summary, event
verification, Established / Contested / Conceded (and rejected) findings, the exposure table (Thor, Loki, Odin;
value and volume), a next-quarter outlook with explicit assumptions, and inline [DOC_ID, P#, timestamp]
citations. Every paragraph carries claim_refs, citation_refs, row_refs, calc_refs and number_refs.

Briefing gate (2.8): the finished briefing goes through the guards. A paragraph that fails is removed from its
section and listed under "Removed by validator" (visible, not hidden); the header counts the removed numbers.
"""
import hashlib
import json
import re

from .. import guards
from ..agents.claims import _norm_num, number_tokens
from ..agents.odin import _val
from ..llm.provider import canonical
from ..provenance.citations import parse_citations

SCHEMA_VERSION = "briefing-1"
OUTLOOK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["executive_summary", "drivers", "risks", "indicators"],
    "properties": {"executive_summary": {"type": "string"},
                   "drivers": {"type": "array", "items": {"type": "string"}},
                   "risks": {"type": "array", "items": {"type": "string"}},
                   "indicators": {"type": "array", "items": {"type": "string"}}},
}


def _fmt(x):
    return f"{x:.1f}"


def _calc_index(cf):
    return {c["calc_id"]: c for c in cf["calc_ledger"]}


def row_refs_for(cf, calc_ids):
    seen, out = set(), []
    calcs = _calc_index(cf)
    for cid in calc_ids:
        rec = calcs.get(cid)
        for row in (rec["direct_inputs"] + rec["substitute_inputs"]) if rec else []:
            key = (row["doc_id"], row["table_id"], row["native_row_number"], row["row_key"])
            if key not in seen:
                seen.add(key)
                out.append({"doc_id": row["doc_id"], "paragraph": row["paragraph"], "table_id": row["table_id"],
                            "native_row_number": row["native_row_number"], "row_key": row["row_key"]})
    return out


def _para(pid, text, classification, claim_refs, citations, calc_ids, number_refs, confidence, cf):
    return {"paragraph_id": pid, "text": text, "finding_classification": classification, "claim_refs": claim_refs,
            "citation_refs": list(dict.fromkeys(citations)), "row_refs": row_refs_for(cf, calc_ids), "calc_refs": calc_ids,
            "number_refs": number_refs, "confidence": confidence}


def _claim_para(pid, claim, ruling, cf, extra=""):
    cites = claim["citations"]
    text = claim["claim_text"] + (" " + extra if extra else "") + " " + " ".join(cites[:3])
    return _para(pid, text.strip(), ruling["classification"], [claim["claim_id"]], cites, claim["calc_ids"],
                 list(claim["number_refs"]), ruling["confidence"], cf)


def _strip_cites(text):
    return " ".join(re.sub(r"\[[^\]]*\]", "", text).split())


def calibration(cf, cell, corpus):
    """7.3: why the range is that wide, from the data: tier mix, independent evidence families, conflicts."""
    ids = set(cell["claim_ids"])
    cites = [c for x in cf["claim_ledger"] if x["claim_id"] in ids for c in x["citations"]]
    docs = {p["doc_id"] for c in cites for p in parse_citations(c)}
    recs = [corpus.records[d] for d in docs if d in corpus.records]
    tiers = {}
    for r in recs:
        tiers[str(r["reliability"])] = tiers.get(str(r["reliability"]), 0) + 1
    families = {r["evidence_family_id"] or r["doc_id"] for r in recs}
    calcs = [c for c in cf["calc_ledger"] if c["calc_id"] in cell["calc_ids"]]
    odin = cell.get("odin")
    width = round(odin["high"] - odin["low"], 1) if odin else None
    thor, loki = cell["thor"], cell["loki"]
    overlap = bool(thor and loki and thor["low"] is not None and loki["low"] is not None
                   and thor["low"] <= loki["high"] and loki["low"] <= thor["high"])
    return {"width_points": width, "tier_mix": tiers, "independent_families": len(families),
            "sides_overlap": overlap if thor and loki and thor["low"] is not None and loki["low"] is not None else None,
            "widened_by_repeated_rows": any(c["widened"] for c in calcs),
            "baseline_conflict": any(c["baseline_conflict"] for c in calcs),
            "baseline_basis": sorted({c["baseline_basis"] for c in calcs}),
            "coverage": cell["coverage"]}


def calibration_sentence(cal):
    if cal["width_points"] is None:
        return "No range: the evidence did not support a number."
    parts = [f"The range is {cal['width_points']} percentage points wide",
             f"rests on {cal['independent_families']} independent evidence families (tier mix {cal['tier_mix']})"]
    if cal["sides_overlap"] is False:
        parts.append("the two sides' ranges do not overlap")
    elif cal["sides_overlap"]:
        parts.append("the two sides' ranges overlap")
    if cal["widened_by_repeated_rows"]:
        parts.append("it is widened because repeated-value rows are in the inputs")
    if cal["baseline_conflict"]:
        parts.append("the baseline cross-check conflicts with the trade rows")
    return "; ".join(parts) + "."


def build(cf, rulings, cells, corpus, run_info, narrative=None, mode="RULES"):
    """Returns the briefing dict (before the gate)."""
    claims = {c["claim_id"]: c for c in cf["claim_ledger"]}
    ruling = {r["claim_id"]: r for r in rulings}
    sections = {"established": [], "contested": [], "conceded": [], "rejected": []}
    n = {"established": 0, "contested": 0, "conceded": 0, "rejected": 0}
    for r in rulings:
        c = claims[r["claim_id"]]
        if r["classification"] == "CONCEDED":
            key = "conceded"
            ch = next((e for e in cf["cross_examination"] if e["target_claim_id"] == c["claim_id"]), None)
            reason = (ch["response"] or {}).get("reason") if ch and ch.get("response") else None
            extra = f"Conceded by {c['agent'].title()} after a {ch['challenge_kind']} challenge." if ch else "Conceded."
            para = _claim_para("", c, r, cf, extra)
            if reason:
                para["text"] += f" Reason given: {reason}"
                para["number_refs"] += list(ch["response"]["number_refs"])
                para["citation_refs"] = list(dict.fromkeys(para["citation_refs"] + ch["response"]["citations"]))
        elif r["classification"] == "REJECTED":
            key = "rejected"
            para = _claim_para("", c, r, cf, f"Rejected by Odin ({', '.join(r.get('rejection_reasons', []))}).")
        elif c["status"] != "submitted":
            continue                              # superseded claims are replaced by their revision
        elif r["classification"] == "CONTESTED":
            key = "contested"
            ch = [e for e in cf["cross_examination"] if e["target_claim_id"] == c["claim_id"]]
            extra = " ".join(f"Challenged ({e['challenge_kind']}); response: {(e['response'] or {}).get('response_type', 'none')}."
                             for e in ch)
            para = _claim_para("", c, r, cf, extra)
        else:
            key = "established"
            para = _claim_para("", c, r, cf)
        twin = next((q for q in sections[key] if q["text_key"] == _strip_cites(para["text"])), None)
        if twin:                                   # the same finding from two sides or two runs is stated once
            twin["claim_refs"] = list(dict.fromkeys(twin["claim_refs"] + para["claim_refs"]))
            twin["citation_refs"] = list(dict.fromkeys(twin["citation_refs"] + para["citation_refs"]))
            continue
        para["text_key"] = _strip_cites(para["text"])
        n[key] += 1
        para["paragraph_id"] = f"{key[:3]}-{n[key]:02d}"
        para["ruling_id"] = r["ruling_id"]
        sections[key].append(para)

    table = []
    for cell in cells:
        cal = calibration(cf, cell, corpus)
        row = {"country": cell["country"], "sector": cell["sector"], "status": cell["status"], "reason": cell["reason"],
               "coverage": cell["coverage"], "thor": cell["thor"], "loki": cell["loki"], "odin": cell["odin"],
               "calibration": cal, "calibration_text": calibration_sentence(cal), "calc_refs": cell["calc_ids"],
               "claim_refs": cell["claim_ids"],
               "citation_refs": list(dict.fromkeys(c for x in cf["claim_ledger"] if x["claim_id"] in cell["claim_ids"]
                                                    for c in x["citations"])),
               "row_refs": row_refs_for(cf, cell["calc_ids"])}
        if cell["status"] == "INSUFFICIENT_EVIDENCE":
            gap = [g for g in cf["evidence_gaps"] if (g["country"], g["sector"]) == (cell["country"], cell["sector"])]
            row["targeted_queries"] = run_info.get("queries_by_cell", {}).get(f"{cell['country']}|{cell['sector']}") \
                or [q for g in gap for q in g["queries"]]
        table.append(row)

    flagged = [f"{c['country']} / {c['sector']}" for c in cells if c["status"] == "INSUFFICIENT_EVIDENCE"]
    not_assessed = [f"{c['country']} / {c['sector']}" for c in cells if c["status"] == "INCOMPLETE_BUDGET_LIMIT"]
    incomplete = bool(run_info.get("stop_reason") or run_info.get("agent_failures") or not_assessed)
    header = {"case_id": cf["case_id"], "event_id": cf["event_id"], "event": cf["event_name"], "as_of_date": cf["as_of_date"],
              "question": cf["question"],
              "completion_status": "INCOMPLETE" if incomplete else "COMPLETE",
              "stop_reason": run_info.get("stop_reason"), "flagged_cells": flagged, "cells_not_assessed": not_assessed,
              "scope_assumptions": cf["scope_assumptions"],
              "integrity_warnings": cf["run_status"][0]["integrity_warnings"], "removed_numbers": 0,
              "run2_new_evidence_families": run_info.get("run2_new_evidence_families", []),
              "run2_notice": None if run_info.get("run2_new_evidence_families") or not run_info.get("run2_ran")
              else "Run 2 found no new evidence: " + (run_info.get("run2_no_evidence_reason") or "no new evidence family."),
              "ruling_mode": mode}

    story = narrative or template_narrative(cf, cells, rulings)
    ev = cf["event_verification"]
    reason = re.sub(r"Tier\s*\d(?:\s*-\s*\d)?", "top-tier", ev["reason"])
    event = [_para("evt-01", f"{cf['event_name']} is verified: {reason}.", "ESTABLISHED", [],
                   [c["citation"] for c in ev["citations"]][:4], [], [], 0.9, cf)]
    for i, rel in enumerate(cf["correction_map"]["relations"][:3], 1):
        event.append(_para(f"evt-c{i}", f"{rel['from']['citation']} {rel['type'].lower().replace('_', ' ')} "
                           f"{rel['to']['citation']}.", "ESTABLISHED", [], [rel["from"]["citation"], rel["to"]["citation"]],
                           [], [], 0.9, cf))
    summary = _summary_para(cf, cells, story["executive_summary"], rulings)
    for sec in sections.values():
        for q in sec:
            q.pop("text_key", None)
    return {"schema_version": SCHEMA_VERSION, "header": header, "executive_summary": summary,
            "event_verification": event, "established": sections["established"], "contested": sections["contested"],
            "conceded": sections["conceded"], "rejected": sections["rejected"], "exposure_table": table,
            "outlook": {"drivers": story["drivers"], "risks": story["risks"], "indicators": story["indicators"],
                        "assumptions": outlook_assumptions(cf, cells)},
            "assumptions_limitations": limitations(cf, cells), "sources": sources(cf, corpus, rulings),
            "removed_by_validator": []}


def _summary_para(cf, cells, text, rulings):
    claims = {c["claim_id"]: c for c in cf["claim_ledger"]}
    refs, cites, calc_ids, claim_refs = [], [], [], []
    for c in cells:
        o = c["odin"]
        if not o:
            continue
        for which in ("low", "high"):
            cl = claims[o[f"{which}_from"]]
            ref = cl["estimate"][f"{which}_ref"]
            refs.append({"value": _fmt(o[which]), "calc_id": ref["calc_id"], "field": ref["field"]})
            claim_refs.append(cl["claim_id"])
            cites += cl["citations"][:2]
            calc_ids.append(ref["calc_id"])
    conf = [r["confidence"] for r in rulings if r["decision"] != "REJECTED"]
    para = _para("sum-01", text, "ESTABLISHED", list(dict.fromkeys(claim_refs)), cites, list(dict.fromkeys(calc_ids)),
                 refs, round(sum(conf) / len(conf), 2) if conf else 0.0, cf)
    return para


def template_narrative(cf, cells, rulings):
    """The deterministic summary and outlook (also the labelled fallback when Odin's briefing call fails)."""
    parts = []
    for c in cells:
        o = c["odin"]
        if o:
            parts.append(f"{c['country']} {c['sector']}: net value shortfall of {_fmt(o['low'])}% to {_fmt(o['high'])}%")
        else:
            parts.append(f"{c['country']} {c['sector']}: insufficient evidence ({c['reason']}), no number given")
    text = (f"As of {cf['as_of_date']}, the exposure to {cf['event_name']} is: " + "; ".join(parts) + ".")
    assessed = [c for c in cells if c["odin"]]
    drivers = [f"{c['country']} {c['sector']}: documented substitute routes offset part of the direct-route loss."
               for c in assessed if any(x["status"] == "OK" and x["substitute_inputs"] and c["odin"]
                                         for x in cf["calc_ledger"] if x["calc_id"] in c["calc_ids"])]
    risks = [f"{c['country']} {c['sector']}: no documented flow or baseline; exposure cannot be quantified."
             for c in cells if not c["odin"]]
    risks += [f"{c['country']} {c['sector']}: range widened by repeated-value trade rows." for c in assessed if c["odin"].get("widened")]
    return {"executive_summary": text, "drivers": drivers or ["No documented substitute growth in the assessed cells."],
            "risks": risks or ["No unquantified cell."],
            "indicators": ["New monthly trade notes for the assessed routes", "Any later corrections or retractions of the event documents",
                           "Documents that name a substitute route for a flagged cell"]}


def outlook_assumptions(cf, cells):
    return ["The event stays in force through the next quarter; the Odin ranges are as-of values held constant, not a forecast.",
            "Substitute supply keeps the pattern shown by the documented months; no new route is assumed.",
            "Cells without a documented flow stay unquantified; they are not read as zero exposure.",
            f"Only documents published on or before {cf['as_of_date']} in the case scope are used."]


def limitations(cf, cells):
    out = [f"Coverage {c['country']} / {c['sector']}: {c['status']}" for c in cf["coverage"]]
    out += [f"Evidence gap: {g['country']} / {g['sector']} lacks {g['missing']}" for g in cf["evidence_gaps"]]
    out += [f"Scope assumption: {a['reason']}" for a in cf["scope_assumptions"]]
    return out


def sources(cf, corpus, rulings):
    cites = {}
    for r in rulings:
        for ref in r["supporting_refs"]:
            cites.setdefault(ref["doc_id"], set()).add(ref["span_id"])
    out = []
    for d in sorted(cites):
        rec = corpus.records.get(d)
        if rec:
            out.append({"doc_id": d, "title": rec["agent_title"], "tier": rec["reliability"], "source_type": rec["source_type"],
                        "pub_date": rec["pub_date"], "spans": sorted(cites[d])})
    return out


# ---------- the gate (2.8) ----------

def gate(briefing, cf, corpus, masked, resolve_span):
    """Run every paragraph and table row through the guards; remove what fails, list it under removed_by_validator."""
    calcs = _calc_index(cf)

    def resolve_calc(cid, field):
        rec = calcs.get(cid)
        try:
            return _val(rec, field) if rec else None
        except (KeyError, TypeError):
            return None

    eligible = {r["doc_id"] for r in corpus.records.values() if (r["pub_date"] or "9999") <= cf["as_of_date"]}
    removed, removed_numbers = [], 0

    def check(where, para):
        nonlocal removed_numbers
        problems = guards.number_guard(where, [para["text"]], number_tokens, para["number_refs"], resolve_calc, resolve_span, _norm_num)
        removed_numbers += sum("number" in p and "no span or calc_id" in p for p in problems)
        problems += guards.citation_guard(where, para["citation_refs"], corpus, cf["as_of_date"], eligible)
        problems += guards.text_guards(where, [para["text"]], para["citation_refs"], cf, corpus, masked)
        return problems

    def filt(section, items):
        keep = []
        for p in items:
            problems = check(p["paragraph_id"], p)
            if problems:
                removed.append({"section": section, "paragraph_id": p["paragraph_id"], "text": p["text"], "problems": problems[:6]})
            else:
                keep.append(p)
        return keep

    for key in ("event_verification", "established", "contested", "conceded", "rejected"):
        briefing[key] = filt(key, briefing[key])
    problems = check("sum-01", briefing["executive_summary"])
    if problems:
        removed.append({"section": "executive_summary", "paragraph_id": "sum-01", "text": briefing["executive_summary"]["text"],
                        "problems": problems[:6]})
        briefing["executive_summary"]["text"] = "[summary removed by validator; see the exposure table]"
    rows = []
    for row in briefing["exposure_table"]:
        probs = []
        o = row["odin"]
        if o:
            for name in ("value", "volume"):
                part = o.get(name)
                if part:
                    for which in ("low", "high"):
                        ref = part[f"{which}_ref"]
                        if resolve_calc(ref["calc_id"], ref["field"]) is None or \
                                round(float(resolve_calc(ref["calc_id"], ref["field"])), 1) != round(float(part[which]), 1):
                            probs.append(f"{name} {which} {part[which]} has no calc source")
            probs += guards.range_guard(f"{row['country']}/{row['sector']}", o["low"], o["high"])
        if probs:
            removed.append({"section": "exposure_table", "paragraph_id": f"{row['country']}|{row['sector']}", "text": "", "problems": probs})
            removed_numbers += len(probs)
            row["odin"], row["status"], row["reason"] = None, "INSUFFICIENT_EVIDENCE", "NUMBER_REMOVED_BY_VALIDATOR"
        rows.append(row)
    briefing["exposure_table"] = rows
    briefing["removed_by_validator"] = removed
    briefing["header"]["removed_numbers"] = removed_numbers
    briefing["header"]["guards_passed"] = not removed
    return briefing


def briefing_hash(briefing):
    """Hash of the briefing without the volatile case_id and the validator's removal list (reproducibility proof)."""
    body = {k: v for k, v in briefing.items() if k != "removed_by_validator"}
    body["header"] = {k: v for k, v in briefing["header"].items() if k != "case_id"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


# ---------- markdown ----------

def _fmt_range(side):
    if side is None:
        return "-"
    if side["low"] is None:
        return side["status"] or "-"
    return f"{_fmt(side['low'])}% to {_fmt(side['high'])}%"


def _money(part):
    if not part:
        return "-"
    return f"{part['low']:,.0f} to {part['high']:,.0f} {part.get('unit') or ''}".strip()


def render_markdown(b):
    h = b["header"]
    lines = [f"# Briefing: {h['event']}", "",
             f"- Case: {h['case_id']}  |  As of: {h['as_of_date']}  |  Completion: **{h['completion_status']}**"
             + (f" ({h['stop_reason']})" if h["stop_reason"] else ""),
             f"- Question: {h['question'].strip()}",
             f"- Rulings by: {h['ruling_mode']}",
             f"- Flagged cells (insufficient evidence): {', '.join(h['flagged_cells']) or 'none'}",
             f"- Cells not assessed (budget): {', '.join(h['cells_not_assessed']) or 'none'}",
             f"- Numbers removed by the validator: {h['removed_numbers']}"]
    if h.get("run2_notice"):
        lines.append(f"- **{h['run2_notice']}**")
    for a in h["scope_assumptions"]:
        lines.append(f"- Scope assumption: {a['reason']}")
    lines += ["", "## Executive judgement", "", b["executive_summary"]["text"], "",
              f"Overall confidence: {b['executive_summary']['confidence']}", "", "## Event verification", ""]
    lines += [f"- {p['text']}" for p in b["event_verification"]]
    for title, key in (("Established findings", "established"), ("Contested findings", "contested"),
                       ("Conceded findings", "conceded"), ("Rejected by Odin", "rejected")):
        lines += ["", f"## {title}", ""]
        lines += [f"- {p['text']}" for p in b[key]] or ["- none"]
    lines += ["", "## Exposure table", "",
              "| Cell | Thor | Loki | Odin | Odin value | Odin volume | Status |", "|---|---|---|---|---|---|---|"]
    for r in b["exposure_table"]:
        o = r["odin"]
        lines.append(f"| {r['country']} / {r['sector']} | {_fmt_range(r['thor'])} | {_fmt_range(r['loki'])} | "
                     f"{_fmt_range(o) if o else 'Insufficient evidence'} | {_money(o and o.get('value'))} | "
                     f"{_money(o and o.get('volume'))} | {r['status']} |")
    lines += ["", "Why each range is that wide:", ""]
    for r in b["exposure_table"]:
        lines.append(f"- {r['country']} / {r['sector']}: {r['calibration_text']}")
        if r.get("targeted_queries"):
            lines.append(f"  - targeted queries: {'; '.join(r['targeted_queries'])}")
    o = b["outlook"]
    lines += ["", "## Next-quarter outlook", "", "Drivers:"] + [f"- {x}" for x in o["drivers"]]
    lines += ["", "Risks:"] + [f"- {x}" for x in o["risks"]] + ["", "Leading indicators:"] + [f"- {x}" for x in o["indicators"]]
    lines += ["", "Assumptions:"] + [f"- {x}" for x in o["assumptions"]]
    lines += ["", "## Assumptions and limitations", ""] + [f"- {x}" for x in b["assumptions_limitations"]]
    lines += ["", "## Sources", ""] + [f"- {s['doc_id']} (tier {s['tier']}, {s['source_type']}, {s['pub_date']}): {s['title']}"
                                        for s in b["sources"]]
    if b["removed_by_validator"]:
        lines += ["", "## Removed by validator", ""]
        lines += [f"- {r['section']} {r['paragraph_id']}: {'; '.join(r['problems'][:2])}" for r in b["removed_by_validator"]]
    return "\n".join(lines) + "\n"
