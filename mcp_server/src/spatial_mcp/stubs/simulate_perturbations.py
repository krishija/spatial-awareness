"""simulate_perturbations — live scLDM-CD4 only. No surrogate path."""

from __future__ import annotations

from typing import Any

from spatial_mcp.stubs.cell_store import MARKER_GENES, get_cell
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

    try:
        cell = get_cell(cell_id)
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": "data_missing",
            "message": str(exc),
            "cell_id": cell_id,
            "gene": gene,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "data_load_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "cell_id": cell_id,
            "gene": gene,
        }

    if cell is None:
        return {
            "ok": False,
            "error": "cell_not_found",
            "message": f"No cell with id '{cell_id}' in cells.parquet.",
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

    before = {g: float(cell["expression"][g]) for g in MARKER_GENES}
    after = {g: _clamp(before[g] + float(ko.deltas.get(g, 0.0))) for g in MARKER_GENES}
    deltas = {g: _round2(after[g] - before[g]) for g in MARKER_GENES}

    return {
        "ok": True,
        "cell_id": cell_id,
        "gene": gene,
        "ensembl_id": ko.ensembl_id,
        "backend": ko.backend,
        "before": before,
        "after": after,
        "deltas": deltas,
        "top_effects": ko.top_effects,
        "details": ko.details,
    }
