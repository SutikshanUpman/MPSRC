"""Tools for Thor and Loki (SYSTEM_ARCHITECTURE 16; Stage 2 B1, B2).

One AgentTools per agent per case. Everything goes through the case scope:
CaseIndex is built on case_scope(), so the as-of gate and the event scope (two
mandatory metadata filters) apply to every search and every trade-row lookup.

- search: logged (agent, query, filters, result spans). An exact repeat by the
  same agent in the same case is served from the cache and logged as
  SEARCH_CACHE_HIT; it never runs a second search.
- get_document: masked paragraphs of one in-scope document (DOCUMENT_RETRIEVED).
- get_trade_rows: route rows for cells, labelled direct (event origin) or substitute.
- calc: deterministic calc records (backend/agents/calc.py), stored for the Case File; the
  F11 cross-check statements it reads are returned, so they count as retrieved.
Every span or row an agent sees is recorded in `retrieved`; claims may cite only those.
Caps (config): max_tool_calls_per_agent_step, max_searches_per_agent_per_run.
"""
import json

from ..provenance.citations import format_citation
from . import calc as calc_mod


def _key(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class AgentTools:
    def __init__(self, agent, cf, corpus, index, config, trace, run_number=1):
        self.agent, self.cf, self.corpus, self.index, self.config, self.trace = agent, cf, corpus, index, config, trace
        self.run_number = run_number
        self.origins = {o.lower() for o in (cf["manifest_scope"] or {}).get("event_origins", [])}
        self.cache, self.search_log, self.retrieved, self.rows_seen, self.calcs = {}, [], {}, {}, []
        self.searches = self.cache_hits = self.tool_calls = self.step_calls = 0
        self.total_searches = 0
        self.search_cap = config["max_searches_per_agent_per_run"]
        self.round = 1
        self.retrieved_rounds = {}      # citation -> rounds in which a tool (not a cache hit) returned it

    def _saw(self, citation, span):
        self.retrieved[citation] = span
        self.retrieved_rounds.setdefault(citation, set()).add(self.round)

    def retrieved_in(self, round_number):
        return {c for c, rounds in self.retrieved_rounds.items() if round_number in rounds}

    def begin_step(self):
        self.step_calls = 0

    def _filters(self, countries, sectors):
        return {"event_scope": [self.cf["event_id"], "NONE"], "published_before_or_on": self.cf["as_of_date"],
                "countries": countries or [], "sector_boost": sectors or []}

    def execute(self, call):
        if not isinstance(call, dict):
            return {"tool": None, "args": None, "error": "a tool call is an object with `tool` and `args`"}
        tool, args = call.get("tool"), call.get("args") or {}
        self.step_calls += 1
        self.tool_calls += 1
        if self.step_calls > self.config["max_tool_calls_per_agent_step"]:
            self.trace.emit(self.agent, "TOOL_LIMIT_REACHED", {"tool": tool, "step_calls": self.step_calls}, "WARNING")
            return {"tool": tool, "args": args, "error": "TOOL_LIMIT_REACHED: submit now"}
        try:
            if tool == "search":
                result = self.search(args["query"], args.get("countries"), args.get("sectors"), args.get("limit", 5))
            elif tool == "get_document":
                result = self.get_document(args["doc_id"], args.get("paragraphs"))
            elif tool == "get_trade_rows":
                result = self.get_trade_rows(args["cells"])
            elif tool == "calc":
                result = self.calc(args["cells"])
            else:
                return {"tool": tool, "args": args, "error": f"unknown tool {tool!r}"}
        except (KeyError, TypeError, AttributeError, ValueError, IndexError) as e:   # a model's arguments are untrusted: an error result, never a crash
            return {"tool": tool, "args": args, "error": f"bad arguments: {type(e).__name__}: {e}"}
        return {"tool": tool, "args": args, "result": result}

    # ---------- search ----------
    def search(self, query, countries=None, sectors=None, limit=5):
        filters = self._filters(countries, sectors)
        key = _key({"query": query, "filters": filters, "limit": limit})
        if key in self.cache:
            self.cache_hits += 1
            entry = {"agent": self.agent, "query": query, "filters": filters, "cache_hit": True,
                     "result_doc_ids": [s["doc_id"] for s in self.cache[key]],
                     "spans": [s["citation"] for s in self.cache[key]]}
            self.search_log.append(entry)
            self.trace.emit(self.agent, "SEARCH_CACHE_HIT", entry)
            return self.cache[key]
        if self.searches >= self.search_cap:
            self.trace.emit(self.agent, "SEARCH_LIMIT_REACHED", {"query": query, "searches": self.searches}, "WARNING")
            return {"error": "SEARCH_LIMIT_REACHED"}
        self.searches += 1
        self.total_searches += 1
        spans = []
        for h in self.index.search_docs(query, countries=countries, sectors=sectors, limit=limit):
            rec = self.corpus.records[h["doc_id"]]
            span = {"doc_id": h["doc_id"], "paragraph": h["paragraph"],
                    "citation": format_citation(h["doc_id"], h["paragraph"], rec["pub_date"], rec["pub_time"]),
                    "title": h["title"], "text": h["text"], "tier": h["reliability"], "event_id": h["event_id"],
                    "source_type": h["source_type"], "context_only": h["context_only"],
                    "evidence_family_id": h["evidence_family_id"]}
            spans.append(span)
            self._saw(span["citation"], {"doc_id": span["doc_id"], "paragraph": span["paragraph"], "text": span["text"]})
        self.cache[key] = spans
        entry = {"agent": self.agent, "query": query, "filters": filters, "cache_hit": False,
                 "result_doc_ids": [s["doc_id"] for s in spans], "spans": [s["citation"] for s in spans]}
        self.search_log.append(entry)
        self.trace.emit(self.agent, "SEARCH_EXECUTED", entry)
        return spans

    # ---------- document ----------
    def get_document(self, doc_id, paragraphs=None):
        """Masked paragraphs of one in-scope document (all, or the listed P# ids); each becomes retrieved."""
        if doc_id not in self.index.eligible_ids:
            self.trace.emit(self.agent, "DOCUMENT_RETRIEVED", {"doc_id": doc_id, "spans": [], "error": "OUT_OF_CASE_SCOPE"},
                            "WARNING")
            return {"error": f"{doc_id} is not in the case scope"}
        rec = self.corpus.records[doc_id]
        wanted = set(paragraphs or [])
        spans = []
        for p in rec["paragraphs"]:
            if wanted and p["id"] not in wanted:
                continue
            cite = format_citation(doc_id, p["id"], rec["pub_date"], rec["pub_time"])
            self._saw(cite, {"doc_id": doc_id, "paragraph": p["id"], "text": p["text_masked"]})
            spans.append({"paragraph": p["id"], "citation": cite, "text": p["text_masked"]})
        self.trace.emit(self.agent, "DOCUMENT_RETRIEVED", {"doc_id": doc_id, "spans": [s["citation"] for s in spans]})
        return {"doc_id": doc_id, "title": rec["agent_title"], "tier": rec["reliability"], "event_id": rec["event_id"],
                "source_type": rec["source_type"], "context_only": rec["background_only"], "pub_date": rec["pub_date"],
                "paragraphs": spans}

    # ---------- trade rows ----------
    def get_trade_rows(self, cells):
        out = []
        for cell in cells:
            country, sector = cell["country"], cell["sector"]
            rows = []
            for rec in self.index.eligible:
                for r in rec["trade_rows"]:
                    if not (r["origin"] and (r["destination"] or "").lower() == country.lower()
                            and (r["sector"] or "").lower() == sector.lower()):
                        continue
                    self.rows_seen[r["row_key"]] = r
                    para_text = next((p["text_masked"] for p in rec["paragraphs"] if p["id"] == r["paragraph"]), "")
                    self._saw(r["citation"]["text"], {"doc_id": rec["doc_id"], "paragraph": r["paragraph"], "text": para_text})
                    # Compact on purpose (input cap): row_key carries the doc_id; OD-1 table fields only for tables.
                    row = {"row_key": r["row_key"], "role": "direct" if r["origin"].lower() in self.origins else "substitute",
                           "origin": r["origin"], "month": r["month"], "value_amount": r["value_amount"],
                           "value_currency": r["value_currency"], "volume_amount": r["volume_amount"],
                           "volume_unit": r["volume_unit"], "usable_for_arithmetic": r["usable_for_arithmetic"],
                           "flags": list(r["flags"]), "citation": r["citation"]["text"]}
                    if r["table_id"] is not None or r["native_row_number"] is not None:
                        row.update(table_id=r["table_id"], native_row_number=r["native_row_number"])
                    rows.append(row)
            rows.sort(key=lambda x: x["row_key"])
            out.append({"country": country, "sector": sector, "rows": rows})
        self.trace.emit(self.agent, "TOOL_CALLED", {"tool": "get_trade_rows", "cells": [[c["country"], c["sector"]] for c in cells],
                                                     "row_count": sum(len(c["rows"]) for c in out)})
        return out

    # ---------- calc ----------
    def calc(self, cells):
        out = []
        verification = self.cf["event_verification"] or {}
        credits = self.config["calc_substitute_credit"]
        for cell in cells:
            keys = list(cell.get("direct_row_keys", [])) + list(cell.get("substitute_row_keys", []))
            unseen = [k for k in keys if k not in self.rows_seen]
            if unseen:
                out.append({"country": cell["country"], "sector": cell["sector"], "error": f"rows not retrieved: {unseen}"})
                continue
            calc_id = f"calc-r{self.run_number}-{self.agent}-{len(self.calcs) + 1:02d}"
            record = calc_mod.compute_cell(
                calc_id, self.agent, cell["country"], cell["sector"],
                [self.rows_seen[k] for k in cell.get("direct_row_keys", [])],
                [self.rows_seen[k] for k in cell.get("substitute_row_keys", [])],
                verification.get("event_month"), self.cf["as_of_date"], credits,
                crosscheck_records=self.index.eligible, origins=sorted(self.origins), event_id=self.cf["event_id"],
                tolerance=self.config["baseline_crosscheck_tolerance_pct_points"])
            # The cross-check statements used are part of the tool result, so this agent has retrieved them.
            for ref in record["crosscheck_refs"]:
                rec = self.corpus.records[ref["doc_id"]]
                text = next(p["text_masked"] for p in rec["paragraphs"] if p["id"] == ref["paragraph"])
                self._saw(ref["citation"], {"doc_id": ref["doc_id"], "paragraph": ref["paragraph"], "text": text})
            record["round"] = self.round
            self.calcs.append(record)
            self.trace.emit(self.agent, "CALC_COMPUTED", {"calc_id": calc_id, "country": cell["country"], "sector": cell["sector"],
                                                          "status": record["status"], "widened": record["widened"],
                                                          "crosscheck": record["crosscheck"],
                                                          "baseline_flags": record["baseline_flags"]})
            out.append(calc_mod.agent_view(record))
        return out

    def search_total(self):
        return self.total_searches

    def calc_by_id(self, calc_id):
        return next((c for c in self.calcs if c["calc_id"] == calc_id), None)
