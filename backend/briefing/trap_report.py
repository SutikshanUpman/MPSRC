"""Trap Report and "Why this number" (FINAL BUILD 7.1, 7.2, 7.3).

Everything here is read from the corpus, the Case File and the trace; nothing is hard-coded to a pack. A trap
is anything the pipeline caught before it could change a number: masked instruction lines, future-dated or
out-of-scope documents, duplicates folded into evidence families, damaged files, tier-4 rumours, interested-party
claims, corrections and supersessions, and repeated-value rows.
"""
from collections import defaultdict

DAMAGED = ("FAILED", "EMPTY", "TRUNCATED")


def trap_report(cf, corpus, index, rulings, trace):
    traps = []

    def add(kind, description, items):
        traps.append({"type": kind, "description": description, "count": len(items), "items": items})

    add("PROMPT_INJECTION_MASKED", "Instruction-like lines in documents were replaced by a placeholder before any agent saw them.",
        [{"doc_id": r["doc_id"], "locations": [m["paragraph"] for m in r["masked_lines"]],
          "lines_masked": sum(len(m["raw"]) for m in r["masked_lines"])}
         for r in corpus.records.values() if r["masked_lines"]])
    future = [{"doc_id": d, "pub_date": corpus.records[d]["pub_date"], "as_of_date": cf["as_of_date"]}
              for d, why in sorted(index.excluded.items()) if why == "FUTURE_DATED"]
    add("FUTURE_DOCUMENT_EXCLUDED", "Documents dated after the as-of date never entered the case.", future)
    other = [{"doc_id": d} for d, why in sorted(index.excluded.items()) if why == "OUT_OF_EVENT_SCOPE"]
    add("OUT_OF_SCOPE_EXCLUDED", "Documents of another event never entered the case.", other)
    add("HASH_MISMATCH_QUARANTINED", "Documents whose file hash does not match the pack's hash list are quarantined.",
        [{"doc_id": d} for d, why in sorted(index.excluded.items()) if why == "HASH_MISMATCH"])
    fams = defaultdict(list)
    for r in corpus.records.values():
        if r["evidence_family_id"]:
            fams[r["evidence_family_id"]].append(r["doc_id"])
    add("DUPLICATES_FOLDED", "Duplicate or near-duplicate documents count once, as one evidence family.",
        [{"family": f, "members": sorted(m)} for f, m in sorted(fams.items()) if len(m) > 1])
    add("DAMAGED_DOCUMENT", "Damaged files were handled and flagged, not crashed on and not trusted blindly.",
        [{"doc_id": r["doc_id"], "status": r["status"], "flags": sorted(r["flags"])}
         for r in corpus.records.values() if r["status"] in DAMAGED or {"TRUNCATED_DOCUMENT", "EMPTY_DOCUMENT", "UNREADABLE_FILE"} & set(r["flags"])])
    add("TIER_4_REJECTED", "Claims resting only on tier-4 sources were rejected before Odin's judgement.",
        [{"claim_id": r["claim_id"], "reasons": r["rejection_reasons"]} for r in rulings
         if "ONLY_TIER_4_SUPPORT" in r.get("rejection_reasons", [])])
    add("INTERESTED_PARTY_QUALIFIED", "Claims resting on a company's own statement were qualified.",
        [{"claim_id": r["claim_id"], "reasons": r.get("qualification_reasons", [])} for r in rulings
         if "COMPANY_STATEMENT_OVERREACH" in r.get("qualification_reasons", [])]
        + [{"challenge_id": e["challenge_id"], "target": e["target_claim_id"]} for e in cf["cross_examination"]
           if e["challenge_kind"] == "INTERESTED_PARTY"])
    add("CORRECTION_APPLIED", "Retractions, corrections and supersessions were applied to the event's document history.",
        [{"type": rel["type"], "from": rel["from"]["citation"], "to": rel["to"]["citation"]}
         for rel in (cf["correction_map"] or {}).get("relations", [])])
    rows = {}
    for rec in cf["calc_ledger"]:
        for key in rec["sensitivity_rows"]:
            rows[key] = {"row_key": key, "calc_ids": sorted({r["calc_id"] for r in cf["calc_ledger"] if key in r["sensitivity_rows"]})}
    add("REPEATED_ROWS_FLAGGED", "Trade rows with repeated values were flagged and bounded by a with/without range.", list(rows.values()))
    add("CLAIMS_REJECTED_BY_RULES", "Claims removed by the pre-ruling checks or by a concession.",
        [{"claim_id": r["claim_id"], "classification": r["classification"], "reasons": r.get("rejection_reasons", [])}
         for r in rulings if r["decision"] == "REJECTED"])
    add("OUTPUT_REJECTED_BY_GUARDS", "Agent outputs that failed a guard were sent back for another attempt.",
        [{"attempt": e["payload"].get("attempt"), "problems": e["payload"].get("problems", [])[:3]}
         for e in trace.of_type("CLAIM_VALIDATION_FAILED")])
    return {"case_id": cf["case_id"], "as_of_date": cf["as_of_date"],
            "summary": {t["type"]: t["count"] for t in traps}, "traps": traps}


FORMULA = ("net_value_shortfall_pct = (direct baseline value - direct post-event value - credit x (substitute post-event value "
           "- substitute baseline value)) / direct baseline value x 100; credit = 0, 0.5 or 1 (no, half or full credit for "
           "documented substitute growth)")
BASELINE_RULE = {
    "PRIMARY_YOY": "Baseline = the same months one year earlier on the same route (F11 primary rule).",
    "CROSS_CHECK_ONLY": "No prior-year rows: the baseline is implied from a cited 'level of normal' statement (F11 cross-check only).",
    "NONE": "No baseline could be formed.",
}


def calc_explain(rec):
    """7.2: formula, input rows with row_refs, the baseline rule, and the result with and without repeated rows."""
    with_, without = rec["passes"].get("with_flagged") or {}, rec["passes"].get("without_flagged")
    return {
        "formula": FORMULA, "baseline_rule": BASELINE_RULE.get(rec["baseline_basis"], rec["baseline_basis"]),
        "baseline_basis": rec["baseline_basis"], "status": rec["status"], "paired_months": with_.get("paired_months", []),
        "inputs": [{"role": role, "row_key": r["row_key"], "doc_id": r["doc_id"], "paragraph": r["paragraph"],
                    "table_id": r["table_id"], "native_row_number": r["native_row_number"], "citation": r["citation"],
                    "repeated_row": r["row_key"] in rec["sensitivity_rows"]}
                   for role, rows in (("direct", rec["direct_inputs"]), ("substitute", rec["substitute_inputs"])) for r in rows],
        "with_repeated_rows": {"scenarios": with_.get("scenarios")} if with_ else None,
        "without_repeated_rows": {"scenarios": without.get("scenarios")} if without and without.get("status") == "OK" else None,
        "crosscheck": rec["crosscheck"], "widened": rec["widened"],
    }
