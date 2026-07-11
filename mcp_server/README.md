# MCP server — K Pro tools

Python MCP server (Streamable HTTP) that exposes seven tools to Owkin K Pro.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
spatial-mcp                 # http://0.0.0.0:8000/mcp
```

Env: `SPATIAL_MCP_HOST`, `SPATIAL_MCP_PORT`, `SPATIAL_MCP_DB`

Tunnel if needed: `ngrok http 8000` → give K Pro `https://…/mcp`

## Layout

```
src/spatial_mcp/
  server.py          # HTTP transport (official MCP SDK)
  registry.py        # Generic dispatcher — no biology logic
  schemas.py         # Precise tool descriptions + input JSON schemas
  logging_util.py    # Structured JSON logs of every call
  memory.py          # SQLite findings store
  fixtures/          # Shared stub cells (aligned with frontend)
  stubs/             # ← TEAMMATES: replace your one file here
  memory_tools/      # Real record_finding + query_prior_findings
scripts/
  test_tool.py       # Test one tool without starting the server
  mock_client.py     # Full MCP client trace (server must be running)
data/                # findings.db created at runtime
```

## Tools

| Tool | Folder | Status |
|------|--------|--------|
| `list_candidate_cells` | `stubs/` | stub — teammate |
| `map_spatial_to_single` | `stubs/` | stub — teammate |
| `search_literature` | `stubs/` | stub — teammate |
| `suggest_perturbations` | `stubs/` | stub — teammate |
| `simulate_perturbations` | `stubs/` | stub — teammate |
| `record_finding` | `memory_tools/` | real |
| `query_prior_findings` | `memory_tools/` | real |

## Teammate swap (one file)

Keep this signature:

```python
def your_tool_name(args: dict) -> dict:
    ...
```

| Tool | File |
|------|------|
| `list_candidate_cells` | `src/spatial_mcp/stubs/list_candidate_cells.py` |
| `map_spatial_to_single` | `src/spatial_mcp/stubs/map_spatial_to_single.py` |
| `search_literature` | `src/spatial_mcp/stubs/search_literature.py` |
| `suggest_perturbations` | `src/spatial_mcp/stubs/suggest_perturbations.py` |
| `simulate_perturbations` | `src/spatial_mcp/stubs/simulate_perturbations.py` |

Do **not** edit `registry.py` or `server.py` when swapping logic. Schemas live in `schemas.py`.

### Test your tool alone

```bash
python scripts/test_tool.py your_tool_name --args '{"...": "..."}'
```

### After swap — smoke the full server

```bash
spatial-mcp                     # terminal 1
python scripts/mock_client.py   # terminal 2
```

## Agent pattern K Pro should follow

1. `query_prior_findings` — already investigated?
2. `list_candidate_cells` / `map_spatial_to_single`
3. `search_literature`
4. `suggest_perturbations`
5. `simulate_perturbations`
6. `record_finding`
