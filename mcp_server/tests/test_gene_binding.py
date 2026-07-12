"""Gene binding, self-citation priors, and external-grounded REPORT bar."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence
from spatial_mcp.agent.gating import decide_next_action
from spatial_mcp.agent.hypothesis import Hypothesis
from spatial_mcp.agent.independence import (
    gene_matches_hypothesis,
    independence_key,
    is_self_citation_prior,
)


def test_gene_mismatch_contributes_zero_bits():
    hyp = Hypothesis(gene="PDCD1", cell_type="CD4_Tex_term", niche="tumor_margin")
    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "queried", "query_prior_findings", "neutral", 0.5,
                {"queried_priors": True},
            ),
            EvidenceItem(
                "cell_context", "cell", "c1", "supports", 0.9,
                {"sample_id": "atera-cervical-01"},
            ),
            EvidenceItem(
                "measured", "TOX hit", "m-tox", "supports", 1.0,
                {"gene": "TOX", "accession": "training:tox"},
            ),
        ],
        hypothesis=hyp,
    )
    tox_bits = next(
        (c["bits"] for c in score.contributions if c["source_id"] == "m-tox"), None
    )
    assert tox_bits == 0.0
    assert score.coverage.get("external_grounded") is False


def test_gene_matched_measured_counts():
    hyp = Hypothesis(gene="TOX", cell_type="CD4_Tex_term", niche="tumor_margin")
    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "queried", "query_prior_findings", "neutral", 0.5,
                {"queried_priors": True},
            ),
            EvidenceItem(
                "cell_context", "cell", "c1", "supports", 0.9,
                {"sample_id": "atera-cervical-01"},
            ),
            EvidenceItem(
                "measured", "TOX hit", "m-tox", "supports", 1.0,
                {"gene": "TOX", "accession": "training:tox"},
            ),
            EvidenceItem(
                "literature", "paper", "pmid:1", "supports", 0.9,
                {"gene": "TOX", "pmid": "1"},
            ),
        ],
        hypothesis=hyp,
    )
    tox_bits = next(c["bits"] for c in score.contributions if c["source_id"] == "m-tox")
    assert tox_bits > 0.5
    assert score.coverage.get("external_grounded") is True
    assert score.coverage.get("hypothesis_gene") == "TOX"


def test_self_citation_prior_zero_bits():
    hyp = Hypothesis(gene="PDCD1", cell_type="CD4_Tex_term", niche="tumor_margin")
    claim = hyp.claim
    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding",
                f"{claim} (confidence=0.736)",
                "finding-scout",
                "supports",
                0.7,
                {"gene": "PDCD1"},
            ),
            EvidenceItem(
                "measured", "PDCD1 hit", "m1", "supports", 1.0,
                {"gene": "PDCD1", "accession": "a"},
            ),
        ],
        hypothesis=hyp,
    )
    prior_bits = next(
        (c["bits"] for c in score.contributions if c["source_id"] == "finding-scout"),
        None,
    )
    assert prior_bits == 0.0
    assert is_self_citation_prior(
        EvidenceItem(
            "prior_finding", f"{claim} (confidence=0.7)", "f", "supports", 0.7,
            {"gene": "PDCD1"},
        ),
        hyp_gene="PDCD1",
        hyp_claim=claim,
    )


def test_prior_findings_same_gene_one_independence_cluster():
    a = EvidenceItem(
        "prior_finding", "a", "finding-1", "supports", 0.7, {"gene": "TOX"}
    )
    b = EvidenceItem(
        "prior_finding", "b", "finding-2", "supports", 0.7, {"gene": "TOX"}
    )
    assert independence_key(a) == independence_key(b) == "prior:gene:TOX"


def test_report_blocked_without_external_grounded():
    # High posterior from cell_context alone should not REPORT
    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "query_prior_findings", "neutral", 0.5,
                {"queried_priors": True},
            ),
            EvidenceItem(
                "cell_context", "cell", "c", "supports", 1.0,
                {"sample_id": "s"},
            ),
        ],
        hypothesis=Hypothesis(gene="PDCD1", cell_type="CD4_T"),
    )
    # Even if we force confidence, gate must refuse without external grounded
    from spatial_mcp.agent.evidence import EvidenceScore

    forced = EvidenceScore(
        confidence=0.95,
        rationale=score.rationale,
        contributions=score.contributions,
        coverage={
            **score.coverage,
            "external_grounded": False,
            "grounded": False,
            "hypothesis_gene": "PDCD1",
        },
        has_conflict=False,
        n_independent_sources=2,
        has_grounded_source=False,
        evidence_budget=score.evidence_budget,
    )
    gate = decide_next_action(
        evidence_score=forced,
        tools_called=["query_prior_findings", "list_candidate_cells"],
        max_iterations=8,
        iteration=5,
    )
    assert gate.decision != "REPORT"
    assert "external" in gate.reason.lower() or "grounded" in gate.reason.lower()


def test_gene_matches_hypothesis_helper():
    item = EvidenceItem("measured", "x", "m", "supports", 1.0, {"gene": "TOX"})
    assert gene_matches_hypothesis(item, "TOX")
    assert not gene_matches_hypothesis(item, "PDCD1")
    untagged = EvidenceItem("cell_context", "c", "c1", "supports", 0.9, {})
    assert gene_matches_hypothesis(untagged, "PDCD1")
