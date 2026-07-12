"""Bayesian log-odds evidence aggregation.

Confidence = P(H | evidence), where H is a falsifiable wet-lab claim
(see hypothesis.py). Accumulation is in log₂ odds (bits):

  logit₂ P(H | E)  =  logit₂ P(H)  +  Σᵢ log₂ LRᵢ

LRᵢ = P(Eᵢ | H) / P(Eᵢ | ¬H)

Evidence combines by independence, not by count (see independence.py).
Conflict penalties / duplicate discounts / agreement bonuses are deleted —
they emerge from signed log-LRs and independence clustering.

LR tiers (visible in every budget entry):
  - estimated: fitted from knowledge-graph agreement history
  - documented_prior: reasoned default with comment (below)
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from spatial_mcp.agent.hypothesis import Hypothesis
from spatial_mcp.agent.independence import (
    GROUNDED_TYPES,
    cluster_items,
    count_independent_sources,
    gene_matches_hypothesis,
    has_external_grounded_source,
    has_grounded_source,
    independence_key,
    is_self_citation_prior,
    summarize_clusters,
)

EvidenceType = Literal[
    "literature",
    "simulation",
    "cohort_prognostic",
    "measured",
    "prior_finding",
    "cell_context",
    "atlas_mapping",
    "suggestion",
    "red_team",
]

# ---------------------------------------------------------------------------
# Documented LR priors (bits = log₂ LR at strength=1.0, polarity=supports)
#
# Reasoning:
# - measured (~2.0): a well context-matched wet-lab signature is strong
#   diagnostic evidence for the same gene/mechanism.
# - literature (~1.0): one independent experimental claim with clean stance ≈
#   one bit — "twice as likely under H than ¬H".
# - cohort_prognostic (~1.0): significant covariate-adjusted Cox HR predicts
#   bulk outcome; ecological inference limits diagnosticity for cell mechanism,
#   so capped near one bit despite population size.
# - simulation (~0.16): if sim agrees with truth ~58% when H and ~52% when ¬H,
#   LR ≈ 1.115 → log₂ ≈ 0.16 bits — a sixth of a coin flip. Allowed to go to 0
#   via conditional trust (trust.py).
# - cell_context / atlas / suggestion / prior: weak scaffolding, not load-bearing.
# ---------------------------------------------------------------------------
DOCUMENTED_LR_BITS: dict[str, float] = {
    "measured": 2.0,
    "literature": 1.0,
    "cohort_prognostic": 1.0,
    "simulation": 0.16,
    "cell_context": 0.30,
    "atlas_mapping": 0.20,
    "suggestion": 0.10,
    "prior_finding": 0.20,
    "red_team": 0.80,  # steelman objection that unrebutted subtracts
}

# Skeptical prior: P(H)=0.20 → logit₂ = log₂(0.2/0.8) = log₂(0.25) = -2.0 bits.
# A wet-lab KO claim in a specific niche starts unlikely until evidence accumulates.
PRIOR_PROB = 0.20
PRIOR_LOG_ODDS_BITS = math.log2(PRIOR_PROB / (1.0 - PRIOR_PROB))

# Back-compat for recommend_next_experiment gap weights (relative importance, not LRs).
# Derived from documented bits, normalized so literature≈0.22 historically.
BASE_WEIGHT: dict[str, float] = {
    k: round(v / DOCUMENTED_LR_BITS["literature"] * 0.22, 3)
    for k, v in DOCUMENTED_LR_BITS.items()
}


@dataclass
class EvidenceItem:
    """One piece of evidence about a candidate hypothesis."""

    evidence_type: EvidenceType
    summary: str
    source_id: str
    polarity: Literal["supports", "contradicts", "neutral"] = "supports"
    strength: float = 1.0  # 0–1 within-type quality
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceItem:
        return cls(
            evidence_type=d["evidence_type"],
            summary=d["summary"],
            source_id=d["source_id"],
            polarity=d.get("polarity", "supports"),
            strength=float(d.get("strength", 1.0)),
            metadata=d.get("metadata") or {},
        )


@dataclass
class EvidenceScore:
    """Posterior belief about H plus an orderable evidence budget (waterfall)."""

    confidence: float  # = P(H | E) — the probability, not a weighted score
    rationale: str
    contributions: list[dict[str, Any]]  # budget entries (bits), renderable as waterfall
    coverage: dict[str, bool]
    has_conflict: bool
    # Epistemics extras (additive; old callers ignore)
    prior_log_odds_bits: float = PRIOR_LOG_ODDS_BITS
    posterior_log_odds_bits: float = PRIOR_LOG_ODDS_BITS
    evidence_budget: list[dict[str, Any]] = field(default_factory=list)
    n_independent_sources: int = 0
    has_grounded_source: bool = False
    independence_summary: dict[str, Any] = field(default_factory=dict)
    hypothesis: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _sigmoid_bits(log_odds_bits: float) -> float:
    """P = 1 / (1 + 2^(-logit₂))."""
    # Numerically stable
    if log_odds_bits >= 30:
        return 1.0
    if log_odds_bits <= -30:
        return 0.0
    return 1.0 / (1.0 + 2.0 ** (-log_odds_bits))


def base_lr_bits(evidence_type: str, metadata: dict[str, Any] | None = None) -> tuple[float, str, str]:
    """Return (bits, tier, note) for a supporting item at strength=1.

    Tier is 'estimated' when trust/graph supplied an LR; else 'documented_prior'.
    """
    md = metadata or {}
    if md.get("lr_bits") is not None:
        return (
            float(md["lr_bits"]),
            "estimated",
            md.get("lr_note") or "LR bits supplied on evidence item metadata.",
        )
    if evidence_type == "simulation" and md.get("sim_trust_bits") is not None:
        return (
            float(md["sim_trust_bits"]),
            "estimated",
            md.get("lr_note")
            or "Simulation LR from conditional trust(gene, context, effect_size).",
        )
    bits = float(DOCUMENTED_LR_BITS.get(evidence_type, 0.1))
    notes = {
        "measured": (
            "Documented prior ≈2 bits: well context-matched measured perturbation."
        ),
        "literature": (
            "Documented prior ≈1 bit: one independent experimental claim with stance."
        ),
        "cohort_prognostic": (
            "Documented prior ≈1 bit: significant Cox HR (bulk association, not mechanism)."
        ),
        "simulation": (
            "Documented prior ≈0.16 bits: LR≈1.115 if sim is barely better than chance "
            "(~58% vs ~52%). May fall to 0 via conditional trust."
        ),
        "cell_context": "Documented prior ≈0.3 bits: relevant cells exist — weak for H.",
        "atlas_mapping": "Documented prior ≈0.2 bits: atlas identity — weak for H.",
        "suggestion": "Documented prior ≈0.1 bits: a proposal is not evidence.",
        "prior_finding": "Documented prior ≈0.2 bits: prior session note.",
        "red_team": "Documented prior ≈0.8 bits: unrebutted steelman objection.",
    }
    return bits, "documented_prior", notes.get(evidence_type, "Default documented prior.")


def item_log_lr_bits(item: EvidenceItem) -> tuple[float, str, str]:
    """Signed log₂ LR for one item before independence collapse."""
    if item.polarity == "neutral":
        return 0.0, "documented_prior", "Neutral polarity → LR=1 → 0 bits."
    base, tier, note = base_lr_bits(item.evidence_type, item.metadata)
    strength = _clamp(float(item.strength))
    signed = base * strength
    if item.polarity == "contradicts":
        signed = -signed
        note = f"Contradicts → negative log-LR. {note}"
    return signed, tier, note


def aggregate_evidence(
    items: list[EvidenceItem] | list[dict[str, Any]],
    *,
    hypothesis: Hypothesis | dict[str, Any] | None = None,
    prior_log_odds_bits: float = PRIOR_LOG_ODDS_BITS,
) -> EvidenceScore:
    """Accumulate evidence in log-odds (bits) under independence clustering.

    Within each independence cluster, only the strongest |bits| item contributes;
    others are recorded at 0 bits as redundant. Evidence combines by independence,
    not by count.
    """
    parsed: list[EvidenceItem] = [
        i if isinstance(i, EvidenceItem) else EvidenceItem.from_dict(i) for i in items
    ]

    hyp_dict: dict[str, Any] | None = None
    hyp_gene: str | None = None
    hyp_claim: str | None = None
    if hypothesis is not None:
        if isinstance(hypothesis, Hypothesis):
            hyp_dict = hypothesis.to_dict()
        else:
            hyp_dict = Hypothesis.from_dict(hypothesis).to_dict()
        hyp_gene = (hyp_dict.get("gene") or "").strip().upper() or None
        if hyp_gene == "UNSPECIFIED":
            hyp_gene = None
        hyp_claim = hyp_dict.get("claim")

    # Per-item raw LRs — gene-mismatched and self-citation priors contribute 0 bits
    raw: list[tuple[EvidenceItem, float, str, str]] = []
    for it in parsed:
        bits, tier, note = item_log_lr_bits(it)
        if hyp_gene and not gene_matches_hypothesis(it, hyp_gene):
            bits = 0.0
            note = (
                f"Gene mismatch: item gene ≠ hypothesis gene {hyp_gene} "
                f"— contributes 0 bits (evidence must bind to H)."
            )
            tier = "gene_binding"
        elif is_self_citation_prior(it, hyp_gene=hyp_gene, hyp_claim=hyp_claim):
            bits = 0.0
            note = (
                "Self-citation prior (same hypothesis already recorded) "
                "— contributes 0 bits (independence: memory ≠ corroboration)."
            )
            tier = "self_citation"
        raw.append((it, bits, tier, note))

    clusters = cluster_items(parsed)
    # Map source_id → contributing bits after independence collapse
    contrib_bits: dict[str, float] = {}
    budget: list[dict[str, Any]] = []
    raw_by_sid = {it.source_id: (it, b, t, n) for it, b, t, n in raw}

    # Prior entry
    budget.append(
        {
            "role": "prior",
            "evidence_type": "prior",
            "source_id": "prior",
            "bits": round(prior_log_odds_bits, 4),
            "signed_bits": round(prior_log_odds_bits, 4),
            "lr_tier": "documented_prior",
            "note": (
                f"Prior P(H)={PRIOR_PROB:.2f} → logit₂={prior_log_odds_bits:.3f} bits "
                "(skeptical wet-lab claim prior)."
            ),
            "summary": "Prior belief",
            "independence_key": "prior",
            "redundant": False,
        }
    )

    for key, members in sorted(clusters.items()):
        member_raw = []
        for m in members:
            row = raw_by_sid.get(m.source_id)
            if row is not None:
                member_raw.append(row)
        if not member_raw:
            continue
        # Strongest by absolute diagnosticity
        member_raw.sort(key=lambda x: abs(x[1]), reverse=True)
        _winner_it, winner_bits, winner_tier, _winner_note = member_raw[0]
        for idx, (it, bits, tier, note) in enumerate(member_raw):
            redundant = idx > 0
            applied = winner_bits if not redundant else 0.0
            if redundant:
                note = (
                    f"{it.evidence_type} from {it.source_id}: redundant within "
                    f"independence cluster '{key}' "
                    f"(evidence combines by independence, not by count). "
                    f"Raw would have been {bits:+.3f} bits."
                )
                tier = winner_tier
            else:
                note = f"{it.evidence_type} from {it.source_id}: {note} → {applied:+.3f} bits."
            contrib_bits[it.source_id] = applied
            budget.append(
                {
                    "role": "evidence",
                    "evidence_type": it.evidence_type,
                    "source_id": it.source_id,
                    "bits": round(applied, 4),
                    "signed_bits": round(applied, 4),
                    "raw_bits": round(bits, 4),
                    "lr_tier": tier,
                    "note": note,
                    "summary": it.summary,
                    "polarity": it.polarity,
                    "strength": it.strength,
                    "independence_key": key,
                    "redundant": redundant,
                }
            )

    posterior_bits = prior_log_odds_bits + sum(contrib_bits.values())
    confidence = round(_sigmoid_bits(posterior_bits), 3)

    # Conflict: grounded source contradicts while another grounded/sim supports (or vice versa)
    support_types = {
        i.evidence_type for i in parsed if i.polarity == "supports"
    }
    contra_types = {
        i.evidence_type for i in parsed if i.polarity == "contradicts"
    }
    grounded_support = bool(support_types & GROUNDED_TYPES)
    grounded_contra = bool(contra_types & GROUNDED_TYPES)
    has_conflict = (grounded_support and grounded_contra) or (
        ("simulation" in support_types and grounded_contra)
        or ("simulation" in contra_types and grounded_support)
    )

    n_indep = count_independent_sources(
        [i for i in parsed if i.polarity != "neutral"],
        bits_by_source_id=contrib_bits,
    )
    grounded = has_grounded_source(
        [i for i in parsed if gene_matches_hypothesis(i, hyp_gene)]
    )
    external_grounded = has_external_grounded_source(
        [i for i in parsed if gene_matches_hypothesis(i, hyp_gene)],
        bits_by_source_id=contrib_bits,
    )

    coverage = {
        # Failed lit calls must not count as a grounded modality
        "literature": any(
            i.evidence_type == "literature" and not i.metadata.get("error")
            for i in parsed
        ),
        "simulation": any(i.evidence_type == "simulation" for i in parsed),
        "cohort_prognostic": any(
            i.evidence_type == "cohort_prognostic" for i in parsed
        ),
        "measured": any(i.evidence_type == "measured" for i in parsed),
        "prior_finding": any(i.evidence_type == "prior_finding" for i in parsed),
        "cell_context": any(i.evidence_type == "cell_context" for i in parsed),
        "atlas_mapping": any(i.evidence_type == "atlas_mapping" for i in parsed),
        "suggestion": any(i.evidence_type == "suggestion" for i in parsed),
        "red_team": any(i.evidence_type == "red_team" for i in parsed),
        "queried_priors": any(
            i.evidence_type == "prior_finding"
            or i.metadata.get("queried_priors") is True
            for i in parsed
        ),
        "grounded": grounded,
        "external_grounded": external_grounded,
        "independent_ge_2": n_indep >= 2,
        "hypothesis_gene": hyp_gene,
    }

    # Contributions alias = budget evidence rows (waterfall-friendly for report/CLI)
    contributions = [
        {
            "evidence_type": e["evidence_type"],
            "source_id": e["source_id"],
            "delta": e["bits"],  # bits (signed); was weight delta — name kept for report compat
            "bits": e["bits"],
            "note": e["note"],
            "summary": e["summary"],
            "lr_tier": e.get("lr_tier"),
            "redundant": e.get("redundant", False),
            "independence_key": e.get("independence_key"),
        }
        for e in budget
        if e["role"] == "evidence"
    ]

    rationale_parts = [e["note"] for e in budget]
    rationale_parts.append(
        f"Posterior logit₂={posterior_bits:.3f} bits → P(H|E)={confidence:.3f} "
        f"({n_indep} independent sources; grounded={grounded})."
    )
    rationale = " ".join(rationale_parts)

    return EvidenceScore(
        confidence=confidence,
        rationale=rationale,
        contributions=contributions,
        coverage=coverage,
        has_conflict=has_conflict,
        prior_log_odds_bits=round(prior_log_odds_bits, 4),
        posterior_log_odds_bits=round(posterior_bits, 4),
        evidence_budget=budget,
        n_independent_sources=n_indep,
        has_grounded_source=grounded,
        independence_summary=summarize_clusters(parsed),
        hypothesis=hyp_dict,
    )


# Re-export for callers that import independence helpers via evidence
__all__ = [
    "EvidenceItem",
    "EvidenceScore",
    "EvidenceType",
    "BASE_WEIGHT",
    "DOCUMENTED_LR_BITS",
    "PRIOR_PROB",
    "PRIOR_LOG_ODDS_BITS",
    "aggregate_evidence",
    "item_log_lr_bits",
    "base_lr_bits",
    "GROUNDED_TYPES",
    "independence_key",
]
