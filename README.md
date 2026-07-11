# Spatial Awareness

<p align="center">
  <img src="media/spatial-awareness.png" alt="Spatial Awareness" width="100%">
</p>

**Read a cell's microenvironment as a physical field, map its phenotype onto a single-cell atlas by optimal transport, and surface confidence-scored immune targets — from spatial tissue, in situ.**

> Physics where it's load-bearing, standard biology everywhere else. Built for the Owkin "Rewiring Biology" hackathon.

---

## Biology — the problem

In the tumour microenvironment (TME), the same broad immune cell type behaves very differently depending on *where* it sits and *what surrounds it*. A CD4 T cell touching tumour is not the CD4 T cell three cell-diameters away in a lymphoid aggregate:

- **CD4 T cells** span helper and regulatory states — Th1 (pro-inflammatory, anti-tumour), Th17, Tfh, and **Tregs** (immunosuppressive, often enriched at the tumour edge).

Single-cell-resolution spatial assays give us *where* every cell is, but their cell-type calls are **coarse** (just "CD4 T cell"). Single-cell reference **atlases** carry the *granular* phenotype but lose spatial context. The scientific move is to bring them together: **map coarse spatial cells onto the granular atlas, in their spatial context**, to recover fine-grained state *in situ* — and then read off phenotype-specific vulnerabilities.

**Goal:** given a spatial dataset and a reference atlas, find the atlas cells most similar to a selected spatial population, with a calibrated confidence — the input to any downstream target hunt.

---

## Approach — physics, not a lookup table

Two steps that look like plumbing are secretly physics problems, and that's where the method earns its rigor:

1. **"Cells near the tumour" is a field problem.** Replace a hard radius with a continuous exposure field derived from a diffusing signal.
2. **"Most similar atlas cells" is a transport problem.** Map the *distribution* of selected cells onto the atlas distribution by optimal transport, which yields a soft, confidence-scored mapping instead of a brittle nearest-neighbour label.

Everything else (subclustering, enrichment) stays standard bioinformatics.

---

## Pipeline

```
spatial cells ─▶ select (field / subcluster) ─▶ keep per-cell [X | u] ─▶ optimal transport ─▶ atlas mapping + confidence
```

1. **Input** — single-cell-resolution spatial dataset with coarse cell-type labels.
2. **Select** — a subset of cells, either by subclustering or by **spatial proximity as a continuous field** (physics).
3. **Aggregate** — into a **per-cell** `cell × gene` matrix (never mean-pooled — see below).
4. **Map** — the selected cells onto the atlas by **field-aware optimal transport** (physics core).
5. *(downstream)* profile the mapped cells → top genes, enriched pathways, candidate targets → in-silico test → clinical link.

---

## The physics & math

### 1. Microenvironment as a field (discrete → continuous)

Model a tumour-secreted signal as a diffusible factor (diffusion `D`, degradation `k`). At steady state, the Green's-function superposition over tumour cells `𝒯` gives a screened (Yukawa) field — the exponential decay falls out of the physics, it isn't assumed:

$$D\nabla^2\phi - k\phi + \sum_{t\in\mathcal T}\delta(\mathbf x-\mathbf x_t)=0 \;\;\Longrightarrow\;\; \phi(\mathbf x)=\frac{1}{2\pi D}\sum_{t\in\mathcal T} K_0\!\Big(\tfrac{\lVert\mathbf x-\mathbf x_t\rVert}{\lambda}\Big),\qquad \lambda=\sqrt{D/k}$$

Each cell gets an exposure `u_i = φ(x_i)` — a graded covariate, not a binary mask, with a single physical parameter `λ` (the signalling range). Colocation is validated against a random null with the pair-correlation function `g(r) > 1`.
*ESTABLISHED (screened Green's function, KDE, Ripley's g(r)); the contribution is a physically-parameterised exposure field feeding the map.*

### 2. Keep per-cell — the distribution matters

Optimal transport maps a *distribution* of cells; mean-pooling to one vector destroys both the distribution and the field, collapsing the next step to a centroid lookup. So the representation is a per-cell matrix with the field carried as a column, `[X | u]`.

### 3. Atlas mapping by field-aware optimal transport (core)

Map the selected-cell distribution `μ` onto the atlas `ν` by entropic OT:

$$P^\star=\arg\min_{P\in\Pi(\mu,\nu)}\ \langle P,C\rangle-\varepsilon\,H(P),\qquad H(P)=-\sum_{ij}P_{ij}\log P_{ij}$$

solved by the Sinkhorn algorithm. It returns three things a nearest-neighbour lookup cannot:

- **soft coupling** `P*` — each cell distributes mass over atlas states rather than snapping to one;
- **transport cost** — how far the population sits from atlas archetypes (a distance, not just a label);
- **per-cell confidence** — the row entropy `κ_i = -Σ_j P̄_ij log P̄_ij` of the normalized coupling; low = confident, high = ambiguous.

The **field-aware cost** carries the microenvironment into the map:

$$C_{ij} \;=\; d_{\text{expr}}(i,j) \;+\; \gamma\, d_{\text{field}}(i,j)$$

with `d_expr` a cosine/PCA distance or a diffusion-map (heat-kernel) metric on the atlas manifold, so "similar" means close *on the curved manifold of cell states*. An optional **Fused Gromov–Wasserstein** term additionally matches spatial geometry.

**Temperature interpretation:** the Sinkhorn plan is a Gibbs/Boltzmann distribution over couplings with `ε` as temperature — small `ε` sharpens the map, large `ε` spreads it — which is what makes the coupling entropy a meaningful confidence.
*ESTABLISHED (entropic OT / Sinkhorn: Cuturi; Peyré–Cuturi). Prior art: moscot, SCOT, Tangram, Waddington-OT. Claim = field-aware cost + entropy confidence as a synthesis for spatial→atlas mapping.*

### 4. Optional — quantum solve

Discrete OT / assignment is a canonical **QUBO**, so the mapping can be solved on quantum annealing hardware. Variable count = `cells × atlas-cells`, so it runs on **niche-sized patches**, with classical Sinkhorn at full scale. Framed as a quantum-ready formulation verified against the classical solver — no advantage claim.

---

## Biological resources

**Atlases (mapping target — method is atlas-agnostic):**
- CD4 T cell atlas — Allen Immune Health Atlas: https://apps.allenimmunology.org/aifi/resources/imm-health-atlas/cell-type-descriptions/cd4-t-cells-dn-t-cells-and-tregs/
- CD8 T cell atlas — Nature Methods: https://www.nature.com/articles/s41592-024-02529-7

**Spatial datasets (single-cell resolution):**
- 10x Atera — whole-transcriptome, single-cell resolution
- 10x Xenium Prime FFPE Human Breast Cancer: https://www.10xgenomics.com/datasets/xenium-prime-ffpe-human-breast-cancer
- Xenium example data: https://www.10xgenomics.com/support/software/xenium-onboard-analysis/latest/resources/xenium-example-data

**Downstream (in-silico perturbation — outside the mapping core):**
- STATE (CD8 virtual cell); scLDM-CD4: https://virtualcellmodels.cziscience.com/model/scldm-cd4

---

## Honesty: what's novel vs. established

- **Synthesis (ours):** field-aware optimal transport as a spatial→atlas map with a coupling-entropy confidence readout; optional quantum solve.
- **Established (cite):** OT for single-cell mapping (Waddington-OT, moscot, SCOT, Tangram); entropic OT / Sinkhorn (Cuturi; Peyré–Cuturi); screened-field Green's function; Ripley's g(r).
- **Limits:** the map yields confidence-scored *phenotype* mappings, not proven causal targets — causal validation is the downstream in-silico + wet-lab work; coupling→specific target is many-to-one

---

## Repo layout

```
spatial-awareness/
├── frontend/      # Scientist-facing UI (Vite + React). Runs on fixture data.
├── mcp_server/    # K Pro tool server (Python MCP). Stubs + real memory tools.
└── README.md      # You are here
```

The frontend and MCP server do **not** call each other yet. They share the same biology vocabulary (samples, niches, markers) so demos tell one story.

### Frontend — explore tissue & perturbations

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build
```

Details: [`frontend/README.md`](frontend/README.md)

### MCP server — tools for K Pro

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
spatial-mcp            # http://0.0.0.0:8000/mcp
```

Details: [`mcp_server/README.md`](mcp_server/README.md)

### Who edits what

| Person | Edit here |
|--------|-----------|
| Frontend / demo UI | `frontend/` |
| MCP scaffold / memory | `mcp_server/src/spatial_mcp/` (not `stubs/`) |
| Teammate tool owner | **one file** in `mcp_server/src/spatial_mcp/stubs/` |

---

## References

Cuturi (2013), *Sinkhorn Distances* · Peyré & Cuturi, *Computational Optimal Transport* · Schiebinger et al., *Waddington-OT* · Klein et al., *moscot* · Demetci et al., *SCOT* · Biancalani et al., *Tangram* · 10x Genomics, *Atera / Xenium*.
