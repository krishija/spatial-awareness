# Data contract — what the frontend needs from the mapping pipeline + scLDM-CD4

This is the handoff spec for wiring real data into the demo. Everything the
frontend currently renders comes from fixtures (`frontend/src/data/generate.ts`
and `mcp_server/src/spatial_mcp/fixtures/cells.py`). Those fixtures already
match the shape below — that's deliberate, so swapping fake → real is a data
source change, not a UI rewrite. Each field below says whether it exists
today (fixture) or is new.

**Single swap points** (so whoever wires this up knows where to look):
- Frontend: `frontend/src/api/client.ts` — `loadSample()` and `runPerturbation()`
  are the only two functions that touch fake data. Everything else (`TissueMap`,
  `CellPanel`, `MarkerChart`, etc.) just renders whatever shape it's given.
- Backend: `mcp_server/src/spatial_mcp/stubs/*.py` — one file per tool, per
  the existing "teammate swap" convention in the main README.

---

## 1. Per-cell record — map rendering + click-to-inspect

One of these per cell, for every cell in a sample (thousands, not the ~8-cell
fixture set in `mcp_server`). This is what makes a cell clickable and
populates the panel on the right.

| field | type | status | used by |
|---|---|---|---|
| `id` | string | ✅ fixture | everything — the key all other tools (suggestions, perturbation) are called with |
| `x`, `y` | number | ✅ fixture (fake coords) | `TissueMap`, `MiniMap` — needs a documented coordinate convention: currently frontend assumes a normalized `[0,100]×[0,100]` tissue box. Real data (`obsm['spatial']`) is in **microns** — pick one: normalize server-side, or teach the frontend to scale from real bounding box. |
| `cell_type` | enum | ✅ fixture, ⚠️ vocabulary TBD | `TissueMap` coloring, `CellPanel` header, drives `suggest_perturbations` query |
| `niche` | enum (`tumor_core` \| `tumor_margin` \| `lymphoid_proximal`) | ✅ fixture (fake ellipses) | niche overlay, `suggest_perturbations` query, niche-mean comparison chart |
| `exposure_field_u` | float | ❌ new, optional | not rendered yet — the continuous field value `φ(x)` from the physics core (README's screened Green's-function step). Nice upgrade: replace the 3 hardcoded niche ellipses with a real continuous heat field. Not required for MVP — discretize to `niche` server-side if this isn't ready in time. |
| `exhaustion_state` | enum | ✅ fixture | badge label in `CellPanel` |
| `exhaustion_score` | float 0–1 | ⚠️ **exists in `mcp_server` fixtures + schema, missing from frontend `Cell` type entirely** | currently unused in the UI — worth adding as a sortable/visual signal (e.g. size or opacity by score) once real |
| `mapping_confidence` | float 0–1 | ❌ new | the per-cell coupling-entropy `κ_i` from the OT mapping — this is the whole point of the "confidence-scored" pitch in the README, and it isn't shown anywhere in the UI yet. Needs a new field + a badge/visual encoding. |
| `expression` | `Record<gene, number>` | ✅ fixture, 8-gene panel only | `MarkerChart`, perturbation dropdown, `simulate_perturbations` input. **Open question for whoever owns the mapping**: is this raw per-cell spatial expression, or atlas-imputed expression post-mapping? Biologically different, and the demo should say which. |
| `top_genes` | ranked `{gene, value}[]`, optional | ❌ new — **this is what "top genes per cell" needs** | Today "top genes" = the fixed 8-marker bar chart, which is really "checkpoint panel expression," not "this cell's most distinguishing genes." If you want literal top genes, that means ranking across the full ~18k-gene profile (`atera_cd4.h5ad`'s `X`/`layers['counts']`) — by raw expression, or by differential expression vs. niche/cluster baseline. Needs a decision from whoever owns that h5ad pipeline; it's a real feature, not just a rename. |

## 2. Sample-level metadata

| field | type | status |
|---|---|---|
| `sample_id`, `name`, `description` | string | ✅ fixture |
| total cell count, atlas reference used | — | ❌ new, optional (nice for a "how was this computed" tooltip) |
| niche field / bounding box | — | needed either way to normalize `x, y` correctly |

## 3. Perturbation gene vocabulary (the dropdown)

Today the dropdown = `MARKER_GENES`, the same 8 genes as the expression chart
(`frontend/src/types.ts`). Live AI suggestions can already surface 5 more
checkpoint genes (HAVCR2, ENTPD1, CXCL13, TIGIT, TNFRSF9) that exist in
`suggest_perturbations`'s vocabulary but have no chart row or dropdown entry.

**What's needed:** the real, authoritative list of genes **scLDM-CD4 actually
accepts as a knockout target**. That list should become the single source of
truth for: the dropdown, the expression chart's gene rows, and
`suggest_perturbations`'s candidate vocabulary — right now those three are
three separately-maintained lists that happen to mostly overlap. Once you
have the real model's vocabulary, we collapse them into one.

## 4. Virtual cell model (scLDM-CD4) — perturbation I/O contract

This is the "Run" button's real backend, replacing the local synthetic math
in `generate.ts` (`computePerturbation`). Needed:

**Input:**
- `cell_id` → must resolve to a real cell record with **raw counts**, not
  `X` (log1p). Per `README_tcells.md`: *"scLDM.CD4's autoencoder uses a
  negative-binomial loss... feeding it X will run and be silently wrong."*
  This is the single easiest way to get a demo that runs but is wrong —
  worth a loud comment wherever this gets wired.
- `gene` → the knockout target, validated against the vocabulary in §3.
- **Hard constraint**: scLDM-CD4 is **CD4-only** (`compartment == 'CD4'`).
  The frontend needs to know which cell records are CD4 vs. not, and either
  hide/disable the perturbation section for non-CD4 cells (myeloid, tumor,
  stromal, any CD8) or show a clear "not supported for this cell type"
  state instead of silently running something meaningless.

**Output:**
- `before` / `after` expression, same shape as today's `PerturbationResult`
  (`before: Record<gene, number>`, `after: Record<gene, number>`) — confirm
  which gene panel the model actually outputs (just the target gene? the
  full §3 vocabulary? something else?).
- Model-native confidence/uncertainty, if scLDM-CD4 produces one — not
  currently modeled anywhere in the UI, would upgrade the hypothesis card.
- Out-of-vocabulary error shape — the current stub returns
  `{ok: false, error: "gene_out_of_vocabulary"}`; keep that contract if the
  real model has its own vocabulary boundary.

## 5. Hypothesis generation

`HypothesisCard` currently builds its sentence deterministically (biggest
marker deltas + whichever suggestion citation was clicked) — no LLM involved,
same "extractive, not generative" choice we made for the literature chat.
This needs no new teammate variables beyond §1 (mapping) and §4 (perturbation
output) — it's just a template over data you're already providing. The only
decision to make (yours, not a teammate's) is whether to keep it templated or
add a generative synthesis step later, same tradeoff as the chat.

---

## Open decisions worth settling with teammates early

1. **Coordinate convention** — microns vs. normalized `[0,100]`, and who
   normalizes.
2. **Expression semantics** — raw spatial vs. atlas-imputed, per cell.
3. **Gene vocabulary** — one authoritative list from scLDM-CD4, not three
   independently-maintained ones.
4. **"Top genes" scope** — fixed checkpoint panel (already built) vs. true
   per-cell top-N over the full transcriptome (new work, needs a ranking
   method decided).
5. **CD4-only gating** — frontend needs an explicit signal (a `compartment`
   field, or just restricting `cell_type` to CD4 subtypes) to know when to
   hide the perturbation section entirely.
