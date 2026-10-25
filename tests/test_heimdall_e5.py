"""Stage 1 Heimdall on dev_pack_E5 with the mock provider. No network, no LLM. E5 IDs are allowed here only."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agents.heimdall import open_case  # noqa: E402
from backend.casefile import model as casefile  # noqa: E402
from backend.ingestion.pipeline import ingest_pack  # noqa: E402
from backend.llm.provider import DeterministicMockProvider  # noqa: E402
from backend.provenance.citations import parse_citations, validate_citation  # noqa: E402
from backend.runtime.config import load_config  # noqa: E402

PACK = Path(os.environ["RAGNAROK_PACK_DIR"]) if os.environ.get("RAGNAROK_PACK_DIR") else ROOT / "dev_pack_E5"
QUESTION = next(l for l in (PACK / "sample_question.txt").read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("QUESTION"))
AS_OF = "2027-01-25"
DOC_ID = re.compile(r"\b(?:ATL|ORV|WLD)-\d{4}\b")


class HeimdallE5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.provider = DeterministicMockProvider(cls.config)
        cls.cf, cls.trace, cls.guard = open_case(QUESTION, [PACK], cls.config, cls.provider)
        cls.text = casefile.to_json(cls.cf)
        cls.corpus = ingest_pack(PACK)

    def test_event_as_of_and_status(self):
        self.assertEqual(self.cf["status"], "OPEN")
        self.assertEqual(self.cf["event_id"], "E5")
        self.assertEqual(self.cf["event_mapping"]["decision"], "ACCEPTED")
        self.assertEqual(self.cf["as_of_date"], AS_OF)
        self.assertEqual(self.cf["as_of_source"], "question")
        self.assertEqual(self.cf["event_scope"], ["E5", "NONE"])

    def test_countries_sectors_and_four_cells(self):
        self.assertEqual(set(self.cf["target_countries"]), {"Midgard", "Tolan"})
        self.assertEqual(set(self.cf["target_sectors"]), {"Wheat", "Maize"})
        self.assertEqual(len(self.cf["exposure_cells"]), 4)
        self.assertIn("Orvan", self.cf["question_entities"]["excluded_as_event_origin"])
        self.assertEqual(self.cf["scope_assumptions"], [])

    def test_verification_cites_tier_1_2_case_event_docs(self):
        v = self.cf["event_verification"]
        self.assertEqual(v["verdict"], "VERIFIED")
        self.assertTrue(v["citations"])
        for c in v["citations"]:
            rec = self.corpus[c["doc_id"]]
            self.assertLessEqual(rec["reliability"], 2)
            self.assertEqual(rec["event_id"], "E5")
            self.assertNotEqual(rec["event_id"], "NONE")
        self.assertIn("ORV-0016", [c["doc_id"] for c in v["citations"]])

    def test_correction_and_supersede_relations(self):
        docs = {d["doc_id"]: d for d in self.cf["correction_map"]["documents"]}
        self.assertEqual(docs["ORV-0043"]["status"], "CORRECTED")
        self.assertEqual(docs["ORV-0043"]["corrected_by"], "ORV-0013")
        for superseded in ("ORV-0003", "ORV-0049", "ORV-0015"):
            self.assertEqual(docs[superseded]["status"], "SUPERSEDED", superseded)
        self.assertEqual(docs["ORV-0016"]["status"], "CURRENT")

    def test_no_document_after_as_of_anywhere(self):
        for doc_id in set(DOC_ID.findall(self.text)):
            self.assertLessEqual(self.corpus[doc_id]["pub_date"], AS_OF, doc_id)
        for future in ("ORV-0014", "ORV-0036", "ORV-0041"):
            self.assertNotIn(future, self.text)

    def test_every_citation_validates(self):
        cites = parse_citations(self.text)
        self.assertGreater(len(cites), 10)
        for c in cites:
            self.assertEqual(validate_citation(c, self.corpus, AS_OF), [], c["raw"])

    def test_masked_text_never_reaches_the_packet_unmasked(self):
        packet = json.dumps(self.cf["evidence_packet"], ensure_ascii=False)
        masked = [hit for rec in self.corpus.records.values() for m in rec["masked_lines"] for hit in m["raw"]]
        self.assertTrue(masked)
        for raw in masked:
            self.assertNotIn(raw.strip(), packet)

    def test_coverage_per_cell(self):
        status = {(c["country"], c["sector"]): c["status"] for c in self.cf["coverage"]}
        self.assertEqual(status[("Tolan", "Maize")], "NO_DIRECT_FLOW")
        self.assertEqual(status[("Midgard", "Wheat")], "COVERED")
        self.assertEqual(status[("Tolan", "Wheat")], "COVERED")
        self.assertEqual(status[("Midgard", "Maize")], "PARTIAL")
        gaps = [g for g in self.cf["evidence_gaps"] if (g["country"], g["sector"]) == ("Tolan", "Maize")]
        self.assertIn("direct_flow", [g["missing"] for g in gaps])
        self.assertTrue(all(len(g["queries"]) >= 2 for g in self.cf["evidence_gaps"]))

    def test_premise_and_cell_plan(self):
        self.assertEqual(self.cf["premise_check"]["status"], "NO_PREMISE_WORDS")
        plan = self.cf["cell_plan"]
        self.assertEqual([p["rank"] for p in plan], [1, 2, 3, 4])
        self.assertTrue(all(p["cell_status"] == "PENDING" for p in plan))
        self.assertTrue(self.cf["budget_projection"]["first_batch_affordable"])

    def test_packet_is_narrow(self):
        packet = self.cf["evidence_packet"]
        k = self.config["evidence_packet_top_k_per_cell"]
        self.assertEqual(len(packet["cells"]), 4)
        self.assertTrue(all(len(c["hits"]) <= k for c in packet["cells"]))
        self.assertTrue(packet["families_seen"])
        self.assertIn("AC8", packet["why_narrow"])

    def test_no_model_call_and_no_api_client(self):
        self.assertEqual(self.cf["run_status"][0]["llm_calls"], 0)
        self.assertEqual(self.provider.calls, [])
        self.assertNotIn("anthropic", sys.modules)

    def test_same_question_twice_is_byte_identical(self):
        again, _, _ = open_case(QUESTION, [PACK], self.config, DeterministicMockProvider(self.config))
        self.assertNotEqual(again["case_id"], self.cf["case_id"])
        self.assertEqual(casefile.stable_json(again), casefile.stable_json(self.cf))

    def test_runner_writes_case_file_and_trace(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import run_case
        out = tempfile.mkdtemp(prefix="runs_")
        self.addCleanup(shutil.rmtree, out, True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_case.main(["--pack", str(PACK), "--question", QUESTION, "--out", out,
                                           "--memory-dir", str(Path(out) / "_memory"), "--heimdall-only"]), 0)
        (case_dir,) = [d for d in Path(out).iterdir() if d.name.startswith("case-")]
        cf = json.loads((case_dir / "case_file.json").read_text(encoding="utf-8"))
        casefile.validate(cf)
        self.assertEqual(cf["event_id"], "E5")
        events = [json.loads(l) for l in (case_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIn("EVENT_VERIFICATION", [e["event_type"] for e in events])
        self.assertNotIn(b"\r", (case_dir / "case_file.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
