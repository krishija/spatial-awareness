#!/usr/bin/env bash
# Phase 3–4 on SageMaker: MCP server + spatial-agent trace in a fresh user-owned dir.
# Does NOT fight root-owned lifecycle leftovers. Does NOT activate scLDM into the shell
# (that previously shadowed python3 and dropped the mcp package).
set -eo pipefail
export HOME=/home/ec2-user
export USER=ec2-user
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-west-2}"
BUCKET=owkin-hackathon26-spatialawareness-raw-data
WORK=/home/ec2-user/SageMaker/e2e_work
REPO="$WORK/spatial-awareness"
DATA="$WORK/data"
OUT="$WORK/artifacts"
LOG="$WORK/phase34.log"
mkdir -p "$WORK" "$DATA" "$OUT" "$WORK/downloads" "$OUT/e2e_tool_sequence"
# Fresh log for this run
: >"$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "=== PHASE34 START $(date -Is) ==="
nvidia-smi -L || true

aws s3 cp "s3://$BUCKET/artifacts/mcp_data/spatial.env" "$WORK/spatial.env"
set -a; source "$WORK/spatial.env"; set +a
aws s3 cp "s3://$BUCKET/artifacts/mcp_data/spatial-awareness-code.tgz" "$WORK/downloads/code.tgz"
rm -rf "$REPO"; mkdir -p "$REPO"
tar xzf "$WORK/downloads/code.tgz" -C "$REPO"
aws s3 cp "s3://$BUCKET/artifacts/mcp_data/cells.parquet" "$DATA/cells.parquet"

export SPATIAL_CELLS_PARQUET="$DATA/cells.parquet"
export SPATIAL_MCP_DB="$WORK/findings.db"
export SPATIAL_PREREG_PATH="$DATA/preregistrations.jsonl"
export REPO_ROOT="$REPO"
export E2E_OUT="$OUT/e2e_tool_sequence"
export PATH="/home/ec2-user/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
export PATH="/home/ec2-user/.local/bin:$PATH"

# Dedicated MCP venv — never use a partially-activated scLDM env for the server
MCP_VENV="$WORK/venv_mcp"
if [[ ! -x "$MCP_VENV/bin/python" ]]; then
  uv venv "$MCP_VENV" --python 3.11
fi
uv pip install --python "$MCP_VENV/bin/python" -e "$REPO/mcp_server"
RUN_PY="$MCP_VENV/bin/python"
export PYTHONPATH="$REPO/mcp_server/src"

"$RUN_PY" - <<'PY'
from spatial_mcp.registry import build_default_registry
r = build_default_registry()
print("TOOLS", len(r.list_specs()), sorted(t.name for t in r.list_specs()))
assert len(r.list_specs()) == 12
import mcp
print("mcp_ok", mcp.__version__ if hasattr(mcp, "__version__") else "present")
PY

# Timeboxed scLDM (reuse existing clone if present). Keep SCLDM_ROOT for in-process import,
# but install spatial-mcp *into* the scLDM venv and prefer that interpreter when ready.
SCLDM_ROOT="$WORK/scldm_cd4"
export SCLDM_ROOT SCLDM_DEVICE=cuda
SCLDM_PY="$SCLDM_ROOT/venv/scldm_cd4/bin/python"
if [[ ! -x "$SCLDM_PY" ]]; then
  echo "Starting scLDM install (timeboxed 20m)..."
  if [[ ! -d "$SCLDM_ROOT/.git" ]]; then
    git clone --depth 1 https://github.com/czbiohub-chi/scldm_cd4.git "$SCLDM_ROOT" || true
  fi
  if [[ -d "$SCLDM_ROOT" ]]; then
    (
      cd "$SCLDM_ROOT"
      chmod +x ./init.sh || true
      timeout 1200 ./init.sh || echo "scLDM init timed out or failed — continuing without live sim"
    ) || true
  fi
fi

if [[ -x "$SCLDM_PY" ]]; then
  echo "Installing spatial-mcp into scLDM venv for live KO + MCP in one process"
  # uv can install without pip module present
  uv pip install --python "$SCLDM_PY" -e "$REPO/mcp_server" || {
    "$SCLDM_PY" -m ensurepip --upgrade || true
    "$SCLDM_PY" -m pip install -q -e "$REPO/mcp_server" || true
  }
  if "$SCLDM_PY" -c "import mcp, spatial_mcp, torch; print('scldm_runtime_ok', torch.cuda.is_available())"; then
    RUN_PY="$SCLDM_PY"
    echo "Using scLDM python for MCP+agent: $RUN_PY"
  else
    echo "scLDM python missing mcp/spatial_mcp — falling back to MCP venv (sim will fail loud)"
    unset SCLDM_ROOT
  fi
else
  echo "SCLDM not ready — simulate_perturbations will fail loud (ok:false)"
  unset SCLDM_ROOT
fi

# Start MCP server with the chosen interpreter (absolute path — no activate)
pkill -f "spatial_mcp.server" || true
sleep 1
nohup env \
  HOME="$HOME" \
  SPATIAL_CELLS_PARQUET="$SPATIAL_CELLS_PARQUET" \
  SPATIAL_MCP_DB="$SPATIAL_MCP_DB" \
  SPATIAL_PREREG_PATH="$SPATIAL_PREREG_PATH" \
  SCLDM_ROOT="${SCLDM_ROOT:-}" \
  SCLDM_DEVICE=cuda \
  YOU_API_KEY="${YOU_API_KEY:-}" \
  AWS_BEARER_TOKEN_BEDROCK="${AWS_BEARER_TOKEN_BEDROCK:-}" \
  AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION" \
  PYTHONPATH="$REPO/mcp_server/src" \
  "$RUN_PY" -m spatial_mcp.server >"$WORK/mcp_server.log" 2>&1 &
echo "MCP_PID $! RUN_PY=$RUN_PY"
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/mcp || true)
  echo "mcp_http_try_$i $code"
  if [[ "$code" != "000" ]]; then break; fi
done
head -60 "$WORK/mcp_server.log" || true

# Run agent against local MCP
QUESTION='For atera-cervical-01 tumor-core CD4_Tex_term cell coafefcd-1, evaluate whether LCP2 knockout is a justified next perturbation. Use real tools; do not invent evidence.'
cd "$REPO/mcp_server"
EC=0
"$RUN_PY" -m spatial_mcp.agent.cli \
  --mcp-url http://127.0.0.1:8000/mcp \
  --sample atera-cervical-01 \
  --max-iterations 8 \
  --wall-clock 240 \
  --json "$OUT/agent_trace.json" \
  --md "$OUT/agent_trace.md" \
  "$QUESTION" || EC=$?
echo "AGENT_EXIT=$EC"

# Deterministic tool-sequence smoke (uses REPO_ROOT / SPATIAL_PREREG_PATH / E2E_OUT)
"$RUN_PY" "$REPO/mcp_server/scripts/run_e2e_tool_sequence.py" || true

aws s3 sync "$OUT" "s3://$BUCKET/artifacts/mcp_data/e2e_out/phase34/" || true
aws s3 cp "$LOG" "s3://$BUCKET/artifacts/mcp_data/e2e_out/phase34/phase34.log" || true
echo "=== PHASE34 DONE $(date -Is) exit=$EC ==="
exit $EC
