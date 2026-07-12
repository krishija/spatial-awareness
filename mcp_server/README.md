# MCP server

Python MCP server (Streamable HTTP) for the hackathon tools, a Bedrock agent that
calls them, and a thin REST proxy so the browser never holds `YOU_API_KEY`.

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
spatial-mcp                 # http://0.0.0.0:8000/mcp   — MCP clients / agent
spatial-api                 # http://0.0.0.0:8001       — browser REST proxy
```

Env (repo-root `.env` is fine): `YOU_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK` (or IAM),
`SPATIAL_CELLS_PARQUET` / `mcp_server/data/cells.parquet`, optional `SCLDM_ROOT`,
`SPATIAL_MCP_HOST` / `SPATIAL_MCP_PORT`, `SPATIAL_API_ORIGINS`
(default `http://localhost:5173`).

Tunnel if needed: `ngrok http 8000` → point an MCP client at `https://…/mcp`.

## Tools (12)

| Tool | Notes |
|------|-------|
| `list_candidate_cells` | Real Atera parquet when configured; otherwise fails loud |
| `map_spatial_to_single` | Not implemented — `ok: false` (no fake OT mappings) |
| `search_literature` | You.com (+ PubMed/PMC helpers); stance-labeled evidence cards |
| `suggest_perturbations` | Literature-ranked knockout candidates for a phenotype/niche |
| `simulate_perturbations` | Live scLDM if weights exist; else labeled `scldm_surrogate`. OOV gene → `ok: false` |
| `differential_survival_analysis` | TCGA Cox (local → cBioPortal → fixture). Bulk association only |
| `find_measured_perturbation_evidence` | Context-matched hits from training / measured corpora |
| `recommend_next_experiment` | Graph / confound-aware next-step suggestions |
| `record_finding` / `query_prior_findings` | SQLite session memory |
| `evaluate_evidence` / `decide_next_action` | Log-odds aggregation + REPORT / GATHER_MORE / DISCARD gate |

### Browser REST proxy (`spatial-api`)

Same registry, plain JSON:

| Method | Path | Tool |
|--------|------|------|
| `POST` | `/api/search_literature` | `search_literature` |
| `POST` | `/api/suggest_perturbations` | `suggest_perturbations` |
| `POST` | `/api/chat` | literature (+ optional suggestions) |
| `GET` | `/api/health` | — |

## Agent

```bash
spatial-mcp &
spatial-agent "…"
# or: python scripts/run_agent.py --json out.json --md out.md "…"
python scripts/run_agent.py --dry-run-conflict   # no Bedrock
```

What the driver enforces on top of the LLM:

- Gene args bind to the committed hypothesis after COMMIT
- REPORT needs ≥2 grounded modalities (e.g. measured + literature), not measured alone
- After the evidence bar is met, `simulate_perturbations` runs once as a non-load-bearing check (real delta or honest failure)
- Independence clustering + conflict detection; simulation is weak (~0.16 bits) next to matched measured (~2 bits)

Optional: `--commit-gene PDCD1`, `BEDROCK_MODEL_ID`, `AWS_REGION` / `BEDROCK_REGION`.

Example traces: `artifacts/agent_traces/phase34/`.

SageMaker script: `scripts/run_phase34_sagemaker.sh`.

## Tests

```bash
pytest tests/ -q
# network: pytest tests/test_differential_survival.py -m integration
python -m spatial_mcp.agent.calibrate_benchmark
```

## Layout

```
src/spatial_mcp/
  server.py           # MCP Streamable HTTP
  http_api.py         # REST proxy for the Vite UI
  you_client.py       # You.com Search API
  registry.py         # Dispatcher — no biology logic
  schemas.py          # Tool descriptions + JSON schemas
  memory.py           # SQLite findings
  stubs/              # One file per domain tool
  memory_tools/       # findings + evidence wrappers
  fixtures/           # Small aligned fixtures
  agent/              # Bedrock driver, evidence, gating, traces
scripts/
  test_tool.py
  mock_client.py
  run_agent.py
  run_phase34_sagemaker.sh
tests/
data/                 # cells.parquet / findings.db (local, often gitignored)
```

Swap a domain tool by editing one file in `stubs/`. Leave `registry.py` /
`server.py` / `http_api.py` alone unless you're changing the scaffold.
