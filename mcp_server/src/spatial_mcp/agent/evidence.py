"""Evidence aggregation and calibrated confidence scoring.

Explicit, inspectable weights — not an opaque model call. A judge can ask
"why this score?" and get one sentence per evidence item.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EvidenceType = Literal[
    "literature",
    "simulation",
    "cohort_prognostic",
    "prior_finding",
    "cell_context",
    "atlas_mapping",
    "suggestion",
]

# Base contribution of a single supporting item of each type (0–1 scale before caps).
# cohort_prognostic = population-level bulk survival association (TCGA) — more
# trustworthy than virtual-cell simulation for *prognostic relevance*, but not
# a substitute for mechanistic literature (aggregation caveat).
BASE_WEIGHT: dict[str, float] = {
    "literature": 0.22,
    "cohort_prognostic": 0.30,
    "simulation": 0.28,
    "prior_finding": 0.18,
    "cell_context": 0.12,
    "atlas_mapping": 0.10,
    "suggestion": 0.08,
}

# Multi-source agreement: lit + sim together is worth more than either alone.
AGREEMENT_BONUS = 0.15
# Same source type appearing twice adds diminishing returns.
DUPLICATE_DISCOUNT = 0.35
# Conflicting polarity between literature and simulation.
CONFLICT_PENALTY = 0.25


@dataclass
class EvidenceItem:
    """One piece of evidence about a candidate hypothesis."""

    evidence_type: EvidenceType
    summary: str
    source_id: str
    polarity: Literal["supports", "contradicts", "neutral"] = "supports"
    strength: float = 1.0  # 0–1 within-type quality (citation relevance, delta magnitude, …)
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
    confidence: float
    rationale: str
    contributions: list[dict[str, Any]]
    coverage: dict[str, bool]
    has_conflict: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def aggregate_evidence(items: list[EvidenceItem] | list[dict[str, Any]]) -> EvidenceScore:
    """Combine evidence into a single calibrated confidence + rationale.

    Rules (each maps to one explainable sentence):
    1. Each supporting item contributes BASE_WEIGHT[type] * strength.
    2. A second item of the same type is discounted (DUPLICATE_DISCOUNT).
    3. Independent sources agreeing (literature + simulation, both support)
       adds AGREEMENT_BONUS.
    4. Conflicting polarity between literature and simulation subtracts
       CONFLICT_PENALTY (does not silently average out).
    5. Contradicting items of any type subtract their weighted contribution.
    """
    parsed: list[EvidenceItem] = [
        i if isinstance(i, EvidenceItem) else EvidenceItem.from_dict(i) for i in items
    ]

    contributions: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    score = 0.0

    for item in parsed:
        et = item.evidence_type
        base = BASE_WEIGHT.get(et, 0.1)
        seen = type_counts.get(et, 0)
        type_counts[et] = seen + 1
        weight = base * _clamp(item.strength)
        if seen > 0:
            weight *= DUPLICATE_DISCOUNT
            note = (
                f"{et} from {item.source_id}: duplicate-type discount "
                f"({DUPLICATE_DISCOUNT:.0%}) → {weight:+.3f}."
            )
        else:
            note = f"{et} from {item.source_id}: base {base:.2f} × strength {item.strength:.2f} → {weight:+.3f}."

        if item.polarity == "contradicts":
            score -= weight
            note = (
                f"{et} from {item.source_id} CONTRADICTS hypothesis "
                f"(−{weight:.3f}): {item.summary}"
            )
            contributions.append(
                {
                    "evidence_type": et,
                    "source_id": item.source_id,
                    "delta": round(-weight, 4),
                    "note": note,
                    "summary": item.summary,
                }
            )
        elif item.polarity == "neutral":
            contributions.append(
                {
                    "evidence_type": et,
                    "source_id": item.source_id,
                    "delta": 0.0,
                    "note": f"{et} from {item.source_id}: neutral — no score change.",
                    "summary": item.summary,
                }
            )
        else:
            score += weight
            contributions.append(
                {
                    "evidence_type": et,
                    "source_id": item.source_id,
                    "delta": round(weight, 4),
                    "note": note,
                    "summary": item.summary,
                }
            )

    lit_support = any(
        i.evidence_type == "literature" and i.polarity == "supports" for i in parsed
    )
    lit_contra = any(
        i.evidence_type == "literature" and i.polarity == "contradicts" for i in parsed
    )
    sim_support = any(
        i.evidence_type == "simulation" and i.polarity == "supports" for i in parsed
    )
    sim_contra = any(
        i.evidence_type == "simulation" and i.polarity == "contradicts" for i in parsed
    )

    has_conflict = (lit_support and sim_contra) or (sim_support and lit_contra)

    if lit_support and sim_support and not has_conflict:
        score += AGREEMENT_BONUS
        contributions.append(
            {
                "evidence_type": "agreement",
                "source_id": "aggregator",
                "delta": AGREEMENT_BONUS,
                "note": (
                    f"Independent literature + simulation both support → "
                    f"+{AGREEMENT_BONUS:.2f} agreement bonus."
                ),
                "summary": "Cross-source agreement",
            }
        )

    if has_conflict:
        score -= CONFLICT_PENALTY
        contributions.append(
            {
                "evidence_type": "conflict",
                "source_id": "aggregator",
                "delta": -CONFLICT_PENALTY,
                "note": (
                    f"Literature and simulation disagree on direction → "
                    f"−{CONFLICT_PENALTY:.2f} conflict penalty (not averaged away)."
                ),
                "summary": "Cross-source conflict",
            }
        )

    confidence = round(_clamp(score), 3)
    coverage = {
        "literature": any(i.evidence_type == "literature" for i in parsed),
        "simulation": any(i.evidence_type == "simulation" for i in parsed),
        "cohort_prognostic": any(
            i.evidence_type == "cohort_prognostic" for i in parsed
        ),
        "prior_finding": any(i.evidence_type == "prior_finding" for i in parsed),
        "cell_context": any(i.evidence_type == "cell_context" for i in parsed),
        "atlas_mapping": any(i.evidence_type == "atlas_mapping" for i in parsed),
        "suggestion": any(i.evidence_type == "suggestion" for i in parsed),
        "queried_priors": any(
            i.evidence_type == "prior_finding"
            or i.metadata.get("queried_priors") is True
            for i in parsed
        ),
    }

    rationale_parts = [c["note"] for c in contributions]
    rationale_parts.append(f"Final calibrated confidence = {confidence:.3f}.")
    rationale = " ".join(rationale_parts)

    return EvidenceScore(
        confidence=confidence,
        rationale=rationale,
        contributions=contributions,
        coverage=coverage,
        has_conflict=has_conflict,
    )
