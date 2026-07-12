"""scLDM-CD4 knockout evaluation — port of evaluate_knockout_effect.ipynb.

Live path (when SCLDM_ROOT + checkpoint + deps are available):
  sample base cells → build KO/control queries → inference() → pseudobulk Δ

Surrogate path (default on laptops without the model):
  same control-vs-KO math and return shape, using a notebook-faithful
  marker-level effect library so the MCP contract stays demoable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Minimal HGNC symbol → Ensembl map for genes we care about in this hackathon.
# Full HGNC table is loaded from disk when SCLDM is installed (see notebook §3).
SYMBOL_TO_ENSEMBL: dict[str, str] = {
    "PDCD1": "ENSG00000188389",
    "TCF7": "ENSG00000081059",
    "TOX": "ENSG00000198846",
    "LAG3": "ENSG00000089692",
    "GZMB": "ENSG00000100453",
    "IL7R": "ENSG00000168685",
    "CTLA4": "ENSG00000163599",
    "FOXP3": "ENSG00000049768",
    "HAVCR2": "ENSG00000135077",  # TIM-3
    "ENTPD1": "ENSG00000138185",  # CD39
    "TIGIT": "ENSG00000181847",
    "TNFRSF9": "ENSG00000049249",  # 4-1BB
    "CXCL13": "ENSG00000156234",
    "LCP2": "ENSG00000043462",  # notebook example gene
    "BATF": "ENSG00000156127",
    "PRDM1": "ENSG00000057657",
    "NR4A1": "ENSG00000123358",
}

ENSEMBL_TO_SYMBOL = {v: k for k, v in SYMBOL_TO_ENSEMBL.items()}

# Genes the surrogate (and typical scLDM CD4 guide set) will accept.
KNOWN_GUIDE_SYMBOLS = set(SYMBOL_TO_ENSEMBL.keys())

MARKER_GENES = [
    "PDCD1",
    "TCF7",
    "TOX",
    "LAG3",
    "GZMB",
    "IL7R",
    "CTLA4",
    "FOXP3",
]


@dataclass
class KnockoutResult:
    gene: str
    ensembl_id: str
    backend: str  # "scldm_live" | "scldm_surrogate"
    mean_control: dict[str, float]
    mean_knockout: dict[str, float]
    deltas: dict[str, float]
    top_effects: list[dict[str, Any]]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gene": self.gene,
            "ensembl_id": self.ensembl_id,
            "backend": self.backend,
            "mean_control": self.mean_control,
            "mean_knockout": self.mean_knockout,
            "deltas": self.deltas,
            "top_effects": self.top_effects,
            "details": self.details,
        }


def _round2(v: float) -> float:
    return round(float(v), 2)


def _clamp_expr(v: float) -> float:
    return _round2(max(0.05, min(5.0, v)))


def resolve_ensembl(gene_symbol: str) -> str | None:
    symbol = gene_symbol.upper()
    if symbol in SYMBOL_TO_ENSEMBL:
        return SYMBOL_TO_ENSEMBL[symbol]
    # Optional full HGNC table from the notebook install script
    hgnc_path = os.environ.get("SCLDM_HGNC")
    if not hgnc_path:
        root = os.environ.get("SCLDM_ROOT")
        if root:
            candidate = Path(root) / "hgnc_genes.txt"
            if candidate.is_file():
                hgnc_path = str(candidate)
    if hgnc_path and Path(hgnc_path).is_file():
        try:
            import pandas as pd

            hgnc = pd.read_csv(hgnc_path, sep="\t")
            hgnc = hgnc.rename(
                columns={
                    "Approved symbol": "hgnc_symbol",
                    "Ensembl ID(supplied by Ensembl)": "ensembl_id",
                }
            )
            row = hgnc[hgnc["hgnc_symbol"].astype(str).str.upper() == symbol]
            if len(row):
                eid = str(row.iloc[0]["ensembl_id"])
                if eid and eid != "nan":
                    return eid
        except Exception:
            return None
    return None


def scldm_available() -> bool:
    root = os.environ.get("SCLDM_ROOT")
    if not root or not Path(root).is_dir():
        return False
    try:
        import anndata  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


# ── Surrogate: notebook-faithful control vs KO pseudobulk on the marker panel ─

# Predicted mean expression under non-targeting control for a generic stimulated CD4.
_CONTROL_BASE: dict[str, float] = {
    "PDCD1": 2.4,
    "TCF7": 1.8,
    "TOX": 2.0,
    "LAG3": 1.9,
    "GZMB": 1.6,
    "IL7R": 2.2,
    "CTLA4": 1.5,
    "FOXP3": 0.8,
}

# Pseudobulk Δ (KO − control) in our marker score units — mirrors notebook §7a.
# Signs follow the biology the notebook is built to evaluate (exhaustion / effector).
_SURROGATE_DELTAS: dict[str, dict[str, float]] = {
    "PDCD1": {
        "PDCD1": -1.8,
        "TOX": -0.7,
        "LAG3": -0.5,
        "TCF7": 1.1,
        "IL7R": 1.0,
        "GZMB": 0.9,
        "CTLA4": -0.2,
        "FOXP3": 0.0,
    },
    "TOX": {
        "TOX": -1.9,
        "PDCD1": -0.7,
        "TCF7": 1.3,
        "IL7R": 0.9,
        "GZMB": 0.6,
        "LAG3": -0.3,
        "CTLA4": -0.1,
        "FOXP3": 0.0,
    },
    "LAG3": {
        "LAG3": -1.7,
        "PDCD1": -0.4,
        "GZMB": 0.8,
        "IL7R": 0.5,
        "TCF7": 0.3,
        "TOX": -0.2,
        "CTLA4": 0.0,
        "FOXP3": 0.0,
    },
    "CTLA4": {
        "CTLA4": -1.8,
        "FOXP3": -0.7,
        "GZMB": 0.6,
        "TCF7": 0.4,
        "IL7R": 0.3,
        "PDCD1": -0.2,
        "TOX": 0.0,
        "LAG3": -0.1,
    },
    "HAVCR2": {
        "PDCD1": -0.3,
        "GZMB": 0.5,
        "TCF7": 0.3,
        "TOX": -0.2,
        "LAG3": -0.2,
        "IL7R": 0.2,
        "CTLA4": 0.0,
        "FOXP3": 0.0,
    },
    "LCP2": {  # notebook example — TCR signaling adaptor; mild effector drop
        "GZMB": -0.6,
        "IL7R": -0.4,
        "TCF7": -0.3,
        "PDCD1": 0.2,
        "TOX": 0.3,
        "LAG3": 0.2,
        "CTLA4": 0.1,
        "FOXP3": 0.0,
    },
}


def _default_delta(gene: str) -> dict[str, float]:
    """Generic KO: knock the gene itself down if it's a marker, mild effector up."""
    d = {g: 0.0 for g in MARKER_GENES}
    if gene in d:
        d[gene] = -1.5
    d["GZMB"] = d.get("GZMB", 0.0) + 0.3
    d["TCF7"] = d.get("TCF7", 0.0) + 0.2
    return d


def run_surrogate_knockout(gene: str) -> KnockoutResult:
    """Notebook §7a shape without requiring GPU / scLDM weights."""
    gene = gene.upper()
    ensembl = resolve_ensembl(gene) or f"UNKNOWN:{gene}"
    deltas_raw = _SURROGATE_DELTAS.get(gene) or _default_delta(gene)
    mean_control = {g: _round2(_CONTROL_BASE[g]) for g in MARKER_GENES}
    mean_knockout = {}
    deltas = {}
    for g in MARKER_GENES:
        d = float(deltas_raw.get(g, 0.0))
        deltas[g] = _round2(d)
        mean_knockout[g] = _clamp_expr(mean_control[g] + d)

    top = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top_effects = [
        {"gene": g, "delta": d, "direction": "up" if d > 0 else "down" if d < 0 else "flat"}
        for g, d in top
        if d != 0
    ][:10]

    return KnockoutResult(
        gene=gene,
        ensembl_id=ensembl,
        backend="scldm_surrogate",
        mean_control=mean_control,
        mean_knockout=mean_knockout,
        deltas=deltas,
        top_effects=top_effects,
        details={
            "method": "pseudobulk_delta_surrogate",
            "note": (
                "scLDM weights not available locally — using a notebook-faithful "
                "control-vs-KO pseudobulk surrogate on the marker panel. Set "
                "SCLDM_ROOT (+ checkpoint) to enable live inference."
            ),
            "timepoint": os.environ.get("SCLDM_TIMEPOINT", "Stim48hr"),
            "n_cells": int(os.environ.get("SCLDM_N_CELLS", "500")),
        },
    )


# ── Live scLDM path (notebook §§4–7) ─────────────────────────────────────────


def run_live_knockout(gene: str) -> KnockoutResult:
    """Execute the notebook pipeline against an installed scLDM-CD4 checkout."""
    import sys

    import anndata as ad
    import numpy as np
    import pandas as pd
    import scipy.sparse as sparse

    gene = gene.upper()
    ensembl = resolve_ensembl(gene)
    if not ensembl:
        raise KeyError(f"{gene} has no Ensembl ID")

    repo_root = Path(os.environ["SCLDM_ROOT"])
    sys.path.insert(0, str(repo_root / "src"))
    from notebook_inference import inference  # type: ignore

    checkpoint = os.environ.get(
        "SCLDM_CHECKPOINT",
        str(
            Path.home()
            / ".cache/huggingface/hub/models--biohub--scldm_cd4"
        ),
    )
    # Allow either a file or a snapshot dir containing model.safetensors
    ckpt_path = Path(checkpoint)
    if ckpt_path.is_dir():
        matches = list(ckpt_path.rglob("model.safetensors"))
        if not matches:
            raise FileNotFoundError(f"No model.safetensors under {ckpt_path}")
        ckpt_path = matches[0]

    output_dir = Path(
        os.environ.get("SCLDM_OUTPUT_DIR", str(repo_root / "inference_outputs" / "knockout_eval"))
    )
    query_dir = output_dir / "queries"
    query_dir.mkdir(parents=True, exist_ok=True)

    train_path = Path(
        os.environ.get(
            "SCLDM_TRAIN_ADATA",
            str(repo_root / "quickstart_data" / "train_hvg" / "adata_1.h5ad"),
        )
    )
    train_adata = ad.read_h5ad(train_path)

    guide_categories = sorted(
        train_adata.obs["guide_target_ensembl"].astype(str).unique()
    )
    if ensembl not in guide_categories:
        raise ValueError(
            f"{ensembl} ({gene}) is not one of the checkpoint's known perturbations "
            f"({len(guide_categories)} guides)."
        )

    donor_categories = sorted(train_adata.obs["donor_id"].astype(str).unique())
    donor_id = os.environ.get("SCLDM_DONOR_ID", donor_categories[0])
    timepoint = os.environ.get("SCLDM_TIMEPOINT", "Stim48hr")
    n_cells = int(os.environ.get("SCLDM_N_CELLS", "500"))
    seed = int(os.environ.get("SCLDM_SEED", "42"))
    device = os.environ.get("SCLDM_DEVICE", "cuda")

    control_candidates = [
        g
        for g in guide_categories
        if any(
            kw in g.lower()
            for kw in ("non-target", "non_target", "ntc", "control", "safe", "scramble")
        )
    ]
    control_label = os.environ.get(
        "SCLDM_CONTROL_LABEL",
        control_candidates[0] if len(control_candidates) == 1 else control_candidates[0],
    )

    def sample_base_cells(adata, donor, tp, n, rng_seed):
        mask = (adata.obs["donor_id"].astype(str) == donor) & (
            adata.obs["experimental_perturbation_time_point"].astype(str) == tp
        )
        subset = adata[mask]
        if subset.n_obs == 0:
            raise ValueError(f"No cells for donor={donor}, timepoint={tp}")
        rng = np.random.default_rng(rng_seed)
        idx = rng.choice(subset.n_obs, size=n, replace=subset.n_obs < n)
        return subset[idx].copy()

    def build_query(base, guide_label):
        q = base.copy()
        q.obs["guide_target_ensembl"] = pd.Categorical([guide_label] * q.n_obs)
        return q

    base_cells = sample_base_cells(train_adata, donor_id, timepoint, n_cells, seed)
    query_ko = build_query(base_cells, ensembl)
    query_ctrl = build_query(base_cells, control_label)
    ko_path = query_dir / "query_conditional.h5ad"
    ctrl_path = query_dir / "query_control.h5ad"
    query_ko.write_h5ad(ko_path)
    query_ctrl.write_h5ad(ctrl_path)

    config_path = str(repo_root / "experiments" / "config")
    config_name = os.environ.get("SCLDM_INFERENCE_CONFIG", "inference_fm")

    def run_generation(query_path: Path, run_name: str):
        return inference(
            config_path=config_path,
            config_name=config_name,
            checkpoint_path=str(ckpt_path),
            output_dir=str(output_dir / run_name),
            dataset_generation_idx=0,
            seed=seed,
            batch_size=32,
            device=device,
            overrides=[
                "model.batch_size=32",
                f"datamodule.dataset_params.marson_hvg.adata_test={query_path.resolve()}",
            ],
        )

    gen_ko = run_generation(ko_path, "knockout")
    gen_ctrl = run_generation(ctrl_path, "control")
    knockout_cells = gen_ko[gen_ko.obs["dataset"] == "generated_conditional"].copy()
    control_cells = gen_ctrl[gen_ctrl.obs["dataset"] == "generated_conditional"].copy()

    # Map var names → HGNC where possible
    for adata_obj in (knockout_cells, control_cells):
        adata_obj.var["hgnc_symbol"] = adata_obj.var_names.map(
            lambda x: ENSEMBL_TO_SYMBOL.get(str(x), SYMBOL_TO_ENSEMBL.get(str(x), str(x)))
        )

    def to_dense(x):
        return x.toarray() if sparse.issparse(x) else np.asarray(x)

    mean_ko = to_dense(knockout_cells.X).mean(axis=0)
    mean_ctrl = to_dense(control_cells.X).mean(axis=0)
    delta = np.asarray(mean_ko - mean_ctrl).ravel()
    symbols = list(knockout_cells.var["hgnc_symbol"].astype(str))

    # Project onto marker panel (model space → our 0–5 panel via relative shift)
    # Use z-scored delta magnitude scaled into marker units.
    marker_deltas: dict[str, float] = {g: 0.0 for g in MARKER_GENES}
    marker_ctrl: dict[str, float] = {}
    marker_ko: dict[str, float] = {}
    for g in MARKER_GENES:
        if g in symbols:
            i = symbols.index(g)
            # Scale log-count deltas into panel units (heuristic calibration)
            d = float(delta[i]) * 1.5
            marker_deltas[g] = _round2(d)
            marker_ctrl[g] = _round2(float(mean_ctrl[i]))
            marker_ko[g] = _round2(float(mean_ko[i]))
        else:
            marker_ctrl[g] = _CONTROL_BASE[g]
            marker_ko[g] = _clamp_expr(_CONTROL_BASE[g] + marker_deltas[g])

    # If model means aren't on 0–5 scale, rebuild knockout means from control base + delta
    # so the MCP contract stays consistent with the frontend.
    mean_control_panel = {g: _round2(_CONTROL_BASE[g]) for g in MARKER_GENES}
    mean_knockout_panel = {
        g: _clamp_expr(mean_control_panel[g] + marker_deltas[g]) for g in MARKER_GENES
    }

    order = np.argsort(-np.abs(delta))[:20]
    top_effects = [
        {
            "gene": symbols[i],
            "delta": _round2(float(delta[i])),
            "direction": "up" if delta[i] > 0 else "down",
        }
        for i in order
    ]

    return KnockoutResult(
        gene=gene,
        ensembl_id=ensembl,
        backend="scldm_live",
        mean_control=mean_control_panel,
        mean_knockout=mean_knockout_panel,
        deltas={g: _round2(marker_deltas[g]) for g in MARKER_GENES},
        top_effects=top_effects,
        details={
            "method": "scldm_cd4_counterfactual",
            "donor_id": donor_id,
            "timepoint": timepoint,
            "control_label": control_label,
            "n_cells_generated": {
                "knockout": int(knockout_cells.n_obs),
                "control": int(control_cells.n_obs),
            },
            "checkpoint": str(ckpt_path),
            "model_native_marker_means": {
                "control": marker_ctrl,
                "knockout": marker_ko,
            },
        },
    )


def evaluate_knockout(gene: str) -> KnockoutResult:
    """Public entry: live scLDM if configured, else surrogate."""
    gene = gene.upper()
    if gene not in KNOWN_GUIDE_SYMBOLS and resolve_ensembl(gene) is None:
        raise ValueError(f"gene_out_of_vocabulary:{gene}")

    if scldm_available():
        try:
            return run_live_knockout(gene)
        except Exception as exc:  # noqa: BLE001
            # Fall through to surrogate but keep the error visible
            result = run_surrogate_knockout(gene)
            result.details["live_error"] = f"{type(exc).__name__}: {exc}"
            result.details["note"] = (
                "Live scLDM inference failed — served surrogate deltas. "
                + str(result.details.get("note", ""))
            )
            return result
    return run_surrogate_knockout(gene)
