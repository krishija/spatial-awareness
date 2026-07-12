"""Unit tests for gating / stopping policy."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence
from spatial_mcp.agent.gating import decide_next_action


def _strong_score():
    return aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "q", "neutral", 0.5, {"queried_priors": True}
            ),
            EvidenceItem("cell_context", "cell", "c", "supports", 0.9),
            EvidenceItem("literature", "lit", "l", "supports", 0.9),
            EvidenceItem("suggestion", "sug", "s", "supports", 0.8),
            EvidenceItem("simulation", "sim", "m", "supports", 0.95),
        ]
    )


def test_report_when_confident_and_covered():
    gate = decide_next_action(
        evidence_score=_strong_score(),
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "search_literature",
            "suggest_perturbations",
            "simulate_perturbations",
        ],
        max_iterations=8,
        iteration=5,
    )
    assert gate.decision == "REPORT"


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
            EvidenceItem("simulation", "pro", "m", "supports", 0.95),
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
            "simulate_perturbations",
        ],
        max_iterations=8,
        iteration=8,
    )
    assert gate.decision != "REPORT"
