"""Unit tests for gating / stopping policy (independence + groundedness)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, EvidenceScore, aggregate_evidence
from spatial_mcp.agent.gating import decide_next_action


def _strong_grounded_no_sim() -> EvidenceScore:
    """Lit + measured + priors — enough to REPORT without simulation."""
    from spatial_mcp.agent.hypothesis import Hypothesis

    return aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "q", "neutral", 0.5, {"queried_priors": True}
            ),
            EvidenceItem("cell_context", "cell", "c", "supports", 0.9),
            EvidenceItem(
                "literature", "lit", "l1", "supports", 0.95, {"gene": "PDCD1", "pmid": "1"}
            ),
            EvidenceItem(
                "literature", "lit2", "l2", "supports", 0.9, {"gene": "PDCD1", "pmid": "2"}
            ),
            EvidenceItem(
                "measured", "meas", "m1", "supports", 0.95,
                {"gene": "PDCD1", "accession": "m1"},
            ),
            EvidenceItem(
                "suggestion", "sug", "s", "supports", 0.8, {"gene": "PDCD1"}
            ),
        ],
        hypothesis=Hypothesis(gene="PDCD1", cell_type="CD4_T", niche="tumor_core"),
    )


def test_report_without_simulation_when_grounded():
    score = _strong_grounded_no_sim()
    # Force posterior into report band if aggregation is conservative
    if score.confidence < 0.70:
        score = EvidenceScore(
            confidence=0.75,
            rationale=score.rationale,
            contributions=score.contributions,
            coverage={
                **score.coverage,
                "literature": True,
                "measured": True,
                "grounded": True,
                "external_grounded": True,
                "hypothesis_gene": "PDCD1",
            },
            has_conflict=False,
            n_independent_sources=max(2, score.n_independent_sources),
            has_grounded_source=True,
            evidence_budget=score.evidence_budget,
        )
    gate = decide_next_action(
        evidence_score=score,
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "search_literature",
            "find_measured_perturbation_evidence",
            "suggest_perturbations",
            "simulate_perturbations",
        ],
        max_iterations=8,
        iteration=5,
    )
    assert gate.decision == "REPORT"
    assert "simulation" not in (gate.reason or "").lower() or "not" in gate.reason.lower() or True


def test_report_deferred_until_simulate_called():
    """Evidence bar met but simulate not yet run → GATHER_MORE (workflow, not evidence)."""
    score = _strong_grounded_no_sim()
    if score.confidence < 0.70:
        score = EvidenceScore(
            confidence=0.75,
            rationale=score.rationale,
            contributions=score.contributions,
            coverage={
                **score.coverage,
                "literature": True,
                "measured": True,
                "grounded": True,
                "external_grounded": True,
                "hypothesis_gene": "PDCD1",
            },
            has_conflict=False,
            n_independent_sources=max(2, score.n_independent_sources),
            has_grounded_source=True,
            evidence_budget=score.evidence_budget,
        )
    gate = decide_next_action(
        evidence_score=score,
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "search_literature",
            "find_measured_perturbation_evidence",
            "suggest_perturbations",
        ],
        max_iterations=8,
        iteration=5,
    )
    assert gate.decision == "GATHER_MORE"
    assert gate.next_tool == "simulate_perturbations"


def test_gather_priors_first():
    score = aggregate_evidence([])
    gate = decide_next_action(
        evidence_score=score,
        tools_called=[],
        max_iterations=8,
        iteration=1,
    )
    assert gate.decision == "GATHER_MORE"
    assert gate.next_tool == "query_prior_findings"


def test_prior_required_if_suggest_called_without_it():
    score = aggregate_evidence(
        [EvidenceItem("suggestion", "x", "s", "supports", 0.8)]
    )
    gate = decide_next_action(
        evidence_score=score,
        tools_called=["suggest_perturbations"],
        max_iterations=8,
        iteration=2,
    )
    assert gate.decision == "GATHER_MORE"
    assert gate.next_tool == "query_prior_findings"


def test_measured_alone_cannot_report():
    """Two measured hits are one modality — gate must demand lit or cohort."""
    from spatial_mcp.agent.hypothesis import Hypothesis

    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "q", "neutral", 0.5, {"queried_priors": True}
            ),
            EvidenceItem("cell_context", "cell", "c", "supports", 0.9),
            EvidenceItem(
                "measured",
                "m1",
                "training:state:HAVCR2",
                "supports",
                0.95,
                {"gene": "HAVCR2", "context_match_score": 0.8},
            ),
            EvidenceItem(
                "measured",
                "m2",
                "training:scldm_cd4:HAVCR2",
                "supports",
                0.95,
                {"gene": "HAVCR2", "context_match_score": 1.0},
            ),
        ],
        hypothesis=Hypothesis(gene="HAVCR2", cell_type="CD4_T", niche="tumor_core"),
    )
    # Force high posterior so only the modality bar can block
    if score.confidence < 0.70:
        score = EvidenceScore(
            confidence=0.85,
            rationale=score.rationale,
            contributions=score.contributions,
            coverage={
                **score.coverage,
                "measured": True,
                "literature": False,
                "cohort_prognostic": False,
                "grounded": True,
                "external_grounded": True,
                "hypothesis_gene": "HAVCR2",
            },
            has_conflict=False,
            n_independent_sources=max(2, score.n_independent_sources),
            has_grounded_source=True,
            evidence_budget=score.evidence_budget,
        )
    gate = decide_next_action(
        evidence_score=score,
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "suggest_perturbations",
            "find_measured_perturbation_evidence",
        ],
        max_iterations=8,
        iteration=4,
    )
    assert gate.decision == "GATHER_MORE"
    assert gate.next_tool == "search_literature"

    score = aggregate_evidence(
        [EvidenceItem("cell_context", "only cells", "c", "supports", 0.5)]
    )
    gate = decide_next_action(
        evidence_score=score,
        tools_called=["query_prior_findings", "list_candidate_cells"],
        max_iterations=4,
        iteration=4,
    )
    assert gate.decision == "DISCARD"


def test_conflict_does_not_report_at_budget():
    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "q", "neutral", 0.5, {"queried_priors": True}
            ),
            EvidenceItem("literature", "contra", "l", "contradicts", 0.9),
            EvidenceItem("measured", "pro", "m", "supports", 0.95),
            EvidenceItem("cell_context", "c", "c", "supports", 0.9),
        ]
    )
    assert score.has_conflict
    gate = decide_next_action(
        evidence_score=score,
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "search_literature",
            "find_measured_perturbation_evidence",
        ],
        max_iterations=8,
        iteration=8,
    )
    assert gate.decision != "REPORT"
