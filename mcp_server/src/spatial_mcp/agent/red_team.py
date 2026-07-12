"""Red team: symmetric retrieval, confound enumeration, steelman-the-null.

Confirmation bias enters at retrieval. "No contradiction found" is only
informative if contradiction was searched with equal effort.
"""

from __future__ import annotations

from typing import Any

from spatial_mcp.agent.hypothesis import Hypothesis


def contradiction_queries(hypothesis: Hypothesis) -> list[str]:
    """Equal-budget ¬H / alternative queries for symmetric literature search."""
    g = hypothesis.gene
    ct = hypothesis.cell_type
    niche = hypothesis.niche or "tumor microenvironment"
    return [
        f"{g} knockout OR CRISPR fails to restore T cell effector function {ct}",
        f"{g} deletion premature effector differentiation OR impairs {ct}",
        f"{g} loss of function no benefit checkpoint immunotherapy resistance",
        f"{g} essential for T cell fitness OR depletion harmful {ct} {niche}",
        f"contradicts {g} as therapeutic target exhausted T cells",
    ]


def support_queries(hypothesis: Hypothesis) -> list[str]:
    g = hypothesis.gene
    ct = hypothesis.cell_type
    niche = hypothesis.niche or "tumor"
    markers = " ".join(hypothesis.effect_markers[:3])
    return [
        f"{g} knockout restores effector function {ct} exhaustion",
        f"{g} CRISPR {markers} {ct}",
        f"{g} depletion reprograms exhausted T cells {niche}",
        f"{g} checkpoint {ct} reinvigoration",
        f"{hypothesis.claim}",
    ]


def enumerate_confounds(hypothesis: Hypothesis) -> list[dict[str, Any]]:
    """Plausible alternative explanations a REPORT must address."""
    g = hypothesis.gene
    return [
        {
            "id": "off_target",
            "explanation": (
                f"Observed phenotype after {g} perturbation is an off-target CRISPR effect, "
                "not on-target loss of function."
            ),
            "ruled_out_by": [],
        },
        {
            "id": "wrong_cell_context",
            "explanation": (
                f"Literature/measured effects for {g} come from a different cell type "
                f"than {hypothesis.cell_type}; they do not transfer to this niche."
            ),
            "ruled_out_by": [],
        },
        {
            "id": "bulk_confound",
            "explanation": (
                "TCGA / bulk association reflects tumor-intrinsic or stromal expression, "
                "not the CD4 T-cell mechanism under test (ecological inference)."
            ),
            "ruled_out_by": [],
        },
        {
            "id": "compensation",
            "explanation": (
                f"Redundant checkpoints compensate for {g} loss in vivo, so primary assay "
                "effects will not translate."
            ),
            "ruled_out_by": [],
        },
        {
            "id": "sim_hallucination",
            "explanation": (
                "Virtual-cell deltas are within the model's noise floor or training bias "
                "and do not reflect biology."
            ),
            "ruled_out_by": [],
        },
    ]


def update_confound_status(
    confounds: list[dict[str, Any]],
    *,
    evidence_types_present: set[str],
    measured_context_match: float | None = None,
    cohort_present: bool = False,
) -> list[dict[str, Any]]:
    """Mark which alternatives the pipeline has evidence against."""
    out = []
    for c in confounds:
        ruled = list(c.get("ruled_out_by") or [])
        cid = c["id"]
        if cid == "wrong_cell_context" and measured_context_match is not None:
            if measured_context_match >= 0.45:
                ruled.append("find_measured_perturbation_evidence:context_match≥0.45")
        if cid == "bulk_confound" and cohort_present:
            # Presence of cohort does NOT rule out bulk confound — note that
            pass
        if cid == "sim_hallucination" and "measured" in evidence_types_present:
            ruled.append("measured_evidence_present")
        if cid == "compensation" and "literature" in evidence_types_present:
            # Weak — literature may mention compensation; leave unless explicit
            pass
        out.append({**c, "ruled_out_by": ruled, "surviving": len(ruled) == 0})
    return out


def surviving_alternatives(confounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in confounds if c.get("surviving", True)]


def steelman_prompt(hypothesis: Hypothesis, evidence_summaries: list[str]) -> str:
    """Bedrock prompt whose only job is to argue H is wrong."""
    ev = "\n".join(f"- {s}" for s in evidence_summaries[:12]) or "- (none yet)"
    return (
        "You are a hostile scientific reviewer. Your ONLY job is to argue that the "
        "following hypothesis is FALSE, using the evidence listed (and gaps in it). "
        "Do not hedge toward support. Produce 2–4 concrete objections. "
        "If the evidence cannot rebut an objection, say so explicitly.\n\n"
        f"HYPOTHESIS:\n{hypothesis.claim}\n\n"
        f"EVIDENCE:\n{ev}\n\n"
        "Respond as JSON: {\"objections\": [{\"claim\": str, \"rebuttable_by_evidence\": bool, "
        "\"why\": str}], \"strongest_unrebutted\": str|null}"
    )


def parse_steelman_response(text: str) -> dict[str, Any]:
    import json
    import re

    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {
        "objections": [
            {
                "claim": text[:500] or "Steelman returned unparseable output",
                "rebuttable_by_evidence": False,
                "why": "parse_failed",
            }
        ],
        "strongest_unrebutted": text[:200] if text else None,
        "parse_ok": False,
    }


def run_symmetric_literature_search(
    hypothesis: Hypothesis,
    *,
    search_fn: Any = None,
    budget_per_side: int = 5,
) -> dict[str, Any]:
    """Run equal-budget support vs contradiction literature searches.

    search_fn(args) should be search_literature. If None, imports the stub.
    """
    if search_fn is None:
        from spatial_mcp.stubs.search_literature import search_literature as search_fn

    support_qs = support_queries(hypothesis)[:budget_per_side]
    contra_qs = contradiction_queries(hypothesis)[:budget_per_side]

    support_hits: list[dict[str, Any]] = []
    contra_hits: list[dict[str, Any]] = []
    support_errors: list[str] = []
    contra_errors: list[str] = []

    for q in support_qs:
        r = search_fn(
            {
                "query": q,
                "hypothesis": hypothesis.claim,
                "gene": hypothesis.gene,
                "phenotype": hypothesis.cell_type,
                "niche": hypothesis.niche,
            }
        )
        if r.get("ok") is False:
            support_errors.append(r.get("message") or r.get("error") or "error")
            continue
        support_hits.extend(r.get("evidence_cards") or [])

    for q in contra_qs:
        r = search_fn(
            {
                "query": q,
                "hypothesis": f"NOT ({hypothesis.claim})",
                "gene": hypothesis.gene,
                "phenotype": hypothesis.cell_type,
                "niche": hypothesis.niche,
            }
        )
        if r.get("ok") is False:
            contra_errors.append(r.get("message") or r.get("error") or "error")
            continue
        contra_hits.extend(r.get("evidence_cards") or [])

    return {
        "ok": True,
        "support_search_effort": {
            "n_queries": len(support_qs),
            "queries": support_qs,
            "n_hits": len(support_hits),
            "errors": support_errors or None,
        },
        "contradiction_search_effort": {
            "n_queries": len(contra_qs),
            "queries": contra_qs,
            "n_hits": len(contra_hits),
            "errors": contra_errors or None,
        },
        "support_cards": support_hits,
        "contradiction_cards": contra_hits,
        "symmetric_search_complete": True,
        "message": (
            f"support_search_effort: {len(support_qs)} queries → {len(support_hits)} hits; "
            f"contradiction_search_effort: {len(contra_qs)} queries → {len(contra_hits)} hits."
        ),
    }
