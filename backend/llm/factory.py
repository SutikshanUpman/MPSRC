"""Choosing the models for a run: provider + model(s) -> (provider, config).

A run's spec is `{provider, model?, odin_model?, base_url?}`:

    ollama      a local model through Ollama (free, no key): `model` is an installed model name, e.g. qwen2.5:14b
    anthropic   Claude: key ANTHROPIC_API_KEY; with no `model` the Haiku (agents) / Sonnet (Odin) split from the runtime config

`model` serves Heimdall, Thor and Loki; `odin_model` serves Odin (default: the same). Ollama is priced at $0. Claude is metered:
every model it uses needs a price in the config and the budget owner's switches (LIVE=1, BUDGET_OWNER, prices_verified); the
provider constructor enforces them. A base URL given by a client is honoured only when it is loopback, so a key the server
holds is never sent to an address a page chose.
"""
import re

from ..runtime.config import ConfigError, load_config
from .provider import AnthropicProvider, OllamaProvider, ProviderError, is_loopback

PROVIDERS = ("ollama", "anthropic")
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,99}$")
ROLES = ("heimdall", "thor", "loki")


class SpecError(ValueError):
    pass


def _check_model(name, what):
    if not isinstance(name, str) or not MODEL.match(name):
        raise SpecError(f"{what}: a model name of letters, digits and . _ : / @ + - is required")
    return name


def build_provider(spec, config_path=None):
    """Returns (provider, config). Raises SpecError for a bad request, LiveCallsDisabled when Claude's switches are off,
    ConfigError when a Claude model has no price."""
    name = (spec.get("provider") or "").lower()
    if name not in PROVIDERS:
        raise SpecError(f"provider must be one of {', '.join(PROVIDERS)}")
    base_url = spec.get("base_url") or None
    if base_url:
        if not re.match(r"^https?://[^\s]+$", base_url):
            raise SpecError("base_url must be an http(s) URL")
        if name == "anthropic":
            raise SpecError("the Anthropic provider has a fixed address")
        if not is_loopback(base_url):
            raise SpecError("a base URL from a client must be loopback (localhost); a remote Ollama is set in the server's "
                            "environment (OLLAMA_HOST)")
    base = load_config(config_path)
    model = _check_model(spec["model"], "model") if spec.get("model") else None
    odin = _check_model(spec["odin_model"], "odin_model") if spec.get("odin_model") else model
    if name == "ollama" and not model:
        raise SpecError("model is required (the name of an installed Ollama model)")
    models = {}
    if model:
        models = {r: model for r in ROLES}
        models["odin"] = odin
    elif odin:
        models = {"odin": odin}
    overrides = {"models": models} if models else {}
    if name == "ollama":
        overrides["prices_usd_per_million_tokens"] = {m: {"input": 0.0, "output": 0.0} for m in set(models.values())}
        # A local answer costs nothing, so Odin and the agents may write more before they are cut off (the input window is
        # ollama_num_ctx; 4,096 out + about 19,000 in fits the 24,576 default).
        caps = {r: dict(c, max_output_tokens=max(c["max_output_tokens"], 4096)) for r, c in base["token_caps_by_role"].items()}
        overrides["token_caps_by_role"] = caps
        overrides["max_cells_per_agent_step"] = min(2, base["max_cells_per_agent_step"])     # shorter answers for a small local model
    config = load_config(config_path, overrides=overrides) if overrides else base
    if name == "anthropic":
        for role in ("heimdall", "thor", "loki", "odin_ruling", "odin_briefing"):
            try:
                config.price(config.model_for(role))
            except ConfigError as e:
                raise ConfigError(f"{e}. Add its price to prices_usd_per_million_tokens in the runtime config and verify it.") from e
        provider = AnthropicProvider(config)
    else:
        provider = OllamaProvider(config, base_url)
    return provider, config


def provider_status(config_path=None):
    """What the console shows: which providers can start a run from this server right now, and why not."""
    import os
    from .provider import ollama_models, ollama_url
    cfg = load_config(config_path)
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if os.environ.get("LIVE") != "1":
        missing.append("LIVE=1")
    if not (os.environ.get("BUDGET_OWNER") or "").strip():
        missing.append("BUDGET_OWNER")
    if cfg.get("prices_verified") is not True:
        missing.append("PRICES_VERIFIED=1 (after checking the prices)")
    installed = ollama_models()
    claude_models = sorted(dict.fromkeys(cfg["models"].values()))
    return [
        {"name": "ollama", "label": "Ollama (local)", "configured": installed is not None, "free": True,
         "description": f"Models on this machine through Ollama at {ollama_url()}. Free, no key.",
         "hint": None if installed is not None else "Ollama is not running here: install it from ollama.com and `ollama serve`.",
         "models": installed or [], "needs_model": True, "default_model": (installed or [None])[0]},
        {"name": "anthropic", "label": "Claude (Anthropic API)", "configured": not missing, "free": False,
         "description": "Claude through the Messages API. Metered: the per-case cap, Odin's reserve and the project ledger apply.",
         "hint": None if not missing else "Set " + ", ".join(missing) + " in the server's environment.",
         "models": claude_models, "needs_model": False, "default_model": None,
         "default_label": f"Default split: {cfg['models']['thor']} for the agents, {cfg['models']['odin']} for Odin"},
    ]


__all__ = ["build_provider", "provider_status", "SpecError", "PROVIDERS", "ProviderError"]
