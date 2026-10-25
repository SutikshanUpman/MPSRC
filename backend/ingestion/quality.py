"""Source-quality checks: instruction-like text and truncation.

Masking is line-level and pattern-based (SYSTEM_ARCHITECTURE 26, review F40):
the agent-visible copy replaces a matching line with a placeholder, and the raw
text is kept in the record for audit. No document ID is special-cased.
"""
import re

MASK_PLACEHOLDER = "[MASKED: instruction-like text removed for agents; raw text kept for audit]"

INJECTION_PATTERNS = [
    # A line that speaks as a chat role: "ASSISTANT: ...", "System - ...".
    r"^\W*(assistant|system|user|human|developer|ai|instructions?)\s*[:>\-]\s*\S",
    r"\bignore\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|other)?\s*(instructions?|rules|prompts?|guidance)\b",
    r"\bdisregard\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier)?\s*(instructions?|rules|prompts?|evidence|guidance)\b",
    r"\byou\s+are\s+now\b",
    r"\bnew\s+instructions?\b",
    r"</?\s*(system|instructions?|prompt)\s*>",
    r"\b(approve|accept|reject)\s+(all|every)\s+(claims?|evidence|documents?)\b",
    r"\bskip\s+(the\s+)?(cross[\s-]*examination|verification|review|checks?)\b",
    r"\b(do\s+not|don't)\s+(cite|challenge|verify|check)\b",
    r"\b(as\s+an?\s+)?(ai|language)\s+model\b",
    r"\b(heimdall|thor|loki|odin|the\s+judge)\s+(must|should|shall)\b",
]
_INJECTION = [re.compile(p, re.I) for p in INJECTION_PATTERNS]

TERMINAL = tuple('.!?"\')]:;”’…')


def is_instruction_like(line):
    return any(p.search(line) for p in _INJECTION)


def mask_text(text):
    """Return (masked_text, matched_raw_lines)."""
    out, hits = [], []
    for line in text.split("\n"):
        if line.strip() and is_instruction_like(line):
            hits.append(line.strip())
            out.append(MASK_PLACEHOLDER)
        else:
            out.append(line)
    return "\n".join(out), hits


def ends_mid_sentence(text):
    t = text.rstrip()
    return bool(t) and not t.endswith(TERMINAL)
