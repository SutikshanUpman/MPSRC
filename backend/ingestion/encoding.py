"""Byte-level decoding for TXT documents (SYSTEM_ARCHITECTURE 14.3, review F18).

The metadata header and the body are decoded independently, because a file can
switch encoding at the `---` separator (ASCII header, UTF-16LE body with a BOM).
Every section records the decoder used and its byte range.
"""
import re

BOMS = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]
PLAIN_DECODERS = {"utf-8", "utf-8-sig", "ascii"}
SEPARATOR = re.compile(rb"(?m)^---[ \t]*\r?$")
NUL_SHARE_FOR_UTF16 = 0.20


def _nul_share(b):
    return b.count(0) / len(b) if b else 0.0


def _printable_ascii(s):
    return sum(1 for c in s if 32 <= ord(c) < 127 or c in "\n\r\t")


def _decode_utf16_guess(b):
    """No BOM but many NUL bytes: try both byte orders, keep the more readable one."""
    flags = []
    if len(b) % 2:
        b = b[:-1]
        flags.append("MALFORMED_ENCODING")
    best = None
    for enc in ("utf-16-le", "utf-16-be"):
        s = b.decode(enc, "replace")
        score = _printable_ascii(s)
        if best is None or score > best[2]:
            best = (s, enc, score)
    return best[0], best[1] + " (no BOM)", flags


def _find_inner_bom(b):
    """A UTF-16 BOM inside a section, followed by NUL-heavy bytes, starts a new encoding."""
    for bom, enc in BOMS[1:]:
        i = b.find(bom, 1)
        while i > 0:
            if _nul_share(b[i + 2:i + 66]) >= 0.3:
                return i, bom, enc
            i = b.find(bom, i + 1)
    return None


def decode_section(b, offset=0):
    """Decode one byte section. Returns (text, [section records], flags)."""
    if not b:
        return "", [], []
    inner = _find_inner_bom(b)
    if inner:
        i = inner[0]
        t1, s1, f1 = decode_section(b[:i], offset)
        t2, s2, f2 = decode_section(b[i:], offset + i)
        return t1 + t2, s1 + s2, f1 + f2
    for bom, enc in BOMS:
        if b.startswith(bom):
            body = b[len(bom):]
            flags = []
            if enc.startswith("utf-16") and len(body) % 2:
                body = body[:-1]
                flags.append("MALFORMED_ENCODING")
            text = body.decode(enc.replace("-sig", ""), "replace")
            rep = text.count("�")
            if rep:
                flags.append("MALFORMED_ENCODING")
            return text, [_sec(offset, len(b), enc + " (BOM)", rep)], flags
    if _nul_share(b) >= NUL_SHARE_FOR_UTF16:
        text, dec, flags = _decode_utf16_guess(b)
        return text, [_sec(offset, len(b), dec, text.count("�"))], flags
    try:
        return b.decode("utf-8"), [_sec(offset, len(b), "utf-8", 0)], []
    except UnicodeDecodeError:
        pass
    try:
        text = b.decode("cp1252")
        return text, [_sec(offset, len(b), "cp1252", 0)], ["MALFORMED_ENCODING"]
    except UnicodeDecodeError:
        text = b.decode("utf-8", "replace")
        return text, [_sec(offset, len(b), "utf-8 (replace)", text.count("�"))], ["MALFORMED_ENCODING"]


def _sec(start, length, decoder, replacements):
    return {"start": start, "end": start + length, "decoder": decoder, "replacements": replacements}


def decode_txt(b):
    """Decode a TXT file. Returns (text, sections, flags, recoded)."""
    # A UTF-16 header hides the ASCII `---`, so a match means the header is byte-oriented.
    m = SEPARATOR.search(b)
    if m and (b.startswith((b"\xff\xfe", b"\xfe\xff")) or _nul_share(b[:m.start()]) >= NUL_SHARE_FOR_UTF16):
        m = None
    if m:
        head, sep, tail = b[:m.start()], b[m.start():m.end()], b[m.end():]
        t1, s1, f1 = decode_section(head, 0)
        t3, s3, f3 = decode_section(tail, m.end())
        for s in s1:
            s["part"] = "header"
        for s in s3:
            s["part"] = "body"
        text = t1 + sep.decode("ascii").rstrip("\r") + t3
        sections, flags = s1 + s3, f1 + f3
    else:
        text, sections, flags = decode_section(b, 0)
        for s in sections:
            s["part"] = "whole"
    recoded = any(s["decoder"] not in PLAIN_DECODERS or s["replacements"] for s in sections)
    return text.replace("\r\n", "\n").replace("\r", "\n"), sections, sorted(set(flags)), recoded
