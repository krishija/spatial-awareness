"""Stub: map_spatial_to_single — swap this file for real teammate logic."""

from __future__ import annotations

from collections import Counter
from typing import Any

from spatial_mcp.fixtures.cells import SAMPLE_META, cells_for_sample


# Atlas label aliases used in the stub mapping table
ATLAS_LABEL = {
    "CD4_Tex_term": "CD4_T_exhausted_terminal",
    "CD4_Tex_prog": "CD4_T_exhausted_progenitor",
    "CD4_Teff": "CD4_T_effector",
    "CD4_Treg": "CD4_T_regulatory",
    "myeloid": "Myeloid_macrophage",
    "tumor": "Malignant_epithelial",
    "stromal": "Fibroblast_stromal",
}


def map_spatial_to_single(args: dict[str, Any]) -> dict[str, Any]:
    sample_id = args["sample_id"]
    atlas = args.get("atlas_reference") or "human_immune_v1"

    if sample_id not in SAMPLE_META:
        return {
            "sample_id": sample_id,
            "atlas_reference": atlas,
            "mappings": [],
            "summary": {},
            "warning": f"Unknown sample_id '{sample_id}'. Known: {sorted(SAMPLE_META)}",
        }

    cells = cells_for_sample(sample_id)
    mappings = []
    for c in cells:
        atlas_label = ATLAS_LABEL[c["cell_type"]]
        # Confidence: high for T-lineage in expected niches, slightly lower elsewhere
        base = 0.92 if c["cell_type"].startswith("CD4") else 0.88
        if c["cell_type"] == "CD4_Tex_term" and c["niche"] == "tumor_core":
            base = 0.96
        if c["cell_type"] == "CD4_Teff" and c["niche"] == "lymphoid_proximal":
            base = 0.95
        mappings.append(
            {
                "cell_id": c["id"],
                "spatial_xy": {"x": c["x"], "y": c["y"]},
                "atlas_label": atlas_label,
                "resolved_cell_type": c["cell_type"],
                "confidence": round(base, 2),
            }
        )

    counts = Counter(m["atlas_label"] for m in mappings)
    return {
        "sample_id": sample_id,
        "atlas_reference": atlas,
        "n_mapped": len(mappings),
        "mappings": mappings,
        "summary": {
            "counts_by_atlas_label": dict(counts),
            "mean_confidence": round(
                sum(m["confidence"] for m in mappings) / max(len(mappings), 1), 3
            ),
        },
    }
