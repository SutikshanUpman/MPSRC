"""Hallucination guardrails (FINAL BUILD phase 2).

One module, applied to every agent output before it enters the Case File. Each
guard returns a list of problems; a non-empty list is a schema failure (the agent
retries, then AGENT_FAILED, F07). The guards are generic: they read the Case File,
the corpus and the agent's own tool log, never a document ID or an event name.

    schema_guard     structured output only, unknown fields rejected
    citation_guard   citation resolves, in case scope, dated <= as-of, retrieved by the author
    quote_guard      quoted text is an exact (whitespace-normalised) substring of a cited masked span
    number_guard     every number maps to a cited span or a calc field; low <= high
    entity_guard     capitalised names exist in the Case File or a cited span
    injection_guard  masked text never reappears; no instruction-like text in an output
    abstain_guard    no evidence -> NO_DOCUMENTED_FLOW / INSUFFICIENT_EVIDENCE, never a guess
"""
import re

from ..ingestion.quality import MASK_PLACEHOLDER, is_instruction_like
from ..llm.provider import validate_schema
from ..provenance.citations import parse_citations, validate_citation

QUOTE = re.compile(r'"([^"]{12,})"|“([^”]{12,})”')
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
MONTHS = {m.lower() for m in ("January February March April May June July August September October November December "
                              "Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec").split()}
# Capitalised words that open a sentence or name the runtime's own vocabulary; never entities.
COMMON = {w.lower() for w in (
    "A An The This That These Those It Its Their There Here No Not None One Two Both Each Any All Some Documented "
    "Baseline Rows Row Thor Loki Odin Heimdall Tier Run Round Claim Calc Estimate Estimates Based Because Where When While "
    "If In On At As By For From To Of And Or But With Without After Before Against Under Over Direct Substitute Mitigation "
    "Per Net Value Volume Unit Price Prices Percent USD EUR GBP Insufficient Evidence Established "
    "Contested Conceded Removed Validator Exposure Outlook Assumptions Drivers Risks Indicators Summary Table Source "
    "Sources Executive Header Completion Status Flagged Cells Cell Scope Case Event File Ruling Rulings Finding Findings").split()}


def _norm(text):
    return " ".join((text or "").split())


def schema_guard(value, schema, where="$"):
    """Structured output only: the JSON-schema subset of provider.validate_schema, which rejects unknown fields
    wherever the schema says additionalProperties: false."""
    return validate_schema(value, schema, where)


def citation_guard(where, citations, corpus, as_of, eligible_ids, retrieved=None, author="author"):
    problems = []
    for cit in citations:
        parsed = parse_citations(cit)
        if len(parsed) != 1:
            problems.append(f"{where}: unparseable citation {cit}")
            continue
        issues = validate_citation(parsed[0], corpus, as_of)
        if issues:
            problems.append(f"{where}: citation {cit} invalid: {issues}")
        if parsed[0]["doc_id"] not in eligible_ids:
            problems.append(f"{where}: citation {cit} is outside the case scope")
        if retrieved is not None and cit not in retrieved:
            problems.append(f"{where}: citation {cit} was not retrieved by {author}")
    return problems


def cited_text(citations, corpus):
    out = []
    for cit in citations:
        for p in parse_citations(cit):
            rec = corpus.records.get(p["doc_id"])
            if rec:
                out += [_norm(q["text_masked"]) for q in rec["paragraphs"] if q["id"] == p["paragraph"]]
    return out


def quotes_in(text):
    return [a or b for a, b in QUOTE.findall(text or "")]


def quote_guard(where, texts, citations, corpus):
    """Any quoted text must be an exact (whitespace-normalised) substring of a cited masked span."""
    spans = cited_text(citations, corpus)
    problems = []
    for text in texts:
        for q in quotes_in(text):
            if not any(_norm(q) in s for s in spans):
                problems.append(f"{where}: quoted text not found verbatim in a cited span: {q[:80]!r}")
    return problems


def number_guard(where, texts, number_tokens, number_refs, resolve_calc, span_text, norm):
    """Every number in `texts` has a number_ref: a calc field with that value, or a whole number in a cited span.
    `resolve_calc(calc_id, field)` returns the calc value or None; `span_text(citation)` the span text or None.
    Agents never do arithmetic: a number that is neither is rejected."""
    problems, refs = [], set()
    for ref in number_refs:
        refs.add(norm(ref["value"]))
        if "calc_id" in ref:
            value = resolve_calc(ref["calc_id"], ref.get("field", ""))
            try:
                # prose gives the size of a change ("fell 60.3%") and the calc field carries its sign: compare magnitudes
                ok = value is not None and round(abs(float(value)), 1) == round(abs(float(norm(ref["value"]))), 1)
            except (TypeError, ValueError):
                ok = False
            if not ok:
                problems.append(f"{where}: number {ref['value']} does not match {ref.get('calc_id')}:{ref.get('field')}")
        elif "citation" in ref:
            text = span_text(ref["citation"])
            if text is None or norm(ref["value"]) not in {norm(t) for t in NUMBER.findall(text)}:
                problems.append(f"{where}: number {ref['value']} is not in the cited span {ref['citation']}")
        else:
            problems.append(f"{where}: number_ref {ref['value']} has neither calc_id nor citation")
    for text in texts:
        for token in number_tokens(text):
            if norm(token) not in refs:
                problems.append(f"{where}: number {token} has no span or calc_id")
    return problems


def range_guard(where, low, high, unit="percent"):
    problems = []
    if low is not None and high is not None and low > high:
        problems.append(f"{where}: low {low} > high {high}")
    if unit != "percent":
        problems.append(f"{where}: unit {unit!r} is not the case metric unit")
    return problems


def allowed_names(cf, corpus, citations=()):
    """Words an output may use as names: the Case File's own vocabulary plus the cited spans and their titles."""
    text = [cf.get("question") or "", cf.get("event_name") or ""]
    text += cf.get("target_countries", []) + cf.get("target_sectors", [])
    ms = cf.get("manifest_scope") or {}
    text += ms.get("scope_countries", []) + ms.get("scope_sectors", []) + ms.get("route_countries", []) + ms.get("event_origins", [])
    for c in cf.get("exposure_cells", []):
        text += [c["country"], c["sector"]]
    for cit in citations:
        for p in parse_citations(cit):
            rec = corpus.records.get(p["doc_id"])
            if rec:
                text.append(rec["agent_title"])
                text += [q["text_masked"] for q in rec["paragraphs"]]
    return {w.lower() for t in text for w in WORD.findall(t)}


def entity_guard(where, texts, cf, corpus, citations=()):
    """Countries, sectors, routes and dates must exist in the Case File or the cited span; nothing invented.
    A capitalised word that does not start a sentence must appear in that vocabulary."""
    allowed = allowed_names(cf, corpus, citations) | COMMON | MONTHS
    problems = []
    for text in texts:
        body = QUOTE.sub(" ", text or "")                      # quotes are checked by quote_guard
        body = re.sub(r"\[[^\]]*\]", " ", body)                # citation brackets
        for m in WORD.finditer(body):
            w = m.group(0)
            if not w[0].isupper() or w.isupper() or w.lower() in allowed:
                continue
            if re.sub(r"'s?$", "", w).lower() in allowed:     # a possessive of a known name: "Harbour's"
                continue
            parts = [x for x in w.split("-") if x]
            if len(parts) > 1 and all(not x[0].isupper() or x.lower() in allowed for x in parts):
                continue                                       # a route written "Orvan-to-Ravik": every name in it is known
            before = body[:m.start()].rstrip()
            if not before or before[-1] in ".!?:;(\n":        # sentence start
                continue
            problems.append(f"{where}: name {w!r} is not in the Case File or the cited spans")
    return problems


def injection_guard(where, texts, masked_lines=()):
    problems = []
    for text in texts:
        text = text or ""
        if MASK_PLACEHOLDER in text or any(line in text for line in masked_lines):
            problems.append(f"{where}: output contains masked document text")
        elif is_instruction_like(QUOTE.sub(" ", text)):
            problems.append(f"{where}: output contains instruction-like text")
    return problems


def abstain_guard(where, claim):
    """No evidence -> a status, never a guess: a cell without an ESTIMATED status carries no range."""
    if claim.get("claim_type") == "CELL_ESTIMATE" and claim.get("estimate_status") != "ESTIMATED" and claim.get("estimate"):
        return [f"{where}: {claim.get('estimate_status')} cell carries a range"]
    return []


def text_guards(where, texts, citations, cf, corpus, masked_lines):
    """Quote, entity and injection guards over the free text of one output item."""
    return (quote_guard(where, texts, citations, corpus) + entity_guard(where, texts, cf, corpus, citations)
            + injection_guard(where, texts, masked_lines))
