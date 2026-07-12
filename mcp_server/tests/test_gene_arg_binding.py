"""Post-COMMIT gene-argument binding in the driver."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.driver import _enforce_committed_gene


def test_rewrites_mismatched_measured_gene():
    focus = {"gene": "PDCD1", "gene_locked": True}
    args, corr = _enforce_committed_gene(
        focus, "find_measured_perturbation_evidence", {"gene": "HAVCR2", "cell_type": "CD4_T"}
    )
    assert args["gene"] == "PDCD1"
    assert corr is not None
    assert corr["forced"] == "PDCD1"
    assert corr["passed"] == "HAVCR2"


def test_injects_gene_into_literature():
    focus = {"gene": "PDCD1", "gene_locked": True}
    args, corr = _enforce_committed_gene(
        focus, "search_literature", {"query": "HAVCR2 TIM-3 knockout"}
    )
    assert args["gene"] == "PDCD1"
    assert args["genes"] == ["PDCD1"]
    assert corr is not None


def test_noop_before_commit():
    focus = {"gene": None, "gene_locked": False}
    args, corr = _enforce_committed_gene(
        focus, "find_measured_perturbation_evidence", {"gene": "HAVCR2"}
    )
    assert args["gene"] == "HAVCR2"
    assert corr is None


def test_noop_when_already_bound():
    focus = {"gene": "PDCD1", "gene_locked": True}
    args, corr = _enforce_committed_gene(
        focus, "simulate_perturbations", {"gene": "PDCD1", "cell_id": "c1"}
    )
    assert args["gene"] == "PDCD1"
    assert corr is None


def test_cohort_genes_forced_to_committed():
    focus = {"gene": "PDCD1", "gene_locked": True}
    args, corr = _enforce_committed_gene(
        focus,
        "differential_survival_analysis",
        {"genes": ["HAVCR2", "TOX", "PDCD1"], "cancer_type": "CRC"},
    )
    assert args["genes"] == ["PDCD1"]
    assert corr is not None
