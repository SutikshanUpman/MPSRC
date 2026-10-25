"""Ingest a pack and write normalised records as JSON (raw text included, for audit).

Usage: python scripts/ingest_pack.py <pack_dir> [out_dir]
Default out_dir: data/normalized/<pack name>. No network, no model calls.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.ingestion.pipeline import ingest_pack  # noqa: E402


def main():
    pack_dir = Path(sys.argv[1])
    corpus = ingest_pack(pack_dir)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "normalized" / (corpus.pack.get("pack") or pack_dir.name)
    out.mkdir(parents=True, exist_ok=True)
    for doc_id, rec in corpus.records.items():
        (out / f"{doc_id}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    summary = {
        "pack": corpus.pack, "pack_flags": corpus.pack_flags,
        "status": Counter(r["status"] for r in corpus.records.values()),
        "trade_rows": Counter(r["parse_status"] for r in corpus.trade_rows()),
        "documents": {d: {"status": r["status"], "flags": r["flags"], "family": r["evidence_family_id"]}
                      for d, r in corpus.records.items()},
    }
    (out / "_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"out": str(out), "status": summary["status"], "trade_rows": summary["trade_rows"]}))


if __name__ == "__main__":
    main()
