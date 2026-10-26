"""The trial record as the web console reads it (`schema_version: trial-2`).

The console (ui/) was designed around one result shape: a Case File, one entry per trial round, a briefing built from
Odin's rulings, an exposure range per cell, and a private-memory audit. This module turns the files a case writes
(case_file.json, rulings.json, briefing.json, run_record.json, events.jsonl, llm_calls.jsonl) into that shape, and answers
the console's three read endpoints: the as-of document feed, and click-through to a document paragraph or a trade row.
Nothing here decides anything; every number and every citation is copied from the case's own files.
"""
import json
import re
from pathlib import Path

from ..provenance.citations import parse_citations

SCHEMA = "trial-2"
CLASS = {"ESTABLISHED": "established", "CONTESTED": "contested", "CONCEDED": "conceded", "REJECTED": "rejected"}
EXCERPT = 700


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_jsonl(path):
    try:
        return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def load_bundle(case_dir):
    d = Path(case_dir)
    return {"dir": d, "run_record": _read(d / "run_record.json"), "case_file": _read(d / "case_file.json"),
            "rulings": _read(d / "rulings.json") or [], "briefing": _read(d / "briefing.json"),
            "events": _read_jsonl(d / "events.jsonl"), "llm": _read_jsonl(d / "llm_calls.jsonl"),
            "calcs": _read(d / "calc_ledger.json") or []}


def iso(date, time=None):
    return f"{date}T{time or '00:00'}:00Z" if date else ""


def _text(rec, para):
    p = next((x for x in rec["paragraphs"] if x["id"] == para), None)
    return p["text_masked"] if p else ""


def citation(corpus, cit):
    """A `[DOC, P#, timestamp]` string -> the console's TrialCitation (None when it does not resolve)."""
    parsed = parse_citations(cit)
    if len(parsed) != 1 or parsed[0]["doc_id"] not in corpus.records:
        return None
    p = parsed[0]
    rec = corpus.records[p["doc_id"]]
    return {"source_id": p["doc_id"], "row_id": None, "excerpt": _text(rec, p["paragraph"])[:EXCERPT],
            "published_at": iso(rec["pub_date"], rec["pub_time"]), "title": rec["agent_title"], "source_type": rec["source_type"],
            "reliability": rec["reliability"] or 0, "locator": f"{p['doc_id']}:{p['paragraph']}"}


def citations(corpus, cits):
    return [c for c in (citation(corpus, x) for x in dict.fromkeys(cits)) if c]


def _scaled(calcs, ref, family):
    rec = calcs.get(ref["calc_id"])
    try:
        v = rec
        for part in ref["field"].replace("envelope.", family + ".", 1).split("."):
            v = v[part]
        return v
    except (KeyError, TypeError):
        return None


def exposure_rows(bundle, corpus):
    cf, b = bundle["case_file"], bundle["briefing"]
    claims = {c["claim_id"]: c for c in cf["claim_ledger"]}
    calcs = {c["calc_id"]: c for c in bundle["calcs"]}
    rulings = {r["claim_id"]: r for r in bundle["rulings"]}
    rows = []
    for r in b["exposure_table"]:
        o = r["odin"]
        thor, loki = r["thor"], r["loki"]
        cid = {a: (r[a] or {}).get("claim_id") for a in ("thor", "loki")}
        side_value = {}
        for a, which in (("thor", "high"), ("loki", "low")):
            c = claims.get(cid[a]) if cid[a] else None
            side_value[a] = _scaled(calcs, c["estimate"][f"{which}_ref"], "envelope_value") if c and c.get("estimate") else None
        conf = [rulings[i]["confidence"] for i in r["claim_refs"] if i in rulings and rulings[i]["decision"] != "REJECTED"]
        locators = []
        for x in r["row_refs"][:10]:
            locators.append(x["row_key"])
        for cit in r["citation_refs"][:6]:
            c = citation(corpus, cit)
            if c:
                locators.append(c["locator"])
        rows.append({
            "country": r["country"], "sector": r["sector"], "unit": ((o or {}).get("value") or {}).get("unit") or "USD",
            "period": "next quarter", "loki_low": side_value["loki"], "thor_high": side_value["thor"],
            "odin_low": ((o or {}).get("value") or {}).get("low"), "odin_high": ((o or {}).get("value") or {}).get("high"),
            "confidence": round(sum(conf) / len(conf), 2) if conf and o else None,
            "assumptions": [x for x in b["outlook"]["assumptions"][:1]], "citation_ids": list(dict.fromkeys(locators)),
            # Final-build fields (the percent range is the headline metric; value is the same scenario in currency)
            "status": r["status"], "reason": r["reason"], "pct_low": o and o["low"], "pct_high": o and o["high"],
            "thor_pct": thor and {k: thor[k] for k in ("status", "low", "high")},
            "loki_pct": loki and {k: loki[k] for k in ("status", "low", "high")},
            "volume_low": ((o or {}).get("volume") or {}).get("low"), "volume_high": ((o or {}).get("volume") or {}).get("high"),
            "volume_unit": ((o or {}).get("volume") or {}).get("unit"), "widened": bool(o and o.get("widened")),
            "calibration": r["calibration_text"], "targeted_queries": r.get("targeted_queries", []),
            "calc_ids": r["calc_refs"],
        })
    return rows


def _premise(cf, corpus):
    pc = cf.get("premise_check")
    if not pc:
        return None
    return {"status": pc["status"], "words": pc["premise_words"],
            "findings": [{"premise": f["premise"], "supported": f["supported"],
                          "citations": citations(corpus, [c["citation"] for c in f["citations"]])} for f in pc["findings"]],
            "established": citations(corpus, [c["citation"] for c in pc["citations"] if c.get("role") == "established_event"])}


def _claim(c, ruling, corpus):
    est = c["estimate"]
    return {
        "id": c["claim_id"], "side": c["agent"], "statement": c["claim_text"], "nature": c["claim_kind"].lower(),
        "country": c["country"], "sector": c["sector"], "estimate": None, "estimate_kind": c["metric"],
        "estimate_unit": "percent", "estimate_low": est and est["low"], "estimate_high": est and est["high"],
        "estimate_status": c["estimate_status"], "period": None, "confidence": c["confidence"],
        "citations": citations(corpus, c["citations"]), "assumptions": c["assumptions"],
        "status": CLASS.get(ruling["classification"]) if ruling else None,
        "ruling_rationale": ruling["rationale"] if ruling else None, "decision": ruling["decision"] if ruling else None,
        "claim_status": c["status"], "supersedes": c.get("supersedes"), "superseded_by": c.get("superseded_by"),
        "claim_type": c["claim_type"], "round": c["round"],
    }


def _challenge(e, corpus):
    r = e.get("response")
    return {"id": e["challenge_id"], "attacker": e["challenger"], "target_claim_id": e["target_claim_id"],
            "argument": e["challenge_text"], "citations": citations(corpus, e["citations"]),
            "response": r and r["response_text"], "response_citations": citations(corpus, (r or {}).get("citations", [])),
            "concedes": bool(r and r["response_type"] == "CONCEDE"),
            "outcome": (r["response_type"].lower() if r else "unanswered"), "kind": e["challenge_kind"],
            "response_type": r and r["response_type"]}


def _ruling(r, corpus):
    cits = []
    for ref in r["supporting_refs"][:4]:
        doc, para = ref["span_id"].split(":")
        rec = corpus.records.get(doc)
        if rec:
            cits.append({"source_id": doc, "row_id": None, "excerpt": _text(rec, para)[:EXCERPT],
                         "published_at": iso(rec["pub_date"], rec["pub_time"]), "title": rec["agent_title"],
                         "source_type": rec["source_type"], "reliability": rec["reliability"] or 0, "locator": ref["span_id"]})
    return {"claim_id": r["claim_id"], "classification": CLASS[r["classification"]], "nature": r["claim_kind"].lower(),
            "rationale": r["rationale"], "citations": cits,
            "missing_evidence": r.get("qualification_reasons", []) + (r.get("rejection_reasons", []) if r["decision"] == "REJECTED" else []),
            "decision": r["decision"], "decided_by": r["decided_by"], "rejected_by": r.get("rejected_by")}


def memory_audit(events):
    out = []
    run = 1
    for e in events:
        t, p = e["event_type"], e["payload"]
        if t == "RUN_2_STARTED":
            run = 2
        if e["actor"] not in ("thor", "loki", "heimdall", "odin"):
            continue
        base = {"agent": e["actor"], "run_number": run, "timestamp": e["timestamp"], "influenced_action": None, "value": None}
        if t == "MEMORY_READ":
            out += [dict(base, action="read", key=m) for m in p["memory_ids"]]
            out += [dict(base, action="hidden by as-of rule", key=m) for m in p["hidden_ids"]]
        elif t == "MEMORY_WRITTEN":
            out.append(dict(base, action="write", key=p["key"], value=f"{p['memory_id']} · sources {', '.join(p['source_doc_ids'][:4])}"))
        elif t in ("DECISION_CHANGED", "DECISION_UNVERIFIED"):
            out.append(dict(base, action="decision changed" if t == "DECISION_CHANGED" else "decision unverified", key=p["memory_id"],
                            influenced_action=f"{p['kind']}: {p['before']} → {p['after']}"))
    return out


def trial_result(run_id, bundle, corpus):
    cf, b, rec = bundle["case_file"], bundle["briefing"], bundle["run_record"]
    events = bundle["events"]
    rulings = {r["claim_id"]: r for r in bundle["rulings"]}
    status = ("completed" if b and b["header"]["completion_status"] == "COMPLETE" else "partial" if b and "event_status" not in b
              else "unverified" if cf["status"] != "OPEN" else "failed")
    ev = cf.get("event_verification") or {}
    ms = cf.get("manifest_scope") or {}
    manifest = (rec["input_hashes"]["packs"].get(rec["pack_paths"][-1]) or {}).get("manifest.json", "") if rec else ""
    case_file = {
        "question": cf["question"], "as_of": cf["as_of_date"] or "", "corpus_pack": Path(rec["pack_paths"][-1]).name if rec else "",
        "corpus_version": manifest[:10] or "unversioned", "event_id": cf["event_id"], "event_name": cf["event_name"],
        "event_verified": ev.get("verdict") == "VERIFIED", "verification_summary": ev.get("reason", (cf["rejection"] or {}).get("detail", "")),
        "countries": cf["target_countries"], "sectors": cf["target_sectors"], "relevant_source_ids": ms.get("scope_doc_ids", []),
        "contradictions": [f"{x['from']['citation']} {x['type'].lower().replace('_', ' ')} {x['to']['citation']}"
                           for x in (cf.get("correction_map") or {}).get("relations", [])],
        "assumptions": [a["reason"] for a in cf["scope_assumptions"]],
        "issues": [f"{q['doc_id']}: {q['reason']}" for r in cf["run_status"][:1] for q in r["quarantined_documents"]]
        + [f"{c['country']} {c['sector']}: coverage {c['status']}" for c in cf["coverage"] if c["status"] != "COVERED"],
        "coverage": [{"country": c["country"], "sector": c["sector"], "status": c["status"]} for c in cf["coverage"]],
        "evidence_gaps": cf["evidence_gaps"], "premise": _premise(cf, corpus), "event_status": "VERIFIED" if ev.get("verdict") == "VERIFIED" else "EVENT_UNVERIFIED",
    }
    t0 = events[0]["timestamp"] if events else ""
    t1 = events[-1]["timestamp"] if events else ""
    split = next((e["sequence"] for e in events if e["event_type"] == "RUN_2_STARTED"), None)
    runs = []
    for status_rec in cf["run_status"]:
        n = status_rec["run_number"]
        mine = [c for c in cf["claim_ledger"] if c["run"] == n]
        ids = {c["claim_id"] for c in mine}
        xs = cf["cross_examination"] if n == 1 else []
        searches = [e for e in events if e["event_type"] == "SEARCH_EXECUTED" and ((e["sequence"] < split) if (split and n == 1) else (e["sequence"] > split if split else True))]
        new_ev = status_rec.get("run2_new_evidence_citations", {})
        sent_back = len(cf["run_status"]) > 1
        runs.append({
            "run_number": n, "started_at": t0 if n == 1 else next((e["timestamp"] for e in events if e["event_type"] == "RUN_2_STARTED"), t1),
            "finished_at": t1, "new_evidence_ids": sorted({c for v in new_ev.values() for c in v}) if n == 2 else [],
            "new_evidence_families": status_rec.get("run2_new_evidence_families", []) if n == 2 else [],
            "query_count": len(searches), "claims": [_claim(c, rulings.get(c["claim_id"]), corpus) for c in mine],
            "challenges": [_challenge(e, corpus) for e in xs],
            "rulings": [_ruling(rulings[i], corpus) for i in sorted(ids) if i in rulings],
            # Run 2 is the last run (max_runs): with gaps left it is not "sufficient", the run limit stopped it and the cells are flagged
            "sufficient": (not sent_back) if n == 1 else not status_rec.get("gaps"), "returned_by_odin": sent_back and n == 1,
            "missing_evidence": [f"{g['country']} {g['sector']}: {', '.join(g['missing']) or g['reason']}" for g in status_rec.get("gaps", [])]
            if n == 2 else [f"{g['country']} {g['sector']}: {g['missing']}" for g in cf["evidence_gaps"]] if sent_back else [],
            "errors": [f"{f['agent']}: {f['reason']}" for f in status_rec.get("agent_failures", [])]
            + [f"{f['agent']}: {f['reason']}" for f in (status_rec.get("round_1") or {}).get("agent_failures", [])]
            + [f"{f['agent']}: {f['reason']}" for f in (status_rec.get("round_2") or {}).get("agent_failures", [])],
            "no_new_evidence_reason": status_rec.get("run2_no_evidence_reason") if n == 2 else None,
        })
    briefing = None
    if b and "event_status" not in b and b["exposure_table"]:
        text = lambda ps: [p["text"] for p in ps]  # noqa: E731
        briefing = {
            "executive_summary": b["executive_summary"]["text"], "established": text(b["established"]), "contested": text(b["contested"]),
            "conceded": text(b["conceded"]), "rejected": text(b["rejected"]), "exposure": exposure_rows(bundle, corpus),
            "outlook": " ".join(b["outlook"]["drivers"] + b["outlook"]["risks"]),
            "outlook_parts": {k: b["outlook"][k] for k in ("drivers", "risks", "indicators")},
            "assumptions": b["outlook"]["assumptions"], "source_ids": [s["doc_id"] for s in b["sources"]],
            "citations": citations(corpus, [c for r in b["exposure_table"] for c in r["citation_refs"]][:30]),
            "verification": [{"text": p["text"], "classification": p["finding_classification"], "citations": citations(corpus, p["citation_refs"])}
                             for p in b["event_verification"]],
            "complete": b["header"]["completion_status"] == "COMPLETE", "flagged_cells": b["header"]["flagged_cells"],
            "removed_by_validator": b["removed_by_validator"], "ruling_mode": b["header"]["ruling_mode"],
            "run2_notice": b["header"]["run2_notice"], "briefing_hash": rec.get("briefing_hash") if rec else None,
        }
    tokens_in = sum(x["usage"]["input_tokens"] for x in bundle["llm"] if x.get("usage"))
    tokens_out = sum(x["usage"]["output_tokens"] for x in bundle["llm"] if x.get("usage"))
    sp = rec["spend"] if rec else {}
    return {
        "schema_version": SCHEMA, "run_id": run_id, "question": cf["question"], "case_file": case_file, "runs": runs,
        "briefing": briefing, "memory_audit": memory_audit(events),
        "issues": ([f"EVENT_REJECTED: {cf['rejection']['detail']}"] if cf["rejection"] else [])
        + ([b["header"]["run2_notice"]] if b and b["header"].get("run2_notice") else [])
        + [f"{x}" for x in ([b["header"]["stop_reason"]] if b and b["header"].get("stop_reason") else [])],
        "status": status, "created_at": cf["created_at"], "finished_at": t1, "provider": rec["provider"] if rec else None,
        "usage": {"calls": sp.get("model_calls", 0), "input_tokens": tokens_in, "output_tokens": tokens_out,
                  "cost_usd": sp.get("case_spent_usd") if sp.get("billable") else 0.0, "shadow_cost_usd": sp.get("shadow_spent_usd"),
                  "latency_s": 0.0},
        "acceptance": rec["ac"] if rec else None, "ruling_mode": rec["ruling_mode"] if rec else None,
        "traps": _read(bundle["dir"] / "trap_report.json"),
        "calc_explain": {c["calc_id"]: c.get("calc_explain") for c in bundle["calcs"] if c.get("calc_explain")},
    }


def run_events(bundle, after=0):
    return [{"seq": e["sequence"], "type": e["event_type"], "timestamp": e["timestamp"], "step": None, "agent": e["actor"],
             "data": e["payload"], "level": e["level"]} for e in bundle["events"] if e["sequence"] > after]


# ---------- the sealed archive: feed and click-through ----------

def feed(corpus, as_of, event_id):
    """Documents the case may read: dated on or before the as-of date, in the event's scope (event or background)."""
    from ..search.bm25 import CaseIndex
    index = CaseIndex(corpus, as_of, event_id)
    out = []
    for r in index.eligible:
        first = next((p["text_masked"] for p in r["paragraphs"]), "")
        out.append({"id": r["doc_id"], "title": r["agent_title"], "source_name": r["source_name"], "source_type": r["source_type"],
                    "reliability": r["reliability"] or 0, "published_at": iso(r["pub_date"], r["pub_time"]), "event_id": r["event_id"],
                    "country": r["country"] or "", "sector": r["declared_sector"] or "", "excerpt": first[:280]})
    return out


def _doc_item(rec, para=None):
    text = _text(rec, para) if para else "\n\n".join(f"[{p['id']}] {p['text_masked']}" for p in rec["paragraphs"])
    item = {"id": rec["doc_id"] + (f":{para}" if para else ""), "title": rec["agent_title"], "published_at": iso(rec["pub_date"], rec["pub_time"]),
            "text": text, "source_name": rec["source_name"], "source_type": rec["source_type"], "reliability": rec["reliability"],
            "country": rec["country"], "sector": rec["declared_sector"], "event_id": rec["event_id"], "status": rec["status"],
            "evidence_family": rec["evidence_family_id"], "flags": ", ".join(sorted(rec["flags"])) or None}
    if para:
        item["paragraph"] = para
    return item


def source(corpus, source_id):
    """`DOC` (whole document), `DOC:P#` (one paragraph) or a trade row key `DOC|YYYY-MM`."""
    if "|" in source_id:
        doc = source_id.split("|")[0]
        rec = corpus.records.get(doc)
        row = next((r for r in (rec["trade_rows"] if rec else []) if r["row_key"] == source_id), None)
        if row is None:
            return None
        para = _text(rec, row["paragraph"])
        return {"kind": "trade_row", "item": {
            "id": row["row_key"], "country_from": row["origin"], "country_to": row["destination"], "sector": row["sector"],
            "month": row["month"], "value": row["value_amount"], "value_unit": row["value_currency"], "volume": row["volume_amount"],
            "volume_unit": row["volume_unit"], "table_id": row["table_id"], "row_id": row["native_row_number"],
            "source_doc": doc, "paragraph": row["paragraph"], "layout": row["source_layout"],
            "flags": ", ".join(row["flags"]) or None, "usable_for_arithmetic": row["usable_for_arithmetic"],
            "published_at": iso(rec["pub_date"], rec["pub_time"]), "text": row["raw_text"] + "\n\n" + para}}
    m = re.match(r"^([A-Z][A-Z0-9]*-\d+)(?::(P\d+))?$", source_id)
    if not m or m.group(1) not in corpus.records:
        return None
    rec = corpus.records[m.group(1)]
    if m.group(2) and m.group(2) not in {p["id"] for p in rec["paragraphs"]}:
        return None
    return {"kind": "document", "item": _doc_item(rec, m.group(2))}
