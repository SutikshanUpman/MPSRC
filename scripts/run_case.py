"""Run a whole case: Heimdall, Round 1, Round 2 (cross-examination), Odin's rulings, the send-back and Run 2,
Odin again, and the briefing. Everything is written to data/runs/<case_id>/ (see backend/runtime/orchestrator.py).

    python scripts/run_case.py --pack dev_pack_E5 --question "..."            mock provider, $0
    python scripts/run_case.py --demo                                         E5 sample question, mock, two cases
    python scripts/run_case.py --provider replay --from <case_id>             re-run a recorded case at $0
    python scripts/run_case.py --provider anthropic --pack ... --question ... live: the budget owner only, once
                                                                              (needs LIVE=1, BUDGET_OWNER, ANTHROPIC_API_KEY)

Private memory persists in --memory-dir across cases (one folder per agent).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.llm.provider import ProviderError, make_provider  # noqa: E402
from backend.runtime.orchestrator import run_full_case  # noqa: E402
from backend.runtime.config import ConfigError, load_config  # noqa: E402
from backend.runtime import ledger  # noqa: E402

DEMO_PACK = ROOT / "dev_pack_E5"


def sample_question(pack):
    lines = (Path(pack) / "sample_question.txt").read_text(encoding="utf-8").splitlines()
    return next(l for l in lines if l.strip() and not l.startswith("QUESTION"))


def summarise(res):
    cf, rec, b = res["case_file"], res["record"], res["briefing"]
    print(f"{cf['status']} event={cf['event_id']} as_of={cf['as_of_date']} provider={rec['provider']}")
    for c in res["cells"]:
        o = c["odin"]
        rng = f"{o['low']}..{o['high']} %" if o else f"{c['status']} ({c['reason']})"
        print(f"  Odin {c['country']}/{c['sector']}: {rng}")
    if rec["rulings"]["total"]:
        print(f"  rulings: {rec['rulings']['decisions']} {rec['rulings']['classes']}  mode={rec['ruling_mode']}")
        print(f"  AC: {rec['ac']}")
    if b:
        print(f"  briefing: {rec['briefing_completion']} hash={str(rec['briefing_hash'])[:12]}")
    print(f"  spend: case ${rec['spend']['case_spent_usd']:.4f} (shadow ${rec['spend']['shadow_spent_usd']:.4f}), "
          f"{rec['spend']['model_calls']} model calls")
    print(f"wrote {res['out_dir']}")


def run_demo(config, out_root, args):
    memory = ROOT / "data" / "memory_demo"
    if memory.exists():
        shutil.rmtree(memory)
    question = sample_question(DEMO_PACK)
    provider = make_provider("mock", config)
    first = run_full_case(question, [DEMO_PACK], config, provider, out_root, memory, out_name="demo_E5")
    summarise(first)
    provider = make_provider("mock", config)
    second = run_full_case(question, [DEMO_PACK], config, provider, out_root, memory, out_name="demo_E5_memory")
    print("--- second case, same private memory")
    summarise(second)
    return 0


def run_replay(config_path, out_root, case_id):
    src = Path(out_root) / case_id
    record = json.loads((src / "run_record.json").read_text(encoding="utf-8"))
    config = load_config(src / "config.json")
    provider = make_provider("replay", config, path=src / "llm_calls.jsonl")
    memory = ROOT / "data" / "memory_replay"
    if memory.exists():
        shutil.rmtree(memory)
    if (src / "memory_before").exists():                      # start from the memory the original case started from
        shutil.copytree(src / "memory_before", memory)
    res = run_full_case(record["question"], record["pack_paths"], config, provider, out_root, memory, case_id=record["case_id"],
                        created_at=record["created_at"], out_name=f"{case_id}__replay")
    summarise(res)
    same = res["record"]["briefing_hash"] == record["briefing_hash"]
    print(f"replay briefing hash {'MATCHES' if same else 'DIFFERS FROM'} the original ({record['briefing_hash']})")
    return 0 if same else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack", help="live (or only) pack directory")
    ap.add_argument("--base", help="base reference pack, listed first in pack_paths")
    ap.add_argument("--question")
    ap.add_argument("--provider", default="mock", choices=["mock", "replay", "anthropic"])
    ap.add_argument("--from", dest="from_case", help="replay: the recorded case_id under --out")
    ap.add_argument("--config", help="runtime config JSON (default config/runtime_config.json)")
    ap.add_argument("--out", default=str(ROOT / "data" / "runs"))
    ap.add_argument("--memory-dir", default=str(ROOT / "data" / "memory"))
    ap.add_argument("--demo", action="store_true", help="E5 sample question, mock provider, writes data/runs/demo_E5/")
    ap.add_argument("--final-round", action="store_true", help="live only: raise the ledger ceiling to the project cap")
    ap.add_argument("--heimdall-only", action="store_true", help="stop after the Case File is opened")
    ap.add_argument("--round1-only", action="store_true", help="stop after Round 1")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    if args.demo:
        return run_demo(config, args.out, args)
    if args.provider == "replay":
        if not args.from_case:
            ap.error("--provider replay needs --from <case_id>")
        return run_replay(args.config, args.out, args.from_case)
    if not args.pack or not args.question:
        ap.error("--pack and --question are required")
    try:
        provider = make_provider(args.provider, config)       # AnthropicProvider refuses unless LIVE=1, BUDGET_OWNER, prices verified
    except ProviderError as e:
        print(f"REFUSED: {e}")
        return 2
    pack_paths = [args.base, args.pack] if args.base else [args.pack]
    stop = "heimdall" if args.heimdall_only else "round1" if args.round1_only else None
    try:
        res = run_full_case(args.question, pack_paths, config, provider, args.out, args.memory_dir,
                            final_round=args.final_round, stop_after=stop)
    except ledger.LedgerRefused as e:
        print(f"REFUSED: {e}")
        return 2
    summarise(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
