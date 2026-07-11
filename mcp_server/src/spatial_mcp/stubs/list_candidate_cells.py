"""Stub: list_candidate_cells — swap this file for real teammate logic."""

from __future__ import annotations

from typing import Any

from spatial_mcp.fixtures.cells import cells_for_sample, public_cell, SAMPLE_META


def list_candidate_cells(args: dict[str, Any]) -> dict[str, Any]:
    sample_id = args["sample_id"]
    if sample_id not in SAMPLE_META:
        return {
            "sample_id": sample_id,
            "cells": [],
            "warning": f"Unknown sample_id '{sample_id}'. Known: {sorted(SAMPLE_META)}",
        }

    cells = cells_for_sample(sample_id)
    niche = args.get("niche")
    cell_type = args.get("cell_type")
    min_score = args.get("min_exhaustion_score")

    out = []
    for c in cells:
        if niche is not None and c["niche"] != niche:
            continue
        if cell_type is not None and c["cell_type"] != cell_type:
            continue
        if min_score is not None and c["exhaustion_score"] < min_score:
            continue
        out.append(public_cell(c))

    # Rank most exhausted first — useful default for the agent
    out.sort(key=lambda c: c["exhaustion_score"], reverse=True)
    return {"sample_id": sample_id, "n": len(out), "cells": out}
