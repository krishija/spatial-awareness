"""Unit tests for evidence aggregation — known relative orderings."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence


def _lit(polarity="supports", strength=0.9, sid="lit"):
    return EvidenceItem("literature", "lit hit", sid, polarity, strength)


def _sim(polarity="supports", strength=0.95, sid="sim"):
    return EvidenceItem("simulation", "sim hit", sid, polarity, strength)


def _cell(strength=0.9):
    return EvidenceItem("cell_context", "Tex in core", "cell", "supports", strength)


def _prior():
    return EvidenceItem(
        "prior_finding",
        "checked",
        "qpf",
        "neutral",
        0.5,
        {"queried_priors": True},
    )


def test_lit_plus_sim_beats_lit_alone():
    alone = aggregate_evidence([_prior(), _cell(), _lit()])
    both = aggregate_evidence([_prior(), _cell(), _lit(), _sim()])
    assert both.confidence > alone.confidence
    assert both.coverage["literature"] and both.coverage["simulation"]


def test_agreement_bonus_when_lit_and_sim_support():
    score = aggregate_evidence([_lit(), _sim()])
    assert any(c["evidence_type"] == "agreement" for c in score.contributions)
    assert score.has_conflict is False


def test_conflict_penalty_lowers_score_vs_agreement():
    agree = aggregate_evidence([_lit("supports"), _sim("supports")])
    conflict = aggregate_evidence([_lit("contradicts"), _sim("supports")])
    assert conflict.has_conflict is True
    assert conflict.confidence < agree.confidence
    assert any(c["evidence_type"] == "conflict" for c in conflict.contributions)


def test_duplicate_literature_discounted():
    one = aggregate_evidence([_lit(sid="a")])
    two = aggregate_evidence([_lit(sid="a"), _lit(sid="b")])
    # Second lit adds less than a full base weight
    delta = two.confidence - one.confidence
    assert 0 < delta < 0.22


def test_contradicting_simulation_without_lit_is_weak():
    weak = aggregate_evidence([_sim("contradicts")])
    strong = aggregate_evidence([_lit(), _sim("supports")])
    assert weak.confidence < strong.confidence


def test_full_supporting_stack_reaches_report_band():
    score = aggregate_evidence(
        [
            _prior(),
            _cell(),
            _lit(),
            EvidenceItem("suggestion", "PDCD1", "sug", "supports", 0.85),
            _sim(),
        ]
    )
    assert score.confidence >= 0.70


def test_rationale_mentions_each_input():
    score = aggregate_evidence([_lit(sid="paper-1"), _sim(sid="vc-1")])
    assert "paper-1" in score.rationale
    assert "vc-1" in score.rationale
    assert "Final calibrated confidence" in score.rationale
