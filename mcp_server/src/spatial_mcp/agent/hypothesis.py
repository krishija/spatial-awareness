"""Falsifiable wet-lab hypothesis — the referent of every confidence number.

Confidence means: P(H is true | evidence), where H is this concrete claim.
Without a named event, a decimal is a score, not a probability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Hypothesis:
    """Wet-lab-testable claim the evidence layer is scoring.

    Example referent:
      CRISPR knockout of gene G in cell type C from niche N produces a
      significant increase in effector-function markers in a primary human
      T-cell assay.
    """

    gene: str
    cell_type: str
    niche: str | None = None
    cell_id: str | None = None
    sample_id: str | None = None
    assay: str = "primary_human_t_cell_crispr_ko"
    effect_direction: str = "increase"
    effect_markers: list[str] = field(
        default_factory=lambda: ["TCF7", "IL7R", "GZMB"]
    )
    claim: str | None = None  # if None, rendered from fields

    def __post_init__(self) -> None:
        self.gene = (self.gene or "").strip().upper()
        self.cell_type = (self.cell_type or "CD4_T").strip()
        if self.niche:
            self.niche = str(self.niche).strip()
        if not self.claim:
            niche_bit = f" from niche {self.niche}" if self.niche else ""
            markers = "/".join(self.effect_markers[:4])
            self.claim = (
                f"CRISPR knockout of {self.gene} in {self.cell_type}{niche_bit} "
                f"produces a significant {self.effect_direction} in effector-function "
                f"markers ({markers}) in a primary human T-cell assay."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Hypothesis:
        return cls(
            gene=str(d.get("gene") or ""),
            cell_type=str(d.get("cell_type") or "CD4_T"),
            niche=d.get("niche"),
            cell_id=d.get("cell_id"),
            sample_id=d.get("sample_id"),
            assay=str(d.get("assay") or "primary_human_t_cell_crispr_ko"),
            effect_direction=str(d.get("effect_direction") or "increase"),
            effect_markers=list(d.get("effect_markers") or ["TCF7", "IL7R", "GZMB"]),
            claim=d.get("claim"),
        )

    @classmethod
    def from_focus(cls, focus: dict[str, Any]) -> Hypothesis:
        return cls(
            gene=str(focus.get("gene") or "UNSPECIFIED"),
            cell_type=str(focus.get("cell_type") or "CD4_T"),
            niche=focus.get("niche"),
            cell_id=focus.get("cell_id"),
            sample_id=focus.get("sample_id"),
        )
