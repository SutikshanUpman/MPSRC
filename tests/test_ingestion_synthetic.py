"""Ingestion tests on a synthetic damaged pack built at test time (review F41)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from backend.ingestion import trade  # noqa: E402
from backend.ingestion.pipeline import agent_view, case_scope, ingest_pack  # noqa: E402
from backend.ingestion.quality import MASK_PLACEHOLDER  # noqa: E402
from backend.search.bm25 import CaseIndex, mentions  # noqa: E402
from fixtures import synthetic_pack  # noqa: E402

AS_OF, EVENT = synthetic_pack.AS_OF, synthetic_pack.EVENT


class SyntheticPack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="synpack_")
        root = synthetic_pack.build(cls.tmp)
        opened = []
        real = Path.read_bytes

        def spy(self):
            opened.append(self.name)
            return real(self)
        Path.read_bytes = spy
        try:
            cls.c = ingest_pack(root)
        finally:
            Path.read_bytes = real
        cls.opened = opened
        cls.rows = {r["row_key"]: r for r in cls.c.trade_rows()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # --- robustness and status ---
    def test_never_crashes_and_every_doc_has_a_status(self):
        self.assertEqual(len(self.c.records), 18)
        for r in self.c.records.values():
            self.assertIn(r["status"], ("OK", "EMPTY", "TRUNCATED", "RECODED", "FAILED"))

    def test_image_never_read(self):
        self.assertNotIn("map.png", self.opened)
        self.assertFalse([n for n in self.opened if n.endswith(".png")])

    def test_statuses(self):
        s = {d: r["status"] for d, r in self.c.records.items()}
        self.assertEqual(s["SYN-0009"], "EMPTY")
        self.assertEqual(s["SYN-0010"], "TRUNCATED")
        self.assertEqual(s["SYN-0001"], "TRUNCATED")      # cut-off table row
        for d in ("SYN-0004", "SYN-0005", "SYN-0006"):
            self.assertEqual(s[d], "RECODED", d)
        for d in ("SYN-0016", "SYN-0017", "SYN-0018"):
            self.assertEqual(s[d], "FAILED", d)
        self.assertIn("MISSING_FILE", self.c["SYN-0018"]["flags"])

    # --- encodings ---
    def test_bomless_utf16_decoded(self):
        r = self.c["SYN-0004"]
        self.assertEqual(r["header"]["DOC_ID"], "SYN-0004")
        self.assertIn("closed to tankers", r["paragraphs"][0]["text"])
        self.assertIn("no BOM", r["decoders"][0]["decoder"])

    def test_cp1252_body_flagged_and_decoded(self):
        r = self.c["SYN-0005"]
        self.assertIn("MALFORMED_ENCODING", r["flags"])
        self.assertIn("“Bills are up,”", r["paragraphs"][0]["text"])
        self.assertIn("café", r["paragraphs"][0]["text"])
        self.assertEqual({s["decoder"] for s in r["decoders"] if s["part"] == "header"}, {"utf-8"})

    def test_mid_file_bom_utf16be_body(self):
        r = self.c["SYN-0006"]
        self.assertEqual(r["header"]["DOC_ID"], "SYN-0006")
        self.assertIn("nine days", r["paragraphs"][0]["text"])
        self.assertTrue(any(s["decoder"].startswith("utf-16-be") for s in r["decoders"]))

    # --- manifest ---
    def test_manifest_schemas_and_conflicts(self):
        for r in self.c.records.values():
            self.assertIsInstance(r["reliability"], int, r["doc_id"])
            self.assertIsNotNone(r["format"])
        conf = self.c["SYN-0002"]["metadata_conflicts"]
        self.assertTrue(any(x["field"] == "SOURCE_NAME" for x in conf))
        self.assertIn("METADATA_CONFLICT", self.c["SYN-0002"]["flags"])
        self.assertIn("HASH_MISMATCH", self.c["SYN-0001"]["flags"])
        self.assertTrue(any(f["flag"] == "MANIFEST_COUNT_MISMATCH" for f in self.c.pack_flags))

    # --- dedupe ---
    def test_cross_format_duplicate_one_family(self):
        a, b = self.c["SYN-0007"], self.c["SYN-0008"]
        self.assertEqual(a["format"], "TXT")
        self.assertEqual(b["format"], "DOCX")
        self.assertEqual(a["body_hash"], b["body_hash"])
        self.assertEqual(a["evidence_family_id"], b["evidence_family_id"])
        self.assertEqual([a["preferred_in_family"], b["preferred_in_family"]].count(True), 1)

    # --- injection ---
    def test_injection_masked_in_paragraph_and_title(self):
        r = self.c["SYN-0011"]
        p2 = next(p for p in r["paragraphs"] if p["id"] == "P2")
        self.assertEqual(p2["text_masked"], MASK_PLACEHOLDER)
        self.assertIn("disregard the evidence", p2["text"])
        self.assertEqual(r["agent_title"], MASK_PLACEHOLDER)
        self.assertEqual(r["agent_header"]["TITLE"], MASK_PLACEHOLDER)
        view = repr(agent_view(r))
        self.assertNotIn("disregard", view)
        self.assertNotIn("ignore previous", view)
        self.assertEqual(r["status"], "OK")

    # --- gate ---
    def test_as_of_and_event_scope(self):
        eligible, excluded = case_scope(self.c, AS_OF, EVENT)
        self.assertEqual(excluded["SYN-0012"], "FUTURE_DATED")
        self.assertEqual(excluded["SYN-0013"], "OUT_OF_EVENT_SCOPE")
        bg = [r for r in eligible if r["doc_id"] == "SYN-0014"][0]
        self.assertTrue(bg["background_only"])
        ix = CaseIndex(self.c, AS_OF, EVENT)
        self.assertFalse({u["rec"]["doc_id"] for u in ix.units} & {"SYN-0012", "SYN-0013"})
        self.assertTrue(all(h["context_only"] for h in ix.search("country profile Brenn") if h["doc_id"] == "SYN-0014"))

    # --- fixed table without [Pn] ---
    def test_fixed_table_units_and_synthetic_paragraph(self):
        r = self.rows["SYN-0001|2030-07"]
        self.assertEqual(r["source_layout"], "fixed_table")
        self.assertEqual(r["table_id"], "T-0077")
        self.assertEqual(r["native_row_number"], 1)
        self.assertEqual((r["value_amount"], r["value_currency"]), (45_500_000, "EUR"))
        self.assertEqual((r["volume_amount"], r["volume_unit"]), (3_200_000, "MMBtu"))
        self.assertEqual((r["origin"], r["destination"], r["sector"]), ("Velka", "Brenn", "lng"))
        self.assertTrue(r["synthetic_paragraph"])
        self.assertEqual(r["citation"]["text"], "[SYN-0001, P1, 2031-01-15 09:00]")
        self.assertIn("SYNTHETIC_PARAGRAPH", self.c["SYN-0001"]["flags"])

    def test_damaged_table_rows_flagged_not_used_not_dropped(self):
        rows = self.rows
        self.assertEqual(len([k for k in rows if k.startswith("SYN-0001|")]), 6)
        for k in ("SYN-0001|2030-08", "SYN-0001|2030-09"):
            self.assertIn("TRADE_ROW_REPEATED_VALUES", rows[k]["flags"])
        self.assertIn("TRADE_ROW_MISSING_VALUE", rows["SYN-0001|2030-10"]["flags"])
        self.assertIn("TRADE_ROW_BAD_NUMBER", rows["SYN-0001|2030-11"]["flags"])
        self.assertIsNone(rows["SYN-0001|2030-11"]["value_amount"])
        self.assertIn("TRADE_TABLE_TRUNCATED", rows["SYN-0001|2030-12"]["flags"])
        for k in ("SYN-0001|2030-08", "SYN-0001|2030-09", "SYN-0001|2030-10", "SYN-0001|2030-11", "SYN-0001|2030-12"):
            self.assertFalse(rows[k]["usable_for_arithmetic"], k)
        self.assertTrue(rows["SYN-0001|2030-07"]["usable_for_arithmetic"])
        table = self.c["SYN-0001"]["trade_tables"][0]
        self.assertEqual(table["missing_months"], ["2031-01"])

    def test_missing_value_never_filled_from_volume(self):
        r = self.rows["SYN-0001|2030-10"]
        self.assertIsNone(r["value_amount"])
        self.assertEqual(r["volume_amount"], 2_000_000)

    # --- table inside a [Pn] paragraph ---
    def test_table_in_paragraph_cites_that_paragraph(self):
        r = self.rows["SYN-0002|2031-01"]
        self.assertEqual(r["paragraph"], "P2")
        self.assertFalse(r["synthetic_paragraph"])
        self.assertEqual((r["value_amount"], r["value_currency"]), (1_250_000_000, "USD"))
        self.assertAlmostEqual(r["volume_amount"], 9_000)          # 9,000,000 kg
        self.assertEqual((r["volume_unit"], r["volume_unit_raw"]), ("tonnes", "kg"))
        self.assertEqual(r["citation"]["text"], "[SYN-0002, P2, 2031-04-02 10:15]")

    # --- PDF prose note ---
    def test_pdf_prose_any_unit_and_wrapped_number(self):
        r = self.rows["SYN-0003|2031-03"]
        self.assertEqual((r["value_amount"], r["value_currency"]), (1_200_000_000, "USD"))
        self.assertEqual((r["volume_amount"], r["volume_unit"]), (4_500_000, "MMBtu"))
        r = self.rows["SYN-0003|2031-04"]
        self.assertEqual((r["value_amount"], r["value_currency"]), (950_000, "EUR"))
        self.assertEqual(r["volume_amount"], 61_000)

    def test_unparseable_prose_rows_flagged_not_guessed(self):
        r = self.rows["SYN-0003|2031-05"]
        self.assertIn("TRADE_ROW_MISSING_VALUE", r["flags"])
        self.assertIsNone(r["value_amount"])
        r = self.rows["SYN-0003|2031-06"]
        self.assertEqual(r["parse_status"], "invalid")
        self.assertIn("TRADE_ROW_INVALID", r["flags"])
        self.assertIsNone(r["value_amount"])
        self.assertIsNone(r["volume_amount"])
        self.assertIn("withheld", r["raw_text"])

    def test_sector_boost_not_filter(self):
        ix = CaseIndex(self.c, AS_OF, EVENT)
        ids = [h["doc_id"] for h in ix.search_docs("LNG value volume", sectors=["Wheat"], limit=20)]
        self.assertIn("SYN-0001", ids)
        self.assertIn("SYN-0003", ids)
        self.assertTrue(any(x["field"] == "SECTOR" for x in self.c["SYN-0003"]["metadata_conflicts"]))

    def test_word_boundary_names(self):
        self.assertFalse(mentions("Svelka Freight has chartered", "Velka"))
        ix = CaseIndex(self.c, AS_OF, EVENT)
        self.assertNotIn("SYN-0015", [h["doc_id"] for h in ix.search_docs("Velka", limit=50)])


class TradeGrammarUnits(unittest.TestCase):
    """Unit-agnostic value/volume grammar (review F02)."""

    def test_value_variants(self):
        cases = {
            "USD 62.1M": (62_100_000, "USD"), "$62.1M": (62_100_000, "USD"), "USD 1.2B": (1_200_000_000, "USD"),
            "EUR 4.5 bn": (4_500_000_000, "EUR"), "62.1 million US dollars": (62_100_000, "USD"),
            "RMK 300K": (300_000, "RMK"), "950 thousand euros": (950_000, "EUR"), "USD 1,250": (1_250, "USD"),
        }
        for text, (amount, cur) in cases.items():
            v = trade.parse_value(text)
            self.assertAlmostEqual(v["amount"], amount, msg=text)
            self.assertEqual(v["currency"], cur, text)

    def test_volume_variants(self):
        cases = {
            "146,000 tonnes": (146_000, "tonnes"), "146,000 t": (146_000, "tonnes"), "146,000 MT": (146_000, "tonnes"),
            "3,400,000 kg": (3_400, "tonnes"), "120 kt": (120_000, "tonnes"), "1.2 million MMBtu": (1_200_000, "MMBtu"),
            "40,000 units": (40_000, "units"), "12,000 tons": (12_000, "tons"),
        }
        for text, (amount, unit) in cases.items():
            v = trade.parse_volume(text)
            self.assertAlmostEqual(v["amount"], amount, msg=text)
            self.assertEqual(v["unit"], unit, text)

    def test_bad_and_missing(self):
        with self.assertRaises(trade.BadNumber):
            trade.parse_value("USD 6,21.0M")
        with self.assertRaises(LookupError):
            trade.parse_value("n/a")
        with self.assertRaises(KeyError):
            trade.parse_value("62.1")          # no currency: flagged, never assumed
        with self.assertRaises(KeyError):
            trade.parse_volume("146,000")      # no unit

    def test_wrapped_numbers_rejoined(self):
        self.assertEqual(trade.join_wrapped_numbers("was 43,\n000\ntonnes"), "was 43,000 tonnes")
        self.assertEqual(trade.join_wrapped_numbers("USD 62.\n1M"), "USD 62.1M")


if __name__ == "__main__":
    unittest.main()
