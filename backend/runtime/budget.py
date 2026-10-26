"""Minimal budget guard (SYSTEM_ARCHITECTURE 17; the full persisted ledger is Stage 5).

Projection = actual spend so far + worst case of the NEXT batch only
(manager decision: re-project after every batch, never the whole run up front).

Reserve protection: `odin_briefing_reserve_usd` (derived in config.py) can be
spent only by Odin's final ruling and the briefing. The briefing may use the
whole reserve; the final ruling only down to the briefing's worst case; every
other call stops at `per_case_cap_usd - odin_briefing_reserve_usd`.

A provider that is not billable (Ollama, a localhost server, replay) records its calls with `cost_usd: 0` and
a `shadow_cost_usd` at configured prices, so the guard logic stays observable.
"""
from ..llm.provider import SchemaError, message_tokens, validate_schema


class BudgetExceeded(RuntimeError):
    pass


class BudgetGuard:
    def __init__(self, config, billable=True, mode=None, project_spent=0.0):
        self.config = config
        self.billable = billable
        self.mode = mode or config.get("budget_mode", "development")
        self.case_cap = config["per_case_cap_usd"]
        self.reserve = config.odin_briefing_reserve_usd
        self.case_spent = 0.0
        self.project_spent = project_spent
        self.shadow_spent = 0.0
        self.calls = []
        self.refusals = []
        self.chars_per_token = {}      # model -> observed ratios from live usage (calibration hook, not used yet)

    # ---------- limits ----------
    def case_limit(self, role, final_ruling=False):
        if role == "odin_briefing":
            return self.case_cap
        if role == "odin_ruling" and final_ruling:
            return self.case_cap - self.config.worst_case("odin_briefing")
        return self.case_cap - self.reserve

    def project_limit(self):
        cap = self.config["project_cap_usd"]
        return cap - self.config["final_round_reserve_usd"] if self.mode == "development" else cap

    def _fits(self, role, extra, final_ruling=False):
        return (self.case_spent + extra <= self.case_limit(role, final_ruling) + 1e-12
                and self.project_spent + extra <= self.project_limit() + 1e-12)

    # ---------- projections ----------
    def batch_worst_case(self, role, batch=1):
        """`batch` = agent steps for `role` in the next batch; each step may use every allowed model turn."""
        return batch * self.config["max_model_turns_per_agent_step"] * self.config.worst_case(role)

    def can_afford(self, role, batch=1, final_ruling=False):
        return self._fits(role, self.batch_worst_case(role, batch), final_ruling)

    def cell_batch_worst_case(self, rounds=2):
        """Next cell batch: one Thor step and one Loki step per round."""
        return self.batch_worst_case("thor", rounds) + self.batch_worst_case("loki", rounds)

    def can_afford_cell_batch(self, rounds=2):
        return self._fits("thor", self.cell_batch_worst_case(rounds))

    def projection(self, rounds=2):
        return {"case_spent_usd": self.case_spent, "next_cell_batch_worst_case_usd": self.cell_batch_worst_case(rounds),
                "case_limit_usd": self.case_limit("thor"), "odin_briefing_reserve_usd": self.reserve,
                "project_spent_usd": self.project_spent, "project_limit_usd": self.project_limit(), "mode": self.mode}

    # ---------- calls ----------
    def record(self, role, model, usage, provider="local", input_chars=None):
        cost = self.config.call_cost(role, usage["input_tokens"], usage["output_tokens"])
        entry = {"role": role, "model": model, "provider": provider, "input_tokens": usage["input_tokens"],
                 "output_tokens": usage["output_tokens"], "cost_usd": cost if self.billable else 0.0,
                 "shadow_cost_usd": cost}
        # Stage 3 A4 calibration hook: a live (billable) usage record carries the provider's real token count, so the
        # observed characters per token are kept per model for future estimates. Mock counts are estimates: skipped.
        if self.billable and input_chars and usage["input_tokens"]:
            entry["observed_chars_per_token"] = round(input_chars / usage["input_tokens"], 3)
            self.chars_per_token.setdefault(model, []).append(entry["observed_chars_per_token"])
        if self.billable:
            self.case_spent += cost
            self.project_spent += cost
        self.shadow_spent += cost
        self.calls.append(entry)
        return entry

    def observed_chars_per_token(self, model):
        """Mean observed ratio for a model, or None (no live usage yet). Not used by any estimate yet."""
        seen = self.chars_per_token.get(model)
        return round(sum(seen) / len(seen), 3) if seen else None

    def call(self, provider, role, messages, schema, final_ruling=False):
        """The only way agents reach a provider: check the worst case, call, record actual usage, then
        schema-check the output (SchemaError after the spend is recorded, whatever the provider)."""
        worst = self.config.worst_case(role, message_tokens(messages))
        if not self._fits(role, worst, final_ruling):
            self.refusals.append({"role": role, "worst_case_usd": worst, "case_spent_usd": self.case_spent})
            raise BudgetExceeded(f"BUDGET_CAP_REACHED for {role}: worst case {worst:.4f} does not fit")
        result = provider.complete(role, messages, schema, self.config.caps(role)["max_output_tokens"])
        self.record(role, result["model"], result["usage"], provider.name,
                    input_chars=sum(len(m["content"]) for m in messages))
        problems = validate_schema(result["output"], schema)
        if problems:
            raise SchemaError("; ".join(problems[:20]))
        return result
