"""Stub: map_spatial_to_single — real signature transfer, Atera -> AIFI atlas.

Self-contained. Same function name and signature as the fixture version, so
schemas.py, registry.py and the frontend are untouched.

WHAT THIS ACTUALLY DOES, AND WHY IT IS NOT WHAT THE FIXTURE DID
--------------------------------------------------------------
The fixture pretended to assign each spatial cell an atlas identity. We do the
opposite, deliberately:

    spatial Tregs  ->  DE signature  ->  score every atlas cell  ->  pick barcodes

Direction matters. Assigning a tumour-margin Treg to a specific healthy-blood cell
would be a confident answer to a question with no answer — blood has no tumour margin,
so no blood cell "is" that cell. What CAN be asked, and answered, is: which atlas cells
most resemble the Tregs we found at the invasive front? Those are the control cells the
perturbation model starts from.

WHY THE ATLAS IS IN THE CHAIN AT ALL
------------------------------------
scLDM.CD4 was trained on Chromium Perturb-seq of primary blood CD4 T cells. Atera is
probe-based, FFPE, in-situ, ~10x lower depth — OUT OF DISTRIBUTION for that model.
The AIFI atlas is Chromium blood CD4: the same domain. It supplies the CONTROL
POPULATION. Atera supplies the question.

THE SIGNATURE
-------------
DE between tumour-INFILTRATING Tregs (>=20% invasive/hypoxic tumour neighbours) and all
other Tregs, in the spatial data. Not "Treg vs everything" — that would just re-find
Tregs, which is a sanity check, not a result.

Abundance genes (ribosomal, mito, ACTB) are dropped: leave them in and the atlas score
becomes a ranking by library size. Stromal/epithelial genes are dropped too: infiltrating
Tregs are by construction the ones touching tumour and stroma, so they carry the most
segmentation spillover, and an unmasked signature is a contamination signature.

DATA
----
Reads mcp_server/data/atlas_mapping.parquet, precomputed by score_atlas.py.
Falls back to the fixtures if absent, and SAYS SO.

    aws s3 cp s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/atlas_mapping.parquet \
      mcp_server/data/
    aws s3 cp s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/margin_signature.csv \
      mcp_server/data/
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
MAPPING_PARQUET = DATA_DIR / "atlas_mapping.parquet"
SIGNATURE_CSV = DATA_DIR / "margin_signature.csv"

SAMPLE_META: dict[str, dict[str, Any]] = {
    "atera-cervical-01": {
        "assay": "10x Atera whole-transcriptome in situ",
        "tissue": "human cervical squamous cell carcinoma, FFPE",
    }
}

ATLAS_NAME = "AIFI_human_immune_health_atlas_CD4"

PROVENANCE = (
    "Spatial: 10x Atera WTA, cervical SCC, ONE section (CC BY 4.0). "
    "Atlas: AIFI Human Immune Health Atlas, CD4 arm — healthy-donor PBMC. "
    "Mapping is SIGNATURE TRANSFER, not cell-to-cell assignment."
)

_MAP = None
_SIG = None
_LOADED = False


def _load():
    global _MAP, _SIG, _LOADED
    if _LOADED:
        return _MAP
    _LOADED = True
    if MAPPING_PARQUET.exists():
        import pandas as pd

        _MAP = pd.read_parquet(MAPPING_PARQUET)
        if SIGNATURE_CSV.exists():
            _SIG = pd.read_csv(SIGNATURE_CSV)
        print(f"[map_spatial_to_single] REAL: {len(_MAP):,} atlas cells scored")
    else:
        print(f"[map_spatial_to_single] {MAPPING_PARQUET} missing -> FIXTURE MODE")
    return _MAP


def _fixture_fallback(args: dict[str, Any]) -> dict[str, Any]:
    from collections import Counter

    from spatial_mcp.fixtures.cells import SAMPLE_META as FIX, cells_for_sample

    sample_id = args["sample_id"]
    atlas = args.get("atlas_reference") or "human_immune_v1"
    if sample_id not in FIX:
        return {
            "sample_id": sample_id,
            "atlas_reference": atlas,
            "mappings": [],
            "summary": {},
            "warning": f"Unknown sample_id '{sample_id}'. Known: {sorted(FIX)}",
        }

    labels = {
        "CD4_Tex_term": "CD4_T_exhausted_terminal",
        "CD4_Tex_prog": "CD4_T_exhausted_progenitor",
        "CD4_Teff": "CD4_T_effector",
        "CD4_Treg": "CD4_T_regulatory",
        "myeloid": "Myeloid_macrophage",
        "tumor": "Malignant_epithelial",
        "stromal": "Fibroblast_stromal",
    }
    mappings = [
        {
            "cell_id": c["id"],
            "spatial_xy": {"x": c["x"], "y": c["y"]},
            "atlas_label": labels[c["cell_type"]],
            "resolved_cell_type": c["cell_type"],
            "confidence": 0.92,
        }
        for c in cells_for_sample(sample_id)
    ]
    counts = Counter(m["atlas_label"] for m in mappings)
    return {
        "sample_id": sample_id,
        "atlas_reference": atlas,
        "n_mapped": len(mappings),
        "mappings": mappings,
        "summary": {"counts_by_atlas_label": dict(counts), "mean_confidence": 0.92},
        "warning": "FIXTURE MODE — synthetic. Fetch atlas_mapping.parquet into mcp_server/data/.",
    }


def map_spatial_to_single(args: dict[str, Any]) -> dict[str, Any]:
    df = _load()
    if df is None:
        return _fixture_fallback(args)

    sample_id = args["sample_id"]
    atlas = args.get("atlas_reference") or ATLAS_NAME
    if sample_id not in SAMPLE_META:
        return {
            "sample_id": sample_id,
            "atlas_reference": atlas,
            "mappings": [],
            "summary": {},
            "warning": f"Unknown sample_id '{sample_id}'. Known: {sorted(SAMPLE_META)}",
        }

    sel = df[df["selected"]].sort_values("infiltration_score", ascending=False)
    tregs = df[df["is_treg"]] if "is_treg" in df.columns else df

    # Which atlas subtypes are ENRICHED among the selected cells, versus all atlas
    # Tregs? This is the finding. A flat 1.0x everywhere means the signature is not
    # transferring and nothing downstream should be trusted.
    sel_frac = sel["aifi_label"].value_counts(normalize=True)
    base_frac = tregs["aifi_label"].value_counts(normalize=True)
    enrich = (sel_frac / base_frac.reindex(sel_frac.index)).sort_values(ascending=False)

    # Cap the payload — thousands of barcodes would blow the agent's context window.
    # The full list lives in the CSV.
    head = sel.head(50)

    return {
        "sample_id": sample_id,
        "atlas_reference": atlas,
        "method": (
            "signature transfer: DE between tumour-infiltrating and non-infiltrating "
            "spatial Tregs, scored onto atlas cells with gene-set scoring "
            "(expression-bin-matched background)"
        ),
        "direction": (
            "spatial signature -> atlas cells. NOT cell-to-cell assignment. A "
            "tumour-margin Treg has no counterpart in healthy blood, so assigning one "
            "would be a confident answer to a question with no answer."
        ),
        "n_atlas_cells_scored": int(len(df)),
        "n_atlas_tregs": int(len(tregs)),
        "n_selected": int(len(sel)),
        "score_cutoff": round(float(sel["infiltration_score"].min()), 4) if len(sel) else None,
        "signature_genes": (
            _SIG["names"].head(30).tolist() if _SIG is not None and "names" in _SIG else None
        ),
        "signature_size": int(len(_SIG)) if _SIG is not None else None,
        # schema-shaped: the selected barcodes, ranked
        "mappings": [
            {
                "cell_id": str(r.barcode),
                "atlas_label": str(r.aifi_label),
                "confidence": round(float(r.infiltration_score), 4),
            }
            for r in head.itertuples()
        ],
        "summary": {
            "counts_by_atlas_label": {
                str(k): int(v) for k, v in sel["aifi_label"].value_counts().head(10).items()
            },
            "enrichment_vs_all_tregs": {
                str(k): round(float(v), 2) for k, v in enrich.head(8).items()
            },
            "mean_confidence": (
                round(float(sel["infiltration_score"].mean()), 4) if len(sel) else None
            ),
        },
        "how_to_read_the_enrichment": (
            "If ACTIVATED / EFFECTOR Treg subtypes are enriched and NAIVE ones depleted, a "
            "tumour-infiltration programme derived from spatial tissue is picking activated "
            "Tregs out of healthy blood — coherent, and a real result. If every subtype sits "
            "near 1.0x, the signature is not transferring and nothing downstream should be "
            "trusted."
        ),
        "why_the_atlas": (
            "scLDM.CD4 was trained on Chromium Perturb-seq of blood CD4 T cells. Atera is "
            "probe-based FFPE in-situ at ~10x lower depth — out of distribution for that "
            "model. The AIFI atlas is Chromium blood CD4: the same domain. It supplies the "
            "CONTROL POPULATION; Atera supplies the question."
        ),
        "handoff": (
            "The selected barcodes are AIFI atlas cell IDs. Subset the atlas h5ad on them "
            "and that is the control population for perturbation. Full list: "
            "artifacts/selected_barcodes.csv"
        ),
        "caveat": (
            "The atlas is HEALTHY BLOOD. Core Treg identity transfers; the tumour-margin "
            "programme does not, because blood has no tumour margin. That gap is not a bug "
            "— it is the context gap, and scLDM.CD4 has the same one, having been trained "
            "on blood-derived CD4 cells."
        ),
        "provenance": PROVENANCE,
        "note": (
            f"Returning the top 50 of {len(sel):,} selected barcodes."
            if len(sel) > 50
            else None
        ),
    }
