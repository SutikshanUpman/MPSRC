"""Test-only fakes: a deterministic stand-in provider and rule-based agent policies. Not part of the product."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.llm.provider import (Provider, ReplayProvider, SchemaError, canonical, estimate_tokens, message_tokens,  # noqa: F401
                                  skeleton, validate_schema)


class DeterministicMockProvider(Provider):
    """`responders` maps role -> fn(role, messages, schema) returning the output object.
    Without a responder the output is the schema's skeleton. Outputs are schema-checked."""
    name = "mock"
    billable = False

    def __init__(self, config, responders=None, call_log_path=None):
        super().__init__(config)
        self.responders = dict(responders or {})
        self.call_log_path = call_log_path
        self.calls = []

    def complete(self, role, messages, schema, max_output_tokens=None):
        cap = max_output_tokens or self.config.caps(role)["max_output_tokens"]
        model = self.model_for(role)
        payload = canonical({"role": role, "model": model, "messages": messages, "schema": schema, "max_output_tokens": cap})
        input_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        responder = self.responders.get(role)
        output = responder(role, messages, schema) if responder else skeleton(schema)
        problems = validate_schema(output, schema)
        if problems:
            raise SchemaError("; ".join(problems))
        out_tokens = estimate_tokens(canonical(output))
        if out_tokens > cap:   # a live call would stop at max_tokens and return truncated JSON
            raise SchemaError(f"output of about {out_tokens} tokens exceeds max_output_tokens {cap} (truncated)")
        usage = {"input_tokens": message_tokens(messages), "output_tokens": out_tokens}
        record = {"seq": len(self.calls) + 1, "provider": self.name, "role": role, "model": model,
                  "input_hash": input_hash, "input_tokens_est": usage["input_tokens"],
                  "output_tokens_est": usage["output_tokens"], "max_output_tokens": cap}
        self.calls.append(record)
        if self.call_log_path:
            with open(self.call_log_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(canonical(record) + "\n")
        return {"output": output, "usage": usage, "model": model, "input_hash": input_hash}


def cli_factory(spec, config_path=None):
    """For tests of scripts/run_case.py: the same signature as backend.llm.factory.build_provider, answered by the fake."""
    from backend.runtime.config import load_config
    config = load_config(config_path)
    return make_provider("mock", config), config


def make_provider(name, config, **kw):
    """Tests only: "mock" is the rule-based fake; "replay" re-runs a recording."""
    if name == "mock":
        if "responders" not in kw:
            from .mock_policy import default_responders
            kw["responders"] = default_responders()
        return DeterministicMockProvider(config, **kw)
    if name == "replay":
        return ReplayProvider(config, kw["path"])
    raise ValueError(f"unknown provider {name!r}")
