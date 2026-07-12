"""Map raw MCP tool results into EvidenceItem objects for aggregation."""

from __future__ import annotations

from typing import Any

from spatial_mcp.agent.evidence import EvidenceItem


def evidence_from_tool_result(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    *,
    focus_gene: str | None = None,
) -> list[EvidenceItem]:
    """Extract evidence items from a single tool call result.

    Returns [] on hard errors so a failed call does not invent support.
    """
    if result.get("ok") is False and result.get("error"):
        return [
            EvidenceItem(
                evidence_type="suggestion",
                summary=f"Tool {tool_name} failed: {result.get('message') or result.get('error')}",
                source_id=f"{tool_name}:error",
                polarity="neutral",
                strength=0.0,
                metadata={"tool": tool_name, "error": True},
            )
        ]

    extractors = {
        "query_prior_findings": _from_priors,
        "list_candidate_cells": _from_cells,
        "map_spatial_to_single": _from_atlas,
        "search_literature": _from_literature,
        "suggest_perturbations": _from_suggestions,
        "simulate_perturbations": _from_simulation,
        "differential_survival_analysis": _from_cohort_prognostic,
        "record_finding": _from_record,
    }
    fn = extractors.get(tool_name)
    if not fn:
        return []
    return fn(arguments, result, focus_gene=focus_gene)


def _from_priors(
    arguments: dict[str, Any], result: dict[str, Any], **_: Any
) -> list[EvidenceItem]:
    findings = result.get("findings") or []
    items = [
        EvidenceItem(
            evidence_type="prior_finding",
            summary="Prior-findings query executed (anti-duplication check).",
            source_id="query_prior_findings",
            polarity="neutral",
            strength=0.5,
            metadata={"queried_priors": True, "n": len(findings)},
        )
    ]
    for f in findings[:3]:
        gene = (f.get("gene") or "").upper()
        items.append(
            EvidenceItem(
                evidence_type="prior_finding",
                summary=f.get("finding_summary") or "Prior finding",
                source_id=f.get("id") or "prior",
                polarity="supports",
                strength=0.7,
                metadata={"gene": gene, "niche": f.get("niche"), "queried_priors": True},
            )
        )
    return items


def _from_cells(
    arguments: dict[str, Any], result: dict[str, Any], **_: Any
) -> list[EvidenceItem]:
    cells = result.get("cells") or []
    if not cells:
        return [
            EvidenceItem(
                evidence_type="cell_context",
                summary="No candidate cells matched filters.",
                source_id="list_candidate_cells",
                polarity="contradicts",
                strength=0.6,
            )
        ]
    top = cells[0]
    return [
        EvidenceItem(
            evidence_type="cell_context",
            summary=(
                f"Resolved {len(cells)} cells; top={top.get('id')} "
                f"{top.get('cell_type')} in {top.get('niche')} "
                f"(exhaustion_score={top.get('exhaustion_score')})."
            ),
            source_id=top.get("id") or "cells",
            polarity="supports",
            strength=min(1.0, 0.5 + float(top.get("exhaustion_score") or 0) * 0.5),
            metadata={
                "cell_id": top.get("id"),
                "niche": top.get("niche"),
                "cell_type": top.get("cell_type"),
                "sample_id": result.get("sample_id") or arguments.get("sample_id"),
            },
        )
    ]


def _from_atlas(
    arguments: dict[str, Any], result: dict[str, Any], **_: Any
) -> list[EvidenceItem]:
    summary = result.get("summary") or {}
    mean_c = float(summary.get("mean_confidence") or 0)
    return [
        EvidenceItem(
            evidence_type="atlas_mapping",
            summary=(
                f"Mapped {result.get('n_mapped', 0)} cells via "
                f"{result.get('atlas_reference')}; mean_confidence={mean_c}."
            ),
            source_id=result.get("atlas_reference") or "atlas",
            polarity="supports" if mean_c >= 0.85 else "neutral",
            strength=min(1.0, mean_c),
            metadata={"sample_id": result.get("sample_id") or arguments.get("sample_id")},
        )
    ]


def _from_literature(
    arguments: dict[str, Any],
    result: dict[str, Any],
    *,
    focus_gene: str | None = None,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for i, c in enumerate(result.get("citations") or []):
        title = c.get("title") or "Untitled"
        score = float(c.get("score") or 1.0)
        # Optional conflict hook: titles containing "contradict" / "fails to"
        # mark contradicting literature (used by conflict demos / tests).
        lower = (title + " " + (c.get("relevance") or "")).lower()
        polarity = "contradicts" if any(
            k in lower for k in ("contradict", "fails to restore", "no benefit", "ineffective")
        ) else "supports"
        gene_hit = focus_gene and focus_gene.upper() in (
            title + " " + (c.get("relevance") or "")
        ).upper()
        items.append(
            EvidenceItem(
                evidence_type="literature",
                summary=f"{title} — {c.get('source')}",
                source_id=c.get("url") or f"lit-{i}",
                polarity=polarity,  # type: ignore[arg-type]
                strength=min(1.0, 0.5 + score * 0.15 + (0.2 if gene_hit else 0)),
                metadata={
                    "title": title,
                    "source": c.get("source"),
                    "url": c.get("url"),
                    "relevance": c.get("relevance"),
                },
            )
        )
    return items


def _from_suggestions(
    arguments: dict[str, Any],
    result: dict[str, Any],
    *,
    focus_gene: str | None = None,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for s in result.get("suggestions") or []:
        gene = (s.get("gene") or "").upper()
        strength = 0.9 if focus_gene and gene == focus_gene.upper() else 0.7
        cite = (s.get("citations") or [{}])[0]
        items.append(
            EvidenceItem(
                evidence_type="suggestion",
                summary=f"Suggested KO {gene}: {s.get('rationale')}",
                source_id=f"suggest:{gene}",
                polarity="supports",
                strength=strength,
                metadata={
                    "gene": gene,
                    "cell_id": result.get("cell_id") or arguments.get("cell_id"),
                    "niche": result.get("niche") or arguments.get("niche"),
                    "phenotype": result.get("phenotype") or arguments.get("phenotype"),
                    "citation": cite,
                },
            )
        )
    return items


def _from_simulation(
    arguments: dict[str, Any],
    result: dict[str, Any],
    *,
    focus_gene: str | None = None,
) -> list[EvidenceItem]:
    if result.get("ok") is False:
        return [
            EvidenceItem(
                evidence_type="simulation",
                summary=result.get("message") or "Simulation failed",
                source_id=f"sim:{arguments.get('gene')}",
                polarity="contradicts",
                strength=0.8,
                metadata={"error": result.get("error")},
            )
        ]
    deltas = result.get("deltas") or {}
    # "Supports reversion from exhaustion" if PDCD1/TOX down and TCF7/IL7R/GZMB up
    inhibitory_down = sum(
        1 for g in ("PDCD1", "TOX", "LAG3", "CTLA4") if float(deltas.get(g, 0)) < -0.3
    )
    effector_up = sum(
        1 for g in ("TCF7", "IL7R", "GZMB") if float(deltas.get(g, 0)) > 0.3
    )
    supports = inhibitory_down >= 1 and effector_up >= 1
    # Conflict demo: metadata flag or net effector drop
    if effector_up == 0 and inhibitory_down == 0:
        polarity = "neutral"
        strength = 0.3
    elif supports:
        polarity = "supports"
        strength = min(1.0, 0.55 + 0.1 * (inhibitory_down + effector_up))
    else:
        polarity = "contradicts"
        strength = 0.7

    gene = result.get("gene") or arguments.get("gene")
    summary = (
        f"Simulated {gene} KO on {result.get('cell_id')}: "
        f"inhibitory_down={inhibitory_down}, effector_up={effector_up}; "
        f"top deltas={dict(sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)[:4])}"
    )
    return [
        EvidenceItem(
            evidence_type="simulation",
            summary=summary,
            source_id=f"sim:{gene}:{result.get('cell_id')}",
            polarity=polarity,  # type: ignore[arg-type]
            strength=strength,
            metadata={
                "gene": gene,
                "cell_id": result.get("cell_id"),
                "niche": result.get("niche"),
                "cell_type": result.get("cell_type"),
                "before": result.get("before"),
                "after": result.get("after"),
                "deltas": deltas,
            },
        )
    ]


def _from_cohort_prognostic(
    arguments: dict[str, Any],
    result: dict[str, Any],
    *,
    focus_gene: str | None = None,
) -> list[EvidenceItem]:
    """Map TCGA differential survival output → cohort_prognostic evidence.

    Never framed as validation — metadata carries the bulk-aggregation caveat.
    """
    if result.get("ok") is False:
        return [
            EvidenceItem(
                evidence_type="cohort_prognostic",
                summary=result.get("message") or "Cohort survival analysis failed",
                source_id="differential_survival_analysis:error",
                polarity="neutral",
                strength=0.0,
                metadata={
                    "error": result.get("error"),
                    "interpretation_caveat": result.get("interpretation_caveat"),
                },
            )
        ]

    hr = result.get("hazard_ratio")
    direction = result.get("direction") or "null"
    genes = result.get("genes") or arguments.get("genes") or []
    gene_note = ",".join(genes[:6]) + ("…" if len(genes) > 6 else "")
    match = result.get("association_matches_expectation")
    if match is True:
        polarity: str = "supports"
    elif match is False:
        polarity = "contradicts"
    else:
        polarity = "neutral"

    p = result.get("p_value")
    summary = (
        f"TCGA {result.get('cancer_type')} bulk cohort association for [{gene_note}]: "
        f"HR={hr} (95% CI {result.get('hr_ci_low')}–{result.get('hr_ci_high')}), "
        f"p={p} (uncorrected), direction={direction}, "
        f"scoring={result.get('scoring_method')}, mode={result.get('mode')}. "
        f"Not cell-level validation."
    )
    strength = float(result.get("effect_strength") or 0.5)
    if focus_gene and focus_gene.upper() in {g.upper() for g in genes}:
        strength = min(1.0, strength + 0.05)

    return [
        EvidenceItem(
            evidence_type="cohort_prognostic",
            summary=summary,
            source_id=(
                f"tcga:{result.get('cancer_type')}:{result.get('backend') or result.get('mode')}"
            ),
            polarity=polarity,  # type: ignore[arg-type]
            strength=strength,
            metadata={
                "claim_type": "cohort_association",
                "hazard_ratio": hr,
                "hr_ci_low": result.get("hr_ci_low"),
                "hr_ci_high": result.get("hr_ci_high"),
                "p_value": p,
                "p_value_session_corrected": result.get("p_value_session_corrected"),
                "multiple_testing": result.get("multiple_testing"),
                "direction": direction,
                "scoring_method": result.get("scoring_method"),
                "covariates_included": result.get("covariates_included"),
                "covariates_skipped": result.get("covariates_skipped"),
                "mode": result.get("mode"),
                "backend": result.get("backend"),
                "n_patients": result.get("n_patients"),
                "interpretation_caveat": result.get("interpretation_caveat"),
                "genes": genes,
            },
        )
    ]


def _from_record(
    arguments: dict[str, Any], result: dict[str, Any], **_: Any
) -> list[EvidenceItem]:
    finding = result.get("finding") or {}
    return [
        EvidenceItem(
            evidence_type="prior_finding",
            summary=f"Recorded finding {finding.get('id')}: {finding.get('finding_summary')}",
            source_id=finding.get("id") or "record",
            polarity="neutral",
            strength=0.4,
            metadata={"queried_priors": True},
        )
    ]
