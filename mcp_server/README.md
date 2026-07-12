# MCP server

Python MCP server (Streamable HTTP) for the hackathon tools, plus a Bedrock agent that calls them, plus a thin REST proxy for the browser demo.

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
spatial-mcp                 # http://0.0.0.0:8000/mcp   — K Pro / MCP clients / agent
spatial-api                 # http://0.0.0.0:8001       — browser REST proxy
```

Env: `SPATIAL_MCP_HOST`, `SPATIAL_MCP_PORT`, `SPATIAL_MCP_DB`, `YOU_API_KEY` (repo-root `.env`), `SPATIAL_API_ORIGINS` (default `http://localhost:5173`)

Tunnel if needed: `ngrok http 8000` → give K Pro `https://…/mcp`

## Tools

| Tool | Notes |
|------|-------|
| `list_candidate_cells` | Fixture cells |
| `map_spatial_to_single` | Fixture atlas labels |
| `search_literature` | You.com (via shared `you_client`) if `YOU_API_KEY`, else curated fallback corpus |
| `suggest_perturbations` | You.com-grounded ranked knockouts (gene mentions in retrieved literature), falls back to niche-based static suggestions |
| `simulate_perturbations` | scLDM if configured, else surrogate (`backend` field) |
| `differential_survival_analysis` | TCGA Cox association (local → cBioPortal → fixture). Not cell-level validation. Uncorrected p; session FDR is the agent's job |
| `record_finding` / `query_prior_findings` | SQLite |
| `evaluate_evidence` / `decide_next_action` | Programmatic confidence + gating |

### Browser REST proxy (`spatial-api`)

The frontend cannot speak MCP Streamable HTTP (and must not hold `YOU_API_KEY`). `http_api.py` exposes the same `ToolRegistry` over plain JSON:

| Method | Path | Tool |
|--------|------|------|
| `POST` | `/api/search_literature` | `search_literature` |
| `POST` | `/api/suggest_perturbations` | `suggest_perturbations` |
| `POST` | `/api/chat` | `search_literature` (+ optional `suggest_perturbations`) |
| `GET` | `/api/health` | — |

## Agent

```bash
# needs AWS_BEARER_TOKEN_BEDROCK in repo-root .env
spatial-mcp &
spatial-agent "…"
# or: python scripts/run_agent.py --json out.json --md out.md "…"
python scripts/run_agent.py --dry-run-conflict   # no Bedrock
```

Optional: `BEDROCK_MODEL_ID`, `AWS_REGION` / `BEDROCK_REGION`.

## Tests

```bash
pytest tests/ -q
# network: pytest tests/test_differential_survival.py -m integration
```

## Layout

```
src/spatial_mcp/
  server.py          # MCP Streamable HTTP transport (official MCP SDK)
  http_api.py        # Thin REST proxy for the Vite frontend demo
  you_client.py       # Shared You.com Search API client
  registry.py        # Generic dispatcher — no biology logic
  schemas.py          # Precise tool descriptions + input JSON schemas
  memory.py           # SQLite findings store
  stubs/              # ← TEAMMATES: replace your one file here
  memory_tools/        # findings + evidence MCP wrappers
  fixtures/            # cells + TCGA fixture cohorts (aligned with frontend)
  agent/               # Bedrock driver, evidence, gating, reports
scripts/
  test_tool.py         # Test one tool without starting the server
  mock_client.py       # Full MCP client trace (server must be running)
  run_agent.py
tests/
data/                  # findings.db created at runtime
```

Swap a domain tool by editing one file in `stubs/`. Leave `registry.py` / `server.py` / `http_api.py` / `agent/` alone unless you're changing the scaffold.
