"""Manifest loading and normalisation (SYSTEM_ARCHITECTURE 14.2, review F17).

Live packs may use either schema seen in dev_pack_E5:
- ATL/WLD style: upper-case keys, string RELIABILITY, FORMAT and LANGUAGE present.
- ORV style: upper-case keys plus lower-case duplicates, integer RELIABILITY, no FORMAT.
Upper-case keys win; a lower-case duplicate that disagrees is a METADATA_CONFLICT.
"""
import hashlib
import json
import re
from pathlib import Path

FIELDS = ["DOC_ID", "EVENT_ID", "TITLE", "SOURCE_NAME", "SOURCE_TYPE", "RELIABILITY",
          "PUB_DATE", "PUB_TIME", "COUNTRY", "SECTOR", "LANGUAGE", "FORMAT", "FILE"]
FORMATS = {".txt": "TXT", ".pdf": "PDF", ".docx": "DOCX"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _coerce_reliability(v):
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def normalise_entry(raw):
    """Return (entry, conflicts). Entry keys are upper-case FIELDS plus any extras."""
    entry, conflicts = {}, []
    lower = {}
    for k, v in raw.items():
        if k.isupper():
            entry[k] = v
        else:
            lower[k.upper()] = v
    for k, v in lower.items():
        if k not in entry:
            entry[k] = v
        elif str(entry[k]).strip() != str(v).strip():
            conflicts.append({"field": k, "upper": entry[k], "lower": v, "source": "manifest duplicate keys"})
    rel_raw = entry.get("RELIABILITY")
    entry["RELIABILITY"] = _coerce_reliability(rel_raw)
    if rel_raw not in (None, "") and entry["RELIABILITY"] is None:
        conflicts.append({"field": "RELIABILITY", "upper": rel_raw, "lower": None, "source": "not an integer"})
    file_name = entry.get("FILE")
    inferred = FORMATS.get(Path(file_name).suffix.lower()) if file_name else None
    if entry.get("FORMAT") and inferred and str(entry["FORMAT"]).upper() != inferred:
        conflicts.append({"field": "FORMAT", "upper": entry["FORMAT"], "lower": inferred, "source": "file extension"})
    entry["FORMAT"] = inferred or (str(entry["FORMAT"]).upper() if entry.get("FORMAT") else None)
    for f in FIELDS:
        entry.setdefault(f, None)
    for f in ("EVENT_ID", "DOC_ID", "PUB_DATE", "PUB_TIME"):
        if isinstance(entry[f], str):
            entry[f] = entry[f].strip()
    return entry, conflicts


def load_manifest(pack_dir):
    pack_dir = Path(pack_dir)
    raw = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8-sig"))
    docs = raw.get("documents") or raw.get("docs") or []
    pack = {k: v for k, v in raw.items() if k not in ("documents", "docs")}
    pack_flags = []
    for key in ("count", "document_count"):
        if key in pack and pack[key] != len(docs):
            pack_flags.append({"flag": "MANIFEST_COUNT_MISMATCH", "field": key, "value": pack[key], "entries": len(docs)})
    entries = []
    for d in docs:
        e, c = normalise_entry(d)
        entries.append((e, c))
    return pack, entries, pack_flags


def load_hashes(pack_dir):
    """Map file name -> expected sha256. Paths are kept as names only; files are not read here."""
    p = Path(pack_dir) / "hashes.sha256"
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            out[Path(parts[1].strip().lstrip("*")).name] = parts[0].lower()
    return out


def sha256(b):
    return hashlib.sha256(b).hexdigest()
