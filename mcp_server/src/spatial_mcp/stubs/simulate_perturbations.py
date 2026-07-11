"""Stub: simulate_perturbations — swap this file for real teammate logic."""

from __future__ import annotations

from typing import Any

from spatial_mcp.fixtures.cells import MARKER_GENES, get_cell

# Genes the stub "virtual cell" knows about
IN_VOCAB = set(MARKER_GENES) | {
    "HAVCR2",  # TIM-3
    "ENTPD1",  # CD39
    "CXCL13",
    "TIGIT",
    "TNFRSF9",  # 4-1BB
}


def _round2(v: float) -> float:
    return round(max(0.05, min(5.0, v)), 2)


def _apply(before: dict[str, float], gene: str, cell_type: str) -> dict[str, float]:
    after = dict(before)
    g = gene.upper()
    is_tex = cell_type in ("CD4_Tex_term", "CD4_Tex_prog", "CD4_Teff")
    is_treg = cell_type == "CD4_Treg"

    def bump(key: str, delta: float) -> None:
        after[key] = _round2(after[key] + delta)

    if g == "PDCD1":
        bump("PDCD1", -2.2)
        if is_tex:
            bump("TOX", -0.9)
            bump("LAG3", -0.6)
            bump("TCF7", 1.4)
            bump("IL7R", 1.2)
            bump("GZMB", 1.0)
    elif g == "TOX":
        bump("TOX", -2.0)
        if is_tex:
            bump("PDCD1", -0.8)
            bump("TCF7", 1.6)
            bump("IL7R", 1.1)
            bump("GZMB", 0.7)
    elif g == "LAG3":
        bump("LAG3", -2.0)
        if is_tex:
            bump("PDCD1", -0.5)
            bump("GZMB", 0.9)
            bump("IL7R", 0.6)
    elif g == "CTLA4":
        bump("CTLA4", -2.0)
        if is_treg:
            bump("FOXP3", -0.8)
            bump("IL7R", 0.4)
        if is_tex:
            bump("GZMB", 0.8)
            bump("TCF7", 0.5)
    elif g in MARKER_GENES:
        bump(g, -1.8)
    elif g in ("HAVCR2", "ENTPD1", "TIGIT"):
        # Checkpoint-like: mild effector recovery
        bump("PDCD1", -0.4)
        bump("GZMB", 0.6)
        bump("TCF7", 0.4)
    elif g in ("CXCL13", "TNFRSF9"):
        bump("IL7R", 0.5)
        bump("GZMB", 0.4)
    return after


def simulate_perturbations(args: dict[str, Any]) -> dict[str, Any]:
    cell_id = args["cell_id"]
    gene = args["gene"].upper()

    cell = get_cell(cell_id)
    if cell is None:
        return {
            "ok": False,
            "error": "cell_not_found",
            "message": f"No resolved cell with id '{cell_id}'.",
            "cell_id": cell_id,
            "gene": gene,
        }

    if gene not in IN_VOCAB:
        return {
            "ok": False,
            "error": "gene_out_of_vocabulary",
            "message": (
                f"Gene '{gene}' is outside the virtual-cell model's training vocabulary. "
                f"In-vocab examples: {sorted(IN_VOCAB)}."
            ),
            "cell_id": cell_id,
            "gene": gene,
        }

    before = {g: float(cell["expression"][g]) for g in MARKER_GENES}
    after = _apply(before, gene, cell["cell_type"])
    deltas = {g: round(after[g] - before[g], 2) for g in MARKER_GENES}

    return {
        "ok": True,
        "cell_id": cell_id,
        "gene": gene,
        "cell_type": cell["cell_type"],
        "niche": cell["niche"],
        "before": before,
        "after": after,
        "deltas": deltas,
    }
