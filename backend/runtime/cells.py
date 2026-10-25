"""Cell budget rule (SYSTEM_ARCHITECTURE 17), with the manager's re-projection decision.

Cells are ranked once (in-scope trade rows, then event-document mentions, then
question order, then alphabetical) and split into batches of
`max_cells_per_agent_step`. Before each batch the guard projects spend so far
plus the worst case of that batch only. The first batch that does not fit, and
every batch after it, is marked INCOMPLETE_BUDGET_LIMIT. No cell is dropped.
"""

PENDING, ASSESSED, BUDGET_LIMIT = "PENDING", "ASSESSED", "INCOMPLETE_BUDGET_LIMIT"


def rank_cells(cells, trade_rows_per_cell, doc_mentions_per_cell):
    """cells: [(country, sector)] in question order. Returns plan entries sorted by rank."""
    order = {c: i for i, c in enumerate(cells)}
    ranked = sorted(cells, key=lambda c: (-trade_rows_per_cell.get(c, 0), -doc_mentions_per_cell.get(c, 0),
                                          order[c], c[0].lower(), c[1].lower()))
    return [{"country": c[0], "sector": c[1], "rank": i + 1,
             "rank_inputs": {"trade_rows": trade_rows_per_cell.get(c, 0), "doc_mentions": doc_mentions_per_cell.get(c, 0),
                             "question_order": order[c] + 1},
             "batch": None, "cell_status": PENDING} for i, c in enumerate(ranked)]


def assign_batches(plan, size):
    for i, cell in enumerate(plan):
        cell["batch"] = i // size + 1
    return plan


def next_batch(plan, guard, rounds=2):
    """Return (batch_number, cells) for the next PENDING batch if the guard can afford it.

    If it cannot, every PENDING cell is marked INCOMPLETE_BUDGET_LIMIT and (None, []) is
    returned. The caller marks a processed batch ASSESSED and calls this again.
    """
    pending = [c for c in plan if c["cell_status"] == PENDING]
    if not pending:
        return None, []
    number = min(c["batch"] for c in pending)
    if guard.can_afford_cell_batch(rounds):
        return number, [c for c in pending if c["batch"] == number]
    for c in pending:
        c["cell_status"] = BUDGET_LIMIT
    return None, []


def mark(plan, batch_number, status):
    for c in plan:
        if c["batch"] == batch_number and c["cell_status"] == PENDING:
            c["cell_status"] = status


def cell_input_tokens(cell, estimates):
    """Projected input tokens one cell adds to the last turn of a Thor/Loki step (config batch_token_estimates)."""
    return (cell["rank_inputs"]["trade_rows"] * estimates["per_trade_row"] + estimates["per_search_result_set"]
            + estimates["per_calc_view"] + estimates["per_cell_turn_outputs"])


def resize_batches(plan, base_tokens, input_cap, share, max_cells, estimates):
    """Stage 3 A4: re-batch PENDING cells in rank order so no step's projected input exceeds share x input_cap.
    A batch holds at most max_cells and at least one cell. Returns (resized?, per-batch projections)."""
    target = share * input_cap
    pending = sorted((c for c in plan if c["cell_status"] == PENDING), key=lambda c: c["rank"])
    before = [c["batch"] for c in pending]
    first = min(before) if before else 1
    batches, current, tokens = [], [], base_tokens
    for c in pending:
        add = cell_input_tokens(c, estimates)
        if current and (len(current) >= max_cells or tokens + add > target):
            batches.append((current, tokens))
            current, tokens = [], base_tokens
        current.append(c)
        tokens += add
    if current:
        batches.append((current, tokens))
    for i, (cells, _) in enumerate(batches):
        for c in cells:
            c["batch"] = first + i
    projections = [{"batch": first + i, "cells": [[c["country"], c["sector"]] for c in cells],
                    "projected_input_tokens": tokens, "target_tokens": int(target)} for i, (cells, tokens) in enumerate(batches)]
    return before != [c["batch"] for c in pending], projections
