"""Persistent project ledger (FINAL BUILD 3.3): data/ledger.json, cumulative spend across all runs.

One $4 key pays for everything. During development the ceiling is project_cap_usd - final_round_reserve_usd
(1.50); `--final-round` raises it to project_cap_usd (4.00). A live run is refused when the cumulative spend plus
the projected worst case of one case would pass the ceiling. Mock and replay runs cost nothing and are logged at 0.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "ledger.json"


class LedgerRefused(RuntimeError):
    pass


def load(path=DEFAULT_PATH):
    p = Path(path)
    if not p.exists():
        return {"total_spent_usd": 0.0, "runs": []}
    return json.loads(p.read_text(encoding="utf-8"))


def ceiling(config, final_round=False):
    cap = config["project_cap_usd"]
    return cap if final_round else cap - config["final_round_reserve_usd"]


def projected_worst_case(config):
    """One case never spends more than the per-case cap (the guard enforces it per call)."""
    return config["per_case_cap_usd"]


def check_live_allowed(config, ledger, final_round=False):
    total, worst, limit = ledger["total_spent_usd"], projected_worst_case(config), ceiling(config, final_round)
    if total + worst > limit + 1e-12:
        raise LedgerRefused(f"LEDGER_REFUSED: spent {total:.4f} + worst case of one case {worst:.4f} > ceiling {limit:.2f}"
                            + ("" if final_round else " (development; --final-round raises it to the project cap)"))
    return {"total_spent_usd": total, "worst_case_usd": worst, "ceiling_usd": limit}


def record(case_id, provider, spent_usd, mode, path=DEFAULT_PATH):
    ledger = load(path)
    ledger["runs"].append({"case_id": case_id, "provider": provider, "spent_usd": round(spent_usd, 6), "mode": mode,
                           "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    ledger["total_spent_usd"] = round(sum(r["spent_usd"] for r in ledger["runs"]), 6)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8", newline="\n")
    return ledger
