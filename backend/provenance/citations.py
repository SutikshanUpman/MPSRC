"""Citation spans: `[DOC_ID, P#, timestamp]` is the only format (SYSTEM_ARCHITECTURE 20).

Closed decision OD-1: a table ID or row number never goes inside the bracket, so
a locator that is not `P<n>` is invalid. A table row is cited by the paragraph
that holds it; the sentence names the row in words (table ID and row number),
and the row stays traceable through `row_refs` (doc_id, table_id,
native_row_number) for the click-through.
"""
import re

CITATION_RE = re.compile(r"\[\s*([A-Z][A-Z0-9]*-\d+)\s*,\s*([^,\]]+?)\s*,\s*(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?\s*\]")
LOCATOR_RE = re.compile(r"^P(\d+)$")


def format_citation(doc_id, paragraph, pub_date, pub_time=None):
    if not LOCATOR_RE.match(paragraph or ""):
        raise ValueError(f"citation locator must be P<n>, got {paragraph!r}")
    ts = f"{pub_date} {pub_time}" if pub_time else pub_date
    return f"[{doc_id}, {paragraph}, {ts}]"


def parse_citations(text):
    return [{"doc_id": m.group(1), "paragraph": m.group(2), "date": m.group(3), "time": m.group(4),
             "raw": m.group(0)} for m in CITATION_RE.finditer(text)]


def validate_citation(c, corpus, as_of):
    """Return a list of problems; empty means the citation resolves."""
    problems = []
    if not LOCATOR_RE.match(c["paragraph"]):
        problems.append("LOCATOR_NOT_PARAGRAPH")
    rec = corpus.records.get(c["doc_id"])
    if rec is None:
        return problems + ["DOC_NOT_IN_MANIFEST"]
    if c["paragraph"] not in {p["id"] for p in rec["paragraphs"]}:
        problems.append("PARAGRAPH_NOT_FOUND")
    if c["date"] != rec["pub_date"] or (c["time"] and c["time"] != rec["pub_time"]):
        problems.append("TIMESTAMP_MISMATCH")
    if rec["pub_date"] and rec["pub_date"] > as_of:
        problems.append("POST_AS_OF")
    return problems
