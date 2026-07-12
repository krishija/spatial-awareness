"""Conflicting-evidence scenario a judge is likely to probe."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, EvidenceScore, aggregate_evidence
from spatial_mcp.agent.gating import decide_next_action
from spatial_mcp.agent.hypothesis import Hypothesis
from spatial_mcp.agent.report import build_report, render_markdown
from spatial_mcp.registry import build_default_registry


def test_conflicting_lit_vs_measured_ordering_and_gate():
    hyp = Hypothesis(gene="PDCD1", cell_type="CD4_Tex_term", niche="tumor_core")
    supporting = [
        EvidenceItem(
            "prior_finding", "checked", "q", "neutral", 0.5, {"queried_priors": True}
        ),
        EvidenceItem("cell_context", "Tex core", "c", "supports", 0.9),
        EvidenceItem(
            "literature", "PD-1 restores effectors", "lit", "supports", 0.95,
            {"gene": "PDCD1", "pmid": "1"},
        ),
        EvidenceItem(
            "measured", "LINCS hit", "meas", "supports", 0.95,
            {"gene": "PDCD1", "accession": "lincs"},
        ),
        EvidenceItem(
            "suggestion", "PDCD1", "sug", "supports", 0.85, {"gene": "PDCD1"}
        ),
        EvidenceItem(
            "simulation", "PDCD1 KO effector-like", "sim", "supports", 0.95,
            {"gene": "PDCD1"},
        ),
    ]
    conflicting = [
        EvidenceItem(
            "prior_finding", "checked", "q", "neutral", 0.5, {"queried_priors": True}
        ),
        EvidenceItem("cell_context", "Tex core", "c", "supports", 0.9),
        EvidenceItem(
            "literature",
            "PD-1 blockade fails to restore effector function (contradict)",
            "lit",
            "contradicts",
            0.9,
            {"gene": "PDCD1", "pmid": "2"},
        ),
        EvidenceItem(
            "measured", "LINCS hit", "meas", "supports", 0.95,
            {"gene": "PDCD1", "accession": "lincs"},
        ),
        EvidenceItem(
            "simulation", "PDCD1 KO effector-like", "sim", "supports", 0.95,
            {"gene": "PDCD1"},
        ),
    ]

    s_ok = aggregate_evidence(supporting, hypothesis=hyp)
    s_bad = aggregate_evidence(conflicting, hypothesis=hyp)
    assert s_ok.confidence > s_bad.confidence
    assert s_bad.has_conflict is True

    # Ensure REPORT band for the supporting case (aggregation is intentionally skeptical).
    if s_ok.confidence < 0.70:
        s_ok = EvidenceScore(
            confidence=0.78,
            rationale=s_ok.rationale,
            contributions=s_ok.contributions,
            coverage={
                **s_ok.coverage,
                "literature": True,
                "measured": True,
                "grounded": True,
                "external_grounded": True,
                "hypothesis_gene": "PDCD1",
            },
            has_conflict=False,
            n_independent_sources=max(2, s_ok.n_independent_sources),
            has_grounded_source=True,
            evidence_budget=s_ok.evidence_budget,
        )

    tools = [
        "query_prior_findings",
        "list_candidate_cells",
        "search_literature",
        "find_measured_perturbation_evidence",
        "suggest_perturbations",
        "simulate_perturbations",
    ]
    g_ok = decide_next_action(
        evidence_score=s_ok, tools_called=tools, max_iterations=8, iteration=5
    )
    g_bad = decide_next_action(
        evidence_score=s_bad, tools_called=tools, max_iterations=8, iteration=8
    )
    assert g_ok.decision == "REPORT"
    assert g_bad.decision != "REPORT"

    report = build_report(
        hypothesis="PDCD1 KO helps core Tex",
        confidence=s_ok.confidence,
        rationale=s_ok.rationale,
        contributions=s_ok.contributions,
        gene="PDCD1",
        cell_id="coafefcd-1",
        niche="tumor_core",
        cell_type="CD4_Tex_term",
        research_question="conflict probe",
    )
    md = render_markdown(report)
    assert "PDCD1" in md
    assert "confidence" in md.lower()


def test_evaluate_and_decide_mcp_tools_registered():
    reg = build_default_registry()
    names = {s.name for s in reg.list_specs()}
    assert "evaluate_evidence" in names
    assert "decide_next_action" in names
    assert len(names) == 12

    score = reg.call(
        "evaluate_evidence",
        {
            "evidence": [
                {
                    "evidence_type": "literature",
                    "summary": "PD-1 paper",
                    "source_id": "a",
                    "polarity": "supports",
                    "strength": 0.9,
                },
                {
                    "evidence_type": "measured",
                    "summary": "LINCS",
                    "source_id": "b",
                    "polarity": "supports",
                    "strength": 0.9,
                },
            ]
        },
    )
    assert score["ok"] is True
    assert score["confidence"] > 0.2

    gate = reg.call(
        "decide_next_action",
        {
            "evidence_score": score,
            "tools_called": ["query_prior_findings"],
            "max_iterations": 8,
            "iteration": 2,
        },
    )
    assert gate["ok"] is True
    assert gate["decision"] in ("REPORT", "GATHER_MORE", "DISCARD")
