"""Pack ingestion: manifest -> normalised records -> families -> case scope.

Every document yields a record, whatever happens to it. Status is one of
OK / EMPTY / TRUNCATED / RECODED / FAILED; all detail lives in `flags`.
Only files the manifest lists with a TXT/PDF/DOCX extension are ever opened.
"""
import hashlib
import re
from pathlib import Path

from ..provenance.citations import format_citation
from . import quality, trade
from .extractors import extract
from .manifest import DATE_RE, FORMATS, load_hashes, load_manifest, sha256
from .structure import normalise_ws, split_header, split_paragraphs

HEADER_FIELDS = ["DOC_ID", "EVENT_ID", "TITLE", "SOURCE_NAME", "SOURCE_TYPE", "RELIABILITY",
                 "PUB_DATE", "PUB_TIME", "COUNTRY", "SECTOR"]
STATUS_ORDER = ["FAILED", "EMPTY", "TRUNCATED", "RECODED", "OK"]
BACKGROUND_TAG = "context only"


class Corpus:
    def __init__(self, pack, records, pack_flags):
        self.pack = pack
        self.records = records          # doc_id -> record (insertion order = manifest order)
        self.pack_flags = pack_flags

    def __getitem__(self, doc_id):
        return self.records[doc_id]

    def trade_rows(self):
        return [r for rec in self.records.values() for r in rec["trade_rows"]]


def _add(rec, flag):
    if flag not in rec["flags"]:
        rec["flags"].append(flag)


def _set_status(rec, status):
    if STATUS_ORDER.index(status) < STATUS_ORDER.index(rec["status"]):
        rec["status"] = status


def _blank_record(entry, conflicts):
    doc_id = entry["DOC_ID"]
    return {
        "doc_id": doc_id, "file": entry["FILE"], "format": entry["FORMAT"], "manifest": entry,
        "event_id": entry["EVENT_ID"], "title": entry["TITLE"] or "", "source_name": entry["SOURCE_NAME"],
        "source_type": entry["SOURCE_TYPE"], "reliability": entry["RELIABILITY"],
        "pub_date": entry["PUB_DATE"], "pub_time": entry["PUB_TIME"], "country": entry["COUNTRY"],
        "declared_sector": entry["SECTOR"], "content_sectors": [], "route": None,
        "status": "OK", "flags": [], "metadata_conflicts": list(conflicts), "decoders": [],
        "raw_file_sha256": None, "raw_text": "", "header": {}, "preamble": "", "paragraphs": [],
        "masked_lines": [], "agent_title": entry["TITLE"] or "", "agent_header": {},
        "body_hash": None, "evidence_family_id": None, "family_members": [doc_id],
        "preferred_in_family": True, "background_only": entry["EVENT_ID"] == "NONE",
        "scope_tag": BACKGROUND_TAG if entry["EVENT_ID"] == "NONE" else None,
        "trade_rows": [], "trade_tables": [], "error": None,
    }


def _process(rec, data, hashes):
    rec["raw_file_sha256"] = sha256(data)
    expected = hashes.get(Path(rec["file"]).name)
    if expected is None:
        _add(rec, "HASH_NOT_LISTED")
    elif expected != rec["raw_file_sha256"]:
        _add(rec, "HASH_MISMATCH")
    if not data:
        _add(rec, "EMPTY_DOCUMENT")
        _set_status(rec, "EMPTY")
        return
    ex = extract(data, rec["format"])
    rec["decoders"] = ex.decoder_sections
    for f in ex.flags:
        _add(rec, f)
    if "UNREADABLE_FILE" in ex.flags:
        _set_status(rec, "FAILED")
        return
    if ex.recoded:
        _set_status(rec, "RECODED")
    rec["raw_text"] = ex.text
    header, body, _ = split_header(ex.text)
    rec["header"] = header
    if not header:
        _add(rec, "HEADER_MISSING")
    for f in HEADER_FIELDS:
        hv, mv = header.get(f), rec["manifest"].get(f)
        if hv is not None and mv is not None and str(hv).strip() != str(mv).strip():
            rec["metadata_conflicts"].append({"field": f, "header": hv, "manifest": mv, "source": "document header"})
    preamble, paras, pflags = split_paragraphs(body, rec["title"])
    for f in pflags:
        _add(rec, f)
    rec["preamble"] = preamble
    if not normalise_ws(body):
        _add(rec, "EMPTY_DOCUMENT")
        _set_status(rec, "EMPTY")
        return

    # Agent-visible copies: mask instruction-like lines in paragraphs, title and header values.
    for p in paras:
        p["text_masked"], hits = quality.mask_text(p["text"])
        p["masked"] = bool(hits)
        if hits:
            rec["masked_lines"].append({"paragraph": p["id"], "raw": hits})
    rec["agent_title"], t_hits = quality.mask_text(rec["title"])
    agent_header = {}
    for k, v in header.items():
        agent_header[k], h_hits = quality.mask_text(v)
        if h_hits:
            rec["masked_lines"].append({"paragraph": f"header:{k}", "raw": h_hits})
    rec["agent_header"] = agent_header
    if t_hits:
        rec["masked_lines"].append({"paragraph": "title", "raw": t_hits})
    if rec["masked_lines"]:
        _add(rec, "PROMPT_INJECTION_TEXT")
    rec["paragraphs"] = paras

    # Trade rows: fixed tables first (they mark their paragraphs), then prose.
    rows, tables, tflags = trade.parse_fixed_tables(rec["doc_id"], paras)
    for f in tflags:
        _add(rec, f)
    trade_doc = trade.is_trade_doc(rec["source_type"], rec["title"]) or bool(tables)
    rows += trade.parse_prose_rows(rec["doc_id"], paras, trade_doc)
    origin, dest, sector = trade.route_from([p["text"] for p in paras[:3]] + [rec["title"]])
    if origin:
        rec["route"] = {"origin": origin, "destination": dest, "sector": sector}
    for r in rows:
        if origin and (r["source_layout"] == "prose_note" or not r["origin"]):
            r.update(origin=origin, destination=dest, sector=r["sector"] or sector)
    gaps = trade.missing_month_gaps(rows)
    if gaps:
        _add(rec, "TRADE_TABLE_MISSING_MONTH")
        rec["missing_months"] = gaps
    for t in tables:
        for f in t["flags"]:
            _add(rec, f)
    citation_for = lambda pid: {"doc_id": rec["doc_id"], "paragraph": pid,
                                "published_at": f"{rec['pub_date']} {rec['pub_time'] or '00:00'}",
                                "text": format_citation(rec["doc_id"], pid, rec["pub_date"], rec["pub_time"])}
    rec["trade_rows"] = trade.finalise_rows(rows, citation_for)
    rec["trade_tables"] = tables
    for r in rec["trade_rows"]:
        for f in r["flags"]:
            _add(rec, f)

    # Sectors: declared vs content (title, route line, table header). Sector is a ranking signal only.
    content = set()
    if sector:
        content.add(sector)
    for t in tables:
        if t["header"].get("SECTOR"):
            content.add(t["header"]["SECTOR"].strip().lower())
    rec["content_sectors"] = sorted(content)
    declared = (rec["declared_sector"] or "").strip().lower()
    if content and declared and declared != "general" and declared not in content:
        rec["metadata_conflicts"].append({"field": "SECTOR", "manifest": rec["declared_sector"],
                                          "content": sorted(content), "source": "route/title/table"})

    # Truncation: the last paragraph that is neither masked nor a table ends mid-sentence.
    prose = [p for p in paras if not p["masked"] and not p.get("is_table")]
    if prose and quality.ends_mid_sentence(prose[-1]["text"]):
        _add(rec, "TRUNCATED_DOCUMENT")
        _set_status(rec, "TRUNCATED")
    if any("TRADE_TABLE_TRUNCATED" in t["flags"] for t in tables):
        _set_status(rec, "TRUNCATED")

    canon = "\n".join(f"{p['id']} {normalise_ws(p['text'])}" for p in paras)
    rec["body_hash"] = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    rec["_canon"] = canon


def _families(records):
    """Group by body hash; then fold damaged twins (same title, date, source) into the clean copy."""
    fam = {}
    for rec in records.values():
        if rec["body_hash"]:
            fam.setdefault(rec["body_hash"], []).append(rec["doc_id"])
    family_of = {}
    for h, ids in fam.items():
        for d in ids:
            family_of[d] = "FAM-" + h[:12]
    for rec in records.values():
        if rec["doc_id"] not in family_of:
            family_of[rec["doc_id"]] = "FAM-" + hashlib.sha256(rec["doc_id"].encode()).hexdigest()[:12] + "-solo"
    twins = {}
    for rec in records.values():
        key = (normalise_ws(rec["title"]).lower(), rec["pub_date"], (rec["source_name"] or "").lower())
        twins.setdefault(key, []).append(rec)
    for group in twins.values():
        if len(group) < 2:
            continue
        clean = [r for r in group if r["status"] in ("OK", "RECODED") and r.get("_canon")]
        for r in group:
            for c in clean:
                if c is r or family_of[c["doc_id"]] == family_of[r["doc_id"]]:
                    continue
                rc, cc = r.get("_canon", ""), c["_canon"]
                prefix = bool(rc) and len(rc) < len(cc) and _norm_prefix(rc, cc)
                if r["status"] == "EMPTY" or r["status"] == "TRUNCATED" or prefix:
                    if prefix and r["status"] not in ("EMPTY", "FAILED"):
                        _add(r, "TRUNCATED_DOCUMENT")
                        _set_status(r, "TRUNCATED")
                    old = family_of[r["doc_id"]]
                    for d, f in list(family_of.items()):
                        if f == old:
                            family_of[d] = family_of[c["doc_id"]]
                    _add(r, "EVIDENCE_FAMILY_DUPLICATE")
                    break
    members = {}
    for d, f in family_of.items():
        members.setdefault(f, []).append(d)
    for f, ids in members.items():
        # Clean statuses (OK, RECODED) sort first; then the longest body; then doc_id.
        ranked = sorted(ids, key=lambda d: (records[d]["status"] not in ("OK", "RECODED"),
                                            -len(records[d].get("_canon", "")), d))
        for d in ids:
            rec = records[d]
            rec["evidence_family_id"] = f
            rec["family_members"] = sorted(ids)
            rec["preferred_in_family"] = d == ranked[0]
            if len(ids) > 1:
                same_hash = [x for x in ids if records[x]["body_hash"] and records[x]["body_hash"] == rec["body_hash"]]
                if len(same_hash) > 1:
                    _add(rec, "DUPLICATE_CONTENT")
                    _add(rec, "CONTENT_HASH_DUPLICATE")
                _add(rec, "EVIDENCE_FAMILY_DUPLICATE")


def _cross_doc_rows(records):
    """Repeat case "c": the same route, month, value and volume in another document.

    Same family = one source (dedupe); different family = corroboration. Either
    way the row is counted once in arithmetic. This adds no flag.
    """
    seen = {}
    for rec in records.values():
        for r in rec["trade_rows"]:
            if r["month"] and r["value_amount"] is not None and r["volume_amount"] is not None:
                key = (r["origin"], r["destination"], r["sector"], r["month"],
                       r["value_amount"], r["value_currency"], r["volume_amount"], r["volume_unit"])
                seen.setdefault(key, []).append((rec["evidence_family_id"], r))
    for group in seen.values():
        docs = {r["source_doc_id"] for _, r in group}
        if len(docs) < 2:
            continue
        for fam, r in group:
            for ofam, o in group:
                if o["source_doc_id"] != r["source_doc_id"]:
                    r["cross_doc_matches"].append({"row_key": o["row_key"], "same_family": ofam == fam})
            if "c" not in r["repeat_cases"]:
                r["repeat_cases"] = sorted(r["repeat_cases"] + ["c"])


def _norm_prefix(short, long):
    a = re.sub(r"\s+", " ", short).strip()
    b = re.sub(r"\s+", " ", long).strip()
    return b.startswith(a) or b.startswith(a.rsplit(" ", 1)[0])


def ingest_pack(pack_dir):
    pack_dir = Path(pack_dir)
    pack, entries, pack_flags = load_manifest(pack_dir)
    hashes = load_hashes(pack_dir)
    records = {}
    for entry, conflicts in entries:
        if not entry["DOC_ID"]:
            pack_flags.append({"flag": "MANIFEST_ENTRY_WITHOUT_DOC_ID", "entry": entry})
            continue
        rec = _blank_record(entry, conflicts)
        if rec["doc_id"] in records:
            pack_flags.append({"flag": "DUPLICATE_DOC_ID", "doc_id": rec["doc_id"]})
            continue
        records[rec["doc_id"]] = rec
        if not DATE_RE.match(rec["pub_date"] or ""):
            _add(rec, "INVALID_PUB_DATE")
        name = rec["file"] or ""
        if Path(name).suffix.lower() not in FORMATS:
            _add(rec, "UNSUPPORTED_FORMAT")   # never opened
            _set_status(rec, "FAILED")
            continue
        path = next((p for p in (pack_dir / name, pack_dir / "docs" / Path(name).name) if p.is_file()), None)
        if path is None:
            _add(rec, "MISSING_FILE")
            _set_status(rec, "FAILED")
            continue
        try:
            _process(rec, path.read_bytes(), hashes)
        except Exception as e:   # one bad file must never stop the pack
            rec["error"] = f"{type(e).__name__}: {e}"
            _add(rec, "UNREADABLE_FILE")
            _set_status(rec, "FAILED")
        if rec["metadata_conflicts"]:
            _add(rec, "METADATA_CONFLICT")
    _families(records)
    _cross_doc_rows(records)
    for rec in records.values():
        rec.pop("_canon", None)
    return Corpus(pack, records, pack_flags)


# ---------- case scope ----------

def case_scope(corpus, as_of, event_id):
    """As-of gate and event scope, applied before indexing.

    Eligible = (EVENT_ID == event OR NONE) AND valid PUB_DATE <= as_of.
    Returns (eligible records, {doc_id: reason}) for the excluded ones.
    """
    eligible, excluded = [], {}
    for rec in corpus.records.values():
        d = rec["pub_date"] or ""
        if not DATE_RE.match(d):
            excluded[rec["doc_id"]] = "INVALID_PUB_DATE"
        elif d > as_of:
            excluded[rec["doc_id"]] = "FUTURE_DATED"
        elif rec["event_id"] not in (event_id, "NONE"):
            excluded[rec["doc_id"]] = "OUT_OF_EVENT_SCOPE"
        else:
            eligible.append(rec)
    return eligible, excluded


def agent_view(rec):
    """What an agent may see: masked text only, never raw_text or masked raw lines."""
    return {
        "doc_id": rec["doc_id"], "title": rec["agent_title"], "header": rec["agent_header"],
        "event_id": rec["event_id"], "pub_date": rec["pub_date"], "pub_time": rec["pub_time"],
        "source_name": rec["source_name"], "source_type": rec["source_type"], "reliability": rec["reliability"],
        "country": rec["country"], "declared_sector": rec["declared_sector"], "content_sectors": rec["content_sectors"],
        "status": rec["status"], "flags": list(rec["flags"]), "background_only": rec["background_only"],
        "scope_tag": rec["scope_tag"], "evidence_family_id": rec["evidence_family_id"],
        "paragraphs": [{"id": p["id"], "text": p["text_masked"], "masked": p["masked"]} for p in rec["paragraphs"]],
    }
