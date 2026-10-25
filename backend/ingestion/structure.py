"""Metadata header and [Pn] paragraph structure.

Paragraph locators follow the citation contract `[DOC_ID, P#, timestamp]`.
A body without any `[Pn]` label (e.g. a PS fixed-layout trade table) gets
positional paragraphs flagged SYNTHETIC_PARAGRAPH: the interim rule of open
decision OD-1 in SYSTEM_ARCHITECTURE section 20.
"""
import re

HEADER_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*:\s*(.*?)\s*$")
SEPARATOR_LINE = re.compile(r"^\s*---\s*$")
LABEL = re.compile(r"\[P(\d+)\]")


def normalise_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def split_header(text):
    """Return (header dict, body text, separator_found).

    Header = leading `KEY: value` lines up to a `---` line. Without a separator,
    the header ends at the first line that is not `KEY: value`.
    """
    lines = text.split("\n")
    header, i = {}, 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    start = i
    while i < len(lines):
        line = lines[i]
        if SEPARATOR_LINE.match(line):
            return header, "\n".join(lines[i + 1:]), True
        m = HEADER_LINE.match(line)
        if m:
            header.setdefault(m.group(1), m.group(2))
        elif line.strip():
            break
        i += 1
    if not header:
        return {}, "\n".join(lines[start:]), False
    return header, "\n".join(lines[i:]), False


def split_paragraphs(body, title=""):
    """Return (preamble, paragraphs, flags).

    paragraphs: [{"id": "P3", "n": 3, "text": str, "synthetic": bool}]
    preamble: text before the first label (normally the repeated title).
    """
    flags = []
    labels = list(LABEL.finditer(body))
    if labels:
        preamble = body[:labels[0].start()].strip()
        paras = []
        for k, m in enumerate(labels):
            end = labels[k + 1].start() if k + 1 < len(labels) else len(body)
            n = int(m.group(1))
            paras.append({"id": f"P{n}", "n": n, "text": body[m.end():end].strip(), "synthetic": False})
        nums = [p["n"] for p in paras]
        if nums != list(range(1, len(nums) + 1)):
            flags.append("PARAGRAPH_SEQUENCE_ANOMALY")
        return preamble, paras, flags
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    preamble = ""
    if blocks and title and normalise_ws(blocks[0]).lower() == normalise_ws(title).lower():
        preamble = blocks.pop(0)
    paras = [{"id": f"P{i}", "n": i, "text": b, "synthetic": True} for i, b in enumerate(blocks, 1)]
    if paras:
        flags.append("SYNTHETIC_PARAGRAPH")
    return preamble, paras, flags
