"""Unit tests for evidence aggregation — Bayesian log-odds (bits)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence


def _lit(polarity="supports", strength=0.9, sid="lit"):
    return EvidenceItem("literature", "lit hit", sid, polarity, strength)


def _sim(polarity="supports", strength=0.95, sid="sim"):
    return EvidenceItem("simulation", "sim hit", sid, polarity, strength)


def _measured(polarity="supports", strength=0.9, sid="meas"):
    return EvidenceItem("measured", "measured hit", sid, polarity, strength)


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


def test_conflict_lowers_score_vs_agreement():
    agree = aggregate_evidence([_lit("supports"), _measured("supports")])
    conflict = aggregate_evidence([_lit("contradicts"), _measured("supports")])
    assert conflict.has_conflict is True
    assert conflict.confidence < agree.confidence


def test_duplicate_literature_same_cluster_does_not_double_count():
    one = aggregate_evidence([_lit(sid="same-paper")])
    two = aggregate_evidence([_lit(sid="same-paper"), _lit(sid="same-paper")])
    # Identical source_ids must not raise confidence above a single hit.
    assert two.confidence <= one.confidence + 1e-9


def test_contradicting_simulation_without_lit_is_weak():
    weak = aggregate_evidence([_sim("contradicts")])
    strong = aggregate_evidence([_lit(), _measured("supports")])
    assert weak.confidence < strong.confidence


def test_grounded_stack_moves_posterior():
    score = aggregate_evidence(
        [
            _prior(),
            _cell(),
            _lit(),
            _measured(),
            EvidenceItem("suggestion", "PDCD1", "sug", "supports", 0.85),
        ]
    )
    assert score.has_grounded_source
    assert score.n_independent_sources >= 2
    assert "Posterior" in score.rationale or "posterior" in score.rationale.lower()


def test_rationale_mentions_sources():
    score = aggregate_evidence([_lit(sid="paper-1"), _sim(sid="vc-1")])
    assert "paper-1" in score.rationale
    assert "vc-1" in score.rationale
