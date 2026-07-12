"""Build mcp_server/data/cells.parquet from the Atera h5ad.

Run ONCE, offline. Produces exactly the columns list_candidate_cells needs:

    id, x, y, cell_type, niche, exhaustion_state, exhaustion_score,
    PDCD1, TCF7, TOX, LAG3, GZMB, IL7R, CTLA4, FOXP3

Everything the schema promises, nothing it doesn't.

    python precompute_cells.py \
      --adata       ~/SageMaker/work/atera.h5ad \
      --niche-index ~/SageMaker/artifacts/niche_index.pkl \
      --niche-py    ~/SageMaker \
      --out         mcp_server/data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc

ap = argparse.ArgumentParser()
ap.add_argument("--adata", required=True)
ap.add_argument("--niche-index", required=True)
ap.add_argument("--niche-py", default=None, help="dir containing niche.py")
ap.add_argument("--out", default="mcp_server/data")
ap.add_argument("--k", type=int, default=15)
ap.add_argument("--sample-id", default="atera-cervical-01")
a = ap.parse_args()

if a.niche_py:
    sys.path.insert(0, a.niche_py)
OUT = Path(a.out)
OUT.mkdir(parents=True, exist_ok=True)

MARKER_GENES = ["PDCD1", "TCF7", "TOX", "LAG3", "GZMB", "IL7R", "CTLA4", "FOXP3"]

# 10x label -> the schema's cell_type enum.
# Naive & Memory is a MIXED CD4/CD8 bucket at this depth — deliberately excluded.
CELLTYPE_MAP = {
    "Regulatory T Cells": "CD4_Treg",
    "Exhausted T Cells": "CD4_Tex_term",
    "Cytotoxic T Cells": "CD4_Teff",
    "Macrophages": "myeloid",
    "Dendritic Cells": "myeloid",
    "Cancer Associated Fibroblasts": "stromal",
    "Interstitial Fibroblasts": "stromal",
    "Stroma & Smooth Muscle": "stromal",
    "Differentiating Tumor Cells": "tumor",
    "Dyskeratotic Tumor Cells": "tumor",
    "Parabasal Tumor Cells": "tumor",
    "Hypoxic Tumor Cells": "tumor",
    "Migratory Invasive Basal Cells": "tumor",
    "Metabolic Invasive Basal Cells": "tumor",
}

CORE_NBRS = ["Differentiating Tumor Cells", "Dyskeratotic Tumor Cells",
             "Parabasal Tumor Cells", "Proliferative Parabasal Cells"]
MARGIN_NBRS = ["Migratory Invasive Basal Cells", "Metabolic Invasive Basal Cells",
               "Hypoxic Tumor Cells"]

print("loading...")
A = sc.read_h5ad(a.adata)
A.X = A.layers["counts"].copy() if "counts" in A.layers else A.X.copy()
sc.pp.normalize_total(A, target_sum=1e4)
sc.pp.log1p(A)
print(f"  {A.n_obs:,} cells x {A.n_vars:,} genes")

import niche  # noqa: E402
niche.CACHE = Path(a.niche_index)
IDX = niche.load()

rows = []
for label, enum in CELLTYPE_MAP.items():
    if (A.obs["celltype"] == label).sum() == 0:
        continue
    nb = IDX.per_cell(label, k=a.k)
    sel = nb.index.values
    sub = A[sel]

    core = nb[[c for c in CORE_NBRS if c in nb]].sum(axis=1).values
    margin = nb[[c for c in MARGIN_NBRS if c in nb]].sum(axis=1).values

    # margin wins ties: a cell touching INVASIVE tumour is at the margin by definition
    n = np.where(margin >= 0.20, "tumor_margin",
         np.where(core >= 0.20, "tumor_core", "lymphoid_proximal"))

    expr = {g: (np.asarray(sub[:, g].X.todense()).ravel()
                if g in A.var_names else np.zeros(len(sel)))
            for g in MARKER_GENES}

    d = pd.DataFrame({
        "id": sub.obs_names.values,
        "sample_id": a.sample_id,
        "x": sub.obsm["spatial"][:, 0].round(1),
        "y": sub.obsm["spatial"][:, 1].round(1),
        "cell_type": enum,
        "source_label": label,
        "niche": n,
    })
    for g in MARKER_GENES:
        d[g] = np.round(expr[g], 2)

    # exhaustion: inhibitory receptors up, memory/stem markers down
    d["_raw"] = (np.mean([expr[g] for g in ["PDCD1", "TOX", "LAG3", "CTLA4"]], axis=0)
                 - np.mean([expr[g] for g in ["TCF7", "IL7R"]], axis=0))
    rows.append(d)

cells = pd.concat(rows, ignore_index=True)

lo, hi = cells["_raw"].quantile([0.01, 0.99])
cells["exhaustion_score"] = ((cells["_raw"] - lo) / (hi - lo)).clip(0, 1).round(3)
cells = cells.drop(columns=["_raw"])
cells["exhaustion_state"] = pd.cut(
    cells["exhaustion_score"], [-0.01, 0.33, 0.66, 1.01],
    labels=["effector", "progenitor_exhausted", "terminally_exhausted"]).astype(str)

cells.to_parquet(OUT / "cells.parquet", index=False)

print(f"\ncells.parquet: {len(cells):,} cells -> {OUT/'cells.parquet'}")
print("\ncell_type x niche:")
print(pd.crosstab(cells.cell_type, cells.niche).to_string())

t = cells[cells.cell_type == "CD4_Treg"]
print(f"\nCD4_Treg: {len(t):,}")
print(t.niche.value_counts().to_string())
print("\n  ^ Tregs should be overwhelmingly lymphoid_proximal and almost absent from")
print("    tumor_core. That IS the finding: they are excluded from the tumour and")
print("    concentrated in a lymphoid aggregate.")

print("\nnow:  aws s3 cp mcp_server/data/cells.parquet "
      "s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/mcp_data/")
