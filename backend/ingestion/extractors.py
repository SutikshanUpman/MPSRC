"""Text extraction for PDF, DOCX and TXT, stdlib only (SYSTEM_ARCHITECTURE 14.3).

The PDF content-stream parser is adapted from tools/extract.py: it walks BT/ET
text blocks and reads Tj/TJ strings. It is enough for text PDFs written with a
simple font encoding; an image-only PDF is reported as OCR_REQUIRED.
"""
import re
import zipfile
import zlib
from io import BytesIO
from xml.etree import ElementTree

from .encoding import decode_txt

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class Extraction:
    def __init__(self, text, decoder_sections=None, flags=None, recoded=False, pages=None):
        self.text = text
        self.decoder_sections = decoder_sections or []
        self.flags = flags or []
        self.recoded = recoded
        self.pages = pages or []


# ---------- PDF ----------

def _unescape(b):
    b = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 255]), b)
    out, i = bytearray(), 0
    simple = {ord("n"): b"\n", ord("r"): b"", ord("t"): b"\t", ord("b"): b"", ord("f"): b"",
              ord("("): b"(", ord(")"): b")", ord("\\"): b"\\"}
    while i < len(b):
        c = b[i]
        if c == 0x5C and i + 1 < len(b):
            nxt = b[i + 1]
            if nxt in simple:
                out += simple[nxt]
                i += 2
                continue
            if nxt in b"\r\n":  # line continuation
                i += 2
                continue
        out.append(c)
        i += 1
    return bytes(out)


def _hex(b):
    h = re.sub(rb"\s", b"", b)
    if len(h) % 2:
        h += b"0"
    return bytes.fromhex(h.decode("ascii"))


_TOKEN = re.compile(rb"\((?:\\.|[^\\)])*\)\s*(?:Tj|')|<[0-9A-Fa-f\s]*>\s*Tj|\[(.*?)\]\s*TJ|T\*|-?[\d.]+\s+-?[\d.]+\s+T[dD]", re.S)
_STR = re.compile(rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>")


def _string(tok):
    return _unescape(tok[1:-1]) if tok.startswith(b"(") else _hex(tok[1:-1])


def _stream_text(s):
    lines = []
    for bt in re.finditer(rb"BT(.*?)ET", s, re.S):
        parts = []
        for m in _TOKEN.finditer(bt.group(1)):
            t = m.group(0)
            if t.endswith(b"TJ"):
                parts.append(b"".join(_string(x) for x in _STR.findall(m.group(1))))
            elif t.endswith(b"Tj") or t.endswith(b"'"):
                parts.append(_string(_STR.match(t).group(0)))
                if t.endswith(b"'"):
                    parts.append(b"\n")
            else:
                parts.append(b"\n")
        lines.append(b"".join(parts))
    return b"\n".join(lines)


def _inflate(raw, dict_bytes):
    if b"FlateDecode" in dict_bytes:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(raw)
            except zlib.error:
                return None
    return raw


def pdf_extract(data):
    if not data.startswith(b"%PDF"):
        return Extraction("", flags=["UNREADABLE_FILE"])
    objs = {}
    for m in re.finditer(rb"(\d+)\s+0\s+obj(.*?)endobj", data, re.S):
        objs[int(m.group(1))] = m.group(2)
    streams = {}
    for num, body in objs.items():
        sm = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.S)
        if sm:
            streams[num] = _inflate(sm.group(1), body[:sm.start()])
    # Page order: follow /Kids from the Pages tree; fall back to file order.
    page_streams = []
    for num, body in objs.items():
        if re.search(rb"/Type\s*/Page(?![s\w])", body):
            refs = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+0\s+R)", body)
            ids = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", refs.group(1))] if refs else []
            page_streams.append((num, ids))
    kids_order = []
    for body in objs.values():
        if re.search(rb"/Type\s*/Pages", body):
            km = re.search(rb"/Kids\s*\[([^\]]*)\]", body)
            if km:
                kids_order += [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", km.group(1))]
    order = {n: i for i, n in enumerate(kids_order)}
    page_streams.sort(key=lambda p: order.get(p[0], len(order) + p[0]))
    flags, pages = [], []
    if page_streams:
        for i, (_, ids) in enumerate(page_streams, 1):
            chunks = [_stream_text(streams[s]) for s in ids if streams.get(s)]
            pages.append({"page": i, "text": b"\n".join(chunks).decode("cp1252", "replace")})
    else:
        texts = [_stream_text(s) for s in streams.values() if s and b"BT" in s]
        pages = [{"page": None, "text": b"\n".join(texts).decode("cp1252", "replace")}]
    if any(s is None for s in streams.values()):
        flags.append("MALFORMED_ENCODING")
    text = "\n".join(p["text"] for p in pages)
    if not text.strip() and (b"/Image" in data or b"/XObject" in data):
        flags.append("OCR_REQUIRED")
    return Extraction(text, [{"part": "whole", "decoder": "pdf-content-stream/cp1252"}], flags, pages=pages)


# ---------- DOCX ----------

def _para_text(p):
    out = []
    for el in p.iter():
        if el.tag == W + "t" and el.text:
            out.append(el.text)
        elif el.tag == W + "tab":
            out.append("\t")
        elif el.tag in (W + "br", W + "cr"):
            out.append("\n")
    return "".join(out)


def docx_extract(data):
    """Body paragraphs and tables in document order; tables become `a | b | c` lines."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError):
        return Extraction("", flags=["UNREADABLE_FILE"])
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        # Damaged XML: keep whatever w:t text can still be found.
        texts = re.findall(rb"<w:t[^>]*>([^<]*)</w:t>", xml)
        return Extraction(" ".join(t.decode("utf-8", "replace") for t in texts), flags=["XML_FALLBACK"])
    body = root.find(W + "body")
    blocks = []
    for child in list(body) if body is not None else []:
        if child.tag == W + "p":
            t = _para_text(child)
            if t.strip():
                blocks.append(t)
        elif child.tag == W + "tbl":
            rows = []
            for tr in child.iter(W + "tr"):
                cells = [" ".join(_para_text(p) for p in tc.iter(W + "p")).strip() for tc in tr.iter(W + "tc")]
                rows.append(" | ".join(cells))
            if rows:
                blocks.append("\n".join(rows))
    return Extraction("\n\n".join(blocks), [{"part": "whole", "decoder": "docx-xml"}])


# ---------- dispatch ----------

def extract(data, fmt):
    fmt = fmt.upper()
    if fmt == "PDF":
        return pdf_extract(data)
    if fmt == "DOCX":
        return docx_extract(data)
    text, sections, flags, recoded = decode_txt(data)
    return Extraction(text, sections, flags, recoded)
