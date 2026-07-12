"""simulate_perturbations — scLDM-CD4 counterfactual (from evaluate_knockout_effect.ipynb).

Pipeline (notebook §§4–7):
  1. Resolve gene symbol → Ensembl
  2. Generate KO vs non-targeting-control populations (live scLDM, or surrogate)
  3. Pseudobulk Δ = mean(KO) − mean(control)
  4. Apply Δ to the selected spatial cell's marker panel → before / after / deltas

Set SCLDM_ROOT (and optionally SCLDM_CHECKPOINT) to use live weights; otherwise
a notebook-faithful surrogate runs so the MCP contract stays demoable.
"""

from __future__ import annotations

from typing import Any

from spatial_mcp.fixtures.cells import MARKER_GENES, get_cell
from spatial_mcp.stubs.scldm_knockout import (
    KNOWN_GUIDE_SYMBOLS,
    evaluate_knockout,
    resolve_ensembl,
)


def _round2(v: float) -> float:
    return round(float(v), 2)


def _clamp(v: float) -> float:
    return _round2(max(0.05, min(5.0, v)))


def simulate_perturbations(args: dict[str, Any]) -> dict[str, Any]:
    cell_id = args["cell_id"]
    gene = str(args["gene"]).upper()

    cell = get_cell(cell_id)
    if cell is None:
        return {
            "ok": False,
            "error": "cell_not_found",
            "message": f"No resolved cell with id '{cell_id}'.",
            "cell_id": cell_id,
            "gene": gene,
        }

    ensembl = resolve_ensembl(gene)
    if gene not in KNOWN_GUIDE_SYMBOLS and ensembl is None:
        return {
            "ok": False,
            "error": "gene_out_of_vocabulary",
            "message": (
                f"Gene '{gene}' is outside the virtual-cell model's training vocabulary. "
                f"In-vocab examples: {sorted(KNOWN_GUIDE_SYMBOLS)}."
            ),
            "cell_id": cell_id,
            "gene": gene,
        }

    try:
        ko = evaluate_knockout(gene)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("gene_out_of_vocabulary"):
            return {
                "ok": False,
                "error": "gene_out_of_vocabulary",
                "message": (
                    f"Gene '{gene}' is outside the virtual-cell model's training vocabulary. "
                    f"In-vocab examples: {sorted(KNOWN_GUIDE_SYMBOLS)}."
                ),
                "cell_id": cell_id,
                "gene": gene,
            }
        return {
            "ok": False,
            "error": "simulation_failed",
            "message": msg,
            "cell_id": cell_id,
            "gene": gene,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "simulation_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "cell_id": cell_id,
            "gene": gene,
        }

    # Apply population-level pseudobulk Δ to this cell's observed marker profile
    # (spatial cell = before; after = before + model Δ), matching the explorer contract.
    before = {g: float(cell["expression"][g]) for g in MARKER_GENES}
    after = {g: _clamp(before[g] + float(ko.deltas.get(g, 0.0))) for g in MARKER_GENES}
    deltas = {g: _round2(after[g] - before[g]) for g in MARKER_GENES}

    return {
        "ok": True,
        "cell_id": cell_id,
        "gene": gene,
        "ensembl_id": ko.ensembl_id,
        "cell_type": cell["cell_type"],
        "niche": cell["niche"],
        "before": before,
        "after": after,
        "deltas": deltas,
        "backend": ko.backend,
        "pseudobulk": {
            "mean_control": ko.mean_control,
            "mean_knockout": ko.mean_knockout,
            "deltas": ko.deltas,
        },
        "top_effects": ko.top_effects,
        "scldm": ko.details,
    }
