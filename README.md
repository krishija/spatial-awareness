# Spatial Awareness

Owkin *Rewiring Biology* hackathon project. Exhausted CD4 T cells in spatial tumor
data → knockout proposals → evidence integration (literature / measured / sim /
TCGA) → calibrated belief. The biology is the substrate; the epistemics layer
decides how much any answer is worth.

```
frontend/     Vite + React explorer (fixture tissue maps) + live literature chat
mcp_server/   MCP tools + Bedrock research agent + REST proxy for the browser demo
```

Tissue maps still use fixture samples in the UI. Literature search and knockout
suggestions are live via `spatial-api` (same tools the agent uses). Cell listing /
simulation use real Atera parquet + live scLDM when configured — **fail loud**
otherwise (no silent surrogate biology).

## Policy: fail loud

MCP tools do **not** invent synthetic cells, surrogate KO deltas, or fake papers
when real backends are missing. Missing `cells.parquet`, `YOU_API_KEY`,
`SCLDM_ROOT`, or TCGA/cBioPortal → `ok: false`.

## What's built

| Piece | Reality |
|-------|---------|
| Tissue explorer | Fixture samples (`crc-01`, `nsclc-03`, `mel-07`) |
| Literature chat + KO suggestions | Live via `spatial-api` / You.com |
| `list_candidate_cells` | Real 10x Atera when `mcp_server/data/cells.parquet` present |
| Literature / simulate / TCGA | Live APIs/models; lit returns stance-labeled evidence cards |
| Measured evidence + next experiment | Training corpora / LINCS / graph; calibrated sim trust |
| Epistemics agent | Bayesian log-odds (bits), independence clustering, gating |
| Research agent | Bedrock ↔ MCP (`spatial-agent`) |
| Field-aware OT mapping | Not implemented (`map_spatial_to_single` errors) |

## Run the demo (UI + REST)

```bash
# terminal 1 — REST proxy (browser must not hold YOU_API_KEY)
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# YOU_API_KEY in repo-root .env
spatial-api            # http://0.0.0.0:8001

# terminal 2 — UI
cd frontend
npm install
npm run dev             # http://localhost:5173
```

## Run MCP + agent

```bash
cd mcp_server && source .venv/bin/activate
# optional Atera table:
aws s3 cp s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/mcp_data/cells.parquet data/
spatial-mcp             # :8000/mcp
spatial-agent "…"       # needs AWS_BEARER_TOKEN_BEDROCK
```

```bash
cd mcp_server && pytest tests/ -q
python -m spatial_mcp.agent.calibrate_benchmark
```

Details: [`mcp_server/README.md`](mcp_server/README.md), [`frontend/README.md`](frontend/README.md), [`DATA_CONTRACT.md`](DATA_CONTRACT.md).
