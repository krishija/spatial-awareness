"""Stance extraction / refine_stance unit tests (no Bedrock required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.stubs.lit_extract import refine_stance


HYP = (
    "CRISPR knockout of HAVCR2 in CD4_Tex_term from niche tumor_core produces a "
    "significant increase in effector-function markers (TCF7/IL7R/GZMB) in a "
    "primary human T-cell assay."
)


def test_support_claim_upgrades_tangential():
    stance, claim = refine_stance(
        hypothesis=HYP,
        claim=(
            "HAVCR2 knockout in terminally exhausted CD4 T cells increases "
            "effector function markers TCF7/IL7R/GZMB"
        ),
        title="Single-cell CRISPR screens in vivo map T cell fate regulomes",
        source_text="CRISPR knockout of Havcr2 increased Tcf7 and Gzmb in exhausted CD4 T cells.",
        stance="tangential",
        extraction_note="Clear KO result in text.",
    )
    assert stance == "supports"
    assert claim and "HAVCR2" in claim


def test_contradict_claim_upgrades_tangential():
    stance, _ = refine_stance(
        hypothesis=HYP,
        claim=(
            "TIM-3 (HAVCR2) upregulation is associated with T cell exhaustion, "
            "not increased effector function markers"
        ),
        title="Revolutionizing tumor immunotherapy",
        source_text="TIM-3 upregulation marks exhaustion and is not associated with increased effector function.",
        stance="tangential",
        extraction_note="Marker association.",
    )
    assert stance == "contradicts"


def test_hypothesis_echo_cleared_when_note_admits_gap():
    stance, claim = refine_stance(
        hypothesis=HYP,
        claim=(
            "HAVCR2 knockout in terminally exhausted CD4 T cells increases "
            "effector function markers TCF7/IL7R/GZMB"
        ),
        title="CTL heterogeneity review",
        source_text="Tpex and terminally exhausted CD8 subsets were reviewed without gene edits.",
        stance="tangential",
        extraction_note="Text does not mention HAVCR2 knockout effects on TCF7/IL7R/GZMB.",
    )
    assert stance == "tangential"
    assert "increases effector function markers" not in (claim or "").lower()


def test_support_from_source_text_even_if_claim_empty():
    stance, _ = refine_stance(
        hypothesis=HYP,
        claim="Unrelated filler about tissue architecture.",
        title="CRISPR screen",
        source_text=(
            "CRISPR knockout of HAVCR2 increased effector function and restored "
            "TCF7 expression in exhausted CD4 T cells in vivo."
        ),
        stance="tangential",
        extraction_note="Model was unsure.",
    )
    assert stance == "supports"


def test_marker_only_stays_tangential():
    stance, _ = refine_stance(
        hypothesis=HYP,
        claim="HAVCR2 (TIM3) is expressed on exhausted T cells in chronic viral infection and tumor settings",
        title="Opposing regulatory functions of the TIM3 signalosome",
        source_text="HAVCR2 is expressed on exhausted T cells in tumors.",
        stance="tangential",
        extraction_note="Expression only.",
    )
    assert stance == "tangential"
