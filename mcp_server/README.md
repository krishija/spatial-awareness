# MCP server

Python MCP server (Streamable HTTP) for the hackathon tools, plus a Bedrock agent that calls them.

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
spatial-mcp                 # :8000/mcp
```

Env: `SPATIAL_MCP_HOST`, `SPATIAL_MCP_PORT`, `SPATIAL_MCP_DB`.

## Tools

| Tool | Notes |
|------|-------|
| `list_candidate_cells` | Fixture cells |
| `map_spatial_to_single` | Fixture atlas labels |
| `search_literature` | You.com if `YOU_API_KEY`, else curated fallback |
| `suggest_perturbations` | Niche-based KO suggestions |
| `simulate_perturbations` | scLDM if configured, else surrogate (`backend` field) |
| `differential_survival_analysis` | TCGA Cox association (local → cBioPortal → fixture). Not cell-level validation. Uncorrected p; session FDR is the agent’s job |
| `record_finding` / `query_prior_findings` | SQLite |
| `evaluate_evidence` / `decide_next_action` | Programmatic confidence + gating |

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
  server.py  registry.py  schemas.py  memory.py
  stubs/           domain tools
  memory_tools/    findings + evidence MCP wrappers
  fixtures/        cells + TCGA fixture cohorts
  agent/           Bedrock driver, evidence, gating, reports
scripts/  tests/
```

Swap a domain tool by editing one file in `stubs/`. Leave `registry.py` / `server.py` / `agent/` alone unless you’re changing the scaffold.
