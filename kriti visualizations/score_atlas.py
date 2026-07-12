"""
score_atlas.py

1. Split spatial Tregs: TUMOUR-INFILTRATING vs the rest (by spatial niche)
2. DE between them  ->  the infiltration signature
3. Score ATLAS TREGS with it
4. Take the top 5%  ->  barcodes for the perturbation step
5. Show them on the FULL AIFI atlas UMAP, so you can see they localize

    python score_atlas.py \
      --atera work/atera.h5ad \
      --atlas work/human_immune_health_atlas_cd4t-treg-dnt.h5ad \
      --niche-py ~/SageMaker

WHY SCORE TREGS ONLY BUT PLOT EVERYTHING
----------------------------------------
scLDM.CD4 perturbs CD4 T cells; a high-scoring monocyte is not a control cell. And since
every candidate is already a Treg, the score stops asking "is this a Treg?" and starts
asking "WHICH Tregs look like the ones at the invasive front?" — the actual question.

But plotting only Tregs hides the important thing. On the FULL atlas UMAP you can see
whether the selected barcodes LOCALIZE to a coherent region of Treg space, or scatter.
If they localize, the signature found a real cell state. If they scatter, it found noise.

OUTPUT
------
    artifacts/margin_signature.csv     the gene list
    artifacts/treg_scores.parquet      every atlas Treg + score
    artifacts/selected_barcodes.csv    <- THE HANDOFF (top 5%)
    figures/atlas_umap.png             full atlas UMAP + selected barcodes
    figures/atlas_scores.png           distribution, subtype enrichment
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

sc.settings.n_jobs = -1

ap = argparse.ArgumentParser()
ap.add_argument("--atera", default="work/atera.h5ad")
ap.add_argument("--atlas", required=True)
ap.add_argument("--cell-type", default="Regulatory T Cells")
ap.add_argument("--n-genes", type=int, default=50)
ap.add_argument("--k", type=int, default=15)
ap.add_argument("--margin-cut", type=float, default=0.20)
ap.add_argument("--top-pct", type=float, default=5.0)
ap.add_argument("--subsample", type=int, default=300_000)
ap.add_argument("--niche-py", default=None)
ap.add_argument("--niche-index", default="artifacts/niche_index.pkl")
ap.add_argument("--outdir", default="artifacts")
a = ap.parse_args()

if a.niche_py:
    sys.path.insert(0, a.niche_py)
OUT = Path(a.outdir); OUT.mkdir(parents=True, exist_ok=True)
FIG = Path("figures"); FIG.mkdir(exist_ok=True)

MARGIN_NBRS = ["Migratory Invasive Basal Cells", "Metabolic Invasive Basal Cells",
               "Hypoxic Tumor Cells"]

BAD_PREFIX = ("RPL", "RPS", "MT-", "MTRNR", "HB", "MALAT1", "NEAT1")
BAD_GENES = {"ACTB", "ACTG1", "TMSB4X", "TMSB10", "B2M", "GAPDH", "EEF1A1", "FTL",
             "FTH1", "TPT1", "UBA52", "PTMA", "HSPA8", "H3-3B"}

# Stromal / epithelial / adhesion. A Treg does not transcribe collagen. If these appear
# it is segmentation spillover — and INFILTRATING Tregs are by construction the ones
# touching tumour and stroma, so they are maximally exposed. Leave them in and the
# "infiltration signature" is a contamination signature.
AMBIENT = set("""COL1A1 COL1A2 COL3A1 COL4A1 COL4A2 COL5A1 COL5A2 COL6A1 COL6A2 COL6A3
DCN LUM POSTN FN1 SPARC SPARCL1 MMP2 MMP11 MMP14 FBN1 HSPG2 CALD1 TPM2 ACTA2 TAGLN
MYH11 MYL9 DES NOTCH3 PDGFRA PDGFRB RGS5 KRT5 KRT6A KRT13 KRT14 KRT17 KRT8 KRT18
KRT19 EPCAM SFN SPRR3 SPRR2A S100A2 DSP PKP1 CSTA CDH1 PECAM1 VWF CLDN5 CDH5 PLVAP
SFRP1 SFRP2 SFRP4 THBS1 THBS2 CCN1 CCN2 CCN5 DKK3 FGF7 LTBP1 LTBP2 C1R C1S C3 C7
ABI3BP TGM2 VCAM1 IGF1 IGFBP3 IGFBP5 IGFBP7 ELN FBLN1 FBLN2 MGP AEBP1
MYH9 TLN1 ACTN4 PALLD TNS1 MYLK MARCKS DIO2 NREP SPATS2L""".split())


# ══════════════════════════════ 1. SPATIAL TREGS BY NICHE
print("=" * 70)
print("1. SPATIAL TREGS: TUMOUR-INFILTRATING vs THE REST")
print("=" * 70)

atera = sc.read_h5ad(a.atera)
atera.X = atera.layers["counts"].copy() if "counts" in atera.layers else atera.X.copy()
sc.pp.normalize_total(atera, target_sum=1e4)
sc.pp.log1p(atera)

import niche  # noqa: E402
niche.CACHE = Path(a.niche_index)
IDX = niche.load()

nb = IDX.per_cell(a.cell_type, k=a.k)
tregs = atera[nb.index.values].copy()
margin_frac = nb[[c for c in MARGIN_NBRS if c in nb.columns]].sum(axis=1).values
is_margin = margin_frac >= a.margin_cut
tregs.obs["group"] = np.where(is_margin, "infiltrating", "other")

n_inf, n_oth = int(is_margin.sum()), int((~is_margin).sum())
print(f"\n{a.cell_type}: {tregs.n_obs:,}")
print(f"  infiltrating  {n_inf:,}  (>={a.margin_cut:.0%} invasive/hypoxic tumour neighbours)")
print(f"  other         {n_oth:,}")
if n_inf < 100:
    raise SystemExit(f"only {n_inf} infiltrating Tregs — lower --margin-cut")
del atera


# ══════════════════════════════ 2. THE SIGNATURE
print("\n" + "=" * 70)
print("2. DE: INFILTRATING vs OTHER TREGS")
print("=" * 70)

sc.tl.rank_genes_groups(tregs, "group", groups=["infiltrating"], reference="other",
                        method="wilcoxon", n_genes=400)
de = sc.get.rank_genes_groups_df(tregs, "infiltrating")
de = de[(de.logfoldchanges > 0.25) & (de.pvals_adj < 0.05)]
n_sig = len(de)
de = de[~de.names.str.startswith(BAD_PREFIX) & ~de.names.isin(BAD_GENES)]
n_ab = len(de)
de = de[~de.names.isin(AMBIENT)]

print(f"\nsignificant:              {n_sig}")
print(f"  after abundance filter: {n_ab}")
print(f"  after ambient filter:   {len(de)}   <- stromal/epithelial spillover removed")
if len(de) < 15:
    print("  !! few genes survive — the infiltration signal may be largely contamination")

sig = de.head(a.n_genes).names.tolist()
print(f"\nSIGNATURE ({len(sig)} genes):")
for i in range(0, len(sig), 8):
    print("  " + ", ".join(sig[i:i + 8]))
if "CTLA4" in sig:
    print(f"\n  CTLA4 present (rank {sig.index('CTLA4') + 1}) — ipilimumab target,")
    print("  recovered from tissue with no prior knowledge. Positive control.")

de.head(a.n_genes)[["names", "logfoldchanges", "pvals_adj", "scores"]].to_csv(
    OUT / "margin_signature.csv", index=False)
print(f"\nwrote {OUT/'margin_signature.csv'}")


# ══════════════════════════════ 3. ATLAS: score Tregs, KEEP everything for plotting
print("\n" + "=" * 70)
print("3. SCORE ATLAS TREGS")
print("=" * 70)

atlas = sc.read_h5ad(a.atlas)
print(f"atlas: {atlas.n_obs:,} cells x {atlas.n_vars:,} genes")
if a.subsample and atlas.n_obs > a.subsample:
    sc.pp.subsample(atlas, n_obs=a.subsample, random_state=0)
    print(f"  subsampled -> {atlas.n_obs:,}")

atlas.var_names_make_unique()
if float(atlas.X[:1000].max()) > 50:
    sc.pp.log1p(atlas)

label = next((c for c in ["AIFI_L3", "AIFI_L2", "AIFI_L1"] if c in atlas.obs),
             atlas.obs.columns[0])
print(f"\nlabel column: {label}  ({atlas.obs[label].nunique()} subtypes)")
print(atlas.obs[label].value_counts().head(10).to_string())

is_treg = atlas.obs[label].astype(str).str.contains("Treg", case=False, na=False).values
print(f"\nAIFI Tregs: {int(is_treg.sum()):,}")
if is_treg.sum() < 500:
    raise SystemExit("too few atlas Tregs — raise --subsample")

present = [g for g in sig if g in atlas.var_names]
print(f"signature genes in atlas: {len(present)}/{len(sig)}")
if len(present) < 10:
    raise SystemExit("too few genes transfer — check gene symbol builds")

# Score the WHOLE atlas (cheap), then restrict SELECTION to Tregs. This way the full
# UMAP can be coloured by score, which shows whether the signature is Treg-specific
# or just lighting up any activated cell.
sc.tl.score_genes(atlas, present, score_name="score", ctrl_size=100)
s_all = atlas.obs["score"].values
s_treg = s_all[is_treg]


# ══════════════════════════════ 4. TOP 5% OF TREGS
print("\n" + "=" * 70)
print(f"4. SELECT TOP {a.top_pct:.0f}% OF TREGS")
print("=" * 70)

cut = float(np.percentile(s_treg, 100 - a.top_pct))
picked = is_treg & (s_all >= cut)
atlas.obs["selected"] = picked

print(f"\ncutoff (P{100-a.top_pct:.0f} of Tregs) = {cut:.3f}")
print(f"selected {int(picked.sum()):,} of {int(is_treg.sum()):,} atlas Tregs")

comp = atlas.obs.loc[picked, label].value_counts(normalize=True)
base = atlas.obs.loc[is_treg, label].value_counts(normalize=True)
enr = (comp / base.reindex(comp.index)).sort_values(ascending=False)

print(f"\nselected vs all Tregs, by {label}:")
for k in enr.head(8).index:
    print(f"  {str(k)[:38]:40s} {comp[k]:6.1%} of picked  ({enr[k]:.2f}x)")
print("\n  ^ if ACTIVATED / EFFECTOR Treg subtypes are enriched and NAIVE ones depleted,")
print("    the infiltration programme is picking activated Tregs out of blood — which is")
print("    the biologically sensible answer, and a real result.")

# is the signature Treg-specific, or does it light up anything activated?
nont = atlas.obs.loc[~is_treg].groupby(label, observed=True)["score"].mean()
nont = nont.sort_values(ascending=False)
print(f"\nhighest-scoring NON-Treg subtypes (sanity check):")
print(nont.head(5).round(3).to_string())
print("  ^ if these rival the Tregs, the signature is not Treg-specific. Worth knowing.")


# ══════════════════════════════ 5. BARCODES
print("\n" + "=" * 70)
print("5. BARCODES")
print("=" * 70)

bc = pd.DataFrame({
    "barcode": atlas.obs_names[picked].astype(str),
    "aifi_label": atlas.obs.loc[picked, label].astype(str).values,
    "infiltration_score": np.round(s_all[picked], 4),
}).sort_values("infiltration_score", ascending=False)
bc.to_csv(OUT / "selected_barcodes.csv", index=False)
print(f"\nwrote {OUT/'selected_barcodes.csv'}   {len(bc):,} barcodes")
print(bc.head(8).to_string(index=False))

scored = pd.DataFrame({
    "barcode": atlas.obs_names.astype(str),
    "aifi_label": atlas.obs[label].astype(str).values,
    "infiltration_score": np.round(s_all, 4),
    "is_treg": is_treg,
    "selected": picked,
})
scored.to_parquet(OUT / "treg_scores.parquet", index=False)
print(f"wrote {OUT/'treg_scores.parquet'}   (all {atlas.n_obs:,} atlas cells)")

# Same table, named for the MCP stub. map_spatial_to_single reads this.
scored.to_parquet(OUT / "atlas_mapping.parquet", index=False)
print(f"wrote {OUT/'atlas_mapping.parquet'}   <- copy to mcp_server/data/")
print("\n  cp artifacts/atlas_mapping.parquet artifacts/margin_signature.csv \\")
print("     spatial-awareness/mcp_server/data/")


# ══════════════════════════════ 6. THE FULL ATLAS UMAP
print("\n" + "=" * 70)
print("6. FIGURES")
print("=" * 70)

if "X_umap" not in atlas.obsm:
    print("no UMAP in the atlas — computing (few minutes)")
    sc.pp.highly_variable_genes(atlas, n_top_genes=2000)
    sc.pp.pca(atlas, n_comps=40)
    sc.pp.neighbors(atlas, n_neighbors=15)
    sc.tl.umap(atlas)
else:
    print("using the atlas's own UMAP")
u = atlas.obsm["X_umap"]

fig = plt.figure(figsize=(19, 8.5))

# (1) THE FIGURE: full atlas, every subtype, selected barcodes on top
ax = fig.add_subplot(1, 3, 1)
cats = atlas.obs[label].value_counts().index[:22]
cmap = plt.get_cmap("tab20")
for i, c in enumerate(cats):
    m = (atlas.obs[label] == c).values
    ax.scatter(u[m, 0], u[m, 1], s=1.2, color=cmap(i % 20), linewidths=0,
               rasterized=True, label=f"{c} ({m.sum():,})")
ax.scatter(u[picked, 0], u[picked, 1], s=9, facecolors="none", edgecolors="black",
           linewidths=.5, rasterized=True, label=f"SELECTED ({int(picked.sum()):,})")
ax.set_xticks([]); ax.set_yticks([])
ax.set_title(f"AIFI atlas — all {atlas.n_obs:,} cells, {len(cats)} subtypes\n"
             "black rings = selected barcodes", fontsize=11)
ax.legend(fontsize=5.5, markerscale=4, loc="center left", bbox_to_anchor=(1.0, .5),
          frameon=False, ncol=1)

# (2) the same UMAP, coloured by score
ax = fig.add_subplot(1, 3, 2)
o = np.argsort(s_all)
p = ax.scatter(u[o, 0], u[o, 1], c=s_all[o], s=2, cmap="magma", linewidths=0,
               rasterized=True)
plt.colorbar(p, ax=ax, shrink=.55, label="tumour-infiltration score")
ax.set_xticks([]); ax.set_yticks([])
ax.set_title("Infiltration score across the whole atlas\n"
             "(should concentrate in the Treg region)", fontsize=11)

# (3) selected vs everything
ax = fig.add_subplot(1, 3, 3)
ax.scatter(u[:, 0], u[:, 1], s=1.2, c="#e4e4e4", linewidths=0, rasterized=True)
ax.scatter(u[is_treg, 0], u[is_treg, 1], s=2, c="#f0b27a", linewidths=0,
           rasterized=True, label=f"all Tregs ({int(is_treg.sum()):,})")
ax.scatter(u[picked, 0], u[picked, 1], s=5, c="#c0392b", linewidths=0,
           rasterized=True, label=f"selected ({int(picked.sum()):,})")
ax.set_xticks([]); ax.set_yticks([])
ax.set_title(f"Top {a.top_pct:.0f}% of Tregs\n"
             "do they localize, or scatter?", fontsize=11)
ax.legend(fontsize=8, markerscale=4, loc="best", frameon=False)

plt.tight_layout()
plt.savefig(FIG / "atlas_umap.png", dpi=140)
plt.close()
print(f"  {FIG/'atlas_umap.png'}   <- THE SLIDE")

# supporting: distribution + subtype enrichment
fig, ax = plt.subplots(1, 3, figsize=(16, 4.4))

ax[0].hist(s_all[~is_treg], bins=80, alpha=.6, color="#95a5a6", density=True,
           label="non-Treg")
ax[0].hist(s_treg, bins=80, alpha=.75, color="#c0392b", density=True, label="Treg")
ax[0].axvline(cut, c="k", ls="--", lw=1.5, label=f"P{100-a.top_pct:.0f} = {cut:.2f}")
ax[0].set_xlabel("infiltration score"); ax[0].set_ylabel("density")
ax[0].set_title("Score distribution", fontsize=11)
ax[0].legend(fontsize=8)

bt = atlas.obs.groupby(label, observed=True)["score"].agg(["mean", "size"])
bt = bt[bt["size"] >= 30].sort_values("mean").tail(14)
ax[1].barh(range(len(bt)), bt["mean"],
           color=["#c0392b" if "treg" in str(i).lower() else "#95a5a6" for i in bt.index])
ax[1].set_yticks(range(len(bt))); ax[1].set_yticklabels(bt.index, fontsize=7)
ax[1].axvline(0, c="k", lw=.8)
ax[1].set_xlabel("mean score")
ax[1].set_title("Mean score by subtype\nred = Treg", fontsize=11)

e = enr.head(10).iloc[::-1]
ax[2].barh(range(len(e)), e.values,
           color=["#c0392b" if v > 1 else "#2980b9" for v in e.values])
ax[2].set_yticks(range(len(e))); ax[2].set_yticklabels(e.index, fontsize=7)
ax[2].axvline(1, c="k", ls="--", lw=1)
ax[2].set_xlabel("enrichment among selected (vs all Tregs)")
ax[2].set_title(f"What the top {a.top_pct:.0f}% are", fontsize=11)

plt.tight_layout()
plt.savefig(FIG / "atlas_scores.png", dpi=130)
plt.close()
print(f"  {FIG/'atlas_scores.png'}")

print(f"""
SUMMARY
-------
{n_inf:,} infiltrating vs {n_oth:,} other Tregs (spatial)
  -> {len(sig)} DE genes (abundance + ambient masked)
  -> scored {atlas.n_obs:,} atlas cells, selected from the {int(is_treg.sum()):,} Tregs
  -> top {a.top_pct:.0f}% = {int(picked.sum()):,} barcodes

HANDOFF:  artifacts/selected_barcodes.csv
SLIDE:    figures/atlas_umap.png
""")
