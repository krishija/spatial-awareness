"""Graph edges, calibration disagreement, and reanalyze preference."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.graph import clear_edges, find_related, insert_edge
from spatial_mcp.memory import reset_store
from spatial_mcp.stubs.find_measured_perturbation_evidence import (
    STATE_TRAINING_GENES,
    SCLDM_TRAINING_GENES,
    find_measured_perturbation_evidence,
)
from spatial_mcp.stubs.recommend_next_experiment import (
    calibrate_simulation_trust,
    recommend_next_experiment,
)


def _isolated(tmp_path):
    return reset_store(tmp_path / "test_findings.db")


def test_insert_edge_dedupes_source_ids(tmp_path):
    _isolated(tmp_path)
    clear_edges()
    a = insert_edge(
        "PDCD1",
        "literature_supports",
        "exhaustion",
        source_type="literature",
        source_id="pmid:1",
        confidence=0.6,
        metadata={"direction": "up"},
    )
    b = insert_edge(
        "PDCD1",
        "literature_supports",
        "exhaustion",
        source_type="simulation",
        source_id="sim:pdcd1",
        confidence=0.9,
        metadata={"direction": "up"},
    )
    assert a["merged"] is False
    assert b["merged"] is True
    assert b["source_ids"] == ["pmid:1", "sim:pdcd1"]
    assert b["source_type"] == "literature"  # literature ranks above simulation
    # measured would win; re-merge with measured
    c = insert_edge(
        "PDCD1",
        "literature_supports",
        "exhaustion",
        source_type="measured",
        source_id="lincs:1",
        confidence=0.95,
    )
    assert set(c["source_ids"]) == {"pmid:1", "sim:pdcd1", "lincs:1"}
    assert c["source_type"] == "measured"


def test_find_related_bfs_two_hops(tmp_path):
    _isolated(tmp_path)
    clear_edges()
    insert_edge("A", "rel", "B", source_type="literature", source_id="1")
    insert_edge("B", "rel", "C", source_type="literature", source_id="2")
    insert_edge("C", "rel", "D", source_type="literature", source_id="3")
    related = find_related("A", max_hops=2)
    ents = {r["entity"] for r in related["related"]}
    assert ents == {"B", "C"}  # D is hop 3 — excluded


def test_calibrate_disagreement_lowers_empirical_rate(tmp_path):
    """Deliberate sim vs measured disagreement must lower agreement rate."""
    _isolated(tmp_path)
    clear_edges()
    insert_edge(
        "GENEX",
        "simulated_knockout_down",
        "TOX",
        source_type="simulation",
        source_id="sim:genex",
        cell_type_context="CD4_T",
        metadata={"direction": "down", "delta": -1.2, "mechanism": "crispr"},
    )
    insert_edge(
        "GENEX",
        "measured_perturbation_effect",
        "TOX_UP",
        source_type="measured",
        source_id="measured:genex",
        cell_type_context="CD4_T",
        metadata={"direction": "up", "mechanism": "crispr", "species": "human"},
    )
    cal = calibrate_simulation_trust(min_pairs=1)
    assert cal["n_pairs"] == 1
    assert cal["n_disagree"] == 1
    assert cal["n_agree"] == 0
    assert cal["empirical_rate"] == 0.0
    assert cal["trust"] == 0.0  # min_pairs=1 → use empirical rate fully
    assert cal["pairs"][0]["agrees"] is False
    assert float(cal["pairs"][0]["context_match_score"]) >= cal["min_context_match"]


def test_calibrate_agreement_and_disagreement_not_averaged_away(tmp_path):
    _isolated(tmp_path)
    clear_edges()
    # Agreeing pair
    insert_edge(
        "GENEA",
        "simulated_knockout_up",
        "TCF7",
        source_type="simulation",
        source_id="sim:a",
        cell_type_context="CD4_T",
        metadata={"direction": "up", "mechanism": "crispr"},
    )
    insert_edge(
        "GENEA",
        "lit",
        "TCF7",
        source_type="literature",
        source_id="lit:a",
        cell_type_context="CD4_T",
        metadata={"direction": "up", "mechanism": "crispr", "species": "human"},
    )
    # Disagreeing pair
    insert_edge(
        "GENEB",
        "simulated_knockout_up",
        "TOX",
        source_type="simulation",
        source_id="sim:b",
        cell_type_context="CD4_T",
        metadata={"direction": "up", "mechanism": "crispr"},
    )
    insert_edge(
        "GENEB",
        "lit",
        "TOX",
        source_type="literature",
        source_id="lit:b",
        cell_type_context="CD4_T",
        metadata={"direction": "down", "mechanism": "crispr", "species": "human"},
    )
    cal = calibrate_simulation_trust(min_pairs=2)
    assert cal["n_pairs"] == 2
    assert cal["n_agree"] == 1
    assert cal["n_disagree"] == 1
    assert cal["empirical_rate"] == 0.5


def test_calibrate_skips_low_context_pairs(tmp_path):
    """Mismatched-context measured hits must not move the empirical rate.

    A LINCS-style cancer-line signature can still be found by
    find_measured_perturbation_evidence; it just must not calibrate trust.
    """
    _isolated(tmp_path)
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
    # Deliberately bad context: cancer line + small molecule vs CD4 CRISPR
    insert_edge(
        "GENEZ",
        "measured_perturbation_effect",
        "A375_SIG",
        source_type="measured",
        source_id="lincs:a375:z",
        cell_type_context="A375",
        metadata={
            "direction": "up",  # would disagree if counted
            "mechanism": "small_molecule",
            "species": "human",
        },
    )
    cal = calibrate_simulation_trust(min_pairs=1)
    assert cal["n_pairs"] == 0
    assert cal["n_skipped_low_context"] == 1
    assert cal["empirical_rate"] is None
    assert cal["used_default"] is True
    assert cal["trust"] == 0.55  # neutral — not poisoned by the mismatch
    skip = cal["skipped_low_context"][0]
    assert float(skip["context_match_score"]) < cal["min_context_match"]

    # Same gene still surfaces from find_measured with a low labeled score
    measured = find_measured_perturbation_evidence(
        {"gene": "GENEZ", "cell_type": "CD4_T", "perturbation_type": "knockout"}
    )
    assert measured["n_hits"] >= 1
    best = max(measured["hits"], key=lambda h: float(h.get("context_match_score") or 0))
    assert float(best["context_match_score"]) < 0.45


def test_recommend_prefers_reanalyze_when_measured_exists(tmp_path):
    """Seeded measured edge → reanalyze_existing_data, not a new wet-lab assay."""
    store = _isolated(tmp_path)
    clear_edges()

    gene = "ICOS"
    assert gene not in SCLDM_TRAINING_GENES
    assert gene not in STATE_TRAINING_GENES

    store.record(
        {
            "sample_id": "test-sample",
            "niche": "tumor_core",
            "gene": gene,
            "finding_summary": (
                "ICOS hypothesized as compensatory checkpoint axis; "
                "no wet-lab assay yet."
            ),
            "citations": [],
        }
    )
    insert_edge(
        gene,
        "measured_perturbation_effect",
        f"{gene}_CD4_KO_SIGNATURE",
        source_type="measured",
        source_id=f"measured:{gene}:fixture",
        confidence=0.9,
        cell_type_context="CD4_T",
        metadata={"direction": "down", "mechanism": "crispr"},
    )

    out = recommend_next_experiment(
        {"sample_id": "test-sample", "top_k": 10, "cell_type": "CD4_T"}
    )
    assert out["ok"] is True
    by_gene = {r["gene"]: r for r in out["recommendations"]}
    assert gene in by_gene
    rec = by_gene[gene]
    assert rec["recommendation_type"] == "reanalyze_existing_data"
    assert rec["recommendation_type"] != "run_new_wet_lab_assay"
    assert float(rec["context_match_score"] or 0) >= 0.45
    assert rec["score_breakdown"]["assay_cost_divisor"] < 1.0  # reuse tier


def test_find_measured_nothing_found_is_informative(tmp_path):
    _isolated(tmp_path)
    clear_edges()
    out = find_measured_perturbation_evidence(
        {"gene": "ZZZNOTAREALGENE99", "cell_type": "CD4_T"}
    )
    assert out["ok"] is True
    assert out["nothing_found"] is True
    assert out["n_hits"] == 0
    assert out["message"]


def test_calibrate_runs_on_real_store_if_present():
    """Smoke: calibrate against the team's default DB without inventing fixtures."""
    # Restore default path store (not tmp)
    reset_store()
    cal = calibrate_simulation_trust()
    assert "trust" in cal
    assert "n_pairs" in cal
    assert 0.0 <= float(cal["trust"]) <= 1.0
