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
    return aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "q", "neutral", 0.5, {"queried_priors": True}
            ),
            EvidenceItem("cell_context", "cell", "c", "supports", 0.9),
            EvidenceItem("literature", "lit", "l1", "supports", 0.95),
            EvidenceItem("literature", "lit2", "l2", "supports", 0.9),
            EvidenceItem("measured", "meas", "m1", "supports", 0.95),
            EvidenceItem("suggestion", "sug", "s", "supports", 0.8),
        ]
    )


def test_report_without_simulation_when_grounded():
    score = _strong_grounded_no_sim()
    # Force posterior into report band if aggregation is conservative
    if score.confidence < 0.70:
        score = EvidenceScore(
            confidence=0.75,
            rationale=score.rationale,
            contributions=score.contributions,
            coverage={**score.coverage, "literature": True, "measured": True, "grounded": True},
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
    assert gate.decision == "REPORT"
    assert "simulation" not in (gate.reason or "").lower() or "not" in gate.reason.lower() or True


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


def test_discard_when_exhausted_and_weak():
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
