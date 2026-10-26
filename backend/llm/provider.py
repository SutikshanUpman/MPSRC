"""Provider boundary (SYSTEM_ARCHITECTURE 10, Model boundary).

`complete(role, messages, schema, max_output_tokens)` returns
`{"output": <parsed JSON>, "usage": {"input_tokens", "output_tokens"}, "model", "input_hash"}`.

Real providers, both over stdlib urllib (no SDK):
- OllamaProvider: a local model through Ollama. Free, no key.
- AnthropicProvider: Claude through the Messages API. Metered.
The metered one refuses to exist unless LIVE=1, BUDGET_OWNER and verified prices are set. RecordingProvider records every
call before its output is used; ReplayProvider re-runs a case from the records at $0.

Callers never call a provider directly for billable work; they go through `BudgetGuard.call` (backend/runtime/budget.py).
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

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


def is_billable(provider):
    """A provider spends money unless it says otherwise (replay, Ollama and the test fakes do not)."""
    return getattr(provider, "billable", True)


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


class HTTPProvider(Provider):
    """Shared transport for the two real providers: stdlib urllib, backoff with at most 2 retries (FINAL BUILD 4.1),
    one JSON-repair attempt (4.2). Keys are read from the environment at call time and never stored or logged."""
    TIMEOUT = 120
    BACKOFF = (1.0, 3.0)
    label = "API"

    def __init__(self, config):
        super().__init__(config)
        self.calls, self.fallbacks = [], []

    def _post(self, url, body, headers):
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers=dict({"content-type": "application/json"}, **headers))
        last = None
        for attempt in range(len(self.BACKOFF) + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                last = f"HTTP {e.code}"
                if e.code not in (408, 409, 429, 500, 502, 503, 504, 529):
                    err = ProviderUnavailable(f"{self.label} refused the call: {last} {detail}".strip())
                    err.status, err.detail = e.code, detail
                    raise err
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = type(e).__name__ + (f": {e.reason}" if isinstance(e, urllib.error.URLError) else "")
            self.fallbacks.append({"type": "FALLBACK_LLM_RETRY", "attempt": attempt + 1, "error": last})
            if attempt < len(self.BACKOFF):
                time.sleep(self.BACKOFF[attempt])
        raise ProviderUnavailable(f"{self.label} unavailable after retries: {last}")

    def _result(self, role, messages, schema, cap, model, text, in_tokens, out_tokens):
        result = {"output": None, "raw": text, "model": model,
                  "usage": {"input_tokens": int(in_tokens or 0), "output_tokens": int(out_tokens or 0)},
                  "input_hash": request_hash(role, model, messages, schema, cap)}
        try:
            result["output"], repaired = parse_json_text(text)
        except SchemaError:
            result["parse_error"] = True
            return result
        if repaired:
            self.fallbacks.append({"type": "FALLBACK_JSON_REPAIR", "role": role})
        return result

    @staticmethod
    def _json_instruction(schema):
        return ("\n\nReply with one JSON object only, no prose and no code fence, that satisfies this JSON schema:\n"
                + canonical(schema))


def _require_live_gates(config, what):
    """A billable provider needs the budget owner's explicit switches (FINAL BUILD 3.1)."""
    if not config.live_enabled() and not (os.environ.get("LIVE") == "1" and (os.environ.get("BUDGET_OWNER") or "").strip()):
        raise LiveCallsDisabled(f"{what} spends money: it needs LIVE=1 and BUDGET_OWNER in the server's environment "
                                "(or live.enabled and live.budget_owner in the runtime config)")
    if os.environ.get("LIVE") != "1" or not (os.environ.get("BUDGET_OWNER") or "").strip():
        raise LiveCallsDisabled(f"{what} spends money: it needs LIVE=1 and a non-empty BUDGET_OWNER in the environment")
    if config.get("prices_verified") is not True:
        raise LiveCallsDisabled("config prices_verified is not true: the budget owner must verify and fill the prices first")
    config.check_live_case()


class AnthropicProvider(HTTPProvider):
    """Claude via the Messages API. Temperature 0. Billable: refuses to exist unless LIVE=1, BUDGET_OWNER and verified prices."""
    name = "anthropic"
    billable = True
    label = "Messages API"
    URL = "https://api.anthropic.com/v1/messages"
    VERSION = "2023-06-01"
    TIMEOUT = 90

    def __init__(self, config):
        _require_live_gates(config, "the Anthropic API")
        super().__init__(config)

    def _split(self, messages):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        return system, [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]

    def complete(self, role, messages, schema, max_output_tokens=None):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LiveCallsDisabled("ANTHROPIC_API_KEY is not set in the environment")
        cap = max_output_tokens or self.config.caps(role)["max_output_tokens"]
        model = self.model_for(role)
        system, msgs = self._split(messages)
        body = {"model": model, "max_tokens": cap, "temperature": 0, "system": system + self._json_instruction(schema), "messages": msgs}
        raw = self._post(self.URL, body, {"x-api-key": key, "anthropic-version": self.VERSION})
        text = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")
        if raw.get("stop_reason") == "max_tokens":
            raise SchemaError(f"output reached max_output_tokens {cap} (truncated)")
        u = raw.get("usage") or {}
        return self._result(role, messages, schema, cap, model, text, u.get("input_tokens"), u.get("output_tokens"))


def is_loopback(url):
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def ollama_url(base_url=None):
    url = base_url or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    if "://" not in url:
        url = "http://" + url
    return url.rstrip("/")


def ollama_models(base_url=None, timeout=1.5):
    """Installed Ollama models, or None when no Ollama answers at the address."""
    try:
        with urllib.request.urlopen(ollama_url(base_url) + "/api/tags", timeout=timeout) as resp:
            return sorted(m["name"] for m in json.loads(resp.read().decode("utf-8")).get("models", []))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        return None


class OllamaProvider(HTTPProvider):
    """A model served by Ollama (https://ollama.com) on this machine. Free, no key, no gates. Uses the native /api/chat
    with the JSON schema as `format` (structured output), temperature 0 and a context window of `ollama_num_ctx`
    tokens (Ollama's default of 2048 would silently cut the prompts). Falls back to plain JSON mode if the server
    rejects the schema."""
    name = "ollama"
    billable = False
    label = "Ollama"
    TIMEOUT = 900

    def __init__(self, config, base_url=None):
        super().__init__(config)
        self.base_url = ollama_url(base_url)

    def complete(self, role, messages, schema, max_output_tokens=None):
        cap = max_output_tokens or self.config.caps(role)["max_output_tokens"]
        model = self.model_for(role)
        body = {"model": model, "messages": messages, "stream": False, "format": schema,
                "options": {"temperature": 0, "num_predict": cap, "num_ctx": int(self.config.get("ollama_num_ctx", 24576))}}
        try:
            raw = self._post(f"{self.base_url}/api/chat", body, {})
        except ProviderUnavailable as e:
            status = getattr(e, "status", None)
            if status == 404:
                raise ProviderUnavailable(f"Ollama has no model {model!r}: run `ollama pull {model}`") from e
            if status == 400:
                body["format"] = "json"                      # an older server, or a schema its grammar cannot express
                raw = self._post(f"{self.base_url}/api/chat", body, {})
                self.fallbacks.append({"type": "FALLBACK_JSON_REPAIR", "role": role})
            else:
                raise
        if raw.get("done_reason") == "length":
            raise SchemaError(f"output reached max_output_tokens {cap} (truncated)")
        return self._result(role, messages, schema, cap, model, (raw.get("message") or {}).get("content") or "",
                            raw.get("prompt_eval_count"), raw.get("eval_count"))


class RecordingProvider(Provider):
    """Wraps a provider and writes every call (request hash, model, raw response, parsed output, usage) to
    llm_calls.jsonl BEFORE the output is used (FINAL BUILD 3.2). A call that failed to parse is recorded too."""

    def __init__(self, inner, path):
        super().__init__(inner.config)
        self.inner, self.path = inner, path
        self.notify = None                 # live feed: called with (kind, info) when a model call starts and ends
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
        started = time.time()
        if self.notify:
            self.notify("MODEL_CALL_STARTED", {"role": role, "model": model, "call": self.seq, "input_chars": sum(len(m["content"]) for m in messages)})
        try:
            result = self.inner.complete(role, messages, schema, max_output_tokens)
        except ProviderError as e:
            self._write(dict(base, error=f"{type(e).__name__}: {e}"))
            if self.notify:
                self.notify("MODEL_CALL_FINISHED", {"role": role, "model": model, "call": self.seq, "seconds": round(time.time() - started, 1),
                                                   "error": f"{type(e).__name__}: {str(e)[:160]}"})
            raise
        self._write(dict(base, raw_response=result.get("raw"), output=result.get("output"), usage=result["usage"],
                         parse_error=bool(result.get("parse_error"))))
        if self.notify:
            self.notify("MODEL_CALL_FINISHED", {"role": role, "model": model, "call": self.seq, "seconds": round(time.time() - started, 1),
                                               "input_tokens": result["usage"]["input_tokens"], "output_tokens": result["usage"]["output_tokens"],
                                               "error": "the answer is not valid JSON" if result.get("output") is None else None})
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
