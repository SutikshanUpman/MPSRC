"""Run a whole case: Heimdall, Round 1, Round 2 (cross-examination), Odin's rulings, the send-back and Run 2, Odin again,
and the briefing. Everything is written to data/runs/<case_id>/ (see backend/runtime/orchestrator.py).

    python scripts/run_case.py --provider ollama    --model qwen2.5:14b --pack dev_pack_E5 --question "..."     local, free
    python scripts/run_case.py --provider anthropic ...                          Claude (ANTHROPIC_API_KEY)
    python scripts/run_case.py --provider replay --from <case_id>                re-run a recorded case at $0

Claude costs money: it needs LIVE=1, BUDGET_OWNER and "prices_verified": true in the runtime config
(see scripts/live_check.py). Ollama is free. Private memory persists in
--memory-dir across cases.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.llm.factory import SpecError, build_provider  # noqa: E402
from backend.llm.provider import ProviderError, ReplayProvider  # noqa: E402
from backend.runtime.orchestrator import run_full_case  # noqa: E402
from backend.runtime.config import ConfigError, load_config  # noqa: E402
from backend.runtime import ledger  # noqa: E402


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


def run_replay(config_path, out_root, case_id):
    src = Path(out_root) / case_id
    record = json.loads((src / "run_record.json").read_text(encoding="utf-8"))
    config = load_config(src / "config.json")
    provider = ReplayProvider(config, src / "llm_calls.jsonl")
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


PROVIDER_FACTORY = build_provider          # tests swap in an offline stand-in


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack", help="live (or only) pack directory")
    ap.add_argument("--base", help="base reference pack, listed first in pack_paths")
    ap.add_argument("--question")
    ap.add_argument("--provider", default="ollama", choices=["ollama", "anthropic", "replay"])
    ap.add_argument("--model", help="model for Heimdall, Thor and Loki (required for ollama; default for anthropic: the configured split)")
    ap.add_argument("--odin-model", help="model for Odin (default: --model)")
    ap.add_argument("--base-url", help="a loopback Ollama address; a remote one comes from OLLAMA_HOST")
    ap.add_argument("--from", dest="from_case", help="replay: the recorded case_id under --out")
    ap.add_argument("--config", help="runtime config JSON (default config/runtime_config.json)")
    ap.add_argument("--out", default=str(ROOT / "data" / "runs"))
    ap.add_argument("--memory-dir", default=str(ROOT / "data" / "memory"))
    ap.add_argument("--final-round", action="store_true", help="live only: raise the ledger ceiling to the project cap")
    ap.add_argument("--heimdall-only", action="store_true", help="stop after the Case File is opened")
    ap.add_argument("--round1-only", action="store_true", help="stop after Round 1")
    args = ap.parse_args(argv)

    if args.provider == "replay":
        if not args.from_case:
            ap.error("--provider replay needs --from <case_id>")
        return run_replay(args.config, args.out, args.from_case)
    if not args.pack or not args.question:
        ap.error("--pack and --question are required")
    try:
        provider, config = PROVIDER_FACTORY({"provider": args.provider, "model": args.model, "odin_model": args.odin_model,
                                           "base_url": args.base_url}, args.config)
    except (ProviderError, SpecError, ConfigError) as e:         # billable providers refuse unless LIVE=1, BUDGET_OWNER, prices verified
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
