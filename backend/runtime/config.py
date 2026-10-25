"""Runtime configuration: the section 17 config block, loaded from one JSON file.

Every TUNABLE, UNVERIFIED value lives in `config/runtime_config.json` (stdlib has
no YAML parser, so the spec's YAML block is mirrored as JSON). The briefing
reserve and the Heimdall/Thor/Loki minimum are derived here from the per-role
token caps and the configured prices (SYSTEM_ARCHITECTURE 17, Budget stop rules);
they are never set by hand.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "config" / "runtime_config.json"

ROLE_MODEL_KEY = {"heimdall": "heimdall", "thor": "thor", "loki": "loki",
                  "odin_ruling": "odin", "odin_briefing": "odin"}
# Run 1 for Heimdall, Thor and Loki: Heimdall mapping + verifying, Thor rounds 1-2, Loki rounds 1-2.
HTL_RUN1_STEPS = 6


class ConfigError(ValueError):
    pass


class Config:
    def __init__(self, data, path=None):
        self.data = data
        self.path = path

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def model_for(self, role):
        if role not in ROLE_MODEL_KEY:
            raise ConfigError(f"unknown role {role!r}")
        return self.data["models"][ROLE_MODEL_KEY[role]]

    def caps(self, role):
        return self.data["token_caps_by_role"][role]

    def price(self, model):
        p = self.data["prices_usd_per_million_tokens"].get(model)
        if p is None:
            raise ConfigError(f"no configured price for model {model!r}")
        return p["input"] / 1e6, p["output"] / 1e6

    def call_cost(self, role, input_tokens, output_tokens):
        pin, pout = self.price(self.model_for(role))
        return input_tokens * pin + output_tokens * pout

    def worst_case(self, role, input_tokens=None):
        """Worst case of one call: input (actual, else the role's input cap) + the role's output cap."""
        caps = self.caps(role)
        tokens_in = caps["max_input_tokens"] if input_tokens is None else input_tokens
        return self.call_cost(role, tokens_in, caps["max_output_tokens"])

    @property
    def odin_briefing_reserve_usd(self):
        return self.worst_case("odin_ruling") + self.worst_case("odin_briefing")

    @property
    def htl_minimum_usd(self):
        worst = max(self.worst_case(r) for r in ("heimdall", "thor", "loki"))
        return HTL_RUN1_STEPS * self.data["max_model_turns_per_agent_step"] * worst

    def check_live_case(self):
        """Startup check for a case that will call a billable provider."""
        reserve, minimum, cap = self.odin_briefing_reserve_usd, self.htl_minimum_usd, self.data["per_case_cap_usd"]
        if reserve > cap - minimum:
            raise ConfigError(f"BUDGET_CONFIG_INVALID: reserve {reserve:.4f} > per_case_cap {cap:.4f} - htl_minimum {minimum:.4f}")
        return {"odin_briefing_reserve_usd": reserve, "htl_minimum_usd": minimum, "per_case_cap_usd": cap}

    def live_enabled(self):
        live = self.data.get("live") or {}
        return live.get("enabled") is True and bool(str(live.get("budget_owner") or "").strip())


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path=None, overrides=None):
    path = Path(path) if path else DEFAULT_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if "odin_briefing_reserve_usd" in data:
        raise ConfigError("odin_briefing_reserve_usd is derived; remove it from the config file")
    if overrides:
        data = _merge(copy.deepcopy(data), overrides)
    for role in ROLE_MODEL_KEY:
        if role not in data["token_caps_by_role"]:
            raise ConfigError(f"token_caps_by_role is missing {role!r}")
    return Config(data, path)
