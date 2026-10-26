"""One call runs a whole case: Heimdall -> Round 1 -> Round 2 -> Odin -> (send-back, Run 2, Odin) -> briefing.

Everything a run produces is written under <out_root>/<case_id>/ (or <out_root>/<out_name>/):

    case_file.json  claim_ledger.json  calc_ledger.json (with calc_explain)  cross_examination.json
    rulings.json    briefing.json      briefing.md        trap_report.json     run_record.json
    events.jsonl    search_log.jsonl   provider_calls.jsonl                    llm_calls.jsonl  config.json

Providers: ollama (local, free), openai (any OpenAI-compatible API), anthropic, and replay (re-runs a recorded case from
llm_calls.jsonl at $0). Every real provider is wrapped by RecordingProvider so any run can be replayed.
"""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

from .. import guards
from ..agents import odin
from ..agents.claims import masked_raw_lines
from ..agents.counsel import SIDES, run_round1
from ..agents.cross_exam import run_round2
from ..agents.heimdall import open_case
from ..briefing import (OUTLOOK_SCHEMA, briefing_hash, build, gate, render_markdown, template_narrative)
from ..briefing.trap_report import calc_explain, trap_report
from ..casefile import model as casefile
from ..ingestion.packs import load_packs
from ..llm.provider import ProviderError, RecordingProvider, canonical, is_billable, validate_schema
from ..runtime import ledger as ledger_mod
from ..runtime.budget import BudgetExceeded
from ..runtime.config import ROOT, load_config
from ..runtime.run2 import run_second_run, sufficiency
from ..search.bm25 import CaseIndex

OUTPUTS = ["case_file.json", "claim_ledger.json", "calc_ledger.json", "cross_examination.json", "rulings.json",
           "briefing.json", "briefing.md", "trap_report.json", "run_record.json", "events.jsonl", "search_log.jsonl",
           "provider_calls.jsonl", "llm_calls.jsonl", "config.json"]


def _write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def input_hashes(pack_paths, config):
    """7.4: what a replay must find unchanged: pack manifests and hash lists, the config, and every prompt."""
    packs = {}
    for p in pack_paths:
        packs[str(p)] = {name: _sha((Path(p) / name).read_bytes()) for name in ("manifest.json", "hashes.sha256")
                         if (Path(p) / name).exists()}
    prompts = {f.name: _sha(f.read_bytes()) for f in sorted((ROOT / "prompts").glob("*.md"))}
    return {"packs": packs, "config": _sha(canonical(config.data).encode("utf-8")), "prompts": prompts}


def _span_text(corpus):
    def resolve(citation):
        spans = guards.cited_text([citation], corpus)
        return spans[0] if spans else None
    return resolve


def briefing_narrative(cf, cells, rulings, provider, guard, trace, corpus, masked):
    """Odin's briefing call writes only the summary and the outlook, and only inside the guards. Any failure falls
    back to the deterministic template (FALLBACK_BRIEFING_TEMPLATE), and the briefing says so."""
    template = template_narrative(cf, cells, rulings)
    prompt = (ROOT / "prompts" / "odin_briefing.md").read_text(encoding="utf-8")
    messages = [{"role": "system", "content": prompt},
                {"role": "user", "content": canonical({"task": "odin_briefing", "template": template})}]
    try:
        out = guard.call(provider, "odin_briefing", messages, OUTLOOK_SCHEMA, final_ruling=True)["output"]
    except (BudgetExceeded, ProviderError) as e:
        trace.emit("runtime", "FALLBACK_BRIEFING_TEMPLATE", {"reason": type(e).__name__, "detail": str(e)[:200]}, "WARNING")
        return template, "TEMPLATE"
    texts = out["drivers"] + out["risks"] + out["indicators"]
    allowed = {t.replace(",", "") for t in guards.NUMBER.findall(canonical(template))}
    problems = guards.entity_guard("briefing", texts + [out["executive_summary"]], cf, corpus) \
        + guards.injection_guard("briefing", texts + [out["executive_summary"]], masked) \
        + guards.quote_guard("briefing", texts + [out["executive_summary"]], [], corpus)
    problems += [f"briefing: new number {t}" for t in guards.NUMBER.findall(" ".join(texts + [out["executive_summary"]]))
                 if t.replace(",", "") not in allowed]
    if problems:
        trace.emit("runtime", "FALLBACK_BRIEFING_TEMPLATE", {"reason": "GUARD_FAILED", "problems": problems[:10]}, "WARNING")
        return template, "TEMPLATE"
    return out, "MODEL"


def _unverified(cf):
    """4.5: the event could not be verified -> the case continues as EVENT_UNVERIFIED with no exposure numbers."""
    return {"schema_version": "briefing-1", "event_status": "EVENT_UNVERIFIED",
            "header": {"case_id": cf["case_id"], "event_id": cf["event_id"], "event": cf["event_name"],
                       "as_of_date": cf["as_of_date"], "question": cf["question"], "completion_status": "INCOMPLETE",
                       "stop_reason": "EVENT_UNVERIFIED", "flagged_cells": [f"{c['country']} / {c['sector']}" for c in cf["exposure_cells"]],
                       "cells_not_assessed": [], "scope_assumptions": cf["scope_assumptions"], "integrity_warnings": [],
                       "removed_numbers": 0, "run2_new_evidence_families": [], "run2_notice": None, "ruling_mode": "NONE"},
            "executive_summary": {"paragraph_id": "sum-01", "text": "EVENT_UNVERIFIED: " + (cf["rejection"] or {}).get("detail", ""),
                                  "finding_classification": "CONTESTED", "claim_refs": [], "citation_refs": [], "row_refs": [],
                                  "calc_refs": [], "number_refs": [], "confidence": 0.0},
            "event_verification": [], "established": [], "contested": [], "conceded": [], "rejected": [],
            "exposure_table": [], "outlook": {"drivers": [], "risks": [], "indicators": [], "assumptions": []},
            "assumptions_limitations": [], "sources": [], "removed_by_validator": []}


def run_full_case(question, pack_paths, config, provider, out_root, memory_dir, case_id=None, created_at=None, out_name=None,
                  final_round=False, ledger_path=ledger_mod.DEFAULT_PATH, stop_after=None, on_event=None):
    case_id = case_id or f"case-{uuid.uuid4().hex[:12]}"
    out = Path(out_root) / (out_name or case_id)
    out.mkdir(parents=True, exist_ok=True)
    pack_paths = [str(p) for p in pack_paths]
    live = is_billable(provider)
    ledger = ledger_mod.load(ledger_path)
    if live:
        ledger_mod.check_live_allowed(config, ledger, final_round)
    if provider.name != "replay":
        log = out / "llm_calls.jsonl"
        if log.exists():
            log.unlink()
        provider = RecordingProvider(provider, log)
    _write_json(out / "config.json", config.data)
    before = out / "memory_before"                  # the private memory this case started from, so a replay can start there too
    if before.exists():
        shutil.rmtree(before)
    if provider.name != "replay" and Path(memory_dir).exists():
        shutil.copytree(memory_dir, before)

    cf, trace, guard = open_case(question, pack_paths, config, provider, case_id=case_id, created_at=created_at)
    guard.project_spent = ledger["total_spent_usd"]
    if on_event:                                     # the live feed: what is already written, then everything that follows
        for e in trace.events:
            on_event(e)
        trace.on_emit = on_event
    sides, rulings, cells, b, mode, run2rec = {}, [], [], None, "NONE", None
    modes = []
    corpus = index = None
    if cf["status"] == "OPEN" and stop_after != "heimdall":
        try:
            sides = run_round1(cf, provider, config, trace, memory_root=str(memory_dir), guard=guard)
            if stop_after != "round1":
                run_round2(cf, sides, provider, config, trace, guard)
        except BudgetExceeded as e:
            trace.emit("runtime", "FALLBACK_BUDGET_STOP", {"detail": str(e)}, "WARNING")
            cf["run_status"][0]["stop_reason"] = "INCOMPLETE_BUDGET_LIMIT"
    if sides and stop_after not in ("round1",):
        corpus, index = sides[SIDES[0]].tools.corpus, sides[SIDES[0]].tools.index
        masked = masked_raw_lines(corpus)
        eligible = index.eligible_ids
        rulings = odin.rule_claims(cf, corpus, sides, eligible, masked)
        mode = odin.model_pass(cf, rulings, provider, guard, trace, corpus, masked)
        modes.append(f"run 1: {mode}")
        cells = odin.cell_results(cf, rulings)
        trace.emit("odin", "ODIN_RULED", {"run": 1, "rulings": len(rulings), "mode": mode,
                                          "decisions": _count(rulings, "decision"), "classes": _count(rulings, "classification")})
        first_rulings = len(rulings)
        gaps = sufficiency(cf, cells)
        stop = cf["run_status"][0]["stop_reason"]
        if gaps and config["max_runs"] >= 2 and not stop:
            run2rec = run_second_run(cf, cells, gaps, sides, provider, config, trace, guard, memory_root=str(memory_dir))
            rulings = odin.rule_claims(cf, corpus, sides, eligible, masked)
            mode = odin.model_pass(cf, rulings, provider, guard, trace, corpus, masked, final_ruling=True)
            modes.append(f"run 2: {mode}")
            cells = odin.cell_results(cf, rulings)
            trace.emit("odin", "ODIN_RULED", {"run": 2, "rulings": len(rulings), "mode": mode,
                                              "decisions": _count(rulings, "decision"), "classes": _count(rulings, "classification")})
        for c in cells:
            if c["status"] == "INSUFFICIENT_EVIDENCE":
                trace.emit("odin", "CELL_INSUFFICIENT_EVIDENCE", {"country": c["country"], "sector": c["sector"], "reason": c["reason"],
                                                                 "after_run": 2 if run2rec else 1})
        for r in rulings:
            problems = validate_schema(r, odin.RULING_SCHEMA)
            if problems:
                raise ValueError(f"ruling {r['ruling_id']} breaks RULING_SCHEMA: {problems[:3]}")
        cf["ruling_ledger"] = rulings
        failures = [f for r in cf["run_status"] for f in (r.get("round_1", {}).get("agent_failures", [])
                                                           + r.get("round_2", {}).get("agent_failures", [])
                                                           + r.get("agent_failures", []))]
        run_info = {"stop_reason": next((r["stop_reason"] for r in cf["run_status"] if r.get("stop_reason")), None),
                    "agent_failures": failures, "run2_ran": run2rec is not None,
                    "run2_new_evidence_families": (run2rec or {}).get("run2_new_evidence_families", []),
                    "run2_no_evidence_reason": (run2rec or {}).get("run2_no_evidence_reason"),
                    "queries_by_cell": (run2rec or {}).get("queries_by_cell", {})}
        narrative, nmode = briefing_narrative(cf, cells, rulings, provider, guard, trace, corpus, masked)
        mode = "; ".join(modes)
        b = build(cf, rulings, cells, corpus, run_info, narrative, f"{mode}; narrative {nmode}")
        b = gate(b, cf, corpus, masked, _span_text(corpus))
        trace.emit("odin", "BRIEFING_BUILT", {"completion": b["header"]["completion_status"], "removed": len(b["removed_by_validator"]),
                                              "hash": briefing_hash(b)})
        for r in cf["calc_ledger"]:
            r["calc_explain"] = calc_explain(r)
        _write_json(out / "trap_report.json", trap_report(cf, corpus, index, rulings, trace))
    elif cf["status"] == "EVENT_REJECTED" and (cf["rejection"] or {}).get("reason") == "EVENT_NOT_VERIFIED":
        trace.emit("runtime", "FALLBACK_EVENT_UNVERIFIED", {"detail": cf["rejection"]["detail"]}, "WARNING")
        b = _unverified(cf)

    for f in getattr(provider, "fallbacks", []):
        trace.emit("runtime", f["type"], {k: v for k, v in f.items() if k != "type"}, "WARNING")
    if corpus is not None:
        for rec in corpus.records.values():
            if "TRADE_TABLE_UNPARSED" in rec["flags"]:
                trace.emit("runtime", "FALLBACK_TRADE_TABLE_UNPARSED", {"doc_id": rec["doc_id"], "handling": "cells use other evidence"})
    casefile.write(cf, out / "case_file.json")
    _write_json(out / "claim_ledger.json", cf["claim_ledger"])
    _write_json(out / "calc_ledger.json", cf["calc_ledger"])
    _write_json(out / "cross_examination.json", cf["cross_examination"])
    _write_json(out / "rulings.json", rulings)
    if b is not None:
        _write_json(out / "briefing.json", b)
        (out / "briefing.md").write_text(render_markdown(b) if "exposure_table" in b and "event_status" not in b
                                         else f"# EVENT_UNVERIFIED\n\n{b['executive_summary']['text']}\n",
                                         encoding="utf-8", newline="\n")
    _write_jsonl(out / "search_log.jsonl", [e for a in SIDES if a in sides for e in sides[a].tools.search_log])
    _write_jsonl(out / "provider_calls.jsonl", getattr(provider, "calls", []))
    trace.write_jsonl(out / "events.jsonl")

    spent = round(guard.case_spent, 6)
    ac = {"cross_examinations": len(cf["cross_examination"]),
          "rejected_or_conceded": sum(r["decision"] == "REJECTED" or r["classification"] == "CONCEDED" for r in rulings),
          "sent_back": run2rec is not None, "run2_new_evidence_families": (run2rec or {}).get("run2_new_evidence_families", []),
          "memory_decisions_changed": len(trace.of_type("DECISION_CHANGED"))}
    record = {"case_id": cf["case_id"], "status": cf["status"], "question": question, "pack_paths": pack_paths,
              "provider": provider.name, "created_at": cf["created_at"], "as_of_date": cf["as_of_date"],
              "event_id": cf["event_id"], "input_hashes": input_hashes(pack_paths, config),
              "ruling_mode": mode, "rulings": {"total": len(rulings), "decisions": _count(rulings, "decision"),
                                               "classes": _count(rulings, "classification")},
              "ac": ac, "runs": cf["run_status"],
              "spend": {"case_spent_usd": spent, "shadow_spent_usd": round(guard.shadow_spent, 6), "model_calls": len(guard.calls),
                        "project_spent_before_usd": ledger["total_spent_usd"], "billable": live,
                        "project_total_after_usd": round(ledger["total_spent_usd"] + spent, 6)},
              "briefing_hash": briefing_hash(b) if b and "exposure_table" in b else None,
              "briefing_completion": b["header"]["completion_status"] if b else None,
              "events": _count(trace.events, "event_type", key="event_type"),
              "outputs": [f for f in OUTPUTS if (out / f).exists() or f == "run_record.json"]}
    _write_json(out / "run_record.json", record)
    if live:
        ledger_mod.record(cf["case_id"], provider.name, spent, "final" if final_round else "development", ledger_path)
    return {"case_file": cf, "out_dir": out, "record": record, "briefing": b, "rulings": rulings, "cells": cells,
            "trace": trace, "sides": sides, "guard": guard}


def _count(items, field, key=None):
    out = {}
    for i in items:
        v = i[field]
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))
