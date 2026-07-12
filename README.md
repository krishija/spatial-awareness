# Spatial Awareness

Owkin *Rewiring Biology* hackathon project. We look at exhausted CD4 T cells in spatial tumor data, propose gene knockouts, simulate them, and check whether related signatures associate with survival in TCGA bulk cohorts.

```
frontend/     Vite + React explorer (fixture tissue maps)
mcp_server/   MCP tools + Bedrock research agent
```

The UI and MCP server don’t talk to each other yet. They share the same sample / niche / marker vocabulary so the demos line up.

## What’s actually built

| Piece | Reality |
|-------|---------|
| Tissue explorer | Works on seeded fixture samples (`crc-01`, `nsclc-03`, `mel-07`) |
| MCP tools | List cells, map to atlas labels, literature search, suggest/simulate KOs, TCGA survival association, SQLite memory, evidence scoring |
| Research agent | Bedrock Converse loop over the MCP server (`spatial-agent`) |
| Field-aware OT / quantum mapping | Described in earlier notes — **not implemented in this repo** |
| Live scLDM | Needs `SCLDM_ROOT` + weights; otherwise a surrogate |
| TCGA survival | Live via cBioPortal (or local `TCGA_DATA_ROOT`); fixture offline. Bulk association only — not cell-level proof |

## Run the UI

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

## Run the MCP server

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
spatial-mcp    # http://0.0.0.0:8000/mcp
```

## Run the agent

Needs `AWS_BEARER_TOKEN_BEDROCK` in a repo-root `.env`, plus a running MCP server.

```bash
# terminal 1
spatial-mcp

# terminal 2
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
| MCP registry / agent / memory | `mcp_server/src/spatial_mcp/` (avoid rewriting teammates’ stub files unless that’s your tool) |
| One domain tool | a single file under `mcp_server/src/spatial_mcp/stubs/` |

## Links

- scLDM-CD4: https://virtualcellmodels.cziscience.com/model/scldm-cd4
- Allen CD4 atlas: https://apps.allenimmunology.org/aifi/resources/imm-health-atlas/cell-type-descriptions/cd4-t-cells-dn-t-cells-and-tregs/
- Xenium example data: https://www.10xgenomics.com/support/software/xenium-onboard-analysis/latest/resources/xenium-example-data
