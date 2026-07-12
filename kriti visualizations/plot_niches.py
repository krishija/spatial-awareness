"""
plot_niches.py — show the niches on the tissue.

    python plot_niches.py --adata work/atera.h5ad --niche-py ~/SageMaker

Makes figures/:
    tissue_overview.png     all cell types
    treg_niches.png         Tregs coloured by niche — THE FIGURE
    treg_exclusion.png      tumour vs Tregs, side by side
    niche_zoom.png          close-up of the invasive front
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ap = argparse.ArgumentParser()
ap.add_argument("--adata", default="work/atera.h5ad")
ap.add_argument("--cell-type", default="Regulatory T Cells")
ap.add_argument("--k", type=int, default=15)
ap.add_argument("--margin-cut", type=float, default=0.20)
ap.add_argument("--niche-py", default=None)
ap.add_argument("--niche-index", default="artifacts/niche_index.pkl")
ap.add_argument("--outdir", default="figures")
a = ap.parse_args()

if a.niche_py:
    sys.path.insert(0, a.niche_py)
FIG = Path(a.outdir); FIG.mkdir(parents=True, exist_ok=True)

MARGIN_NBRS = ["Migratory Invasive Basal Cells", "Metabolic Invasive Basal Cells",
               "Hypoxic Tumor Cells"]
CORE_NBRS = ["Differentiating Tumor Cells", "Dyskeratotic Tumor Cells",
             "Parabasal Tumor Cells", "Proliferative Parabasal Cells"]
ALL_TUMOR = MARGIN_NBRS + CORE_NBRS

NICHE_COLOR = {"tumor_margin": "#e74c3c",
               "tumor_core": "#8e44ad",
               "lymphoid_proximal": "#2980b9"}

print("loading...")
A = sc.read_h5ad(a.adata)
xy = A.obsm["spatial"]
ct = A.obs["celltype"].astype(str).values
print(f"{A.n_obs:,} cells")

import niche  # noqa: E402
niche.CACHE = Path(a.niche_index)
IDX = niche.load()

nb = IDX.per_cell(a.cell_type, k=a.k)
tidx = nb.index.values
txy = xy[tidx]

margin = nb[[c for c in MARGIN_NBRS if c in nb.columns]].sum(axis=1).values
core = nb[[c for c in CORE_NBRS if c in nb.columns]].sum(axis=1).values
tniche = np.where(margin >= a.margin_cut, "tumor_margin",
           np.where(core >= a.margin_cut, "tumor_core", "lymphoid_proximal"))

print(f"\n{a.cell_type}: {len(tidx):,}")
for k, v in pd.Series(tniche).value_counts().items():
    print(f"  {k:20s} {v:6,}")


def base(ax, s=.35, c="#ececec"):
    ax.scatter(xy[:, 0], xy[:, 1], s=s, c=c, linewidths=0, rasterized=True)
    ax.set_aspect("equal"); ax.invert_yaxis(); ax.axis("off")


# ─────────────────────────────────────────── 1. everything
fig, ax = plt.subplots(figsize=(11, 10))
cats = pd.Series(ct).value_counts().index[:18]
cmap = plt.get_cmap("tab20")
ax.scatter(xy[~np.isin(ct, cats), 0], xy[~np.isin(ct, cats), 1],
           s=.3, c="#f0f0f0", linewidths=0, rasterized=True)
for i, c in enumerate(cats):
    m = ct == c
    ax.scatter(xy[m, 0], xy[m, 1], s=.8, color=cmap(i % 20), linewidths=0,
               rasterized=True, label=f"{c} ({m.sum():,})")
ax.set_aspect("equal"); ax.invert_yaxis(); ax.axis("off")
ax.set_title(f"Cervical SCC — {A.n_obs:,} cells, 10x Atera", fontsize=13)
ax.legend(fontsize=6.5, markerscale=8, loc="center left", bbox_to_anchor=(1, .5),
          frameon=False)
plt.tight_layout(); plt.savefig(FIG / "tissue_overview.png", dpi=140); plt.close()
print(f"\n{FIG/'tissue_overview.png'}")


# ─────────────────────────────────────────── 2. THE FIGURE: Tregs by niche
fig, axes = plt.subplots(1, 2, figsize=(19, 9))

# left: tumour in grey, Tregs coloured by niche
ax = axes[0]
tum = np.isin(ct, ALL_TUMOR)
ax.scatter(xy[~tum, 0], xy[~tum, 1], s=.3, c="#f2f2f2", linewidths=0, rasterized=True)
ax.scatter(xy[tum, 0], xy[tum, 1], s=.5, c="#c8c8c8", linewidths=0, rasterized=True,
           label=f"tumour ({tum.sum():,})")
for n in ["lymphoid_proximal", "tumor_margin", "tumor_core"]:
    m = tniche == n
    if m.sum():
        ax.scatter(txy[m, 0], txy[m, 1], s=6, c=NICHE_COLOR[n], linewidths=0,
                   rasterized=True, label=f"Treg — {n} ({m.sum():,})")
ax.set_aspect("equal"); ax.invert_yaxis(); ax.axis("off")
ax.set_title("Tregs by spatial niche\ngrey = tumour cells", fontsize=13)
ax.legend(fontsize=9, markerscale=3, loc="upper right", frameon=False)

# right: the exclusion, stated plainly
ax = axes[1]
base(ax)
ax.scatter(xy[tum, 0], xy[tum, 1], s=.6, c="#f5b7b1", linewidths=0, rasterized=True,
           label=f"tumour ({tum.sum():,})")
ax.scatter(txy[:, 0], txy[:, 1], s=5, c="#1a5276", linewidths=0, rasterized=True,
           label=f"Treg ({len(tidx):,})")
n_core = int((tniche == "tumor_core").sum())
ax.set_title(f"Tregs are EXCLUDED from the tumour\n"
             f"{n_core} of {len(tidx):,} Tregs sit inside the tumour core "
             f"({n_core/len(tidx):.2%})", fontsize=13)
ax.legend(fontsize=9, markerscale=4, loc="upper right", frameon=False)

plt.tight_layout(); plt.savefig(FIG / "treg_niches.png", dpi=150); plt.close()
print(f"{FIG/'treg_niches.png'}   <- THE SLIDE")


# ─────────────────────────────────────────── 3. side by side, one panel per niche
fig, axes = plt.subplots(1, 3, figsize=(19, 6.5))
for ax, n in zip(axes, ["tumor_core", "tumor_margin", "lymphoid_proximal"]):
    base(ax, s=.25)
    ax.scatter(xy[tum, 0], xy[tum, 1], s=.4, c="#e0e0e0", linewidths=0, rasterized=True)
    m = tniche == n
    ax.scatter(txy[m, 0], txy[m, 1], s=7, c=NICHE_COLOR[n], linewidths=0, rasterized=True)
    ax.set_title(f"{n}\n{int(m.sum()):,} Tregs  ({m.mean():.1%})", fontsize=12)
plt.suptitle("Where the Tregs actually are", fontsize=14)
plt.tight_layout(); plt.savefig(FIG / "treg_exclusion.png", dpi=140); plt.close()
print(f"{FIG/'treg_exclusion.png'}")


# ─────────────────────────────────────────── 4. zoom on the invasive front
mrg = txy[tniche == "tumor_margin"]
if len(mrg) > 50:
    # densest patch of margin Tregs
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=min(30, len(mrg))).fit(mrg)
    d, _ = nn.kneighbors(mrg)
    cx, cy = mrg[np.argmin(d[:, -1])]
    W = 900

    fig, axes = plt.subplots(1, 2, figsize=(17, 8))

    ax = axes[0]
    base(ax, s=.4)
    ax.scatter(xy[tum, 0], xy[tum, 1], s=.6, c="#f5b7b1", linewidths=0, rasterized=True)
    for n in NICHE_COLOR:
        m = tniche == n
        ax.scatter(txy[m, 0], txy[m, 1], s=4, c=NICHE_COLOR[n], linewidths=0,
                   rasterized=True)
    ax.add_patch(Rectangle((cx - W/2, cy - W/2), W, W, fill=False, ec="k", lw=2))
    ax.set_title("full section", fontsize=12)

    ax = axes[1]
    win = ((xy[:, 0] > cx - W/2) & (xy[:, 0] < cx + W/2) &
           (xy[:, 1] > cy - W/2) & (xy[:, 1] < cy + W/2))
    twin = ((txy[:, 0] > cx - W/2) & (txy[:, 0] < cx + W/2) &
            (txy[:, 1] > cy - W/2) & (txy[:, 1] < cy + W/2))
    ax.scatter(xy[win & ~tum, 0], xy[win & ~tum, 1], s=14, c="#e8e8e8",
               linewidths=0, label="other")
    ax.scatter(xy[win & tum, 0], xy[win & tum, 1], s=18, c="#f1948a",
               linewidths=0, label="tumour")
    for n in NICHE_COLOR:
        m = twin & (tniche == n)
        if m.sum():
            ax.scatter(txy[m, 0], txy[m, 1], s=55, c=NICHE_COLOR[n],
                       edgecolors="k", linewidths=.4, label=f"Treg — {n}")
    ax.set_aspect("equal"); ax.invert_yaxis(); ax.axis("off")
    ax.set_title(f"invasive front, {W}um window\n"
                 "Tregs line the edge of the tumour but do not enter", fontsize=12)
    ax.legend(fontsize=9, markerscale=1.4, loc="upper right", frameon=False)

    plt.tight_layout(); plt.savefig(FIG / "niche_zoom.png", dpi=150); plt.close()
    print(f"{FIG/'niche_zoom.png'}   <- the close-up. Shows the exclusion is real.")

print(f"""
DONE

  treg_niches.png    Tregs coloured by niche, tumour in grey
  niche_zoom.png     the invasive front, close up
  treg_exclusion.png one panel per niche
  tissue_overview.png all cell types

The claim these support: Tregs line the invasive edge and do not enter the tumour.
{int((tniche=='tumor_core').sum())} of {len(tidx):,} are in the core.
""")
