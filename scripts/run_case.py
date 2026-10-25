"""Open a case with Heimdall, run Round 1 and Round 2 (cross-examination) for Thor and Loki, and write the results.

Usage: python scripts/run_case.py --pack <dir> [--base <dir>] --question "..." [--provider mock]
                                  [--out data/runs] [--memory-dir data/memory] [--heimdall-only | --round1-only]
Writes data/runs/<case_id>/: case_file.json, claim_ledger.json, calc_ledger.json, cross_examination.json,
search_log.jsonl, provider_calls.jsonl, events.jsonl. The mock provider is the default and the only one that runs today.
Private memory persists in --memory-dir across cases (one folder per agent).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agents.counsel import run_round1  # noqa: E402
from backend.agents.cross_exam import run_round2  # noqa: E402
from backend.agents.heimdall import open_case  # noqa: E402
from backend.casefile import model as casefile  # noqa: E402
from backend.llm.provider import make_provider  # noqa: E402
from backend.runtime.config import load_config  # noqa: E402


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack", required=True, help="live (or only) pack directory")
    ap.add_argument("--base", help="base reference pack, listed first in pack_paths")
    ap.add_argument("--question", required=True)
    ap.add_argument("--provider", default="mock", choices=["mock", "anthropic"])
    ap.add_argument("--config", help="runtime config JSON (default config/runtime_config.json)")
    ap.add_argument("--out", default=str(ROOT / "data" / "runs"))
    ap.add_argument("--memory-dir", default=str(ROOT / "data" / "memory"))
    ap.add_argument("--heimdall-only", action="store_true", help="stop after the Case File is opened")
    ap.add_argument("--round1-only", action="store_true", help="stop after Round 1")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    provider = make_provider(args.provider, config)   # AnthropicProvider raises unless live is enabled
    pack_paths = [args.base, args.pack] if args.base else [args.pack]
    cf, trace, guard = open_case(args.question, pack_paths, config, provider)
    sides = {}
    if cf["status"] == "OPEN" and not args.heimdall_only:
        sides = run_round1(cf, provider, config, trace, memory_root=args.memory_dir, guard=guard)
        if not args.round1_only:
            run_round2(cf, sides, provider, config, trace, guard)
    out = Path(args.out) / cf["case_id"]
    casefile.write(cf, out / "case_file.json")
    _write_json(out / "claim_ledger.json", cf["claim_ledger"])
    _write_json(out / "calc_ledger.json", cf["calc_ledger"])
    _write_json(out / "cross_examination.json", cf["cross_examination"])
    _write_jsonl(out / "search_log.jsonl", [e for a in ("thor", "loki") if a in sides for e in sides[a].tools.search_log])
    _write_jsonl(out / "provider_calls.jsonl", getattr(provider, "calls", []))
    trace.write_jsonl(out / "events.jsonl")
    cells = ", ".join(f"{c['country']}/{c['sector']}={c['status']}" for c in cf["coverage"]) or "-"
    print(f"{cf['status']} event={cf['event_id']} as_of={cf['as_of_date']} cells: {cells}")
    for c in cf["claim_ledger"]:
        if c["claim_type"] == "CELL_ESTIMATE" and c["status"] != "superseded":
            est = c["estimate"]
            rng = f"{est['low']}..{est['high']} %" if est else c["estimate_status"]
            print(f"  {c['agent']:<4} {c['country']}/{c['sector']}: {rng}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
