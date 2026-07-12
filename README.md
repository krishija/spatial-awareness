# Spatial Awareness

Owkin *Rewiring Biology* hackathon project.

Start from exhausted CD4 T cells in spatial tumor data, propose knockouts, pull
independent evidence (literature, measured perturbations, virtual-cell simulation,
TCGA survival), and update belief in bits — so a nice-looking answer still has to
earn its weight.

```
frontend/     Spatial tissue map + separate UMAP/atlas window; literature chat
mcp_server/   12 MCP tools, Bedrock research agent, REST proxy for the UI
```

The UI and the agent share the same tool registry. They are not fully wired into
one product yet — you can demo either side on its own.

Atlas mapping pipeline (Kriti): `kriti visualizations/` — `score_atlas.py` builds
`atlas_mapping.parquet`; the MCP tool reads it from `mcp_server/data/`.

## What works today

| Piece | Status |
|-------|--------|
| Spatial explorer | Fixture samples in the browser (`crc-01`, `nsclc-03`, `mel-07`) |
| UMAP / atlas window | Second view at `?view=umap` (open from the toolbar) |
| Literature + KO suggestions | Live via `spatial-api` → You.com (`YOU_API_KEY`) |
| `list_candidate_cells` | Real 10x Atera table when `cells.parquet` is present |
| `simulate_perturbations` | Live scLDM when weights are configured; otherwise a **labeled** `scldm_surrogate` (`backend` field). Out-of-vocab genes still `ok: false` |
| Literature cards | Stance extraction (support / contradict / neutral) with PMC/You.com sources |
| Measured evidence + next experiment | Training corpora / LINCS-style hits; graph-backed experiment suggestions |
| TCGA survival | Cox association (local → cBioPortal → fixture). Bulk prognostic signal, not cell-level proof |
| Research agent | Bedrock ↔ MCP: gene binding after COMMIT, ≥2 grounded modalities before REPORT, mandatory non-load-bearing simulate step, independence clustering, conflict-aware gating |
| Agent traces | Example runs under `mcp_server/artifacts/agent_traces/phase34/` |
| `map_spatial_to_single` | Signature transfer (spatial Treg DE → AIFI atlas barcodes). Real when `atlas_mapping.parquet` is in `mcp_server/data/`; fixture fallback with warning otherwise. Pipeline in `kriti visualizations/` |

## Honest failure modes

Tools do not invent missing biology:

- No `cells.parquet` → cell listing / sim against real IDs fail with `ok: false`
- No `YOU_API_KEY` → literature/suggestions degrade or error (no fake papers)
- Gene outside scLDM guide vocabulary → `ok: false` (`gene_out_of_vocabulary`)
- Missing live scLDM weights → surrogate deltas are allowed **only** if labeled `backend: scldm_surrogate` (calibrated weak, ~0.16 bits vs ~2 bits for well-matched measured evidence)

## Run the UI + REST proxy

```bash
# terminal 1 — keep YOU_API_KEY server-side
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# put YOU_API_KEY in repo-root .env
spatial-api            # http://0.0.0.0:8001

# terminal 2
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Optional: `VITE_API_BASE_URL` (default `http://localhost:8001`).

## Run MCP + research agent

```bash
cd mcp_server && source .venv/bin/activate

# optional — real Atera cells for the agent path
aws s3 cp s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/mcp_data/cells.parquet data/

spatial-mcp            # http://0.0.0.0:8000/mcp
spatial-agent "Investigate CD4 T-cell exhaustion in sample atera-cervical-01…"
# needs AWS_BEARER_TOKEN_BEDROCK (or IAM) in repo-root .env
```

Useful flags: `--commit-gene PDCD1`, `--json out.json`, `--md out.md`,
`--max-iterations`, `--wall-clock`.

SageMaker overnight-style run: `mcp_server/scripts/run_phase34_sagemaker.sh`.

## Tests + calibration

```bash
cd mcp_server && source .venv/bin/activate
pytest tests/ -q
python -m spatial_mcp.agent.calibrate_benchmark
```

More detail: [`mcp_server/README.md`](mcp_server/README.md),
[`frontend/README.md`](frontend/README.md),
[`DATA_CONTRACT.md`](DATA_CONTRACT.md).
