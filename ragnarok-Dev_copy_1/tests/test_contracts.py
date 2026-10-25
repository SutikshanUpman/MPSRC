"""Contracts (docs/CONTRACTS.md) and the OD-1 row-reference chain, checked on a mock E5 run. No network, no LLM."""
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
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_case  # noqa: E402
from backend import contracts  # noqa: E402
from backend.agents.heimdall import open_case  # noqa: E402
from backend.casefile.schema import CASE_FILE_SCHEMA  # noqa: E402
from backend.ingestion.packs import load_packs  # noqa: E402
from backend.ingestion.pipeline import ingest_pack  # noqa: E402
from backend.llm.provider import DeterministicMockProvider, validate_schema  # noqa: E402
from backend.provenance.citations import parse_citations, validate_citation  # noqa: E402
from backend.runtime.budget import BudgetGuard  # noqa: E402
from backend.runtime.config import load_config  # noqa: E402
from fixtures import synthetic_pack  # noqa: E402

PACK = Path(os.environ["RAGNAROK_PACK_DIR"]) if os.environ.get("RAGNAROK_PACK_DIR") else ROOT / "dev_pack_E5"
QUESTION = next(l for l in (PACK / "sample_question.txt").read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("QUESTION"))
AS_OF = "2027-01-25"
CONTRACTS_MD = ROOT / "docs" / "CONTRACTS.md"


def documented_list(name):
    text = CONTRACTS_MD.read_text(encoding="utf-8")
    block = re.search(rf"<!-- contract:{name} -->\s*```text\n(.*?)```", text, re.S)
    return [l.strip() for l in block.group(1).splitlines() if l.strip()]


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def resolve_row_ref(corpus, ref):
    """Follow a row ref back to its trade row: (doc_id, table_id, native_row_number) for a table row,
    (doc_id, row_key) for a prose row. Returns (row, paragraph text)."""
    rec = corpus.records[ref["doc_id"]]
    if ref["table_id"] is not None:
        rows = [r for r in rec["trade_rows"] if r["table_id"] == ref["table_id"] and r["native_row_number"] == ref["native_row_number"]]
    else:
        rows = [r for r in rec["trade_rows"] if r["row_key"] == ref["row_key"]]
    assert len(rows) == 1, (ref, len(rows))
    para = next(p for p in rec["paragraphs"] if p["id"] == ref["paragraph"])
    return rows[0], para["text"]


class ContractsOnMockE5Run(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp(prefix="contracts_")
        with contextlib.redirect_stdout(io.StringIO()):
            run_case.main(["--pack", str(PACK), "--question", QUESTION, "--out", cls.out,
                          "--memory-dir", str(Path(cls.out) / "_memory")])
        (case_dir,) = [d for d in Path(cls.out).iterdir() if d.name.startswith("case-")]
        cls.cf = json.loads((case_dir / "case_file.json").read_text(encoding="utf-8"))
        cls.cross = json.loads((case_dir / "cross_examination.json").read_text(encoding="utf-8"))
        cls.events = [json.loads(l) for l in (case_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        cls.corpus = ingest_pack(PACK)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_case_file_and_its_parts(self):
        self.assertEqual(validate_schema(self.cf, CASE_FILE_SCHEMA), [])
        for cell in self.cf["exposure_cells"]:
            self.assertEqual(validate_schema(cell, contracts.EXPOSURE_CELL_SCHEMA), [])
        self.assertEqual(validate_schema(self.cf["evidence_packet"], contracts.EVIDENCE_PACKET_SCHEMA), [])
        for run in self.cf["run_status"]:
            self.assertEqual(validate_schema(run, contracts.RUN_RECORD_SCHEMA), [])

    def test_round_2_structures(self):
        # Stage 3 B7: challenge, response and revised estimate, as written by the runner.
        self.assertEqual(self.cross, self.cf["cross_examination"])
        self.assertTrue(self.cross)
        for x in self.cross:
            self.assertEqual(validate_schema(x, contracts.CROSS_EXAMINATION_SCHEMA), [])
            self.assertEqual(validate_schema({k: v for k, v in x.items() if k != "response"}, contracts.CHALLENGE_SCHEMA), [])
            self.assertEqual(validate_schema(x["response"], contracts.RESPONSE_SCHEMA), [])
        claims = {c["claim_id"]: c for c in self.cf["claim_ledger"]}
        revised = [c for c in claims.values() if c["round"] == 2]
        self.assertTrue(revised)
        for c in claims.values():
            self.assertEqual(validate_schema(c, contracts.LEDGER_CLAIM_SCHEMA), [])
        for c in revised:
            self.assertEqual(claims[c["supersedes"]]["superseded_by"], c["claim_id"])

    def test_trace_events(self):
        self.assertTrue(self.events)
        for e in self.events:
            self.assertEqual(contracts.trace_event_problems(e), [], e["event_type"])
        self.assertEqual([e["sequence"] for e in self.events], list(range(1, len(self.events) + 1)))
        self.assertTrue([e for e in self.events if e["event_type"] == "SEARCH_COMPLETED"])

    def test_trade_rows_e5_and_synthetic(self):
        for r in self.corpus.trade_rows():
            self.assertEqual(validate_schema(r, contracts.TRADE_ROW_SCHEMA), [], r["row_key"])
        tmp = tempfile.mkdtemp(prefix="contracts_syn_")
        self.addCleanup(shutil.rmtree, tmp, True)
        syn = ingest_pack(synthetic_pack.build(tmp))
        layouts = set()
        for r in syn.trade_rows():
            self.assertEqual(validate_schema(r, contracts.TRADE_ROW_SCHEMA), [], r["row_key"])
            layouts.add(r["source_layout"])
        self.assertEqual(layouts, {"prose_note", "fixed_table"})

    def test_trade_row_evidence_carries_row_refs(self):
        items = [e for c in self.cf["coverage"] for chk in c["checks"].values() for e in chk["evidence"] if e["kind"] == "trade_row"]
        self.assertTrue(items)
        for item in items:
            self.assertEqual(validate_schema(item, contracts.ROW_REF_SCHEMA), [], item["citation"])

    def test_provider_and_budget_records(self):
        config = load_config()
        provider, guard = DeterministicMockProvider(config), BudgetGuard(config, billable=False)
        guard.call(provider, "heimdall", [{"role": "user", "content": "contract check"}], {"type": "object"})
        self.assertEqual(validate_schema(provider.calls[0], contracts.PROVIDER_CALL_SCHEMA), [])
        self.assertEqual(validate_schema(guard.calls[0], contracts.BUDGET_CALL_SCHEMA), [])

    def test_contracts_doc_matches_code(self):
        self.assertEqual(documented_list("case_file_fields"), CASE_FILE_SCHEMA["required"])
        self.assertEqual(documented_list("event_types"), contracts.EVENT_TYPES)


class OD1RowChain(unittest.TestCase):
    """Trade row -> Case File row ref -> citation: the bracket validates and the ref resolves to the exact row text.
    The chain also runs from a round-2 revised claim through its calc_id to the rows (Stage 3 B7). Briefing row_refs
    and the source-span API are not built yet (docs/CONTRACTS.md, TODO)."""

    def test_chain_through_a_revised_claim(self):
        from backend.agents.counsel import run_round1
        from backend.agents.cross_exam import run_round2
        from backend.llm.provider import make_provider
        config = load_config()
        provider = make_provider("mock", config)
        tmp = tempfile.mkdtemp(prefix="rowchain_")
        self.addCleanup(shutil.rmtree, tmp, True)
        cf, trace, guard = open_case(QUESTION, [PACK], config, provider)
        sides = run_round1(cf, provider, config, trace, memory_root=Path(tmp) / "mem", guard=guard)
        run_round2(cf, sides, provider, config, trace, guard)
        corpus = ingest_pack(PACK)
        revised = next(c for c in cf["claim_ledger"] if c["round"] == 2 and c["estimate"])
        calc = next(r for r in cf["calc_ledger"] if r["calc_id"] == revised["calc_ids"][0])
        self.assertEqual(calc["round"], 2)
        for ref in calc["direct_inputs"] + calc["substitute_inputs"]:
            (bracket,) = parse_citations(ref["citation"])
            self.assertEqual(validate_citation(bracket, corpus, AS_OF), [])
            row, para_text = resolve_row_ref(corpus, ref)
            self.assertEqual(row["citation"]["text"], ref["citation"])
            self.assertIn(norm(row["raw_text"]), norm(para_text))
        for cit in revised["citations"]:
            self.assertIn(cit, {r["citation"] for r in calc["direct_inputs"] + calc["substitute_inputs"]})

    def test_e5_prose_row(self):
        config = load_config()
        cf, _, _ = open_case(QUESTION, [PACK], config, DeterministicMockProvider(config))
        corpus = ingest_pack(PACK)
        cell = next(c for c in cf["coverage"] if (c["country"], c["sector"]) == ("Midgard", "Wheat"))
        ref = cell["checks"]["direct_flow"]["evidence"][0]
        self.assertEqual(ref["doc_id"], "ORV-0009")
        (bracket,) = parse_citations(ref["citation"])
        self.assertEqual(validate_citation(bracket, corpus, AS_OF), [])
        self.assertEqual(bracket["paragraph"], ref["paragraph"])
        row, para_text = resolve_row_ref(corpus, ref)
        self.assertEqual(row["row_key"], ref["row_key"])
        self.assertEqual(row["citation"]["text"], ref["citation"])
        self.assertIn(norm(row["raw_text"]), norm(para_text))
        self.assertEqual(row["raw_text"], "In July 2026, the value was USD 90.0M and the volume was 250,000 tonnes.")

    def test_synthetic_fixed_table_row(self):
        tmp = tempfile.mkdtemp(prefix="od1_")
        self.addCleanup(shutil.rmtree, tmp, True)
        base = synthetic_pack.build(Path(tmp) / "base")
        question = "As of 30 June 2031, how exposed are importers to the Velka canal closure? Give a range for LNG imports."
        cf, _, _ = open_case(question, [base], load_config())
        corpus, _, _ = load_packs([base])
        # Case File link: SYN-0002's table sits in [P2] and has row numbers but no TABLE_ID header.
        cell = next(c for c in cf["coverage"] if (c["country"], c["sector"]) == ("Osk", "LNG"))
        ref = next(e for e in cell["checks"]["direct_flow"]["evidence"] if e["source_layout"] == "fixed_table")
        self.assertEqual(validate_schema(ref, contracts.ROW_REF_SCHEMA), [])
        self.assertEqual((ref["doc_id"], ref["paragraph"], ref["table_id"]), ("SYN-0002", "P2", None))
        self.assertIsNotNone(ref["native_row_number"])
        (bracket,) = parse_citations(ref["citation"])
        self.assertEqual(validate_citation(bracket, corpus, synthetic_pack.AS_OF), [])
        row, para_text = resolve_row_ref(corpus, ref)
        self.assertEqual(row["native_row_number"], ref["native_row_number"])
        self.assertIn(norm(row["raw_text"]), norm(para_text))
        # Ingestion link for a table WITH a table ID (SYN-0001, T-0077; quarantined from cases for its hash mismatch).
        row5 = next(r for r in corpus["SYN-0001"]["trade_rows"] if r["native_row_number"] == 5)
        ref5 = {"doc_id": "SYN-0001", "paragraph": row5["paragraph"], "table_id": row5["table_id"],
                "native_row_number": 5, "row_key": row5["row_key"]}
        self.assertEqual(row5["table_id"], "T-0077")
        self.assertNotIn("T-0077", row5["citation"]["text"])       # OD-1: no table ID inside the bracket
        (bracket5,) = parse_citations(row5["citation"]["text"])
        self.assertEqual(validate_citation(bracket5, corpus, synthetic_pack.AS_OF), [])
        found, para_text5 = resolve_row_ref(corpus, ref5)
        self.assertEqual(found["raw_text"], "5 | 2030-11 | 4O.1 | 1,900,000")
        self.assertIn(norm(found["raw_text"]), norm(para_text5))


if __name__ == "__main__":
    unittest.main()
