"""Stub: list_candidate_cells — real 10x Atera spatial data.

Self-contained. Same function name, signature, and return keys as the fixture
version, so schemas.py, registry.py, and the frontend are all untouched.

USAGE FOR THE AGENT
-------------------
Call with cell_type ONLY to see where that cell type lives (niche_composition),
then call again with niche= to isolate the population in one microenvironment.

    list_candidate_cells(sample_id="atera-cervical-01", cell_type="CD4_Treg")
        -> niche_composition: Tregs are overwhelmingly lymphoid_proximal and
           almost absent from tumor_core. That IS the finding.

    list_candidate_cells(sample_id="atera-cervical-01", cell_type="CD4_Treg",
                         niche="tumor_margin")
        -> the ~2,500 Tregs that actually contact invasive tumour

WHERE THE DATA COMES FROM
-------------------------
Reads mcp_server/data/cells.parquet, precomputed offline from a 3GB h5ad. The
server must not load an h5ad at request time — a tool that thinks for 30 seconds
dies on stage. Falls back to fixtures if the parquet is absent, and SAYS SO, so a
demo can never silently run on fake data.

    aws s3 cp s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/mcp_data/cells.parquet \
      mcp_server/data/

THE DATA
--------
10x Atera whole-transcriptome in-situ. Human cervical squamous cell carcinoma,
ONE FFPE section, CC BY 4.0. 715,413 cells, 18,028 genes, single-cell resolution.
Cell type labels are 10x's own (cell_groups.csv), not ours.

HOW THE NICHE ENUM MAPS ONTO THE TISSUE
---------------------------------------
Assigned per cell from its k=15 spatial nearest neighbours:

    tumor_margin       >=20% neighbours are Migratory/Metabolic Invasive Basal or
                       Hypoxic Tumor cells. Takes priority — a cell touching
                       INVASIVE tumour is at the margin by definition.
    tumor_core         >=20% neighbours are Differentiating / Dyskeratotic /
                       Parabasal tumour cells.
    lymphoid_proximal  everything else. B/plasma/stroma-rich, little tumour contact.

CD4 MAPPING — READ BEFORE ADDING CELL TYPES
-------------------------------------------
Only "Regulatory T Cells" -> CD4_Treg is safe. 10x's "Naive & Memory T Cells" is a
MIXED CD4/CD8 bucket at this detection depth (naive CD4 and naive CD8 are near
identical transcriptionally). It is deliberately NOT mapped to a CD4 type —
pushing it through a CD4-only perturbation model would be wrong.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CELLS_PARQUET = DATA_DIR / "cells.parquet"

MARKER_GENES = [
    "PDCD1",
    "TCF7",
    "TOX",
    "LAG3",
    "GZMB",
    "IL7R",
    "CTLA4",
    "FOXP3",
]

SAMPLE_META: dict[str, dict[str, Any]] = {
    "atera-cervical-01": {
        "assay": "10x Atera whole-transcriptome in situ (18,028 genes)",
        "tissue": "human cervical squamous cell carcinoma, FFPE",
        "n_cells": 715413,
        "n_sections": 1,
        "licence": "CC BY 4.0",
    }
}

PROVENANCE = (
    "10x Atera WTA preview, cervical SCC, ONE section (CC BY 4.0). Cell type labels are "
    "10x Genomics' own. Niche assigned from k=15 spatial nearest neighbours. All statistics "
    "are WITHIN-SAMPLE (n=1) — a pipeline demonstration, not a cohort claim."
)

NICHE_NOTE = (
    "Niche is assigned per cell from its 15 nearest spatial neighbours. For CD4_Treg, cells "
    "are overwhelmingly lymphoid_proximal and almost absent from tumor_core: Tregs are "
    "EXCLUDED from the tumour (0.002-0.06x enrichment vs a permutation null over 715,000 "
    "cells) and concentrated in a lymphoid aggregate alongside CAFs, plasma cells, "
    "macrophages and B cells. Filter by niche='tumor_margin' to isolate the ~2,500 Tregs "
    "that do contact the invasive front."
)

_CELLS = None
_LOADED = False


def _load():
    """Load once, lazily. Keeps import cheap and the failure mode obvious."""
    global _CELLS, _LOADED
    if _LOADED:
        return _CELLS
    _LOADED = True
    if CELLS_PARQUET.exists():
        import pandas as pd

        _CELLS = pd.read_parquet(CELLS_PARQUET)
        print(f"[list_candidate_cells] REAL Atera: {len(_CELLS):,} cells")
    else:
        print(f"[list_candidate_cells] {CELLS_PARQUET} missing -> FIXTURE MODE")
    return _CELLS


def _fixture_fallback(args: dict[str, Any]) -> dict[str, Any]:
    from spatial_mcp.fixtures.cells import cells_for_sample, public_cell, SAMPLE_META as FIX

    sample_id = args["sample_id"]
    if sample_id not in FIX:
        return {
            "sample_id": sample_id,
            "cells": [],
            "warning": f"Unknown sample_id '{sample_id}'. Known: {sorted(FIX)}",
        }

    out = []
    for c in cells_for_sample(sample_id):
        if args.get("niche") is not None and c["niche"] != args["niche"]:
            continue
        if args.get("cell_type") is not None and c["cell_type"] != args["cell_type"]:
            continue
        if (
            args.get("min_exhaustion_score") is not None
            and c["exhaustion_score"] < args["min_exhaustion_score"]
        ):
            continue
        out.append(public_cell(c))
    out.sort(key=lambda c: c["exhaustion_score"], reverse=True)
    return {
        "sample_id": sample_id,
        "n": len(out),
        "cells": out,
        "warning": "FIXTURE MODE — synthetic cells. Fetch cells.parquet into mcp_server/data/.",
    }


def list_candidate_cells(args: dict[str, Any]) -> dict[str, Any]:
    cells = _load()
    if cells is None:
        return _fixture_fallback(args)

    sample_id = args["sample_id"]
    if sample_id not in SAMPLE_META:
        return {
            "sample_id": sample_id,
            "cells": [],
            "warning": f"Unknown sample_id '{sample_id}'. Known: {sorted(SAMPLE_META)}",
        }

    # --- niche composition: WHERE this cell type lives. The finding, surfaced. ---
    # Computed before the niche filter, so the agent sees the full distribution
    # even when it has narrowed to one niche.
    scope = cells
    if args.get("cell_type") is not None:
        scope = scope[scope["cell_type"] == args["cell_type"]]
    niche_composition = {str(k): int(v) for k, v in scope["niche"].value_counts().items()}

    # --- filters ---
    df = scope
    if args.get("niche") is not None:
        df = df[df["niche"] == args["niche"]]
    if args.get("min_exhaustion_score") is not None:
        df = df[df["exhaustion_score"] >= args["min_exhaustion_score"]]

    n_matching = len(df)

    # Most exhausted first — same default as the fixture version.
    # Cap the payload: 29,000 cells of JSON would blow the agent's context window.
    df = df.sort_values("exhaustion_score", ascending=False).head(200)

    out = [
        {
            "id": str(r.id),
            "x": float(r.x),
            "y": float(r.y),
            "cell_type": str(r.cell_type),
            "niche": str(r.niche),
            "exhaustion_state": str(r.exhaustion_state),
            "exhaustion_score": float(r.exhaustion_score),
            "expression": {g: float(getattr(r, g, 0.0)) for g in MARKER_GENES},
        }
        for r in df.itertuples()
    ]

    result: dict[str, Any] = {
        "sample_id": sample_id,
        "n": n_matching,
        "cells": out,
        "niche_composition": niche_composition,
        "niche_note": NICHE_NOTE,
        "provenance": PROVENANCE,
    }
    if n_matching > len(out):
        result["note"] = (
            f"{n_matching:,} cells match; returning the {len(out)} most exhausted. "
            "Narrow with niche / cell_type / min_exhaustion_score."
        )
    return result
