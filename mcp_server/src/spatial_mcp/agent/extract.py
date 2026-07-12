"""Map raw MCP tool results into EvidenceItem objects for aggregation."""

from __future__ import annotations

from typing import Any

from spatial_mcp.agent.evidence import EvidenceItem
from spatial_mcp.agent.lit_clusters import cluster_literature_cards


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
    extractors = {
        "query_prior_findings": _from_priors,
        "list_candidate_cells": _from_cells,
        "map_spatial_to_single": _from_atlas,
        "search_literature": _from_literature,
        "suggest_perturbations": _from_suggestions,
        "simulate_perturbations": _from_simulation,
        "differential_survival_analysis": _from_cohort_prognostic,
        "find_measured_perturbation_evidence": _from_measured,
        "recommend_next_experiment": _from_recommend,
        "record_finding": _from_record,
    }
    fn = extractors.get(tool_name)
    if fn:
        return fn(arguments, result, focus_gene=focus_gene)

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
    return []


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
    """Map structured evidence_cards (preferred) or legacy citations → literature items."""
    arg_gene = (
        (arguments.get("gene") or focus_gene or "")
        or ((arguments.get("genes") or [None])[0] or "")
    )
    arg_gene = str(arg_gene).strip().upper() or None

    if result.get("ok") is False:
        return [
            EvidenceItem(
                evidence_type="literature",
                summary=result.get("message") or "Literature search failed",
                source_id="search_literature:error",
                polarity="neutral",
                strength=0.0,
                metadata={"error": result.get("error"), "gene": arg_gene},
            )
        ]

    items: list[EvidenceItem] = []
    cards = result.get("evidence_cards")
    if cards is None:
        # Legacy path
        cards = []
        for c in result.get("citations") or []:
            cards.append(
                {
                    "title": c.get("title"),
                    "source": c.get("source"),
                    "url": c.get("url"),
                    "claim": c.get("relevance"),
                    "stance": c.get("stance"),
                    "snippet": c.get("relevance"),
                }
            )

    rollup = result.get("rollup") or {}
    if result.get("under_studied"):
        items.append(
            EvidenceItem(
                evidence_type="literature",
                summary=(
                    "Literature search completed with zero hits after alias-expanded "
                    "sub-queries — claim may be under-studied."
                ),
                source_id="search_literature:under_studied",
                polarity="neutral",
                strength=0.3,
                metadata={"under_studied": True, "rollup": rollup},
            )
        )

    # Independence clustering before evidence items (W4)
    if cards:
        clustering = cluster_literature_cards(cards)
        result["_lit_independence"] = clustering
    else:
        clustering = {"summary": "0 papers → 0 independent experimental claims."}

    # One evidence item per independent cluster (primary card), not per paper
    emitted_clusters: set[str] = set()
    for i, c in enumerate(cards):
        cluster_id = c.get("lit_cluster_id") or f"litc-singleton-{i}"
        if cluster_id in emitted_clusters:
            continue
        emitted_clusters.add(cluster_id)

        title = c.get("title") or "Untitled"
        claim = c.get("claim") or c.get("snippet") or ""
        stance_raw = (c.get("stance") or "").lower()
        if stance_raw == "supports":
            polarity = "supports"
        elif stance_raw == "contradicts":
            polarity = "contradicts"
        elif stance_raw == "tangential":
            polarity = "neutral"
        else:
            lower = (title + " " + claim).lower()
            polarity = (
                "contradicts"
                if any(
                    k in lower
                    for k in ("contradict", "fails to restore", "no benefit", "ineffective")
                )
                else "supports"
            )

        strength = 0.55
        if c.get("metadata_confidence") == "high":
            strength += 0.15
        if c.get("extraction_ok"):
            strength += 0.1
        pub_types = [t.lower() for t in (c.get("publication_types") or [])]
        if any("meta-analysis" in t or "systematic review" in t for t in pub_types):
            strength += 0.1
        elif any("clinical trial" in t or "randomized" in t for t in pub_types):
            strength += 0.08
        elif any(t == "review" for t in pub_types):
            strength += 0.03
        gene_hit = focus_gene and focus_gene.upper() in (
            title + " " + (claim or "") + " " + " ".join(arguments.get("genes") or [])
        ).upper()
        if gene_hit:
            strength += 0.05
        strength = min(1.0, strength)

        n_in_cluster = sum(
            1 for x in cards if (x.get("lit_cluster_id") or "") == cluster_id
        )
        summary = f"{title} — {c.get('source')}"
        if claim:
            summary = f"{summary}: {claim}"
        summary = f"{summary} [{clustering.get('summary', '')} primary of cluster {cluster_id}, n={n_in_cluster}]"

        items.append(
            EvidenceItem(
                evidence_type="literature",
                summary=summary,
                source_id=c.get("pmid") and f"pmid:{c['pmid']}" or c.get("url") or f"lit-{i}",
                polarity=polarity,  # type: ignore[arg-type]
                strength=strength,
                metadata={
                    "gene": arg_gene,
                    "title": title,
                    "source": c.get("source"),
                    "url": c.get("url"),
                    "pmid": c.get("pmid"),
                    "year": c.get("year"),
                    "journal": c.get("journal"),
                    "publication_type": c.get("publication_type"),
                    "publication_types": c.get("publication_types"),
                    "claim": claim,
                    "stance": c.get("stance"),
                    "biological_context": c.get("biological_context"),
                    "extraction_note": c.get("extraction_note"),
                    "metadata_confidence": c.get("metadata_confidence"),
                    "rollup_narrative": rollup.get("narrative"),
                    "lit_cluster_id": cluster_id,
                    "independence_cluster": f"literature:{cluster_id}",
                    "lit_independence_summary": clustering.get("summary"),
                    "symmetric_search": result.get("symmetric_search_complete"),
                    "support_search_effort": result.get("support_search_effort"),
                    "contradiction_search_effort": result.get(
                        "contradiction_search_effort"
                    ),
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
    inhibitory_down = sum(
        1 for g in ("PDCD1", "TOX", "LAG3", "CTLA4") if float(deltas.get(g, 0)) < -0.3
    )
    effector_up = sum(
        1 for g in ("TCF7", "IL7R", "GZMB") if float(deltas.get(g, 0)) > 0.3
    )
    supports = inhibitory_down >= 1 and effector_up >= 1
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
    # Conditional trust → sim_trust_bits for the log-odds layer
    try:
        from spatial_mcp.agent.trust import simulation_trust

        trust = simulation_trust(
            str(gene or ""),
            cell_type_context=result.get("cell_type"),
            metadata={"deltas": deltas, "gene": gene},
        )
        sim_bits = float(trust["bits"])
        trust_meta = trust
    except Exception as exc:  # noqa: BLE001
        sim_bits = 0.16
        trust_meta = {"tier": "documented_prior", "error": str(exc), "bits": sim_bits}

    summary = (
        f"Simulated {gene} KO on {result.get('cell_id')}: "
        f"inhibitory_down={inhibitory_down}, effector_up={effector_up}; "
        f"trust_tier={trust_meta.get('tier')} bits={sim_bits}; "
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
                "sim_trust_bits": sim_bits,
                "lr_note": trust_meta.get("note"),
                "trust": trust_meta,
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
                "cancer_type": result.get("cancer_type"),
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


def _from_measured(
    arguments: dict[str, Any],
    result: dict[str, Any],
    *,
    focus_gene: str | None = None,
) -> list[EvidenceItem]:
    """Measured perturbation evidence — strongest grounded type when context matches."""
    gene = (result.get("gene") or arguments.get("gene") or focus_gene or "").upper()
    if result.get("ok") is False:
        return [
            EvidenceItem(
                evidence_type="measured",
                summary=result.get("message") or "Measured-evidence lookup failed",
                source_id="measured:error",
                polarity="neutral",
                strength=0.0,
                metadata={"error": result.get("error")},
            )
        ]
    if result.get("nothing_found"):
        return [
            EvidenceItem(
                evidence_type="measured",
                summary=(
                    result.get("message")
                    or f"No measured perturbation evidence for {gene} — "
                    "simulated predictions should be trusted less."
                ),
                source_id=f"measured:none:{gene}",
                polarity="neutral",
                strength=0.4,
                metadata={"nothing_found": True, "gene": gene},
            )
        ]

    items: list[EvidenceItem] = []
    for i, h in enumerate(result.get("hits") or []):
        score = float(h.get("context_match_score") or 0)
        comps = h.get("context_match_components") or {}
        # Low context match: still surface, but weak / near-zero diagnosticity
        strength = min(1.0, max(0.1, score))
        polarity: str = "supports" if score >= 0.45 else "neutral"
        # Training-corpus membership is categorically stronger when cell matches
        if h.get("source_type") == "training_corpus" and score >= 0.5:
            polarity = "supports"
            strength = min(1.0, 0.7 + 0.3 * score)
        items.append(
            EvidenceItem(
                evidence_type="measured",
                summary=(
                    f"Measured hit for {gene} via {h.get('dataset')}: "
                    f"context_match={score} (cell={comps.get('cell_type_match')}, "
                    f"species={comps.get('species_match')}, "
                    f"mechanism={comps.get('perturbation_mechanism_match')})"
                ),
                source_id=h.get("source_id") or h.get("accession") or f"measured:{gene}:{i}",
                polarity=polarity,  # type: ignore[arg-type]
                strength=strength,
                metadata={
                    "gene": gene,
                    "accession": h.get("accession"),
                    "dataset": h.get("dataset"),
                    "source_type": h.get("source_type"),
                    "context_match_score": score,
                    "context_match_components": comps,
                    "effect": h.get("effect"),
                    "independence_cluster": f"measured:{h.get('accession') or h.get('dataset') or i}",
                },
            )
        )
    return items


def _from_recommend(
    arguments: dict[str, Any],
    result: dict[str, Any],
    *,
    focus_gene: str | None = None,
) -> list[EvidenceItem]:
    """Recommend is a decision aid — neutral scaffolding, not diagnostic evidence."""
    if result.get("ok") is False:
        return []
    recs = result.get("recommendations") or []
    if not recs:
        return [
            EvidenceItem(
                evidence_type="suggestion",
                summary=result.get("message") or "No experiment recommendations.",
                source_id="recommend:empty",
                polarity="neutral",
                strength=0.2,
                metadata={"calibration": result.get("calibration")},
            )
        ]
    top = recs[0]
    return [
        EvidenceItem(
            evidence_type="suggestion",
            summary=(
                f"Next experiment: {top.get('recommendation_type')} for {top.get('gene')} "
                f"(score={top.get('score')}). {top.get('rationale')}"
            ),
            source_id=f"recommend:{top.get('gene')}",
            polarity="supports",
            strength=0.35,
            metadata={
                "gene": top.get("gene"),
                "recommendation_type": top.get("recommendation_type"),
                "calibration": result.get("calibration"),
                "graph_path": top.get("graph_path"),
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
