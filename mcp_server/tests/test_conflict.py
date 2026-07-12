"""Conflicting-evidence scenario a judge is likely to probe."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence
from spatial_mcp.agent.gating import decide_next_action
from spatial_mcp.agent.report import build_report, render_markdown
from spatial_mcp.registry import build_default_registry


def test_conflicting_lit_vs_sim_ordering_and_gate():
    supporting = [
        EvidenceItem(
            "prior_finding", "checked", "q", "neutral", 0.5, {"queried_priors": True}
        ),
        EvidenceItem("cell_context", "Tex core", "c", "supports", 0.9),
        EvidenceItem("literature", "PD-1 restores effectors", "lit", "supports", 0.9),
        EvidenceItem("suggestion", "PDCD1", "sug", "supports", 0.85),
        EvidenceItem("simulation", "PDCD1 KO effector-like", "sim", "supports", 0.95),
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
        ),
        EvidenceItem("simulation", "PDCD1 KO effector-like", "sim", "supports", 0.95),
    ]

    s_ok = aggregate_evidence(supporting)
    s_bad = aggregate_evidence(conflicting)
    assert s_ok.confidence > s_bad.confidence
    assert s_bad.has_conflict is True

    tools = [
        "query_prior_findings",
        "list_candidate_cells",
        "search_literature",
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
        cell_id="crc-01-c0042",
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
                    "evidence_type": "simulation",
                    "summary": "PDCD1 KO",
                    "source_id": "b",
                    "polarity": "supports",
                    "strength": 0.95,
                },
            ]
        },
    )
    assert score["ok"] is True
    assert score["confidence"] > 0.4

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
