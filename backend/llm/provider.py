"""Provider boundary (SYSTEM_ARCHITECTURE 10, Model boundary).

`complete(role, messages, schema, max_output_tokens)` returns
`{"output": <parsed JSON>, "usage": {"input_tokens", "output_tokens"}, "model", "input_hash"}`.

- DeterministicMockProvider: same input -> same output; every call is logged
  (role, model, input hash, token estimates). Used by tests, CI and replay.
- AnthropicProvider: live Messages API over urllib; refuses to construct unless LIVE=1,
  BUDGET_OWNER and verified prices. RecordingProvider records every call; ReplayProvider
  re-runs a case from the records at $0.

Callers never call a provider directly for billable work; they go through
`BudgetGuard.call` (backend/runtime/budget.py).
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


class ProviderError(RuntimeError):
    pass


class LiveCallsDisabled(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    """The live API failed after its retries (or refused the call): the caller counts it as a failed attempt."""


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




def is_billable(provider):
    """A provider spends money unless it says otherwise (mock and replay do not)."""
    return getattr(provider, "billable", provider.name != "mock")


def request_hash(role, model, messages, schema, max_output_tokens):
    payload = canonical({"role": role, "model": model, "messages": messages, "schema": schema,
                         "max_output_tokens": max_output_tokens})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_json_text(text):
    """FINAL BUILD 4.2: strip code fences and surrounding prose, then parse. Returns (value, repaired)."""
    try:
        return json.loads(text), False
    except ValueError:
        pass
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        t = t[start:end + 1]
    try:
        return json.loads(t), True
    except ValueError as e:
        raise SchemaError(f"model output is not valid JSON after one repair attempt: {e}")


class AnthropicProvider(Provider):
    """Live Messages API over stdlib urllib (no new dependency). It refuses to exist unless LIVE=1, BUDGET_OWNER is
    set and the prices in the config are marked verified. The key is read from the environment at call time and is
    never stored, logged or written to a record. Calls go through BudgetGuard.call and are recorded by
    RecordingProvider before their output is used. Temperature 0."""
    name = "anthropic"
    billable = True
    URL = "https://api.anthropic.com/v1/messages"
    VERSION = "2023-06-01"
    TIMEOUT = 90
    BACKOFF = (1.0, 3.0)

    def __init__(self, config):
        if not config.live_enabled() and not (os.environ.get("LIVE") == "1" and (os.environ.get("BUDGET_OWNER") or "").strip()):
            raise LiveCallsDisabled("live calls need LIVE=1 and BUDGET_OWNER in the environment (or live.enabled and "
                                    "live.budget_owner in the runtime config)")
        if os.environ.get("LIVE") != "1" or not (os.environ.get("BUDGET_OWNER") or "").strip():
            raise LiveCallsDisabled("live calls need LIVE=1 and a non-empty BUDGET_OWNER in the environment")
        if config.get("prices_verified") is not True:
            raise LiveCallsDisabled("config prices_verified is not true: the budget owner must verify and fill the prices first")
        config.check_live_case()
        super().__init__(config)
        self.calls, self.fallbacks = [], []

    def _split(self, messages):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        return system, [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]

    def _post(self, body):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LiveCallsDisabled("ANTHROPIC_API_KEY is not set in the environment")
        req = urllib.request.Request(self.URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"content-type": "application/json", "x-api-key": key,
                                              "anthropic-version": self.VERSION})
        last = None
        for attempt in range(len(self.BACKOFF) + 1):        # FINAL BUILD 4.1: backoff, at most 2 retries
            try:
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code not in (408, 409, 429, 500, 502, 503, 504, 529):
                    raise ProviderUnavailable(f"Messages API refused the call: {last}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = type(e).__name__
            self.fallbacks.append({"type": "FALLBACK_LLM_RETRY", "attempt": attempt + 1, "error": last})
            if attempt < len(self.BACKOFF):
                time.sleep(self.BACKOFF[attempt])
        raise ProviderUnavailable(f"Messages API unavailable after retries: {last}")

    def complete(self, role, messages, schema, max_output_tokens=None):
        cap = max_output_tokens or self.config.caps(role)["max_output_tokens"]
        model = self.model_for(role)
        system, msgs = self._split(messages)
        system += ("\n\nReply with one JSON object only, no prose and no code fence, that satisfies this JSON schema:\n"
                   + canonical(schema))
        body = {"model": model, "max_tokens": cap, "temperature": 0, "system": system, "messages": msgs}
        raw = self._post(body)
        text = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")
        if raw.get("stop_reason") == "max_tokens":
            raise SchemaError(f"output reached max_output_tokens {cap} (truncated)")
        usage = raw.get("usage") or {}
        result = {"output": None, "raw": text, "model": model,
                  "usage": {"input_tokens": int(usage.get("input_tokens", 0)), "output_tokens": int(usage.get("output_tokens", 0))},
                  "input_hash": request_hash(role, model, messages, schema, cap)}
        try:
            result["output"], repaired = parse_json_text(text)
        except SchemaError:
            result["output"] = None
            result["parse_error"] = True
            return result
        if repaired:
            self.fallbacks.append({"type": "FALLBACK_JSON_REPAIR", "role": role})
        return result


class RecordingProvider(Provider):
    """Wraps a provider and writes every call (request hash, model, raw response, parsed output, usage) to
    llm_calls.jsonl BEFORE the output is used (FINAL BUILD 3.2). A call that failed to parse is recorded too."""

    def __init__(self, inner, path):
        super().__init__(inner.config)
        self.inner, self.path = inner, path
        self.name, self.billable = inner.name, is_billable(inner)
        self.seq = 0

    @property
    def calls(self):
        return getattr(self.inner, "calls", [])

    @property
    def fallbacks(self):
        return getattr(self.inner, "fallbacks", [])

    def model_for(self, role):
        return self.inner.model_for(role)

    def complete(self, role, messages, schema, max_output_tokens=None):
        cap = max_output_tokens or self.config.caps(role)["max_output_tokens"]
        model = self.inner.model_for(role)
        self.seq += 1
        base = {"seq": self.seq, "request_hash": request_hash(role, model, messages, schema, cap), "role": role, "model": model,
                "provider": self.inner.name}
        try:
            result = self.inner.complete(role, messages, schema, max_output_tokens)
        except ProviderError as e:
            self._write(dict(base, error=f"{type(e).__name__}: {e}"))
            raise
        self._write(dict(base, raw_response=result.get("raw"), output=result.get("output"), usage=result["usage"],
                         parse_error=bool(result.get("parse_error"))))
        if result.get("output") is None:
            raise SchemaError("model output is not valid JSON")
        # What is used is what was recorded: key order included, so a replay is byte-identical.
        return dict(result, output=json.loads(canonical(result["output"])))

    def _write(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(canonical(record) + "\n")


class ReplayDiverged(ProviderError):
    pass


class ReplayProvider(Provider):
    """Re-runs a case from llm_calls.jsonl at $0: a request whose hash was recorded gets its recorded output, usage
    and model back; anything else is REPLAY_DIVERGED. Not billable."""
    name = "replay"
    billable = False

    def __init__(self, config, path):
        super().__init__(config)
        self.records = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("output") is not None:
                    self.records.setdefault(rec["request_hash"], []).append(rec)
        self.used = {}
        self.calls = []

    def complete(self, role, messages, schema, max_output_tokens=None):
        cap = max_output_tokens or self.config.caps(role)["max_output_tokens"]
        model = self.model_for(role)
        h = request_hash(role, model, messages, schema, cap)
        queue = self.records.get(h)
        if not queue:
            raise ReplayDiverged(f"REPLAY_DIVERGED: no recorded call for request {h[:12]} (role {role})")
        i = self.used.get(h, 0)
        rec = queue[min(i, len(queue) - 1)]
        self.used[h] = i + 1
        self.calls.append({"seq": len(self.calls) + 1, "provider": "replay", "role": role, "model": model, "input_hash": h})
        return {"output": rec["output"], "usage": rec["usage"], "model": rec["model"], "input_hash": h}


def make_provider(name, config, **kw):
    if name == "mock":
        if "responders" not in kw:
            from ..agents.mock_policy import default_responders   # rule-based stand-ins for Heimdall, Thor, Loki, Odin
            kw["responders"] = default_responders()
        return DeterministicMockProvider(config, **kw)
    if name == "anthropic":
        return AnthropicProvider(config)
    if name == "replay":
        return ReplayProvider(config, kw["path"])
    raise ValueError(f"unknown provider {name!r}")
