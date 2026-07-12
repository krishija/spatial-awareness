"""Structured hypothesis reports — object first, then human-readable render."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class EvidenceContribution:
    evidence_type: str
    source_id: str
    note: str
    summary: str
    delta: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HypothesisReport:
    """Strict structured object reused by CLI, MCP, and (later) frontend."""

    hypothesis: str
    cell_id: str | None
    niche: str | None
    gene: str | None
    cell_type: str | None
    confidence: float
    rationale: str
    evidence: list[EvidenceContribution] = field(default_factory=list)
    # Frontend-aligned optional payloads
    citation: dict[str, Any] | None = None
    perturbation: dict[str, Any] | None = None  # before/after/deltas like PerturbationResult
    gate_decision: str = "REPORT"
    research_question: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Alias fields that match frontend AiSuggestion / PerturbationResult shapes
        if self.gene:
            d["suggestion"] = {
                "gene": self.gene,
                "rationale": self.hypothesis,
                "citation": self.citation
                or {
                    "title": "See evidence list",
                    "source": "agent",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/",
                },
            }
        return d


def build_report(
    *,
    hypothesis: str,
    confidence: float,
    rationale: str,
    contributions: list[dict[str, Any]],
    cell_id: str | None = None,
    niche: str | None = None,
    gene: str | None = None,
    cell_type: str | None = None,
    citation: dict[str, Any] | None = None,
    perturbation: dict[str, Any] | None = None,
    gate_decision: str = "REPORT",
    research_question: str = "",
) -> HypothesisReport:
    evidence = [
        EvidenceContribution(
            evidence_type=c.get("evidence_type", "unknown"),
            source_id=c.get("source_id", ""),
            note=c.get("note", ""),
            summary=c.get("summary", ""),
            delta=float(c.get("delta", 0.0)),
        )
        for c in contributions
        if c.get("evidence_type") not in ("agreement", "conflict")
        or True  # keep agreement/conflict notes too — they're explainable
    ]
    return HypothesisReport(
        hypothesis=hypothesis,
        cell_id=cell_id,
        niche=niche,
        gene=gene,
        cell_type=cell_type,
        confidence=confidence,
        rationale=rationale,
        evidence=evidence,
        citation=citation,
        perturbation=perturbation,
        gate_decision=gate_decision,
        research_question=research_question,
    )


def render_markdown(report: HypothesisReport) -> str:
    """Human-readable layer derived from the structured object (never freeform-first)."""
    lines = [
        f"# Hypothesis report (confidence {report.confidence:.3f})",
        "",
        f"**Question:** {report.research_question or '(n/a)'}",
        "",
        f"**Claim:** {report.hypothesis}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Gene | `{report.gene or '—'}` |",
        f"| Cell | `{report.cell_id or '—'}` |",
        f"| Cell type | {report.cell_type or '—'} |",
        f"| Niche | {report.niche or '—'} |",
        f"| Gate | {report.gate_decision} |",
        "",
        "## Why this confidence",
        "",
        report.rationale,
        "",
        "## Evidence (ordered)",
        "",
    ]
    for i, e in enumerate(report.evidence, 1):
        sign = f"{e.delta:+.3f}" if e.delta else "0"
        lines.append(
            f"{i}. **{e.evidence_type}** (`{e.source_id}`, Δ{sign}): {e.summary}"
        )
        lines.append(f"   - {e.note}")
    if report.perturbation:
        lines.extend(
            [
                "",
                "## Predicted marker shift",
                "",
                f"- Gene KO: `{report.perturbation.get('gene', report.gene)}`",
            ]
        )
        deltas = report.perturbation.get("deltas") or {}
        if deltas:
            top = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
            for g, d in top:
                lines.append(f"- {g}: {d:+.2f}")
    if report.citation:
        lines.extend(
            [
                "",
                "## Supporting citation",
                "",
                f"- {report.citation.get('title')} — {report.citation.get('source')}",
                f"- {report.citation.get('url', '')}",
            ]
        )
    lines.append("")
    return "\n".join(lines)
