"""Epistemics layer tests — log-odds, independence, gating, trust gate, LRs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.calibrate_benchmark import run_benchmark
from spatial_mcp.agent.evidence import (
    DOCUMENTED_LR_BITS,
    EvidenceItem,
    aggregate_evidence,
    item_log_lr_bits,
)
from spatial_mcp.agent.gating import decide_next_action
from spatial_mcp.agent.hypothesis import Hypothesis
from spatial_mcp.agent.independence import independence_key
from spatial_mcp.agent.lit_clusters import cluster_literature_cards
from spatial_mcp.agent.preregister import (
    make_preregistration,
    requires_preregistration,
    resolve_preregistration,
)
from spatial_mcp.graph import clear_edges, insert_edge
from spatial_mcp.memory import reset_store
from spatial_mcp.stubs.recommend_next_experiment import calibrate_simulation_trust


def test_zero_lr_source_moves_posterior_by_exactly_zero():
    """LR=1 (0 bits) must not nudge confidence."""
    base = aggregate_evidence([])
    worthless = EvidenceItem(
        "simulation",
        "noise",
        "sim:zero",
        "supports",
        1.0,
        {"sim_trust_bits": 0.0, "lr_note": "worthless"},
    )
    with_zero = aggregate_evidence([worthless])
    assert with_zero.confidence == base.confidence
    entry = next(e for e in with_zero.evidence_budget if e["source_id"] == "sim:zero")
    assert entry["bits"] == 0.0


def test_contradiction_subtracts_without_special_penalty():
    lit_sup = EvidenceItem("literature", "pro", "a", "supports", 1.0)
    lit_con = EvidenceItem("literature", "con", "b", "contradicts", 1.0)
    up = aggregate_evidence([lit_sup])
    down = aggregate_evidence([lit_sup, lit_con])
    assert down.confidence < up.confidence
    assert down.has_conflict is True
    # No 'conflict' contribution type — signed bits only
    assert not any(c["evidence_type"] == "conflict" for c in down.contributions)


def test_correlated_sims_do_not_double_count():
    s1 = EvidenceItem(
        "simulation", "seed1", "sim:1", "supports", 1.0,
        {"gene": "PDCD1", "sim_trust_bits": 0.16},
    )
    s2 = EvidenceItem(
        "simulation", "seed2", "sim:2", "supports", 1.0,
        {"gene": "PDCD1", "sim_trust_bits": 0.16},
    )
    one = aggregate_evidence([s1])
    two = aggregate_evidence([s1, s2])
    # Same independence cluster → second is redundant (0 bits)
    assert abs(two.posterior_log_odds_bits - one.posterior_log_odds_bits) < 1e-9
    redundant = [e for e in two.evidence_budget if e.get("redundant")]
    assert len(redundant) == 1


def test_simulation_bits_near_documented_prior():
    bits, tier, _ = item_log_lr_bits(
        EvidenceItem("simulation", "x", "s", "supports", 1.0)
    )
    assert tier == "documented_prior"
    assert abs(bits - DOCUMENTED_LR_BITS["simulation"]) < 1e-9
    assert 0.1 < bits < 0.25  # ~0.16 order of magnitude


def test_gating_cannot_report_on_simulation_alone():
    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "q", "neutral", 0.5, {"queried_priors": True}
            ),
            EvidenceItem(
                "simulation", "sim", "m", "supports", 1.0,
                {"gene": "PDCD1", "sim_trust_bits": 2.0},  # even if overstated
            ),
            EvidenceItem("cell_context", "c", "c", "supports", 0.9),
            EvidenceItem("suggestion", "s", "s", "supports", 0.9),
        ]
    )
    gate = decide_next_action(
        evidence_score=score,
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "suggest_perturbations",
            "simulate_perturbations",
        ],
        max_iterations=8,
        iteration=5,
    )
    assert gate.decision != "REPORT"
    assert score.has_grounded_source is False


def test_gating_reports_with_grounded_independence_no_sim():
    """Literature + measured + priors — simulation optional."""
    score = aggregate_evidence(
        [
            EvidenceItem(
                "prior_finding", "ok", "q", "neutral", 0.5, {"queried_priors": True}
            ),
            EvidenceItem("cell_context", "c", "c", "supports", 0.9),
            EvidenceItem("literature", "lit", "l", "supports", 1.0),
            EvidenceItem(
                "measured", "meas", "m", "supports", 1.0,
                {"accession": "lincs:1", "context_match_score": 0.9},
            ),
        ]
    )
    assert score.has_grounded_source
    assert score.n_independent_sources >= 2
    gate = decide_next_action(
        evidence_score=score,
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "search_literature",
            "find_measured_perturbation_evidence",
        ],
        max_iterations=8,
        iteration=5,
    )
    assert gate.decision == "REPORT"
    assert score.confidence >= 0.70


def test_hypothesis_is_first_class():
    h = Hypothesis(gene="TOX", cell_type="CD4_Tex_term", niche="tumor_core")
    assert "TOX" in h.claim
    assert "CRISPR" in h.claim
    score = aggregate_evidence(
        [EvidenceItem("literature", "x", "l", "supports", 1.0)],
        hypothesis=h,
    )
    assert score.hypothesis is not None
    assert score.hypothesis["gene"] == "TOX"
    assert score.evidence_budget[0]["role"] == "prior"


def test_lit_clustering_collapses_same_pmid():
    cards = [
        {"title": "A", "pmid": "111", "stance": "supports", "claim": "x"},
        {"title": "A mirror", "pmid": "111", "stance": "supports", "claim": "x"},
        {"title": "B", "pmid": "222", "stance": "supports", "claim": "y"},
    ]
    out = cluster_literature_cards(cards)
    assert out["n_papers"] == 3
    assert out["n_independent_claims"] == 2
    assert "3 papers → 2 independent" in out["summary"]


def test_preregistration_required_and_resolves():
    assert requires_preregistration("simulate_perturbations")
    assert not requires_preregistration("list_candidate_cells")
    reg = make_preregistration(
        tool="simulate_perturbations",
        gene="PDCD1",
        predicted_direction="up",
        predicted_magnitude="moderate",
    )
    resolved = resolve_preregistration(
        reg,
        {
            "ok": True,
            "deltas": {"PDCD1": -1.0, "TOX": -0.5, "TCF7": 0.8, "IL7R": 0.6, "GZMB": 0.5},
        },
        path=ROOT / "data" / "_test_prereg.jsonl",
    )
    assert resolved.confirmed is True


def test_calibration_context_gate_still_fires(tmp_path):
    """Mismatched-context pairs must not enter calibrate_simulation_trust."""
    reset_store(tmp_path / "t.db")
    clear_edges()
    insert_edge(
        "GENEZ",
        "simulated_knockout_down",
        "TOX",
        source_type="simulation",
        source_id="sim:z",
        cell_type_context="CD4_T",
        metadata={"direction": "down", "mechanism": "crispr"},
    )
    insert_edge(
        "GENEZ",
        "measured_perturbation_effect",
        "A375_SIG",
        source_type="measured",
        source_id="lincs:a375",
        cell_type_context="A375",
        metadata={"direction": "up", "mechanism": "small_molecule", "species": "human"},
    )
    cal = calibrate_simulation_trust(min_pairs=1)
    assert cal["n_pairs"] == 0
    assert cal["n_skipped_low_context"] >= 1


def test_benchmark_runs_offline():
    payload = run_benchmark(write=False)
    assert payload["n_cases"] >= 30
    assert "simulation_auroc_delta" in payload
    assert payload["demo"]["GAPDH"]["confidence"] < payload["demo"]["CBLB"]["confidence"]
    # GAPDH should not REPORT
    assert payload["demo"]["GAPDH"]["gate"] != "REPORT"
