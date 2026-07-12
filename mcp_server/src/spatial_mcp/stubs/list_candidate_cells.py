"""list_candidate_cells — real 10x Atera spatial data. No fixture fallback."""

from __future__ import annotations

from typing import Any

from spatial_mcp.stubs.cell_store import MARKER_GENES, require_cells

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


def list_candidate_cells(args: dict[str, Any]) -> dict[str, Any]:
    try:
        cells = require_cells()
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": "data_missing",
            "sample_id": args.get("sample_id"),
            "cells": [],
            "n": 0,
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "data_load_failed",
            "sample_id": args.get("sample_id"),
            "cells": [],
            "n": 0,
            "message": f"{type(exc).__name__}: {exc}",
        }

    sample_id = args["sample_id"]
    if sample_id not in SAMPLE_META:
        return {
            "ok": False,
            "error": "unknown_sample",
            "sample_id": sample_id,
            "cells": [],
            "n": 0,
            "message": f"Unknown sample_id '{sample_id}'. Known: {sorted(SAMPLE_META)}",
        }

    scope = cells
    if args.get("cell_type") is not None:
        scope = scope[scope["cell_type"] == args["cell_type"]]
    niche_composition = {str(k): int(v) for k, v in scope["niche"].value_counts().items()}

    df = scope
    if args.get("niche") is not None:
        df = df[df["niche"] == args["niche"]]
    if args.get("min_exhaustion_score") is not None:
        df = df[df["exhaustion_score"] >= args["min_exhaustion_score"]]

    n_matching = len(df)
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
        "ok": True,
        "sample_id": sample_id,
        "n": n_matching,
        "cells": out,
        "niche_composition": niche_composition,
        "niche_note": NICHE_NOTE,
        "provenance": PROVENANCE,
        "backend": "atera_parquet",
    }
    if n_matching > len(out):
        result["note"] = (
            f"{n_matching:,} cells match; returning the {len(out)} most exhausted. "
            "Narrow with niche / cell_type / min_exhaustion_score."
        )
    return result
