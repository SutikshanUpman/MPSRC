"""Dry run for the budget owner, BEFORE a metered case (Anthropic, or a remote OpenAI-compatible API). It makes NO model call
and reads no key: it prints what such a run would do, and which providers this machine can use. (Ollama and a localhost
OpenAI-compatible server are free and need no check.)

    python scripts/live_check.py [--final-round] [--config config/runtime_config.json]

Exit 0 when a live run would be allowed, 1 when something blocks it (the reasons are printed).
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.llm.factory import provider_status  # noqa: E402
from backend.runtime import ledger  # noqa: E402
from backend.runtime.config import ConfigError, load_config  # noqa: E402
from backend.runtime.orchestrator import input_hashes  # noqa: E402

ROLES = ("heimdall", "thor", "loki", "odin_ruling", "odin_briefing")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config")
    ap.add_argument("--final-round", action="store_true")
    args = ap.parse_args(argv)
    config = load_config(args.config)
    blockers = []

    print("== planned models and caps (per call) ==")
    print(f"{'role':<15}{'model':<22}{'max in':>8}{'max out':>9}{'$ in/M':>8}{'$ out/M':>9}{'worst call $':>14}")
    for role in ROLES:
        model, caps = config.model_for(role), config.caps(role)
        try:
            pin, pout = config.price(model)
            worst = f"{config.worst_case(role):.4f}"
        except ConfigError as e:
            pin = pout = 0.0
            worst = "NO PRICE"
            blockers.append(str(e))
        print(f"{role:<15}{model:<22}{caps['max_input_tokens']:>8}{caps['max_output_tokens']:>9}{pin * 1e6:>8.2f}{pout * 1e6:>9.2f}{worst:>14}")

    print("\n== worst case of one case ==")
    try:
        info = config.check_live_case()
        print(f"Odin briefing reserve  ${info['odin_briefing_reserve_usd']:.4f}  (Odin ruling + briefing worst cases; spendable by Odin only)")
        print(f"Heimdall/Thor/Loki min ${info['htl_minimum_usd']:.4f}  ({config['max_model_turns_per_agent_step']} turns x 6 Run-1 steps at the worst role)")
        print(f"Per-case cap           ${info['per_case_cap_usd']:.2f}  (enforced per call by the budget guard)")
    except ConfigError as e:
        blockers.append(str(e))
        print(f"BLOCKED: {e}")
    print(f"Projected worst case charged to the ledger: ${ledger.projected_worst_case(config):.2f}")

    print("\n== project ledger ==")
    led = ledger.load()
    limit = ledger.ceiling(config, args.final_round)
    print(f"spent so far ${led['total_spent_usd']:.4f} over {len(led['runs'])} live run(s); "
          f"ceiling ${limit:.2f} ({'final round' if args.final_round else 'development: project cap minus the final-round reserve'})")
    try:
        ledger.check_live_allowed(config, led, args.final_round)
        print("ledger: a live run is allowed")
    except ledger.LedgerRefused as e:
        blockers.append(str(e))
        print(f"ledger: {e}")

    print("\n== gates the provider enforces ==")
    gates = [("LIVE=1", os.environ.get("LIVE") == "1"),
             ("BUDGET_OWNER set", bool((os.environ.get("BUDGET_OWNER") or "").strip())),
             ("ANTHROPIC_API_KEY set (value never read here)", bool(os.environ.get("ANTHROPIC_API_KEY"))),
             ("config prices_verified is true", config.get("prices_verified") is True)]
    for name, ok in gates:
        print(f"[{'x' if ok else ' '}] {name}")
        if not ok:
            blockers.append(f"missing: {name}")
    print("    (prices in config/runtime_config.json are UNVERIFIED until the budget owner checks them against the provider's price page,\n"
          "     fills them in and sets prices_verified to true)")

    print("\n== providers this server can use now ==")
    for p in provider_status():
        state = "ready" if p["configured"] else "not set up"
        print(f"[{'x' if p['configured'] else ' '}] {p['label']:<26} {state:<11} {'free' if p['free'] else 'metered'}"
              + (f"  models: {', '.join(p['models'][:6])}" if p["models"] else "") + (f"  ({p['hint']})" if p["hint"] else ""))

    print("\n== inputs a replay must find unchanged ==")
    hashes = input_hashes([ROOT / "dev_pack_E5"], config)
    print(f"config {hashes['config'][:16]}  prompts {len(hashes['prompts'])} files")
    print("\nNo call was made.")
    if blockers:
        print("\nBLOCKED:")
        for b in dict.fromkeys(blockers):
            print(f"  - {b}")
        return 1
    print("\nOK: a live run is allowed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
