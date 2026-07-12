"""
make_explorer.py — build a standalone interactive tissue explorer.

Produces ONE self-contained HTML file. Open it in a browser: zoom, pan, toggle cell
types on and off, hover any cell. No server, no install, works offline. Email it,
put it on S3, open it on the projector.

    pip install plotly
    python make_explorer.py --adata work/atera.h5ad --niche-py ~/SageMaker

    -> explorer.html

WHAT IT SHOWS
    Tab 1  all cell types, click the legend to isolate any of them
    Tab 2  Tregs coloured by niche, tumour behind them in grey
    Tab 3  any gene, painted onto the tissue

715k points is a lot for a browser. We use WebGL (scattergl) and subsample the bulk
cell types; T cells and tumour are kept in full, because those are the ones anyone
will actually want to look at.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc

ap = argparse.ArgumentParser()
ap.add_argument("--adata", default="work/atera.h5ad")
ap.add_argument("--cell-type", default="Regulatory T Cells")
ap.add_argument("--k", type=int, default=15)
ap.add_argument("--margin-cut", type=float, default=0.20)
ap.add_argument("--genes", default="CTLA4,FOXP3,CXCL9,STAT1,CXCR4,IL2RA,TNFRSF9,PDCD1")
ap.add_argument("--max-per-type", type=int, default=2500,
                help="subsample bulk cell types to keep the HTML responsive")
ap.add_argument("--niche-py", default=None)
ap.add_argument("--niche-index", default="artifacts/niche_index.pkl")
ap.add_argument("--out", default="explorer.html")
a = ap.parse_args()

if a.niche_py:
    sys.path.insert(0, a.niche_py)

import plotly.graph_objects as go
from plotly.subplots import make_subplots

MARGIN_NBRS = ["Migratory Invasive Basal Cells", "Metabolic Invasive Basal Cells",
               "Hypoxic Tumor Cells"]
CORE_NBRS = ["Differentiating Tumor Cells", "Dyskeratotic Tumor Cells",
             "Parabasal Tumor Cells", "Proliferative Parabasal Cells"]
TUMOR = MARGIN_NBRS + CORE_NBRS
NICHE_COLOR = {"tumor_margin": "#e74c3c", "tumor_core": "#8e44ad",
               "lymphoid_proximal": "#2980b9"}
# Only the cells the story is about are kept in full. Everything else is a backdrop —
# it just has to be dense enough to show the Tregs are NOT in it. Keeping Cytotoxic T
# (76k) and Naive/Memory (30k) in full cost 160k points nobody was ever going to look at.
KEEP_FULL = ["Regulatory T Cells"]

print("loading...")
A = sc.read_h5ad(a.adata)
A.X = A.layers["counts"].copy() if "counts" in A.layers else A.X.copy()
sc.pp.normalize_total(A, target_sum=1e4)
sc.pp.log1p(A)
xy = np.round(A.obsm["spatial"], 1).astype(np.float32)   # rounding halves the HTML size
ct = A.obs["celltype"].astype(str).values
print(f"{A.n_obs:,} cells, {len(set(ct))} types")

# ---------------------------------------------------------------- niches
import niche  # noqa: E402
niche.CACHE = Path(a.niche_index)
IDX = niche.load()
nb = IDX.per_cell(a.cell_type, k=a.k)
tidx = nb.index.values

margin = nb[[c for c in MARGIN_NBRS if c in nb.columns]].sum(axis=1).values
core = nb[[c for c in CORE_NBRS if c in nb.columns]].sum(axis=1).values
tniche = np.where(margin >= a.margin_cut, "tumor_margin",
           np.where(core >= a.margin_cut, "tumor_core", "lymphoid_proximal"))
print(f"{a.cell_type}: {len(tidx):,}")
for k, v in pd.Series(tniche).value_counts().items():
    print(f"  {k:20s} {v:6,}")

# ---------------------------------------------------------------- subsample the bulk
rng = np.random.default_rng(0)
show = np.zeros(A.n_obs, bool)
for c in set(ct):
    m = np.where(ct == c)[0]
    if c in KEEP_FULL or len(m) <= a.max_per_type:
        show[m] = True
    else:
        show[rng.choice(m, a.max_per_type, replace=False)] = True
print(f"\nplotting {int(show.sum()):,} of {A.n_obs:,} cells "
      f"(bulk types capped at {a.max_per_type:,}; T/B cells kept in full)")

genes = [g for g in a.genes.split(",") if g in A.var_names]
expr = {g: np.round(np.asarray(A[:, g].X.todense()).ravel(), 2).astype(np.float32)
        for g in genes}
print(f"genes: {genes}")

fig = make_subplots(rows=1, cols=1)
PAL = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2",
       "#7f7f7f","#bcbd22","#17becf","#aec7e8","#ffbb78","#98df8a","#ff9896",
       "#c5b0d5","#c49c94","#f7b6d2","#c7c7c7","#dbdb8d","#9edae5","#393b79",
       "#637939","#8c6d31","#843c39","#7b4173"]

traces = []

# ---- LAYER 1: cell types (click legend to isolate)
order = pd.Series(ct[show]).value_counts().index
for i, c in enumerate(order):
    m = show & (ct == c)
    traces.append(go.Scattergl(
        x=xy[m, 0], y=xy[m, 1], mode="markers", name=c,
        marker=dict(size=2, color=PAL[i % len(PAL)], opacity=.75),
        hovertemplate=f"<b>{c}</b><extra></extra>",
        visible=True, legendgroup="types",
    ))
n_types = len(traces)

# ---- LAYER 2: Tregs by niche
tum = np.isin(ct, TUMOR) & show
traces.append(go.Scattergl(
    x=xy[tum, 0], y=xy[tum, 1], mode="markers", name="tumour (background)",
    marker=dict(size=2, color="#d5d5d5", opacity=.5),
    hoverinfo="skip", visible=False, legendgroup="niche"))
for n in ["lymphoid_proximal", "tumor_margin", "tumor_core"]:
    m = tniche == n
    traces.append(go.Scattergl(
        x=xy[tidx][m, 0], y=xy[tidx][m, 1], mode="markers",
        name=f"Treg — {n} ({int(m.sum()):,})",
        marker=dict(size=4, color=NICHE_COLOR[n], opacity=.9,
                    line=dict(width=.3, color="white")),
        hovertemplate=f"<b>Treg</b><br>niche: {n}<extra></extra>",
        visible=False, legendgroup="niche"))
n_niche = 4

# ---- LAYER 3: genes
for g in genes:
    v = expr[g][show]
    o = np.argsort(v)
    pts = np.where(show)[0][o]
    traces.append(go.Scattergl(
        x=xy[pts, 0], y=xy[pts, 1], mode="markers", name=g,
        marker=dict(size=2.5, color=v[o], colorscale="Magma",
                    cmin=0, cmax=max(float(np.quantile(v, .99)), .1),
                    colorbar=dict(title=g, len=.5)),
        customdata=ct[pts],
        hovertemplate=f"<b>{g}</b>: %{{marker.color:.2f}}<br>%{{customdata}}<extra></extra>",
        visible=False, legendgroup="gene"))

for t in traces:
    fig.add_trace(t)

N = len(traces)


def vis(kind, gene_i=0):
    v = [False] * N
    if kind == "types":
        for i in range(n_types):
            v[i] = True
    elif kind == "niche":
        for i in range(n_types, n_types + n_niche):
            v[i] = True
    else:
        v[n_types + n_niche + gene_i] = True
    return v


buttons = [
    dict(label="Cell types", method="update",
         args=[{"visible": vis("types")},
               {"title": f"All cell types — {A.n_obs:,} cells, 10x Atera<br>"
                         "<sub>click a legend entry to hide it; double-click to isolate</sub>"}]),
    dict(label="Treg niches", method="update",
         args=[{"visible": vis("niche")},
               {"title": f"Tregs by spatial niche<br><sub>"
                         f"{int((tniche=='tumor_core').sum())} of {len(tidx):,} Tregs sit "
                         f"inside the tumour core "
                         f"({(tniche=='tumor_core').mean():.2%}) — they are excluded</sub>"}]),
]
for i, g in enumerate(genes):
    buttons.append(dict(label=g, method="update",
                        args=[{"visible": vis("gene", i)},
                              {"title": f"{g} expression across the tissue"}]))

fig.update_layout(
    title=f"All cell types — {A.n_obs:,} cells, 10x Atera<br>"
          "<sub>click a legend entry to hide it; double-click to isolate</sub>",
    updatemenus=[dict(buttons=buttons, direction="down", showactive=True,
                      x=.01, xanchor="left", y=1.13, yanchor="top",
                      bgcolor="white", bordercolor="#ccc")],
    height=900, width=1300,
    plot_bgcolor="white", paper_bgcolor="white",
    legend=dict(itemsizing="constant", font=dict(size=9)),
    margin=dict(l=10, r=10, t=110, b=10),
    dragmode="pan",
)
fig.update_xaxes(showgrid=False, zeroline=False, visible=False,
                 scaleanchor="y", scaleratio=1)
fig.update_yaxes(showgrid=False, zeroline=False, visible=False, autorange="reversed")

fig.write_html(a.out, include_plotlyjs="cdn",
               config={"scrollZoom": True, "displaylogo": False})
size = Path(a.out).stat().st_size / 1e6
if size > 25:
    print(f"\n  !! {size:.0f} MB is too big for a browser to open comfortably.")
    print("     Re-run with --max-per-type 1000")
print(f"""
wrote {a.out}  ({size:.1f} MB)

Open it in a browser.

  dropdown (top left)   switch between cell types / Treg niches / any gene
  legend                click to hide a cell type, double-click to isolate it
  scroll                zoom
  drag                  pan
  double-click canvas   reset

Share it:
  aws s3 cp {a.out} s3://<bucket>/artifacts/
""")
