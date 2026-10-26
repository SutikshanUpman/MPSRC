"""Choosing the models for a run: provider + model(s) -> (provider, config).

A run's spec is `{provider, model?, odin_model?, base_url?}`:

    ollama      a local model through Ollama (free, no key): `model` is an installed model name, e.g. qwen2.5:14b
    openai      an OpenAI-compatible API (OpenAI, OpenRouter, vLLM, LM Studio, ...): key OPENAI_API_KEY, URL OPENAI_BASE_URL
    anthropic   Claude: key ANTHROPIC_API_KEY, models and prices from config/runtime_config.json

`model` serves Heimdall, Thor and Loki; `odin_model` serves Odin (default: the same). A free provider (Ollama, a loopback
URL) is priced at $0. A billable one must have a price in the config for every model it uses, and the budget owner's
switches (LIVE=1, BUDGET_OWNER, prices_verified); the provider constructor enforces them. A base URL given by a client is
honoured only when it is loopback, so a key the server holds is never sent to an address a page chose.
"""
import re

from ..runtime.config import ConfigError, load_config
from .provider import AnthropicProvider, OllamaProvider, OpenAICompatProvider, ProviderError, is_loopback

PROVIDERS = ("ollama", "openai", "anthropic")
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,99}$")
ROLES = ("heimdall", "thor", "loki")


class SpecError(ValueError):
    pass


def _check_model(name, what):
    if not isinstance(name, str) or not MODEL.match(name):
        raise SpecError(f"{what}: a model name of letters, digits and . _ : / @ + - is required")
    return name


def build_provider(spec, config_path=None):
    """Returns (provider, config). Raises SpecError for a bad request, LiveCallsDisabled when a billable provider's
    switches are off, ConfigError when a billable model has no price."""
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
            raise SpecError("a base URL from a client must be loopback (localhost); a remote one is set in the server's "
                            "environment (OPENAI_BASE_URL, OLLAMA_HOST)")
    base = load_config(config_path)
    model = _check_model(spec["model"], "model") if spec.get("model") else None
    odin = _check_model(spec["odin_model"], "odin_model") if spec.get("odin_model") else model
    if name in ("ollama", "openai") and not model:
        raise SpecError("model is required (the name of the model to run)")
    models = {}
    if model:
        models = {r: model for r in ROLES}
        models["odin"] = odin
    overrides = {"models": models} if models else {}

    if name == "ollama":
        free = True
    elif name == "openai":
        import os
        free = is_loopback(base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1")
    else:
        free = False
    if free and models:
        overrides["prices_usd_per_million_tokens"] = {m: {"input": 0.0, "output": 0.0} for m in set(models.values())}
    config = load_config(config_path, overrides=overrides) if overrides else base
    if not free:
        for role in ("heimdall", "thor", "loki", "odin_ruling", "odin_briefing"):
            try:
                config.price(config.model_for(role))
            except ConfigError as e:
                raise ConfigError(f"{e}. Add its price to prices_usd_per_million_tokens in the runtime config and verify it.") from e
    if name == "ollama":
        provider = OllamaProvider(config, base_url)
    elif name == "openai":
        provider = OpenAICompatProvider(config, base_url)
    else:
        provider = AnthropicProvider(config)
    return provider, config


def provider_status(config_path=None):
    """What the console shows: which providers can start a run from this server right now, and why not."""
    import os
    from .provider import ollama_models, ollama_url
    cfg = load_config(config_path)
    switches = os.environ.get("LIVE") == "1" and bool((os.environ.get("BUDGET_OWNER") or "").strip()) and cfg.get("prices_verified") is True
    missing = []
    if os.environ.get("LIVE") != "1":
        missing.append("LIVE=1")
    if not (os.environ.get("BUDGET_OWNER") or "").strip():
        missing.append("BUDGET_OWNER")
    if cfg.get("prices_verified") is not True:
        missing.append("prices_verified in the runtime config")
    installed = ollama_models()
    openai_url = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    openai_free = is_loopback(openai_url)
    return [
        {"name": "ollama", "label": "Ollama (local)", "configured": installed is not None, "free": True,
         "description": f"Models on this machine through Ollama at {ollama_url()}. Free, no key.",
         "hint": None if installed is not None else "Ollama is not running here: install it from ollama.com and `ollama serve`.",
         "models": installed or [], "needs_model": True, "default_model": (installed or [None])[0]},
        {"name": "openai", "label": "OpenAI-compatible API", "configured": bool(os.environ.get("OPENAI_API_KEY")) and (openai_free or switches) or openai_free,
         "free": openai_free, "description": f"Any OpenAI-compatible endpoint ({openai_url}). Key: OPENAI_API_KEY.",
         "hint": None if (openai_free or (os.environ.get("OPENAI_API_KEY") and switches)) else
         "Set " + ", ".join(([] if os.environ.get("OPENAI_API_KEY") else ["OPENAI_API_KEY"]) + missing) + " in the server's environment.",
         "models": [], "needs_model": True, "default_model": None},
        {"name": "anthropic", "label": "Anthropic API (Claude)", "configured": bool(os.environ.get("ANTHROPIC_API_KEY")) and switches, "free": False,
         "description": "Claude through the Messages API. Key: ANTHROPIC_API_KEY. Metered: the budget guard and ledger apply.",
         "hint": None if (os.environ.get("ANTHROPIC_API_KEY") and switches) else
         "Set " + ", ".join(([] if os.environ.get("ANTHROPIC_API_KEY") else ["ANTHROPIC_API_KEY"]) + missing) + " in the server's environment.",
         "models": sorted(set(cfg["models"].values())), "needs_model": False, "default_model": cfg["models"]["thor"]},
    ]


__all__ = ["build_provider", "provider_status", "SpecError", "PROVIDERS", "ProviderError"]
