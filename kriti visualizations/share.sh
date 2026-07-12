#!/usr/bin/env bash
# ==============================================================================
# Push everything to S3 + package the scripts for the team.
#
#     bash share.sh
#
# Run from ~/SageMaker (where the scripts and artifacts/ and figures/ live).
# ==============================================================================
set -uo pipefail

BUCKET="owkin-hackathon26-spatialawareness-raw-data"
B="s3://$BUCKET"

echo "=============================================================="
echo "1. RESULTS -> S3"
echo "=============================================================="

# --- the handoff: what the perturbation arm needs ---
echo
echo ">>> handoff/"
for f in artifacts/selected_barcodes.csv \
         artifacts/margin_signature.csv \
         artifacts/atlas_mapping.parquet; do
  [ -f "$f" ] && aws s3 cp "$f" "$B/handoff/" && echo "    $f"
done

# --- MCP data: what the stubs read ---
echo
echo ">>> artifacts/mcp_data/   (the MCP stubs read these)"
for f in artifacts/cells.parquet \
         artifacts/atlas_mapping.parquet \
         artifacts/margin_signature.csv; do
  [ -f "$f" ] && aws s3 cp "$f" "$B/artifacts/mcp_data/" && echo "    $f"
done
# it may already be in the repo instead
if [ -f spatial-awareness/mcp_server/data/cells.parquet ]; then
  aws s3 cp spatial-awareness/mcp_server/data/cells.parquet "$B/artifacts/mcp_data/"
  echo "    (from repo) cells.parquet"
fi

# --- everything else ---
echo
echo ">>> artifacts/   (all analysis outputs)"
aws s3 cp artifacts/ "$B/artifacts/" --recursive \
  --exclude "*" \
  --include "*.parquet" --include "*.csv" --include "*.json" --include "*.pkl" \
  2>/dev/null && echo "    done"

echo
echo ">>> figures/"
aws s3 cp figures/ "$B/figures/" --recursive 2>/dev/null && echo "    done"

echo
echo ">>> explorer.html   (interactive tissue explorer)"
[ -f explorer.html ] && aws s3 cp explorer.html "$B/" && echo "    done"

# --- shared objects ---
echo
echo ">>> objects/   (h5ads for teammates)"
for f in work/atera_treg.h5ad work/atera_cd4.h5ad artifacts/atlas_control_cells.h5ad; do
  [ -f "$f" ] && aws s3 cp "$f" "$B/objects/" && echo "    $f"
done


echo
echo "=============================================================="
echo "2. SCRIPTS -> zip"
echo "=============================================================="

STAGE=$(mktemp -d)/spatial-scripts
mkdir -p "$STAGE"

for f in niche.py \
         load_atera2.py \
         feasibility.py \
         precompute_cells.py \
         score_atlas.py \
         plot_niches.py \
         make_explorer.py \
         list_candidate_cells.py \
         map_spatial_to_single.py \
         environment.yml; do
  [ -f "$f" ] && cp "$f" "$STAGE/" && echo "    $f"
done

cat > "$STAGE/README.md" <<'EOF'
# Spatial arm — scripts

Everything here runs on the 10x Atera cervical cancer section (CC BY 4.0, public).

## Setup

```bash
conda env create -f environment.yml
conda activate atera
```

`setuptools<81` is pinned deliberately — newer versions removed `pkg_resources`,
which breaks `spatialdata_io`.

## Pipeline

| # | script | does | output |
|---|---|---|---|
| 1 | `load_atera2.py` | reads the Atera `_outs` bundle | `work/atera.h5ad` |
| 2 | `niche.py --build` | spatial kNN index + permutation null | `artifacts/niche_index.pkl` |
| 3 | `precompute_cells.py` | assigns each cell a niche | `cells.parquet` (MCP) |
| 4 | `score_atlas.py` | spatial Treg signature -> AIFI atlas -> **barcodes** | `selected_barcodes.csv` |
| 5 | `plot_niches.py` | tissue figures | `figures/` |
| 6 | `make_explorer.py` | interactive HTML | `explorer.html` |

```bash
python load_atera2.py atera_outs --out work/atera.h5ad
python niche.py --adata work/atera.h5ad --build
python niche.py --query "Regulatory T Cells" --k 15

python precompute_cells.py --adata work/atera.h5ad \
  --niche-index artifacts/niche_index.pkl --niche-py . --out mcp_server/data

python score_atlas.py --adata work/atera.h5ad \
  --atlas work/human_immune_health_atlas_cd4t-treg-dnt.h5ad --niche-py .

python plot_niches.py --adata work/atera.h5ad --niche-py .
python make_explorer.py --adata work/atera.h5ad --niche-py .
```

## MCP stubs

`list_candidate_cells.py` and `map_spatial_to_single.py` go in
`mcp_server/src/spatial_mcp/stubs/`. Both are **self-contained** — no scaffold or
schema changes. Both fall back to the fixtures and **say so** if the parquet files
are missing, so nobody demos on fake data by accident.

They read `mcp_server/data/`:

```bash
aws s3 cp s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/mcp_data/ \
  mcp_server/data/ --recursive
```

## The findings

**Tregs are excluded from the tumour.** 20 of 28,967 have a tumour-core neighbourhood,
in a section where tumour cells are 258k of 715k. 26,478 sit in a lymphoid aggregate
(CAF 2.3x, plasma 1.9x, macrophage 1.8x, B 1.6x, against a permutation null over all
715k cells). 2,469 contact the invasive margin.

**CTLA4** is a top-20 gene up in margin-adjacent Tregs. CTLA4 is the target of
ipilimumab, which works by disabling exactly these tumour-infiltrating Tregs. Recovered
from tissue with no prior knowledge — the positive control.

## Things that will bite you

**Ambient contamination.** Our first Δ was topped by MMP11, COL4A1, POSTN, SFRP1 —
fibroblast and basement-membrane genes. **Tregs don't transcribe those.** They were
segmentation spillover from neighbouring cells, and they looked *completely convincing*:
large effects, tiny p-values. Every script masks stromal/epithelial genes by default.
Turn the mask off and you get a beautiful, confident, entirely wrong answer.

**Naive & Memory T Cells is a mixed CD4/CD8 bucket** at this detection depth. Naive CD4
and naive CD8 are near-identical transcriptionally. We excluded it rather than push
contaminated cells through a CD4-only perturbation model.

**Partial circularity.** 10x annotated tumour subtypes partly *by spatial location*, so
immune-vs-tumour enrichment is partly circular. Immune-immune enrichment is not.

**n = 1 section.** Every statistic is within-sample. Pipeline demonstration, not a
cohort claim.

## Handoff to the perturbation arm

```
Δ_observed  = mean(margin Tregs) − mean(lymphoid Tregs)      [Atera, both poles]
Δ_predicted = mean(generate(guide=g)) − mean(generate(ctrl)) [model, both]
score(g)    = cosine(Δ_predicted, −Δ_observed)
```

Two deltas, each computed **within one platform**, so each platform's bias cancels.
Comparing absolute expression across platforms does not — Atera is probe-based FFPE
in-situ at ~10x lower depth than Chromium, and is out of distribution for scLDM.CD4.

`selected_barcodes.csv` = AIFI atlas cell IDs. Subset the atlas h5ad on them; that's the
control population.
EOF

ZIP="spatial-scripts-$(date +%m%d-%H%M).zip"
(cd "$(dirname "$STAGE")" && zip -qr "$OLDPWD/$ZIP" spatial-scripts)
rm -rf "$(dirname "$STAGE")"

aws s3 cp "$ZIP" "$B/scripts/"

echo
echo "=============================================================="
echo "DONE"
echo "=============================================================="
echo
echo "  $ZIP   <- download this, or send the team the S3 link"
echo
echo "  s3://$BUCKET/handoff/       barcodes + signature  (perturbation arm)"
echo "  s3://$BUCKET/artifacts/     all analysis outputs"
echo "  s3://$BUCKET/figures/       plots"
echo "  s3://$BUCKET/explorer.html  interactive tissue explorer"
echo "  s3://$BUCKET/scripts/       this zip"
echo
echo "Team pulls the scripts with:"
echo "  aws s3 cp s3://$BUCKET/scripts/$ZIP ."
echo "  unzip $ZIP"
echo
aws s3 ls "$B/" --recursive --human-readable | tail -25
