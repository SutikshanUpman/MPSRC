"""Stage 1 Heimdall on the synthetic packs (different event, countries, sector). Mock only."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from backend.agents.heimdall import open_case  # noqa: E402
from backend.casefile import model as casefile  # noqa: E402
from backend.ingestion.packs import load_packs  # noqa: E402
from backend.provenance.citations import parse_citations, validate_citation  # noqa: E402
from backend.runtime.config import load_config  # noqa: E402
from fixtures import synthetic_pack  # noqa: E402

AS_OF = synthetic_pack.AS_OF
Q_NO_SECTOR = "As of 30 June 2031, how exposed is Brenn to the Velka canal closure?"
Q_NO_COUNTRY = "As of 30 June 2031, how exposed are importers to the Velka canal closure? Give a range for LNG imports."
Q_AMBIGUOUS = ("As of 30 June 2031, how exposed is Brenn to the Velka canal closure and the Tarsk rail strike? "
               "Give a range for LNG imports.")
Q_FALSE_PREMISE = "As of 30 June 2031, how exposed is Brenn to the destruction of the Velka canal? Give a range for LNG imports."
Q_FULL = "As of 30 June 2031, how exposed is Brenn to the Velka canal closure? Give a range for LNG imports."


class HeimdallSynthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="synheim_")
        cls.base = synthetic_pack.build(Path(cls.tmp) / "base")
        cls.live = synthetic_pack.build_live(Path(cls.tmp) / "live")
        cls.config = load_config()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_case(self, question, packs, config=None):
        cf, trace, _ = open_case(question, packs, config or self.config)
        casefile.validate(cf)
        return cf, trace

    def assert_citations_valid(self, cf, packs):
        corpus, _, _ = load_packs(packs)
        for c in parse_citations(casefile.to_json(cf)):
            self.assertEqual(validate_citation(c, corpus, AS_OF), [], c["raw"])

    def test_no_sector_defaults_to_manifest_scope_and_records_it(self):
        cf, trace = self.run_case(Q_NO_SECTOR, [self.base])
        self.assertEqual(cf["status"], "OPEN")
        self.assertEqual(cf["event_id"], synthetic_pack.EVENT)
        self.assertEqual(cf["target_countries"], ["Brenn"])
        self.assertEqual(cf["target_sectors"], ["LNG"])
        self.assertEqual(cf["scope_assumptions"], [{"dimension": "sectors", "source": "manifest_scope", "values": ["LNG"],
                                                    "reason": "question named no sector"}])
        self.assertEqual(cf["exposure_cells"], [{"country": "Brenn", "sector": "LNG"}])
        self.assertIn("Velka", cf["question_entities"]["excluded_as_event_origin"])
        self.assertTrue(trace.of_type("SCOPE_DEFAULTED"))
        self.assert_citations_valid(cf, [self.base])

    def test_no_country_defaults_to_scope_destinations(self):
        cf, _ = self.run_case(Q_NO_COUNTRY, [self.base])
        self.assertEqual(cf["target_countries"], ["Brenn", "Osk"])
        self.assertEqual([a["dimension"] for a in cf["scope_assumptions"]], ["countries"])
        self.assertEqual(len(cf["exposure_cells"]), 2)

    def test_ambiguous_question_is_rejected_with_three_candidates(self):
        cf, _ = self.run_case(Q_AMBIGUOUS, [self.base, self.live])
        self.assertEqual(cf["status"], "EVENT_REJECTED")
        self.assertEqual(cf["event_mapping"]["decision"], "REJECTED_AMBIGUOUS_EVENT")
        self.assertEqual(cf["rejection"]["reason"], "REJECTED_AMBIGUOUS_EVENT")
        cands = cf["event_mapping"]["candidates"]
        self.assertEqual(len(cands), 3)
        self.assertEqual({c["event_id"] for c in cands[:2]}, {synthetic_pack.EVENT, synthetic_pack.LIVE_EVENT})
        self.assertLess(cands[0]["score"], 2 * cands[1]["score"])
        self.assertEqual(cf["exposure_cells"], [])

    def test_unrelated_question_is_no_match(self):
        cf, _ = self.run_case("As of 30 June 2031, what will the weather be like?", [self.base])
        self.assertEqual(cf["event_mapping"]["decision"], "REJECTED_NO_MATCH")
        self.assertEqual(cf["status"], "EVENT_REJECTED")

    def test_false_premise_is_recorded_and_the_case_continues(self):
        cf, _ = self.run_case(Q_FALSE_PREMISE, [self.base])
        self.assertEqual(cf["status"], "OPEN")
        self.assertEqual(cf["event_verification"]["verdict"], "VERIFIED")
        pc = cf["premise_check"]
        self.assertEqual(pc["status"], "REJECTED_PREMISE")
        self.assertEqual(pc["premise_words"], ["destroyed"])
        self.assertTrue(pc["citations"])
        self.assertEqual(cf["exposure_cells"], [{"country": "Brenn", "sector": "LNG"}])
        self.assert_citations_valid(cf, [self.base])

    def test_true_premise_is_verified(self):
        cf, _ = self.run_case(Q_FULL, [self.base])
        self.assertEqual(cf["premise_check"]["status"], "VERIFIED")
        self.assertEqual(cf["premise_check"]["premise_words"], ["closed"])

    def test_doc_id_collision_merges_or_live_wins_and_never_stops_the_case(self):
        corpus, events, quarantined = load_packs([self.base, self.live])
        types = {e["doc_id"]: e for e in events if "doc_id" in e}   # CROSS_PACK_DUPLICATE_BODY carries doc_ids
        self.assertEqual(types["SYN-0014"]["event_type"], "PACK_DOC_ID_DUPLICATE")
        self.assertEqual(types["SYN-0014"]["level"], "INFO")
        self.assertNotIn("SYN-0014", quarantined)
        warn = types["SYN-0004"]
        self.assertEqual(warn["event_type"], "INTEGRITY_WARNING")
        self.assertNotEqual(warn["earlier"]["normalized_body_sha256"], warn["later"]["normalized_body_sha256"])
        self.assertTrue(warn["earlier"]["raw_file_sha256"] and warn["later"]["raw_file_sha256"])
        self.assertEqual(corpus["SYN-0004"]["pack_path"], str(self.live))
        self.assertIn("barges", corpus["SYN-0004"]["paragraphs"][0]["text"])
        self.assertEqual(quarantined["SYN-0004"]["pack_path"], str(self.base))

        cf, trace = self.run_case(Q_FULL, [self.base, self.live])
        self.assertEqual(cf["status"], "OPEN")
        run = cf["run_status"][0]
        self.assertEqual([w["doc_id"] for w in run["integrity_warnings"]], ["SYN-0004"])
        self.assertEqual([m["doc_id"] for m in run["pack_merges"]], ["SYN-0014"])
        self.assertIn({"doc_id": "SYN-0004", "pack_path": str(self.base), "reason": "PACK_DOC_ID_COLLISION_EARLIER_COPY"},
                      run["quarantined_documents"])
        self.assertEqual(trace.of_type("INTEGRITY_WARNING")[0]["level"], "WARNING")
        self.assertEqual(trace.of_type("PACK_DOC_ID_DUPLICATE")[0]["level"], "INFO")

    def test_hash_mismatch_document_is_quarantined(self):
        cf, _ = self.run_case(Q_FULL, [self.base])
        self.assertIn({"doc_id": "SYN-0001", "pack_path": str(self.base), "reason": "HASH_MISMATCH"},
                      cf["run_status"][0]["quarantined_documents"])
        self.assertNotIn("[SYN-0001,", casefile.to_json(cf))

    def test_injection_and_future_docs_stay_out(self):
        cf, _ = self.run_case(Q_FULL, [self.base])
        text = casefile.to_json(cf)
        self.assertNotIn("disregard the evidence", text)
        self.assertNotIn("SYN-0012", text)     # dated after as-of
        self.assertNotIn("SYN-0013", text)     # another event

    def test_unaffordable_first_batch_marks_every_cell(self):
        tight = load_config(overrides={"per_case_cap_usd": 0.22})
        cf, trace = self.run_case(Q_NO_COUNTRY, [self.base], tight)
        self.assertTrue(all(c["cell_status"] == "INCOMPLETE_BUDGET_LIMIT" for c in cf["cell_plan"]))
        self.assertEqual(len(cf["cell_plan"]), 2)
        self.assertEqual(cf["run_status"][0]["stop_reason"], "INCOMPLETE_BUDGET_LIMIT")
        self.assertFalse(cf["budget_projection"]["first_batch_affordable"])
        self.assertTrue(trace.of_type("CELL_BUDGET_PROJECTED"))

    def test_mock_determinism_on_a_second_pack(self):
        a, _ = self.run_case(Q_NO_COUNTRY, [self.base, self.live])
        b, _ = self.run_case(Q_NO_COUNTRY, [self.base, self.live])
        self.assertEqual(casefile.stable_json(a), casefile.stable_json(b))
        self.assertEqual(json.loads(casefile.stable_json(a)).get("case_id"), None)


if __name__ == "__main__":
    unittest.main()
