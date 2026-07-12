"""Tests for differential_survival_analysis — fixture + optional live TCGA."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence
from spatial_mcp.agent.extract import evidence_from_tool_result
from spatial_mcp.registry import build_default_registry
from spatial_mcp.stubs.differential_survival_analysis import (
    INTERPRETATION_CAVEAT,
    differential_survival_analysis,
)


CYTOTOXIC = ["CD8A", "GZMA", "PRF1", "CXCL9"]


def test_tool_registered():
    reg = build_default_registry()
    names = {s.name for s in reg.list_specs()}
    assert "differential_survival_analysis" in names


def test_rejects_mismatched_cancer_type():
    out = differential_survival_analysis(
        {"genes": CYTOTOXIC, "cancer_type": "GBM", "force_fixture": True}
    )
    assert out["ok"] is False
    assert out["error"] == "unsupported_cancer_type"
    assert "interpretation_caveat" in out
    assert "validation" not in (out.get("message") or "").lower()


def test_fixture_cytotoxic_signature_protective_in_crc():
    """Planted fixture association: cytotoxic genes → protective HR < 1."""
    out = differential_survival_analysis(
        {
            "genes": CYTOTOXIC,
            "cancer_type": "CRC",
            "expected_direction": "protective",
            "force_fixture": True,
            "prefer_ssgsea": False,
            "split": "median",
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "fixture"
    assert out["backend"] == "tcga_fixture"
    assert out["claim_type"] == "cohort_association"
    assert out["scoring_method"] == "zscore_mean"
    assert out["interpretation_caveat"] == INTERPRETATION_CAVEAT
    assert out["p_value_session_corrected"] is None
    assert out["multiple_testing"]["status"] == "uncorrected"
    assert "orchestrator" in out["multiple_testing"]["note"].lower() or "evidence" in out[
        "multiple_testing"
    ]["note"].lower()
    assert out["hazard_ratio"] < 1.0
    assert out["direction"] == "protective"
    assert out["association_matches_expectation"] is True
    assert "signature_high" in out["covariates_included"]
    # Fixture always has age/stage/purity/immune
    for cov in ("age", "stage", "purity", "immune_infiltration"):
        assert cov in out["covariates_included"]
    assert "validation" not in out["interpretation_caveat"].lower()


def test_evidence_extract_and_weight_vs_simulation():
    out = differential_survival_analysis(
        {
            "genes": CYTOTOXIC,
            "cancer_type": "MEL",
            "force_fixture": True,
            "prefer_ssgsea": False,
        }
    )
    items = evidence_from_tool_result(
        "differential_survival_analysis",
        {"genes": CYTOTOXIC, "cancer_type": "MEL"},
        out,
    )
    assert len(items) == 1
    assert items[0].evidence_type == "cohort_prognostic"
    assert items[0].metadata.get("interpretation_caveat")
    assert items[0].polarity == "supports"

    # Weight: cohort_prognostic base (0.30) > simulation (0.28)
    cohort_only = aggregate_evidence(
        [EvidenceItem("cohort_prognostic", "c", "c1", "supports", 1.0)]
    )
    sim_only = aggregate_evidence(
        [EvidenceItem("simulation", "s", "s1", "supports", 1.0)]
    )
    assert cohort_only.confidence > sim_only.confidence
    assert cohort_only.coverage["cohort_prognostic"] is True


@pytest.mark.integration
def test_live_tcga_melanoma_cytotoxic_association():
    """End-to-end against public cBioPortal SKCM; skip if offline/rate-limited.

    Cytotoxic / T-cell effector genes are a well-characterized protective
    prognostic signal in melanoma bulk cohorts — we expect HR < 1 (or at least
    a successful Cox fit with the required contract fields), not a claim of
    cell-level validation.
    """
    if os.environ.get("SKIP_CBIO_INTEGRATION", "").lower() in ("1", "true", "yes"):
        pytest.skip("SKIP_CBIO_INTEGRATION set")

    out = differential_survival_analysis(
        {
            "genes": ["CD8A", "GZMA", "PRF1", "CXCL9", "CXCL10"],
            "cancer_type": "MEL",
            "expected_direction": "protective",
            "prefer_ssgsea": False,
            "split": "median",
            "force_fixture": False,
        }
    )
    if out.get("mode") == "fixture":
        pytest.skip(f"cBioPortal unreachable; fell back to fixture: {out.get('load_notes')}")

    assert out["ok"] is True
    assert out["mode"] in ("live_cbioportal", "live_local")
    assert out["backend"].startswith("tcga_live")
    assert out["n_patients"] >= 50
    assert out["interpretation_caveat"] == INTERPRETATION_CAVEAT
    assert out["p_value_session_corrected"] is None
    assert "hazard_ratio" in out and out["hr_ci_low"] <= out["hazard_ratio"] <= out["hr_ci_high"]
    # Sanity: known-direction association should be protective (HR < 1).
    # If the public cohort ever drifts, still require a finite HR and caveat.
    assert out["hazard_ratio"] == out["hazard_ratio"]  # not NaN
    assert out["direction"] in ("protective", "risk_associated", "null")
    if out["n_events"] >= 30:
        assert out["hazard_ratio"] < 1.0, (
            f"Expected protective HR for cytotoxic signature in melanoma; got {out}"
        )
