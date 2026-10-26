"""The verdict on a dispute the question names (for example "Ledger Analytics projects a 90% fall; Corvan Grain's statements and the
customs figures say otherwise"). No model is involved: the rules read the documents.

1. The parties are the outlets the question names (a document's `source_name` appearing in the question text).
2. Each party's claim is the first sentence of its documents that states a percentage, the one matching the question's own figure
   first.
3. Independent measures are Tier 1-2 documents from other outlets: a reading of an index whose normal is 100 ("the index was 38"
   means a fall of 62), or a stated percentage fall.
4. A claim is ESTABLISHED when an independent measure for the same month agrees with it (within one point), CONTESTED when it is
   deeper than every independent measure, and a limit the party's own document admits (a method or a source it says is weak) is
   listed as CONCEDED, with the sentence that says so.

Every sentence in the briefing is built from the documents' own words and goes through the same guards as any other paragraph, so a
figure that is not in a cited span is removed by the validator.
"""
import re

from ..agents.claims import number_tokens
from ..provenance.citations import format_citation

PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
INDEX_READING = re.compile(r"\bindex\b[^.]*?\bwas\s+(\d+(?:\.\d+)?)", re.I)
BASE_100 = re.compile(r"\bnormal\s+is\s+100\b", re.I)
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
FALL_WORDS = re.compile(r"\b(?:fall|fell|down|below|lower|drop|dropped|decline|declined|cut)\b", re.I)
CONCESSION = re.compile(r"(?:not a substitute|does not reconcile|did not give a common definition|not reconcile|only an estimate"
                        r"|may be revised|are provisional)", re.I)
INDEPENDENT_TIERS = (1, 2)
AGREE_WITHIN = 1.0                      # percentage points
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _month(text):
    for m in MONTHS:
        if re.search(r"\b" + m + r"\b", text or ""):
            return m
    return None


def _cite(rec, p):
    return format_citation(rec["doc_id"], p["id"], rec["pub_date"], rec["pub_time"])


def _sentences(text):
    return [s for s in SENTENCE.split(re.sub(r"\s+", " ", text or "").strip()) if s]


def _usable(corpus, as_of):
    return [r for r in corpus.records.values()
            if r["status"] in ("OK", "RECODED", "TRUNCATED") and r["paragraphs"] and (r["pub_date"] or "9999") <= as_of
            and r["source_type"] not in (None, "atlas")]


def _question_figures(question):
    return [float(x) for x in PERCENT.findall(question or "")] + [float(x) for x in re.findall(r"-\s?(\d+(?:\.\d+)?)\s?%", question or "")]


def parties(question, docs):
    q = (question or "").lower()
    out = {}
    for r in docs:
        name = (r.get("source_name") or "").strip()
        if len(name) >= 6 and name.lower() in q:
            out.setdefault(name, []).append(r)
    return out


def _headline(recs, figures):
    """(record, paragraph, sentence, figure) for a party's claim: a sentence with a percentage, the question's figure first."""
    found = []
    for r in recs:
        for p in r["paragraphs"]:
            for s in _sentences(p["text_masked"]):
                m = PERCENT.search(s)
                if m and FALL_WORDS.search(s):
                    found.append((r, p, s, float(m.group(1))))
    if not found:
        return None
    matching = [f for f in found if f[3] in figures]
    pool = matching or found
    return sorted(pool, key=lambda f: (f[0]["pub_date"] or "", f[0]["doc_id"]))[-1]


def _measures(docs, party_names):
    """Independent readings: [{rec, paragraphs, month, fall, kind}]. An index counts only where its document gives the normal as 100."""
    out = []
    for r in docs:
        if (r.get("source_name") or "") in party_names or (r["reliability"] or 9) not in INDEPENDENT_TIERS:
            continue
        text = " ".join(p["text_masked"] for p in r["paragraphs"])
        base = next((p for p in r["paragraphs"] if BASE_100.search(p["text_masked"])), None)
        for p in r["paragraphs"]:
            for s in _sentences(p["text_masked"]):
                m = INDEX_READING.search(s)
                if m and base is not None and _month(s):
                    out.append({"rec": r, "paras": [base, p] if base is not p else [p], "month": _month(s),
                                "fall": round(100 - float(m.group(1)), 1), "kind": "index", "reading": m.group(1)})
                pm = PERCENT.search(s)
                if pm and FALL_WORDS.search(s) and "index" not in s.lower() and r["source_type"] != "company_statement":
                    out.append({"rec": r, "paras": [p], "month": _month(s), "fall": float(pm.group(1)), "kind": "percent",
                                "reading": pm.group(1)})
    return out


def _para(pid, text, cls, cites_paras, cf):
    """A briefing paragraph. `cites_paras`: [(record, paragraph)]; every figure in the text is referenced to the cited paragraph that
    contains it (a figure in no cited paragraph gets no reference and is removed by the validator)."""
    cites = list(dict.fromkeys(_cite(r, p) for r, p in cites_paras))
    refs, have = [], set()
    for token in number_tokens(text):
        for r, p in cites_paras:
            if token in number_tokens(p["text_masked"]) and token not in have:
                refs.append({"value": token, "citation": _cite(r, p)})
                have.add(token)
                break
    return {"paragraph_id": pid, "text": text + " " + " ".join(cites), "finding_classification": cls, "claim_refs": [],
            "citation_refs": cites, "row_refs": [], "calc_refs": [], "number_refs": refs, "confidence": 0.9}


def dispute_paragraphs(cf, corpus):
    """{'established': [...], 'contested': [...], 'conceded': [...], 'status': ..., 'parties': [...]} or None when the question names
    no dispute."""
    docs = _usable(corpus, cf["as_of_date"])
    named = parties(cf.get("question"), docs)
    figures = _question_figures(cf.get("question"))
    if len(named) < 2 and not (named and figures):
        return None
    measures = _measures(docs, set(named))
    out = {"established": [], "contested": [], "conceded": [], "parties": [], "measures": [], "status": "NO_CLAIM"}
    deepest = max(measures, key=lambda m: m["fall"], default=None)
    n = {"established": 0, "contested": 0, "conceded": 0}
    for name, recs in named.items():
        head = _headline(recs, figures)
        if not head:
            continue
        r, p, sentence, figure = head
        same = [m for m in measures if m["month"] and m["month"] == _month(sentence)]
        agree = next((m for m in same if abs(m["fall"] - figure) <= AGREE_WITHIN), None)
        party = {"party": name, "doc_id": r["doc_id"], "tier": r["reliability"], "source_type": r["source_type"], "figure": figure,
                 "sentence": sentence, "citation": _cite(r, p)}
        if agree:
            m = agree
            text = (f"The fall of {figure:g}% reported by {name} is established: the {m['rec']['source_name']} "
                    f"({m['rec']['source_type'].replace('_', ' ')}, Tier {m['rec']['reliability']}) reading of {m['reading']} for {m['month']} "
                    f"against a normal of 100 gives the same fall, so a Tier {r['reliability']} {r['source_type'].replace('_', ' ')} is "
                    f"independently corroborated.")
            n["established"] += 1
            out["established"].append(_para(f"dsp-est-{n['established']:02d}", text, "ESTABLISHED",
                                            [(r, p)] + [(m["rec"], q) for q in m["paras"]], cf))
            party["verdict"] = "ESTABLISHED"
        elif deepest and figure > deepest["fall"] + AGREE_WITHIN:
            text = (f"The claim by {name} of a {figure:g}% fall is contested: it rests on a Tier {r['reliability']} "
                    f"{r['source_type'].replace('_', ' ')} and is deeper than every independent measure; the lowest reading in the "
                    f"{deepest['rec']['source_name']} record ({deepest['rec']['source_type'].replace('_', ' ')}, Tier "
                    f"{deepest['rec']['reliability']}) is {deepest['reading']}{' against a normal of 100' if deepest['kind'] == 'index' else '%'}, "
                    f"and a company that reports its own shipments gives a smaller fall.")
            n["contested"] += 1
            own = [(m["rec"], q) for m in [deepest] for q in m["paras"]]
            for other, orecs in named.items():
                oh = _headline(orecs, []) if other != name else None
                if oh and oh[3] < figure:
                    own.append((oh[0], oh[1]))
            out["contested"].append(_para(f"dsp-con-{n['contested']:02d}", text, "CONTESTED", [(r, p)] + own, cf))
            party["verdict"] = "CONTESTED"
        else:
            party["verdict"] = "UNRESOLVED"
        out["parties"].append(party)
        for q in r["paragraphs"]:
            hit = next((s for s in _sentences(q["text_masked"]) if CONCESSION.search(s)), None)
            if hit:
                n["conceded"] += 1
                text = f"The document from {name} itself concedes a limit on its figure: {hit}"
                out["conceded"].append(_para(f"dsp-cnd-{n['conceded']:02d}", text, "CONCEDED", [(r, q)], cf))
                break
    out["measures"] = [{"doc_id": m["rec"]["doc_id"], "kind": m["kind"], "month": m["month"], "fall": m["fall"], "tier": m["rec"]["reliability"],
                        "citation": _cite(m["rec"], m["paras"][-1])} for m in measures]
    if out["parties"]:
        out["status"] = "ADJUDICATED"
    return out if out["parties"] else None


def dispute_sentence(result):
    if not result:
        return ""
    bits = [f"the claim by {p['party']} is {p['verdict'].lower()}" for p in result["parties"] if p["verdict"] != "UNRESOLVED"]
    return ("Dispute check: " + "; ".join(bits) + ". ") if bits else ""
