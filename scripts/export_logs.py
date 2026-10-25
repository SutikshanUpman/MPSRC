"""Copy one finished case to logs/case_<id>/ for the submission (committed; data/ stays ignored).

    python scripts/export_logs.py <case_id> [--from data/runs] [--to logs]

Copies the Case File, ledgers, rulings, briefing, trap report, events, run record and llm_calls.jsonl. Source text is cut to
doc_id + P# + a short quoted span (<= 300 characters): the Case File's evidence-packet hits, the calc inputs and any other
field named `text` or `raw_text` are shortened, and no document is copied whole. No key, no .env, nothing outside the case.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAX_SPAN = 300
FILES = ["case_file.json", "claim_ledger.json", "calc_ledger.json", "cross_examination.json", "rulings.json", "briefing.json",
         "briefing.md", "trap_report.json", "run_record.json", "events.jsonl", "search_log.jsonl", "provider_calls.jsonl",
         "llm_calls.jsonl", "config.json"]
TEXT_FIELDS = {"text", "raw_text", "paragraph_text", "body"}
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}|api[_-]?key\"?\s*[:=]\s*\"?[A-Za-z0-9_\-]{16,}", re.I)


def shorten(obj):
    if isinstance(obj, dict):
        return {k: (v[:MAX_SPAN] + ("…" if len(v) > MAX_SPAN else "") if k in TEXT_FIELDS and isinstance(v, str) else shorten(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [shorten(x) for x in obj]
    return obj


def clip_llm_record(rec):
    """llm_calls.jsonl keeps the parsed output and usage; the raw response text is cut like any other span."""
    rec = shorten(rec)
    if isinstance(rec.get("raw_response"), str) and len(rec["raw_response"]) > 4000:
        rec["raw_response"] = rec["raw_response"][:4000] + "…"
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("case")
    ap.add_argument("--from", dest="src", default=str(ROOT / "data" / "runs"))
    ap.add_argument("--to", default=str(ROOT / "logs"))
    args = ap.parse_args(argv)
    src = Path(args.src) / args.case
    if not (src / "run_record.json").exists():
        print(f"no finished case at {src}")
        return 2
    record = json.loads((src / "run_record.json").read_text(encoding="utf-8"))
    dst = Path(args.to) / f"case_{record['case_id'].removeprefix('case-')}"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    copied = []
    for name in FILES:
        f = src / name
        if not f.exists():
            continue
        if name.endswith(".json"):
            text = json.dumps(shorten(json.loads(f.read_text(encoding="utf-8"))), ensure_ascii=False, indent=1) + "\n"
        elif name == "llm_calls.jsonl":
            text = "".join(json.dumps(clip_llm_record(json.loads(l)), ensure_ascii=False, sort_keys=True) + "\n"
                           for l in f.read_text(encoding="utf-8").splitlines() if l.strip())
        else:
            text = f.read_text(encoding="utf-8")
        for variant in {str(ROOT), ROOT.as_posix(), str(ROOT).replace("\\", "\\\\")}:
            text = text.replace(variant, "<repo>")                # no local paths in committed logs
        if SECRET.search(text):
            print(f"REFUSED: {name} contains something that looks like a key; nothing was copied")
            shutil.rmtree(dst)
            return 3
        (dst / name).write_text(text, encoding="utf-8", newline="\n")
        copied.append(name)
    runs = record["runs"]
    (dst / "README.md").write_text(
        f"# Case {record['case_id']}\n\nProvider: {record['provider']}. Runs: {len(runs)} "
        f"({'two-run case: Odin sent the case back once' if len(runs) > 1 else 'single run'}). "
        f"Briefing hash: `{record['briefing_hash']}`.\n\nFiles: {', '.join(copied)}.\n\n"
        f"Source text in these files is shortened to at most {MAX_SPAN} characters per span; documents are not copied.\n"
        f"Replay at $0: `python scripts/run_case.py --provider replay --from {args.case}` (needs data/runs/{args.case}).\n",
        encoding="utf-8", newline="\n")
    print(f"wrote {dst} ({len(copied)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
