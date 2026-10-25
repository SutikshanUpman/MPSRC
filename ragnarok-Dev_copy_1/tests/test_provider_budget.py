"""Provider boundary, config derivation, budget guard and cell re-projection. No network, no API client."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.llm.provider import (AnthropicProvider, DeterministicMockProvider, LiveCallsDisabled,  # noqa: E402
                                  SchemaError, make_provider)
from backend.runtime import cells  # noqa: E402
from backend.runtime.budget import BudgetExceeded, BudgetGuard  # noqa: E402
from backend.runtime.config import ConfigError, DEFAULT_PATH, load_config  # noqa: E402

SCHEMA = {"type": "object", "required": ["verdict", "doc_ids"], "additionalProperties": False,
          "properties": {"verdict": {"type": "string", "enum": ["VERIFIED", "EVENT_REJECTED"]},
                         "doc_ids": {"type": "array", "items": {"type": "string"}}}}
MESSAGES = [{"role": "user", "content": "Is the event verified?"}]


class ConfigDerivation(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_reserve_is_derived_from_caps_and_prices(self):
        self.assertAlmostEqual(self.config.worst_case("odin_ruling"), 0.108)
        self.assertAlmostEqual(self.config.worst_case("odin_briefing"), 0.092)
        self.assertAlmostEqual(self.config.odin_briefing_reserve_usd, 0.200)
        self.assertAlmostEqual(self.config.htl_minimum_usd, 0.0528)
        self.assertAlmostEqual(self.config.check_live_case()["odin_briefing_reserve_usd"], 0.200)

    def test_live_case_refused_when_reserve_leaves_too_little(self):
        with self.assertRaises(ConfigError):
            load_config(overrides={"per_case_cap_usd": 0.20}).check_live_case()

    def test_hand_set_reserve_is_rejected(self):
        data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
        data["odin_briefing_reserve_usd"] = 0.10
        path = Path(tempfile.mkdtemp()) / "cfg.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_tunable_keys_exist(self):
        for key in self.config["_tunable_unverified"]:
            self.assertIn(key, self.config.data, key)


class Providers(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_mock_is_deterministic_and_logs_every_call(self):
        log = Path(tempfile.mkdtemp()) / "calls.jsonl"
        p = DeterministicMockProvider(self.config, call_log_path=log)
        a = p.complete("heimdall", MESSAGES, SCHEMA)
        b = p.complete("heimdall", MESSAGES, SCHEMA)
        self.assertEqual(a, b)
        self.assertEqual(a["output"], {"verdict": "VERIFIED", "doc_ids": []})
        self.assertEqual(a["model"], self.config.model_for("heimdall"))
        self.assertEqual([c["seq"] for c in p.calls], [1, 2])
        self.assertEqual(p.calls[0]["input_hash"], p.calls[1]["input_hash"])
        lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([l["role"] for l in lines], ["heimdall", "heimdall"])
        self.assertGreater(lines[0]["input_tokens_est"], 0)

    def test_mock_responder_output_is_schema_checked(self):
        good = DeterministicMockProvider(self.config, {"heimdall": lambda r, m, s: {"verdict": "EVENT_REJECTED", "doc_ids": ["X-1"]}})
        self.assertEqual(good.complete("heimdall", MESSAGES, SCHEMA)["output"]["verdict"], "EVENT_REJECTED")
        bad = DeterministicMockProvider(self.config, {"heimdall": lambda r, m, s: {"verdict": "MAYBE"}})
        with self.assertRaises(SchemaError):
            bad.complete("heimdall", MESSAGES, SCHEMA)

    def test_anthropic_provider_raises_without_live_flag(self):
        with self.assertRaises(LiveCallsDisabled):
            AnthropicProvider(self.config)
        with self.assertRaises(LiveCallsDisabled):
            make_provider("anthropic", self.config)
        no_owner = load_config(overrides={"live": {"enabled": True, "budget_owner": ""}})
        with self.assertRaises(LiveCallsDisabled):
            AnthropicProvider(no_owner)
        self.assertNotIn("anthropic", sys.modules)


class Guard(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_reserve_is_protected(self):
        g = BudgetGuard(self.config)
        g.case_spent = 0.295      # general pool is per_case_cap - reserve = 0.30; one Thor step's worst case is 0.0088
        self.assertFalse(g.can_afford("thor"))
        self.assertTrue(g._fits("odin_briefing", self.config.worst_case("odin_briefing")))
        self.assertTrue(g._fits("odin_ruling", self.config.worst_case("odin_ruling"), final_ruling=True))
        self.assertFalse(g._fits("odin_ruling", self.config.worst_case("odin_ruling"), final_ruling=False))

    def test_final_ruling_cannot_eat_the_briefing_slice(self):
        g = BudgetGuard(self.config)
        g.case_spent = 0.40       # final ruling limit is 0.50 - 0.092 = 0.408, so a 0.108 ruling no longer fits
        self.assertFalse(g._fits("odin_ruling", self.config.worst_case("odin_ruling"), final_ruling=True))
        self.assertTrue(g._fits("odin_briefing", self.config.worst_case("odin_briefing")))

    def test_call_goes_through_the_guard_and_records_usage(self):
        g = BudgetGuard(self.config, billable=False)
        p = DeterministicMockProvider(self.config)
        g.call(p, "heimdall", MESSAGES, SCHEMA)
        self.assertEqual(len(g.calls), 1)
        self.assertEqual(g.calls[0]["cost_usd"], 0.0)
        self.assertGreater(g.calls[0]["shadow_cost_usd"], 0.0)
        g.case_spent = 0.5
        with self.assertRaises(BudgetExceeded):
            g.call(p, "thor", MESSAGES, SCHEMA)
        self.assertEqual(len(p.calls), 1)

    def test_development_mode_never_touches_the_final_round_reserve(self):
        g = BudgetGuard(self.config, project_spent=1.495)
        self.assertAlmostEqual(g.project_limit(), 1.50)
        self.assertFalse(g.can_afford("thor"))


class CellReprojection(unittest.TestCase):
    def test_reproject_after_every_batch_and_never_drop_a_cell(self):
        config = load_config(overrides={"max_cells_per_agent_step": 2})
        g = BudgetGuard(config)
        names = [("A", "x"), ("B", "x"), ("C", "x"), ("D", "x"), ("E", "x")]
        plan = cells.assign_batches(cells.rank_cells(names, {("C", "x"): 5}, {}), 2)
        self.assertEqual(plan[0]["country"], "C")
        self.assertEqual([p["batch"] for p in plan], [1, 1, 2, 2, 3])
        number, batch = cells.next_batch(plan, g)
        self.assertEqual((number, len(batch)), (1, 2))
        cells.mark(plan, number, cells.ASSESSED)
        g.case_spent = 0.29                       # spend so far leaves less than one batch's worst case
        self.assertEqual(cells.next_batch(plan, g), (None, []))
        self.assertEqual([p["cell_status"] for p in plan],
                         ["ASSESSED", "ASSESSED"] + ["INCOMPLETE_BUDGET_LIMIT"] * 3)
        self.assertEqual(len(plan), 5)


if __name__ == "__main__":
    unittest.main()
