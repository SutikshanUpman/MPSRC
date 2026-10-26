"""The real providers (Ollama and Anthropic) against a local stub HTTP server: request shape, response parsing,
fallbacks, gates, pricing, and the provider spec the console and the CLI use. No model is called."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from backend.llm.factory import SpecError, build_provider, provider_status  # noqa: E402
from backend.llm.provider import (LiveCallsDisabled, OllamaProvider, ProviderUnavailable,  # noqa: E402
                                  RecordingProvider, ReplayProvider, SchemaError, ollama_models)
from backend.runtime.budget import BudgetGuard  # noqa: E402
from backend.runtime.config import ConfigError, load_config  # noqa: E402

SCHEMA = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
MESSAGES = [{"role": "system", "content": "You are Thor."}, {"role": "user", "content": "{\"task\": \"x\"}"}]


class Stub:
    """A loopback server that answers each request from a queue and records what it was sent."""

    def __init__(self):
        self.seen, self.queue = [], []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}") if length else None
                outer.seen.append({"path": self.path, "body": body, "headers": dict(self.headers)})
                code, payload = outer.queue.pop(0) if outer.queue else (200, {})
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_POST = do_GET = _answer

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def ollama_ok(text='{"a": "x"}', **extra):
    return 200, dict({"message": {"role": "assistant", "content": text}, "done": True, "done_reason": "stop",
                      "prompt_eval_count": 120, "eval_count": 15}, **extra)


class Env(unittest.TestCase):
    KEYS = ("LIVE", "BUDGET_OWNER", "ANTHROPIC_API_KEY", "OLLAMA_HOST")

    def setUp(self):
        saved = {k: os.environ.pop(k, None) for k in self.KEYS}

        def restore():
            for k in self.KEYS:
                os.environ.pop(k, None)
            os.environ.update({k: v for k, v in saved.items() if v is not None})
        self.addCleanup(restore)
        self.stub = Stub()
        self.addCleanup(self.stub.close)


class OllamaTests(Env):
    def provider(self):
        p, _ = build_provider({"provider": "ollama", "model": "qwen2.5:7b", "base_url": self.stub.url})
        p.BACKOFF = (0.0, 0.0)
        return p

    def test_request_shape_and_parsing(self):
        self.stub.queue.append(ollama_ok())
        out = self.provider().complete("thor", MESSAGES, SCHEMA)
        (req,) = self.stub.seen
        self.assertEqual(req["path"], "/api/chat")
        body = req["body"]
        self.assertEqual((body["model"], body["stream"], body["format"]), ("qwen2.5:7b", False, SCHEMA))
        self.assertEqual(body["options"], {"temperature": 0, "num_predict": 2000, "num_ctx": 24576})
        self.assertEqual(body["messages"], MESSAGES)
        self.assertEqual(out["output"], {"a": "x"})
        self.assertEqual(out["usage"], {"input_tokens": 120, "output_tokens": 15})

    def test_is_free_and_needs_no_key_or_switch(self):
        p = self.provider()
        self.assertEqual((p.name, p.billable), ("ollama", False))
        self.assertNotIn("authorization", json.dumps(self.stub.seen))

    def test_a_server_that_rejects_the_schema_gets_plain_json_mode(self):
        self.stub.queue += [(400, {"error": "unsupported schema"}), ollama_ok()]
        p = self.provider()
        out = p.complete("thor", MESSAGES, SCHEMA)
        self.assertEqual([r["body"]["format"] for r in self.stub.seen], [SCHEMA, "json"])
        self.assertEqual(out["output"], {"a": "x"})
        self.assertEqual([f["type"] for f in p.fallbacks], ["FALLBACK_JSON_REPAIR"])

    def test_a_missing_model_says_how_to_pull_it(self):
        self.stub.queue.append((404, {"error": "model not found"}))
        with self.assertRaises(ProviderUnavailable) as cm:
            self.provider().complete("thor", MESSAGES, SCHEMA)
        self.assertIn("ollama pull qwen2.5:7b", str(cm.exception))

    def test_a_truncated_answer_is_a_schema_failure(self):
        self.stub.queue.append(ollama_ok('{"a": "x', done_reason="length"))
        with self.assertRaises(SchemaError):
            self.provider().complete("thor", MESSAGES, SCHEMA)

    def test_fenced_json_is_repaired_once_and_garbage_is_not(self):
        self.stub.queue.append(ollama_ok('```json\n{"a": "x"}\n```'))
        p = self.provider()
        self.assertEqual(p.complete("thor", MESSAGES, SCHEMA)["output"], {"a": "x"})
        self.assertEqual([f["type"] for f in p.fallbacks], ["FALLBACK_JSON_REPAIR"])
        self.stub.queue.append(ollama_ok("I cannot do that"))
        self.assertIsNone(p.complete("thor", MESSAGES, SCHEMA)["output"])

    def test_nothing_listening_is_unavailable_after_two_retries(self):
        dead = Stub()
        url = dead.url
        dead.close()
        p = OllamaProvider(load_config(), url)
        p.BACKOFF = (0.0, 0.0)
        with self.assertRaises(ProviderUnavailable):
            p.complete("thor", MESSAGES, SCHEMA)
        self.assertEqual(len(p.fallbacks), 3)

    def test_installed_models_are_listed(self):
        self.stub.queue.append((200, {"models": [{"name": "qwen2.5:14b"}, {"name": "llama3.1:8b"}]}))
        self.assertEqual(ollama_models(self.stub.url), ["llama3.1:8b", "qwen2.5:14b"])
        dead = Stub()
        url = dead.url
        dead.close()
        self.assertIsNone(ollama_models(url))

    def test_through_the_budget_guard_it_costs_nothing_and_is_recorded_and_replayable(self):
        tmp = Path(tempfile.mkdtemp(prefix="ollama_rec_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        inner = self.provider()
        rec = RecordingProvider(inner, tmp / "llm_calls.jsonl")
        guard = BudgetGuard(inner.config, billable=False)
        self.stub.queue.append(ollama_ok())
        result = guard.call(rec, "thor", MESSAGES, SCHEMA)
        self.assertEqual(result["output"], {"a": "x"})
        self.assertEqual(guard.case_spent, 0.0)
        self.assertEqual(guard.calls[0]["provider"], "ollama")
        line = json.loads((tmp / "llm_calls.jsonl").read_text(encoding="utf-8"))
        self.assertEqual((line["provider"], line["role"], line["model"]), ("ollama", "thor", "qwen2.5:7b"))
        replay = ReplayProvider(inner.config, tmp / "llm_calls.jsonl")
        self.assertEqual(replay.complete("thor", MESSAGES, SCHEMA)["output"], {"a": "x"})


class FactoryTests(Env):
    def test_ollama_spec_sets_every_role_and_prices_the_model_at_zero(self):
        provider, config = build_provider({"provider": "ollama", "model": "qwen2.5:14b", "odin_model": "llama3.3:70b"})
        self.assertEqual(provider.name, "ollama")
        self.assertEqual([config.model_for(r) for r in ("heimdall", "thor", "loki", "odin_ruling", "odin_briefing")],
                         ["qwen2.5:14b"] * 3 + ["llama3.3:70b"] * 2)
        self.assertEqual(config.call_cost("odin_ruling", 100000, 10000), 0.0)
        self.assertEqual(config.price("qwen2.5:14b"), (0.0, 0.0))

    def test_bad_specs(self):
        for spec, text in (({"provider": "banana"}, "provider must be one of"),
                           ({"provider": "ollama"}, "model is required"),
                           ({"provider": "ollama", "model": "bad name; rm"}, "model name"),
                           ({"provider": "ollama", "model": "m", "base_url": "http://evil.example.com"}, "loopback"),
                           ({"provider": "ollama", "model": "m", "base_url": "file:///etc/passwd"}, "http(s)"),
                           ({"provider": "openai", "model": "m"}, "provider must be one of"),
                           ({"provider": "anthropic", "base_url": "http://127.0.0.1:1"}, "fixed address")):
            with self.assertRaises(SpecError, msg=spec) as cm:
                build_provider(spec)
            self.assertIn(text, str(cm.exception))

    def test_a_loopback_endpoint_from_a_client_is_honoured(self):
        provider, _ = build_provider({"provider": "ollama", "model": "m", "base_url": "http://localhost:11500"})
        self.assertEqual(provider.base_url, "http://localhost:11500")

    def test_metered_providers_refuse_without_the_budget_owners_switches(self):
        with self.assertRaises(LiveCallsDisabled):
            build_provider({"provider": "anthropic"})
        os.environ.update(LIVE="1", BUDGET_OWNER="owner")
        cfg = Path(tempfile.mkdtemp(prefix="cfg_")) / "c.json"
        self.addCleanup(shutil.rmtree, cfg.parent, True)
        data = json.loads((ROOT / "config" / "runtime_config.json").read_text(encoding="utf-8"))
        data["prices_verified"] = True
        cfg.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ConfigError) as cm:                                    # a Claude model with no price
            build_provider({"provider": "anthropic", "model": "claude-unpriced-1"}, cfg)
        self.assertIn("price", str(cm.exception))

    def test_anthropic_models_keep_the_configured_split_by_default(self):
        os.environ.update(LIVE="1", BUDGET_OWNER="owner")
        cfg = Path(tempfile.mkdtemp(prefix="cfg_")) / "c.json"
        self.addCleanup(shutil.rmtree, cfg.parent, True)
        data = json.loads((ROOT / "config" / "runtime_config.json").read_text(encoding="utf-8"))
        data["prices_verified"] = True
        cfg.write_text(json.dumps(data), encoding="utf-8")
        provider, config = build_provider({"provider": "anthropic"}, cfg)
        self.assertEqual((provider.name, provider.billable), ("anthropic", True))
        self.assertEqual((config.model_for("thor"), config.model_for("odin_ruling")), ("claude-haiku-5-5", "claude-sonnet-5-5"))

    def test_provider_status_tells_the_console_what_is_ready(self):
        os.environ["OLLAMA_HOST"] = self.stub.url
        self.stub.queue.append((200, {"models": [{"name": "qwen2.5:14b"}]}))
        status = {p["name"]: p for p in provider_status()}
        self.assertTrue(status["ollama"]["configured"] and status["ollama"]["free"])
        self.assertEqual((status["ollama"]["models"], status["ollama"]["default_model"]), (["qwen2.5:14b"], "qwen2.5:14b"))
        self.assertFalse(status["anthropic"]["configured"])
        self.assertIn("ANTHROPIC_API_KEY", status["anthropic"]["hint"])
        self.assertIn("LIVE=1", status["anthropic"]["hint"])
        self.assertEqual(status["anthropic"]["models"], ["claude-haiku-5-5", "claude-sonnet-5-5"])
        self.assertIn("Default split", status["anthropic"]["default_label"])
        self.assertEqual(sorted(status), ["anthropic", "ollama"])                      # only Ollama and Claude
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:1"
        self.assertFalse({p["name"]: p for p in provider_status()}["ollama"]["configured"])


if __name__ == "__main__":
    unittest.main()
