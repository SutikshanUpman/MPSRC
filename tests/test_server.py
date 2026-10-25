"""The web console's server (server.py) and the trial record it serves (backend/runtime/trial_view.py)."""
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from backend.llm.provider import make_provider  # noqa: E402
from backend.runtime.config import load_config  # noqa: E402
from backend.runtime.orchestrator import run_full_case  # noqa: E402

PACK = server.DEFAULT_PACK
QUESTION = next(l for l in (PACK / "sample_question.txt").read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("QUESTION"))


class Console(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="console_"))
        config = load_config()
        run_full_case(QUESTION, [PACK], config, make_provider("mock", config), cls.tmp / "runs", cls.tmp / "mem",
                      out_name="demo", ledger_path=cls.tmp / "ledger.json")
        cls.saved = (server.RUNS, server.ROOT / "data" / "memory")
        server.RUNS = cls.tmp / "runs"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.result = cls.get_json("/api/runs/demo")["result"]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.RUNS = cls.saved[0]
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def raw(cls, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{cls.port}{path}", method="POST" if body is not None else "GET",
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    @classmethod
    def get_json(cls, path, body=None):
        code, data, _ = cls.raw(path, body)
        return json.loads(data) if data and data[:1] in b"[{" else data

    def test_binds_loopback_by_default(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")
        self.assertIn('default=os.environ.get("HOST", "127.0.0.1")', (ROOT / "server.py").read_text(encoding="utf-8"))

    def test_meta_runs_and_health(self):
        self.assertEqual(self.get_json("/api/health")["status"], "ok")
        meta = self.get_json("/api/meta")
        self.assertEqual(meta["modes"], ["trial"])
        self.assertEqual([p["name"] for p in meta["providers"]], ["mock", "replay", "live"])
        runs = self.get_json("/api/runs")
        self.assertEqual([r["run_id"] for r in runs], ["demo"])
        self.assertEqual(runs[0]["status"], "completed")

    def test_the_trial_record_has_what_the_console_reads(self):
        r = self.result
        self.assertEqual(r["schema_version"], "trial-2")
        self.assertEqual(r["status"], "completed")
        self.assertEqual([x["run_number"] for x in r["runs"]], [1, 2])
        cf = r["case_file"]
        self.assertTrue(cf["event_verified"])
        self.assertEqual((cf["event_id"], cf["countries"], cf["sectors"]), ("E5", ["Midgard", "Tolan"], ["Wheat", "Maize"]))
        run1, run2 = r["runs"]
        self.assertTrue(run1["challenges"] and run1["rulings"] and run1["returned_by_odin"] and not run1["sufficient"])
        self.assertTrue(run2["new_evidence_families"])
        self.assertTrue(all(c["claim_status"] in ("submitted", "superseded", "withdrawn") for x in r["runs"] for c in x["claims"]))
        thor = next(c for c in run1["claims"] if c["side"] == "thor" and c["estimate_low"] is not None)
        self.assertLessEqual(thor["estimate_low"], thor["estimate_high"])
        self.assertTrue(thor["citations"] and thor["citations"][0]["locator"].count(":") == 1)
        b = r["briefing"]
        self.assertTrue(b["complete"] and b["established"] and b["conceded"])
        rows = {(x["country"], x["sector"]): x for x in b["exposure"]}
        wheat, maize = rows[("Midgard", "Wheat")], rows[("Tolan", "Maize")]
        self.assertEqual(wheat["status"], "ASSESSED")
        self.assertLessEqual(wheat["odin_low"], wheat["odin_high"])
        self.assertEqual((wheat["unit"], wheat["pct_low"] is not None), ("USD", True))
        self.assertEqual((maize["status"], maize["odin_low"], maize["odin_high"], maize["confidence"]), ("INSUFFICIENT_EVIDENCE", None, None, None))
        self.assertTrue(maize["targeted_queries"])
        self.assertTrue(r["acceptance"]["sent_back"])
        self.assertTrue(r["traps"]["traps"])
        self.assertTrue(any(v for v in r["calc_explain"].values()))

    def test_memory_audit_and_usage(self):
        self.assertTrue(any(a["action"] == "write" for a in self.result["memory_audit"]))
        u = self.result["usage"]
        self.assertEqual((u["cost_usd"], u["calls"] > 0, u["input_tokens"] > 0), (0.0, True, True))

    def test_events_are_served_after_a_sequence_number(self):
        events = self.get_json("/api/runs/demo/events")
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))
        self.assertTrue({"CASE_CREATED", "ODIN_RULED", "ODIN_SENT_BACK", "BRIEFING_BUILT"} <= {e["type"] for e in events})
        later = self.get_json("/api/runs/demo/events?after=10")
        self.assertEqual(later[0]["seq"], 11)

    def test_the_feed_is_gated_by_the_as_of_date(self):
        feed = self.get_json("/api/runs/demo/feed")
        self.assertTrue(feed)
        self.assertTrue(all(x["published_at"][:10] <= "2027-01-25" for x in feed))
        self.assertTrue(all(x["event_id"] in ("E5", "NONE") for x in feed))
        self.assertEqual(len({x["id"] for x in feed}), len(feed))

    def test_click_through_to_a_paragraph_a_document_and_a_trade_row(self):
        para = self.get_json("/api/runs/demo/sources/ORV-0009:P4")
        self.assertEqual(para["kind"], "document")
        self.assertIn("value was", para["item"]["text"])
        doc = self.get_json("/api/runs/demo/sources/ORV-0009")
        self.assertIn("[P1]", doc["item"]["text"])
        row = self.get_json("/api/runs/demo/sources/ORV-0009%7C2026-09")
        self.assertEqual(row["kind"], "trade_row")
        self.assertEqual((row["item"]["country_to"], row["item"]["value"] > 0), ("Midgard", True))
        self.assertEqual(self.raw("/api/runs/demo/sources/ORV-9999:P1")[0], 404)
        # every citation and every exposure locator in the record opens
        for x in self.result["runs"][0]["claims"][:6]:
            for c in x["citations"]:
                self.assertEqual(self.raw(f"/api/runs/demo/sources/{c['locator']}")[0], 200)
        for row in self.result["briefing"]["exposure"]:
            for sid in row["citation_ids"]:
                self.assertEqual(self.raw(f"/api/runs/demo/sources/{sid.replace('|', '%7C')}")[0], 200, sid)

    def test_path_traversal_is_refused_and_console_routes_fall_back_to_the_app(self):
        for p in ("/../server.py", "/..%2fserver.py", "/%2e%2e/server.py", "/api/runs/..%2fx", "/api/runs/../x"):
            self.assertIn(self.raw(p)[0], (400, 404), p)
        self.assertEqual(self.raw("/server.py")[0], 404)
        code, body, _ = self.raw("/")
        self.assertEqual(code, 200)
        self.assertIn(b"Trial of the Nine Realms", body)
        code, body, _ = self.raw("/app")
        self.assertEqual((code, b"root" in body), (200, True))

    def test_a_live_run_cannot_be_started_from_the_console(self):
        code, body, _ = self.raw("/api/runs", {"profile": "anthropic", "question": QUESTION})
        self.assertEqual(code, 400)
        self.assertIn("mock or replay", json.loads(body)["detail"])

    def test_start_a_run_watch_its_events_then_replay_it_at_zero_dollars(self):
        code, body, _ = self.raw("/api/runs", {"question": QUESTION, "profile": "mock"})
        self.assertEqual(code, 202)
        run_id = json.loads(body)["run_id"]
        seen, deadline = [], time.time() + 60
        while time.time() < deadline:
            seen += self.get_json(f"/api/runs/{run_id}/events?after={len(seen)}") or []
            run = self.get_json(f"/api/runs/{run_id}")
            if run["status"] not in ("queued", "running", "done"):
                break
            time.sleep(0.1)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result"]["schema_version"], "trial-2")
        seen += self.get_json(f"/api/runs/{run_id}/events?after={len(seen)}")
        self.assertEqual([e["seq"] for e in seen], list(range(1, len(seen) + 1)))
        code, body, _ = self.raw("/api/runs", {"profile": "replay", "from": run_id})
        self.assertEqual(code, 202)
        rep_id = json.loads(body)["run_id"]
        deadline = time.time() + 60
        while time.time() < deadline:
            rep = self.get_json(f"/api/runs/{rep_id}")
            if rep["status"] not in ("queued", "running", "done"):
                break
            time.sleep(0.1)
        self.assertEqual(rep["status"], "completed")
        self.assertEqual(rep["briefing_hash"], run["briefing_hash"])
        self.assertEqual(rep["spend"]["case_spent_usd"], 0)

    def test_bad_requests(self):
        self.assertEqual(self.raw("/api/runs", {"question": ""})[0], 400)
        self.assertEqual(self.raw("/api/runs", {"question": QUESTION, "runemark_path": "../outside"})[0], 400)
        self.assertEqual(self.raw("/api/runs", {"profile": "replay", "from": "../x"})[0], 400)
        self.assertEqual(self.raw("/api/runs/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
