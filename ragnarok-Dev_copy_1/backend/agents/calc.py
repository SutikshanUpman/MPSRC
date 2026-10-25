"""Deterministic exposure calculation for one cell ($0, no model). SYSTEM_ARCHITECTURE 21.

Baseline (F11). Primary: post-event months = event month through the last month
on or before the as-of date with a direct-route row; each is paired with the
same calendar month one year earlier. Unpaired months are dropped from both
sides and listed. Cross-check: a "% of normal" level or a pre-event index
(base 100) stated in an eligible case-event paragraph that names the route
(an event origin and the cell country) or the cell's country and sector, for
post-event months. Its implied gross shortfall is 100 - level. The lowest tier,
then the latest pub_date, is used; the others are recorded.
    agree (within baseline_crosscheck_tolerance_pct_points) -> primary range, both recorded
    disagree -> extra pass with the baseline scaled to the cross-check; BASELINE_CONFLICT
    cross-check only -> baseline = post-event flow / (level / 100); BASELINE_PROXY
    neither -> NO_BASELINE (no range)

Shortfall = baseline - post-event value on the direct (event-origin) route.
Substitute offset = growth of the substitute routes over the same paired months
(never negative). Scenario c credits a share c of that offset:
    pct(c) = (gross_shortfall - c * offset) / direct_baseline * 100
Repeated-row sensitivity (21, Repeated-row sensitivity): every value is computed
with all usable rows and again without `sensitivity_row` rows; the envelope per
scenario is [min, max] over all passes. Agents only pick named fields from
this record; they never do arithmetic.
"""
import re

from ..ingestion.trade import MONTHS, parse_month
from ..provenance.citations import format_citation
from ..search.bm25 import mentions

STATUS_OK, NO_FLOW, NO_BASELINE, MIXED_UNITS = "OK", "NO_DOCUMENTED_FLOW", "NO_BASELINE", "MIXED_UNITS"
XC_NONE, XC_AGREE, XC_CONFLICT, XC_ONLY = "NONE", "AGREE", "CONFLICT", "CROSS_CHECK_ONLY"

_NUM = r"(\d+(?:\.\d+)?)"
_ABOUT = r"(?:about\s+|around\s+|roughly\s+|some\s+|nearly\s+|almost\s+)?"
LEVEL_PCT = re.compile(r"(?<![\w.])" + _ABOUT + _NUM + r"\s*(?:%|per ?cent)\s+of\s+(?:the\s+|its\s+)?"
                       r"(?:old\s+|usual\s+|pre-?\w+\s+)?(?:normal|usual)\b", re.I)
INDEX_BASE = re.compile(r"\b(?:100\s*=\s*(?:the\s+)?(?:old\s+)?normal|normal\s+(?:of|is|was|at|=)\s+100|"
                        r"based\s+(?:at|on)\s+100|base\s+(?:of\s+)?100)\b", re.I)
INDEX_LEVEL = [re.compile(r"\bindex\b[^.;]{0,60}?\b(?:at|was|of|to)\s+" + _ABOUT + _NUM + r"(?![\d%]|\.\d)", re.I),
               re.compile(r"\b(?:at|of)\s+" + _ABOUT + _NUM + r"\s+on\s+the\s+(?:\w+\s+){0,2}index\b", re.I)]
HEDGE = re.compile(r"\b(?:expect\w*|forecast\w*|project\w*|predict\w*|could|would|might|may|likely|if)\b", re.I)
MONTH_WORD = re.compile(r"\b(" + "|".join(MONTHS) + r")\.?(?:\s+(\d{4}))?\b", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _year_before(month):
    return f"{int(month[:4]) - 1:04d}{month[4:]}"


def _by_month(rows):
    """One row per (origin, month): the first by row_key (cross-document repeats count once)."""
    out = {}
    for r in sorted(rows, key=lambda r: r["row_key"]):
        out.setdefault((r["origin"], r["month"]), r)
    return out


def _totals(rows, months):
    by = _by_month(rows)
    picked = [r for (o, m), r in by.items() if m in months]
    currencies = {r["value_currency"] for r in picked if r["value_amount"] is not None}
    units = {r["volume_unit"] for r in picked if r["volume_amount"] is not None}
    value = sum(r["value_amount"] for r in picked if r["value_amount"] is not None)
    volume = sum(r["volume_amount"] for r in picked if r["volume_amount"] is not None)
    return {"value": value, "volume": volume, "currencies": sorted(c for c in currencies if c),
            "units": sorted(u for u in units if u), "row_keys": sorted(r["row_key"] for r in picked)}


def _months_with_value(rows):
    return {r["month"] for r in rows if r["value_amount"] is not None}


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else None


def _unit_price(value, volume):
    return round(value / volume, 2) if volume else None


def _flow(base, post):
    """Value and volume over the paired months, and the implied unit price (value / volume) before and after."""
    return {"baseline_value": base["value"], "post_value": post["value"], "value_change": post["value"] - base["value"],
            "value_change_pct": _pct(post["value"] - base["value"], base["value"]),
            "baseline_volume": base["volume"], "post_volume": post["volume"], "volume_change": post["volume"] - base["volume"],
            "volume_change_pct": _pct(post["volume"] - base["volume"], base["volume"]),
            "unit_price_before": _unit_price(base["value"], base["volume"]),
            "unit_price_after": _unit_price(post["value"], post["volume"])}


def _substitute(substitute, months):
    sub_have = _months_with_value(substitute)
    sub_paired = [m for m in months if m in sub_have and _year_before(m) in sub_have]
    s_base, s_post = _totals(substitute, [_year_before(m) for m in sub_paired]), _totals(substitute, sub_paired)
    return sub_paired, s_base, s_post, max(0.0, s_post["value"] - s_base["value"])


def _one_pass(direct, substitute, event_month, as_of, credits):
    post = sorted(m for m in _months_with_value(direct) if event_month <= m <= as_of[:7])
    have = _months_with_value(direct)
    paired = [m for m in post if _year_before(m) in have]
    dropped = [m for m in post if m not in paired]
    if not paired:
        return {"status": NO_BASELINE, "post_event_months": post, "paired_months": [], "months_dropped": dropped}
    base_months = [_year_before(m) for m in paired]
    d_base, d_post = _totals(direct, base_months), _totals(direct, paired)
    if len(set(d_base["currencies"]) | set(d_post["currencies"])) > 1:
        return {"status": MIXED_UNITS, "post_event_months": post, "paired_months": paired, "months_dropped": dropped}
    sub_paired, s_base, s_post, offset = _substitute(substitute, paired)
    gross = d_base["value"] - d_post["value"]
    gross_volume = d_base["volume"] - d_post["volume"]
    volume_offset = max(0.0, s_post["volume"] - s_base["volume"])
    return {
        "status": STATUS_OK, "basis": "PRIMARY_YOY", "post_event_months": post, "paired_months": paired,
        "paired_month_count": len(paired), "baseline_months": base_months,
        "months_dropped": dropped, "substitute_paired_months": sub_paired,
        "direct": dict(_flow(d_base, d_post), currency=(d_base["currencies"] or [None])[0],
                       volume_unit=(d_base["units"] or [None])[0], row_keys=d_base["row_keys"] + d_post["row_keys"]),
        "substitute": dict(_flow(s_base, s_post), row_keys=s_base["row_keys"] + s_post["row_keys"]),
        "gross_value_shortfall": gross, "gross_value_shortfall_pct": _pct(gross, d_base["value"]),
        "substitute_offset": offset,
        "scenarios": {name: _pct(gross - c * offset, d_base["value"]) for name, c in credits.items()},
        # A5: the same scenarios as absolute net shortfalls, in the rows' currency and in their volume unit.
        "scenario_values": {name: round(gross - c * offset, 2) for name, c in credits.items()},
        "scenario_volumes": {name: round(gross_volume - c * volume_offset, 2) for name, c in credits.items()},
    }


def _scaled_pass(direct, substitute, months, level, credits, basis):
    """Baseline = observed post-event direct flow / (level / 100) over `months` (cross-check scaling or proxy)."""
    d_post = _totals(direct, months)
    if not months or not d_post["value"] or not level:
        return {"status": NO_BASELINE, "basis": basis, "post_event_months": months}
    if len(d_post["currencies"]) > 1:
        return {"status": MIXED_UNITS, "basis": basis, "post_event_months": months}
    baseline = d_post["value"] / (level / 100.0)
    sub_paired, s_base, s_post, offset = _substitute(substitute, months)
    gross = baseline - d_post["value"]
    return {"status": STATUS_OK, "basis": basis, "post_event_months": months, "level_pct_of_normal": level,
            "implied_baseline_value": round(baseline, 2), "post_value": d_post["value"],
            "currency": (d_post["currencies"] or [None])[0], "row_keys": d_post["row_keys"],
            "substitute_paired_months": sub_paired, "gross_value_shortfall": round(gross, 2),
            "gross_value_shortfall_pct": _pct(gross, baseline), "substitute_offset": offset,
            "scenarios": {name: _pct(gross - c * offset, baseline) for name, c in credits.items()},
            "scenario_values": {name: round(gross - c * offset, 2) for name, c in credits.items()}}


# ---------- cross-check (F11) ----------

def _months_in(sentence, pub_date):
    """Months named in a sentence; a month without a year takes the latest year not after pub_date."""
    out = []
    for word, year in MONTH_WORD.findall(sentence):
        if not year:
            num = MONTHS[word.lower()]
            year = int(pub_date[:4]) if num <= int(pub_date[5:7]) else int(pub_date[:4]) - 1
        m = parse_month(word, year)
        if m and m not in out:
            out.append(m)
    return out


def _levels_in(sentence, doc_has_index_base):
    found = [("pct_of_normal", float(v)) for v in LEVEL_PCT.findall(sentence)]
    if doc_has_index_base:
        for pat in INDEX_LEVEL:
            found += [("index", float(v)) for v in pat.findall(sentence) if float(v) != 100.0]
    return found


def find_crosschecks(records, country, sector, origins, months, event_id):
    """Every qualifying cross-check statement for the cell over `months`, one entry per (document, month).

    A paragraph qualifies when it names the route (an event origin and the cell country) or the cell's
    country and sector; background-only, non-case-event, table and hedged (forecast) text never does."""
    found = []
    for rec in records:
        if rec["event_id"] != event_id or rec.get("background_only") or rec["status"] not in ("OK", "RECODED", "TRUNCATED"):
            continue
        body = " ".join(p["text_masked"] for p in rec["paragraphs"])
        has_base = INDEX_BASE.search(body) is not None
        for p in rec["paragraphs"]:
            text = p["text_masked"]
            if p.get("is_table") or not mentions(text, country):
                continue
            if not (any(mentions(text, o) for o in origins) or mentions(text, sector)):
                continue
            for s in SENTENCE.split(" ".join(text.split())):
                if HEDGE.search(s):
                    continue
                levels, named = _levels_in(s, has_base), [m for m in _months_in(s, rec["pub_date"]) if m in months]
                if not levels or not named:
                    continue
                if len(levels) == 1:
                    pairs = [(m, levels[0]) for m in named]
                elif len(levels) == len(named):
                    pairs = list(zip(named, levels))
                else:
                    continue                          # ambiguous pairing of levels and months
                for m, (kind, level) in pairs:
                    found.append({"doc_id": rec["doc_id"], "paragraph": p["id"], "tier": rec["reliability"],
                                  "pub_date": rec["pub_date"], "month": m, "kind": kind, "level": level,
                                  "citation": format_citation(rec["doc_id"], p["id"], rec["pub_date"], rec["pub_time"]),
                                  "text": text})
    return found


def _pick_crosscheck(found):
    """Lowest tier number, then latest pub_date (then doc_id); returns (used refs, other refs)."""
    if not found:
        return [], []
    docs = {f["doc_id"]: (f["tier"] if f["tier"] is not None else 9, f["pub_date"]) for f in found}
    order = sorted(docs)
    order.sort(key=lambda d: docs[d][1], reverse=True)        # latest pub_date first (stable) ...
    order.sort(key=lambda d: docs[d][0])                       # ... within the lowest tier number
    used = {}
    for f in sorted((f for f in found if f["doc_id"] == order[0]), key=lambda f: (f["month"], int(f["paragraph"][1:]))):
        used.setdefault(f["month"], f)                        # first statement per month
    return list(used.values()), [f for f in found if f["doc_id"] != order[0]]


def _ref(f):
    return {k: f[k] for k in ("doc_id", "paragraph", "citation", "tier", "pub_date", "month", "kind", "level")}


def row_ref(r):
    return {"row_key": r["row_key"], "doc_id": r["source_doc_id"], "paragraph": r["paragraph"],
            "table_id": r["table_id"], "native_row_number": r["native_row_number"], "citation": r["citation"]["text"],
            "month": r["month"], "origin": r["origin"], "sensitivity_row": r["sensitivity_row"],
            "repeat_cases": list(r.get("repeat_cases") or []),
            "flags": [f for f in r.get("flags") or [] if f in ("TRADE_ROW_REPEATED_VALUES", "TRADE_ROW_DUPLICATE")]}


def compute_cell(calc_id, agent, country, sector, direct_rows, substitute_rows, event_month, as_of, credits,
                 crosscheck_records=(), origins=(), event_id=None, tolerance=5.0):
    """`credits` maps scenario name -> share of the substitute offset credited (config calc_substitute_credit).
    `crosscheck_records` are the case-scope records the calculator scans for F11 cross-checks."""
    usable_d = [r for r in direct_rows if r["usable_for_arithmetic"]]
    usable_s = [r for r in substitute_rows if r["usable_for_arithmetic"]]
    record = {"calc_id": calc_id, "agent": agent, "country": country, "sector": sector,
              "metric": "net_value_shortfall_pct", "unit": "percent", "rule": "F11: same months one year earlier, cross-checked",
              "baseline_basis": "PRIMARY_YOY", "crosscheck": XC_NONE, "crosscheck_refs": [], "crosscheck_others": [],
              "crosscheck_implied_gross_shortfall_pct": None, "baseline_flags": [], "event_month": event_month,
              "as_of_date": as_of, "credits": dict(credits), "tolerance_pct_points": tolerance,
              "direct_inputs": [row_ref(r) for r in sorted(usable_d, key=lambda r: r["row_key"])],
              "substitute_inputs": [row_ref(r) for r in sorted(usable_s, key=lambda r: r["row_key"])],
              "excluded_inputs": sorted(r["row_key"] for r in direct_rows + substitute_rows if not r["usable_for_arithmetic"])}
    if not usable_d or not event_month:
        record.update(status=NO_FLOW, baseline_basis="NONE", passes={}, envelope={}, envelope_value={}, envelope_volume={},
                      sensitivity_rows=[], widened=False, baseline_conflict=False, repeat_sensitivity_pct=None,
                      repeat_sensitivity_pct_by_scenario={}, repeated_row_dependent=False)
        return record
    flagged = [r for r in usable_d + usable_s if r["sensitivity_row"]]
    clean_d = [r for r in usable_d if not r["sensitivity_row"]]
    clean_s = [r for r in usable_s if not r["sensitivity_row"]]
    passes = {"with_flagged": _one_pass(usable_d, usable_s, event_month, as_of, credits),
              "without_flagged": _one_pass(clean_d, clean_s, event_month, as_of, credits)}
    main = passes["with_flagged"]
    record["sensitivity_rows"] = sorted(r["row_key"] for r in flagged)

    post = main["paired_months"] if main["status"] == STATUS_OK else main["post_event_months"]
    used, others = _pick_crosscheck(find_crosschecks(crosscheck_records, country, sector, origins, post, event_id))
    record["crosscheck_refs"], record["crosscheck_others"] = [_ref(f) for f in used], [_ref(f) for f in others]
    level = round(sum(f["level"] for f in used) / len(used), 1) if used else None
    if level is not None:
        record["crosscheck_implied_gross_shortfall_pct"] = round(100 - level, 1)
        xc_months = sorted(f["month"] for f in used)
        if main["status"] == STATUS_OK:
            gap = abs(main["gross_value_shortfall_pct"] - (100 - level))
            if gap <= tolerance:
                record["crosscheck"] = XC_AGREE
            else:
                record["crosscheck"] = XC_CONFLICT
                record["baseline_flags"].append("BASELINE_CONFLICT")
                passes["crosscheck_scaled"] = _scaled_pass(usable_d, usable_s, main["paired_months"], level, credits,
                                                           "CROSSCHECK_SCALED")
        elif main["status"] == NO_BASELINE:
            proxy = _scaled_pass(usable_d, usable_s, [m for m in main["post_event_months"] if m in xc_months],
                                 level, credits, "CROSS_CHECK_ONLY")
            if proxy["status"] == STATUS_OK:
                record["crosscheck"] = XC_ONLY
                record["baseline_flags"].append("BASELINE_PROXY")
                record["baseline_basis"] = "CROSS_CHECK_ONLY"
                passes["crosscheck_proxy"] = proxy
                main = proxy
    record["passes"] = passes
    if main["status"] != STATUS_OK:
        record.update(status=main["status"], baseline_basis="NONE" if main["status"] == NO_BASELINE else "PRIMARY_YOY",
                      envelope={}, envelope_value={}, envelope_volume={}, widened=False, baseline_conflict=False,
                      repeat_sensitivity_pct=None,
                      repeat_sensitivity_pct_by_scenario={}, repeated_row_dependent=False)
        return record
    ok = [p for p in passes.values() if p["status"] == STATUS_OK]
    record["envelope"] = {name: {"low": min(p["scenarios"][name] for p in ok), "high": max(p["scenarios"][name] for p in ok)}
                          for name in credits}
    for key, out in (("scenario_values", "envelope_value"), ("scenario_volumes", "envelope_volume")):
        have = [p for p in ok if key in p]   # a scaled or proxy pass has no volume
        record[out] = {name: {"low": min(p[key][name] for p in have), "high": max(p[key][name] for p in have)}
                       for name in credits} if have else {}
    w, wo = passes["with_flagged"], passes["without_flagged"]
    both = bool(flagged) and w["status"] == STATUS_OK and wo["status"] == STATUS_OK
    by_scenario = {n: round(abs(w["scenarios"][n] - wo["scenarios"][n]), 1) for n in credits} if both else {}
    record["repeat_sensitivity_pct_by_scenario"] = by_scenario
    record["repeat_sensitivity_pct"] = max(by_scenario.values()) if by_scenario else None
    record["widened"] = any(v > 0 for v in by_scenario.values())          # by repeated rows only
    record["baseline_conflict"] = record["crosscheck"] == XC_CONFLICT
    record["repeated_row_dependent"] = bool(flagged) and wo["status"] != STATUS_OK
    record["status"] = STATUS_OK
    return record


SECONDARY_FIELDS = ("value_change", "value_change_pct", "volume_change", "volume_change_pct", "unit_price_before",
                    "unit_price_after")
PASS_VIEW_KEYS = ("status", "basis", "paired_months", "paired_month_count", "months_dropped", "gross_value_shortfall_pct",
                  "substitute_offset", "level_pct_of_normal", "scenarios")


def _doc_citations(rows, months):
    """One citation per input document: a post-event row without a repeat flag when there is one."""
    best = {}
    for r in rows:
        rank = (r["sensitivity_row"], r["month"] not in months, r["row_key"])
        if r["doc_id"] not in best or rank < best[r["doc_id"]][0]:
            best[r["doc_id"]] = (rank, r["citation"])
    return [best[d][1] for d in sorted(best)]


def agent_view(record):
    """What the calc tool returns to the agent. Numbers keep the dotted paths of the stored record, so a
    low_ref/high_ref/number_ref resolves against the calc ledger; inputs are reduced to one citation per
    document plus the flagged rows. The full record, with every input row ref, stays in the ledger."""
    view = {k: record[k] for k in ("calc_id", "country", "sector", "status", "baseline_basis", "crosscheck",
                                   "crosscheck_implied_gross_shortfall_pct", "baseline_flags", "sensitivity_rows",
                                   "widened", "repeat_sensitivity_pct", "envelope")}
    view["crosscheck_refs"] = [{k: f[k] for k in ("citation", "month", "kind", "level")} for f in record["crosscheck_refs"]]
    view["passes"] = {}
    for name, p in record["passes"].items():
        v = {k: p[k] for k in PASS_VIEW_KEYS if k in p}
        if "direct" in p:
            v["direct"] = {k: p["direct"][k] for k in SECONDARY_FIELDS + ("currency", "volume_unit")}
            v["substitute"] = {k: p["substitute"][k] for k in ("value_change_pct", "volume_change_pct")}
        view["passes"][name] = v
    months = (record["passes"].get("with_flagged") or {}).get("paired_months") or []
    view["substitute_origins"] = sorted({r["origin"] for r in record["substitute_inputs"]})
    view["input_citations"] = {"direct": _doc_citations(record["direct_inputs"], months),
                               "substitute": _doc_citations(record["substitute_inputs"], months)}
    view["direct_row_keys"] = [r["row_key"] for r in record["direct_inputs"]]
    view["substitute_row_keys"] = [r["row_key"] for r in record["substitute_inputs"]]
    view["flagged_inputs"] = [{k: r[k] for k in ("row_key", "origin", "month", "citation", "flags")}
                              for r in record["direct_inputs"] + record["substitute_inputs"] if r["sensitivity_row"]]
    return view


def field(record, path):
    """Resolve a dotted path such as 'envelope.half_credit.low' in a calc record."""
    value = record
    for part in path.split("."):
        value = value[part]
    return value
