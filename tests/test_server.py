"""Dashboard server (server.py): the API over saved cases, source drawer data, and the guards on the server itself."""
import json
import shutil
import sys
import tempfile
import threading
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


class Dashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dash_"))
        config = load_config()
        run_full_case(QUESTION, [PACK], config, make_provider("mock", config), cls.tmp / "runs", cls.tmp / "mem",
                      out_name="demo", ledger_path=cls.tmp / "ledger.json")
        cls.saved = server.RUNS
        server.RUNS = cls.tmp / "runs"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.RUNS = cls.saved
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_binds_loopback_by_default(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")
        import argparse
        self.assertIn("127.0.0.1", (ROOT / "server.py").read_text(encoding="utf-8").split("--host")[1][:80])

    def test_case_list_and_bundle(self):
        code, body, _ = self.get("/api/cases")
        cases = json.loads(body)
        self.assertEqual((code, [c["id"] for c in cases]), (200, ["demo"]))
        code, body, _ = self.get("/api/cases/demo")
        bundle = json.loads(body)
        self.assertEqual(code, 200)
        for key in ("run_record", "case_file", "rulings", "briefing", "trap_report", "claims", "calcs", "briefing_md", "config"):
            self.assertIsNotNone(bundle[key], key)
        code, body, _ = self.get("/api/cases/demo/events")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body))

    def test_missing_case_and_missing_files_are_reported_not_crashed(self):
        self.assertEqual(self.get("/api/cases/nope")[0], 404)
        (server.RUNS / "demo" / "trap_report.json").rename(server.RUNS / "demo" / "tr.bak")
        try:
            code, body, _ = self.get("/api/cases/demo")
            self.assertEqual(code, 200)
            self.assertIsNone(json.loads(body)["trap_report"])                      # the page shows a pending panel
        finally:
            (server.RUNS / "demo" / "tr.bak").rename(server.RUNS / "demo" / "trap_report.json")

    def test_source_drawer_data_and_table_row_highlight(self):
        code, body, _ = self.get("/api/source?doc_id=ORV-0009&p=P4&case=demo")
        src = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(src["tier"], 1)
        self.assertTrue(src["highlight"] and src["highlight"][0] in src["text"])
        self.assertEqual(self.get("/api/source?doc_id=ORV-9999&p=P1&case=demo")[0], 404)

    def test_path_traversal_is_refused(self):
        for p in ("/../server.py", "/..%2fserver.py", "/%2e%2e/server.py", "/api/cases/..%2f..%2fdemo", "/api/cases/../x"):
            code = self.get(p)[0]
            self.assertIn(code, (400, 404), p)
        self.assertEqual(self.get("/server.py")[0], 404)
        code, body, headers = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"Trial of the Nine Realms", body)

    def test_a_live_run_cannot_be_started_from_the_dashboard(self):
        code, body = self.post("/api/cases", {"provider": "anthropic", "question": QUESTION})
        self.assertEqual(code, 400)
        self.assertIn("mock or replay", body["error"])

    def test_run_and_replay_from_the_dashboard(self):
        code, body = self.post("/api/cases", {"question": QUESTION, "provider": "mock"})
        self.assertEqual((code, body["status"]), (200, "OPEN"))
        code, rep = self.post("/api/cases", {"provider": "replay", "from": "demo"})
        self.assertEqual(code, 200)
        self.assertTrue(rep["replay_matches_original"])
        self.assertEqual(rep["spend"]["case_spent_usd"], 0)
        self.assertEqual(self.post("/api/cases", {"provider": "replay", "from": "../x"})[0], 400)
        self.assertEqual(self.post("/api/cases", {"question": QUESTION, "pack": "../outside"})[0], 400)


if __name__ == "__main__":
    unittest.main()
