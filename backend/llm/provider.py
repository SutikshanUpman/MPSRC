"""Provider boundary (SYSTEM_ARCHITECTURE 10, Model boundary).

`complete(role, messages, schema, max_output_tokens)` returns
`{"output": <parsed JSON>, "usage": {"input_tokens", "output_tokens"}, "model", "input_hash"}`.

- DeterministicMockProvider: same input -> same output; every call is logged
  (role, model, input hash, token estimates). Used by tests, CI and replay.
- AnthropicProvider: refuses to construct unless the config has `live.enabled`
  true AND a non-empty `live.budget_owner`. Stage 1 never makes a live call:
  `complete` raises until the full ledger lands (Stage 5). No API client is
  imported anywhere in this module.

Callers never call a provider directly for billable work; they go through
`BudgetGuard.call` (backend/runtime/budget.py).
"""
import hashlib
import json
import re

TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


class ProviderError(RuntimeError):
    pass


class LiveCallsDisabled(ProviderError):
    pass


class SchemaError(ProviderError):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def estimate_tokens(text):
    """Rough token estimate (about 4 characters per token), never zero for non-empty text."""
    return (len(text) + 3) // 4


MESSAGE_OVERHEAD_TOKENS = 4


def message_tokens(messages):
    """Input estimate for a message list: each content string as sent (not JSON-escaped again) plus a small
    per-message overhead. Used by the mock's usage, the budget guard and the input-cap rule alike."""
    return sum(estimate_tokens(m["content"]) + MESSAGE_OVERHEAD_TOKENS for m in messages)


def validate_schema(value, schema, path="$"):
    """Small JSON-schema subset: type, required, properties, additionalProperties, items, enum, pattern, minItems."""
    problems = []
    t = schema.get("type")
    if t is not None:
        allowed = t if isinstance(t, list) else [t]
        ok = False
        for name in allowed:
            if name == "integer":
                ok = ok or (isinstance(value, int) and not isinstance(value, bool))
            elif name == "number":
                ok = ok or (isinstance(value, (int, float)) and not isinstance(value, bool))
            else:
                ok = ok or isinstance(value, TYPES[name])
        if not ok:
            return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        problems.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}: missing {key!r}")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                problems += validate_schema(value[key], sub, f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    problems.append(f"{path}: unexpected {key!r}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            problems.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                problems += validate_schema(item, schema["items"], f"{path}[{i}]")
    return problems


def skeleton(schema):
    """The smallest value that satisfies `schema` (deterministic)."""
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    t = t[0] if isinstance(t, list) else t
    if t == "object":
        props = schema.get("properties", {})
        return {k: skeleton(props.get(k, {})) for k in schema.get("required", [])}
    if t == "array":
        return [skeleton(schema.get("items", {})) for _ in range(schema.get("minItems", 0))]
    return {"string": "", "integer": 0, "number": 0, "boolean": False, "null": None}.get(t)


class Provider:
    name = "base"

    def __init__(self, config):
        self.config = config

    def model_for(self, role):
        return self.config.model_for(role)

    def complete(self, role, messages, schema, max_output_tokens=None):
        raise NotImplementedError


class DeterministicMockProvider(Provider):
    """`responders` maps role -> fn(role, messages, schema) returning the output object.
    Without a responder the output is the schema's skeleton. Outputs are schema-checked."""
    name = "mock"

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


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, config):
        if not config.live_enabled():
            raise LiveCallsDisabled("AnthropicProvider needs live.enabled = true and a non-empty "
                                    "live.budget_owner in the runtime config; Stage 1 is mock-only")
        config.check_live_case()
        super().__init__(config)

    def complete(self, role, messages, schema, max_output_tokens=None):
        raise LiveCallsDisabled("live model calls are not wired in Stage 1 (they arrive with the full ledger, Stage 5)")


def make_provider(name, config, **kw):
    if name == "mock":
        if "responders" not in kw:
            from ..agents.mock_policy import default_responders   # rule-based stand-ins for Heimdall, Thor, Loki
            kw["responders"] = default_responders()
        return DeterministicMockProvider(config, **kw)
    if name == "anthropic":
        return AnthropicProvider(config)
    raise ValueError(f"unknown provider {name!r}")
