#!/usr/bin/env bash
set -eo pipefail
export HOME=/home/ec2-user
export USER=ec2-user
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-west-2}"
BUCKET=owkin-hackathon26-spatialawareness-raw-data
SM_HOME=/home/ec2-user/SageMaker
WORK="$SM_HOME/e2e_work"
REPO="$WORK/spatial-awareness"
DATA="$WORK/data"
SCLDM_ROOT="$WORK/scldm_cd4"
OUT="$WORK/e2e_out"
DL="$WORK/downloads"
LOG="$WORK/e2e_v4.log"
mkdir -p "$WORK" "$DATA" "$OUT" "$DL"
exec > >(tee -a "$LOG") 2>&1
echo "=== START $(date -Is) uid=$(id -u) ==="
nvidia-smi -L || true
cd "$WORK"
aws s3 cp "s3://$BUCKET/artifacts/mcp_data/spatial.env" "$WORK/spatial.env" || true
if [[ -f "$WORK/spatial.env" ]]; then set -a; source "$WORK/spatial.env"; set +a; fi
aws s3 cp "s3://$BUCKET/artifacts/mcp_data/spatial-awareness-code.tgz" "$DL/code.tgz"
rm -rf "$REPO"; mkdir -p "$REPO"
tar xzf "$DL/code.tgz" -C "$REPO"
aws s3 cp "s3://$BUCKET/artifacts/mcp_data/cells.parquet" "$DATA/cells.parquet"
ls -la "$DATA/cells.parquet"
export PATH="/home/ec2-user/.local/bin:/usr/local/cuda/bin:/usr/bin:/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
export PATH="/home/ec2-user/.local/bin:$PATH"
if [[ ! -d "$SCLDM_ROOT/.git" ]]; then
  git clone https://github.com/czbiohub-chi/scldm_cd4.git "$SCLDM_ROOT"
fi
cd "$SCLDM_ROOT"; chmod +x ./init.sh || true
if [[ ! -x "$SCLDM_ROOT/venv/scldm_cd4/bin/python" ]]; then
  ./init.sh
fi
source "$SCLDM_ROOT/venv/scldm_cd4/bin/activate"
python -m pip install -q --upgrade pip
python -m pip install -q gseapy pandas pyarrow anndata scipy requests boto3 fastapi 'uvicorn[standard]' 'mcp[cli]' jsonschema huggingface_hub || true
python -m pip install -q -e "$REPO/mcp_server"
[[ -f "$SCLDM_ROOT/hgnc_genes.txt" ]] || wget -q -O "$SCLDM_ROOT/hgnc_genes.txt" "https://www.genenames.org/cgi-bin/download/custom?col=gd_app_sym&col=md_ensembl_id&status=Approved&hgnc_dbtag=on&order_by=gd_pub_ensembl_id&format=text&submit=submit" || true
python - <<'PY'
from huggingface_hub import snapshot_download
import os
print(snapshot_download("biohub/scldm_cd4", local_dir=os.path.expanduser("~/.cache/huggingface/hub/models--biohub--scldm_cd4")))
PY
export SCLDM_ROOT SCLDM_DEVICE=cuda
export SPATIAL_CELLS_PARQUET="$DATA/cells.parquet"
export REPO_ROOT="$REPO" E2E_OUT="$OUT"
export PYTHONPATH="$REPO/mcp_server/src${PYTHONPATH:+:$PYTHONPATH}"
python - <<'PY'
import torch
print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
PY
aws s3 cp "s3://$BUCKET/artifacts/mcp_data/run_e2e_tool_sequence.py" "$WORK/run_e2e_tool_sequence.py"
python "$WORK/run_e2e_tool_sequence.py"; EC=$?
echo "E2E_EXIT=$EC"
aws s3 sync "$OUT" "s3://$BUCKET/artifacts/mcp_data/e2e_out/" || true
aws s3 cp "$LOG" "s3://$BUCKET/artifacts/mcp_data/e2e_out/bootstrap.log" || true
echo "=== DONE $(date -Is) exit=$EC ==="
exit $EC
