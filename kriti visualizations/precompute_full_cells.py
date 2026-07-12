"""Build mcp_server/data/cells_full.parquet — ALL 715,413 cells, all 25 raw
10x cell type labels, matching explorer.html's "Cell types" dropdown exactly
(unlike precompute_cells.py, which filters to a 13-label CD4-relevant subset
via CELLTYPE_MAP). Niche is computed for Regulatory T Cells only (Tregs), same
scope as make_explorer.py's "Treg niches" layer — non-Treg cells get niche=None.

Gene panel matches explorer.html's gene-paint dropdown, NOT the old marker
panel: CTLA4, FOXP3, CXCL9, STAT1, CXCR4, IL2RA, TNFRSF9, PDCD1.

    python precompute_full_cells.py \
      --adata       work/atera.h5ad \
      --niche-index artifacts/niche_index.pkl \
      --niche-py    . \
      --out         ../mcp_server/data
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
ap.add_argument("--niche-py", default=None)
ap.add_argument("--out", default="mcp_server/data")
ap.add_argument("--k", type=int, default=15)
ap.add_argument("--margin-cut", type=float, default=0.20)
ap.add_argument("--sample-id", default="atera-cervical-01")
a = ap.parse_args()

if a.niche_py:
    sys.path.insert(0, a.niche_py)
OUT = Path(a.out)
OUT.mkdir(parents=True, exist_ok=True)

GENES = ["CTLA4", "FOXP3", "CXCL9", "STAT1", "CXCR4", "IL2RA", "TNFRSF9", "PDCD1"]

MARGIN_NBRS = ["Migratory Invasive Basal Cells", "Metabolic Invasive Basal Cells",
               "Hypoxic Tumor Cells"]
CORE_NBRS = ["Differentiating Tumor Cells", "Dyskeratotic Tumor Cells",
             "Parabasal Tumor Cells", "Proliferative Parabasal Cells"]

print("loading...")
A = sc.read_h5ad(a.adata)
A.X = A.layers["counts"].copy() if "counts" in A.layers else A.X.copy()
sc.pp.normalize_total(A, target_sum=1e4)
sc.pp.log1p(A)
print(f"  {A.n_obs:,} cells x {A.n_vars:,} genes")

import niche  # noqa: E402
niche.CACHE = Path(a.niche_index)
IDX = niche.load()

# Niche only computed for Tregs -- same scope as her "Treg niches" layer.
nb = IDX.per_cell("Regulatory T Cells", k=a.k)
treg_idx = nb.index.values
margin = nb[[c for c in MARGIN_NBRS if c in nb.columns]].sum(axis=1).values
core = nb[[c for c in CORE_NBRS if c in nb.columns]].sum(axis=1).values
treg_niche = np.where(margin >= a.margin_cut, "tumor_margin",
              np.where(core >= a.margin_cut, "tumor_core", "lymphoid_proximal"))

niche_col = np.full(A.n_obs, None, dtype=object)
niche_col[treg_idx] = treg_niche

expr = {g: (np.asarray(A[:, g].X.todense()).ravel() if g in A.var_names
            else np.zeros(A.n_obs, dtype=np.float32))
        for g in GENES}

# Simple exhaustion proxy off the genes we actually have (PDCD1 + CTLA4 up).
raw = (expr["PDCD1"] + expr["CTLA4"]) / 2.0
lo, hi = np.percentile(raw, [1, 99])
score = np.clip((raw - lo) / max(hi - lo, 1e-6), 0, 1)
state = np.where(score > 0.66, "terminally_exhausted",
         np.where(score > 0.33, "progenitor_exhausted", "effector"))

df = pd.DataFrame({
    "id": A.obs_names.values,
    "sample_id": a.sample_id,
    "x": A.obsm["spatial"][:, 0].round(1),
    "y": A.obsm["spatial"][:, 1].round(1),
    "cell_type": A.obs["celltype"].astype(str).values,
    "niche": niche_col,
    "exhaustion_score": np.round(score, 3),
    "exhaustion_state": state,
})
for g in GENES:
    df[g] = np.round(expr[g], 2)

df.to_parquet(OUT / "cells_full.parquet", index=False)
print(f"\ncells_full.parquet: {len(df):,} cells -> {OUT/'cells_full.parquet'}")
print("\ncell_type counts:")
print(df.cell_type.value_counts().to_string())
print(f"\ncells with niche assigned (Tregs): {(df['niche'].notna()).sum():,}")
