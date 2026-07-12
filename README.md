# Spatial Awareness

Owkin *Rewiring Biology* hackathon project. We look at exhausted CD4 T cells in spatial tumor data, propose gene knockouts, simulate them, and check whether related signatures associate with survival in TCGA bulk cohorts.

```
frontend/     Vite + React explorer (fixture tissue maps) + live literature chat
mcp_server/   MCP tools + Bedrock research agent + REST proxy for the browser demo
```

The UI and MCP server don't talk to each other directly for tissue/cell data yet — that part still runs on shared fixture vocabulary (sample / niche / marker names line up). Literature search and knockout suggestions, however, are live: the frontend calls the same `search_literature` / `suggest_perturbations` MCP tools the agent uses, via a thin REST proxy (`spatial-api`) so the browser never holds `YOU_API_KEY`.

## What's actually built

| Piece | Reality |
|-------|---------|
| Tissue explorer | Works on seeded fixture samples (`crc-01`, `nsclc-03`, `mel-07`) |
| Literature search + KO suggestions | Live in the browser via `spatial-api` — You.com-grounded, with a curated offline fallback |
| MCP tools | List cells, map to atlas labels, literature search, suggest/simulate KOs, TCGA survival association, SQLite memory, evidence scoring |
| Research agent | Bedrock Converse loop over the MCP server (`spatial-agent`) |
| Field-aware OT / quantum mapping | Described in earlier notes — **not implemented in this repo** |
| Live scLDM | Needs `SCLDM_ROOT` + weights; otherwise a surrogate |
| TCGA survival | Live via cBioPortal (or local `TCGA_DATA_ROOT`); fixture offline. Bulk association only — not cell-level proof |

## Run the demo

```bash
# terminal 1 — REST proxy (fronts search_literature / suggest_perturbations for the UI)
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# YOU_API_KEY in repo-root .env (see .env.example)
spatial-api            # http://0.0.0.0:8001

# terminal 2 — UI
cd frontend
npm install
npm run dev             # http://localhost:5173
```

In the UI: select a cell for You.com-grounded knockout suggestions, or open **Ask literature** for free-text `search_literature` chat.

Details: [`frontend/README.md`](frontend/README.md)

## Run the MCP server + agent

```bash
cd mcp_server
source .venv/bin/activate
spatial-mcp             # http://0.0.0.0:8000/mcp  (agent / K Pro)
spatial-api             # http://0.0.0.0:8001      (browser REST proxy)
```

Needs `AWS_BEARER_TOKEN_BEDROCK` in a repo-root `.env` for the agent.

```bash
spatial-agent "Which gene knockout would best re-activate exhausted CD4 T cells in the CRC-01 tumor core?"
```

```bash
cd mcp_server && pytest tests/ -q
```

More detail: [`mcp_server/README.md`](mcp_server/README.md), [`frontend/README.md`](frontend/README.md).

## Who edits what

| Area | Path |
|------|------|
| UI | `frontend/` |
| MCP registry / agent / memory / REST proxy | `mcp_server/src/spatial_mcp/` (avoid rewriting teammates' stub files unless that's your tool) |
| One domain tool | a single file under `mcp_server/src/spatial_mcp/stubs/` |

## Links

- scLDM-CD4: https://virtualcellmodels.cziscience.com/model/scldm-cd4
- Allen CD4 atlas: https://apps.allenimmunology.org/aifi/resources/imm-health-atlas/cell-type-descriptions/cd4-t-cells-dn-t-cells-and-tregs/
- Xenium example data: https://www.10xgenomics.com/support/software/xenium-onboard-analysis/latest/resources/xenium-example-data
