"""Stopping / gating policy — explicit thresholds, not LLM discretion alone."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from spatial_mcp.agent.evidence import EvidenceScore

GateDecision = Literal["REPORT", "GATHER_MORE", "DISCARD"]

# Hard thresholds — demo-bounded and explainable in one sentence each.
REPORT_CONFIDENCE = 0.70
DISCARD_CONFIDENCE = 0.30
# Minimum evidence types for a REPORT (in addition to confidence).
REQUIRED_FOR_REPORT = ("literature", "simulation")


@dataclass
class GateResult:
    decision: GateDecision
    reason: str
    next_tool: str | None = None
    next_tool_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_next_action(
    *,
    evidence_score: EvidenceScore | dict[str, Any],
    tools_called: list[str],
    max_iterations: int,
    iteration: int,
    force_prior_before_suggest: bool = True,
) -> GateResult:
    """Decide REPORT / GATHER_MORE / DISCARD from confidence + coverage.

    Hard constraints (code, not prompt):
    - Never REPORT below REPORT_CONFIDENCE.
    - Never REPORT without literature + simulation coverage.
    - Prefer GATHER_MORE that fills the largest coverage gap.
    - Enforce query_prior_findings before suggest_perturbations.
    - DISCARD when iterations exhausted and confidence still weak.
    """
    if isinstance(evidence_score, dict):
        confidence = float(evidence_score.get("confidence", 0.0))
        coverage = dict(evidence_score.get("coverage") or {})
        has_conflict = bool(evidence_score.get("has_conflict", False))
    else:
        confidence = evidence_score.confidence
        coverage = dict(evidence_score.coverage)
        has_conflict = evidence_score.has_conflict

    called = set(tools_called)
    exhausted = iteration >= max_iterations

    # Hard ordering constraint for the agent loop / K Pro wrappers
    if force_prior_before_suggest and "suggest_perturbations" in called:
        if "query_prior_findings" not in called:
            return GateResult(
                decision="GATHER_MORE",
                reason=(
                    "Hard rule: query_prior_findings must run before relying on "
                    "suggest_perturbations — priors were never checked."
                ),
                next_tool="query_prior_findings",
                next_tool_reason="Anti-duplication check required before knockout proposals.",
            )

    missing_required = [t for t in REQUIRED_FOR_REPORT if not coverage.get(t)]

    if (
        confidence >= REPORT_CONFIDENCE
        and not missing_required
        and not has_conflict
        and ("query_prior_findings" in called or coverage.get("queried_priors"))
    ):
        return GateResult(
            decision="REPORT",
            reason=(
                f"Confidence {confidence:.3f} ≥ {REPORT_CONFIDENCE}, "
                f"literature+simulation present, priors checked, no unresolved conflict."
            ),
        )

    # Conflict with both sides present: try one more clarifying gather if budget left
    if has_conflict and not exhausted:
        if "query_prior_findings" not in called:
            return GateResult(
                decision="GATHER_MORE",
                reason=(
                    f"Literature/simulation conflict with confidence {confidence:.3f}; "
                    "check prior findings before discarding or reporting."
                ),
                next_tool="query_prior_findings",
                next_tool_reason="Priors may resolve whether this gene/niche was already ruled out.",
            )
        if confidence < REPORT_CONFIDENCE:
            return GateResult(
                decision="GATHER_MORE" if iteration < max_iterations - 1 else "DISCARD",
                reason=(
                    f"Unresolved lit↔sim conflict; confidence {confidence:.3f} "
                    f"below report floor {REPORT_CONFIDENCE}."
                ),
                next_tool="search_literature" if "search_literature" in called else None,
                next_tool_reason="Seek additional literature to break the tie."
                if iteration < max_iterations - 1
                else None,
            )

    if exhausted:
        if confidence >= REPORT_CONFIDENCE and not missing_required:
            return GateResult(
                decision="REPORT",
                reason=(
                    f"Iteration budget reached ({iteration}/{max_iterations}) but "
                    f"confidence {confidence:.3f} and required coverage are met."
                ),
            )
        return GateResult(
            decision="DISCARD",
            reason=(
                f"Evidence exhausted after {iteration} iterations; "
                f"confidence {confidence:.3f} and/or coverage "
                f"(missing={missing_required or 'none'}) insufficient to report."
            ),
        )

    # Prefer filling gaps in a useful order
    next_tool, why = _pick_next_tool(coverage, called, confidence)
    if next_tool is None:
        if confidence < DISCARD_CONFIDENCE:
            return GateResult(
                decision="DISCARD",
                reason=(
                    f"No remaining useful tools and confidence {confidence:.3f} "
                    f"< discard floor {DISCARD_CONFIDENCE}."
                ),
            )
        if confidence >= REPORT_CONFIDENCE and not missing_required:
            return GateResult(
                decision="REPORT",
                reason=f"No gaps left; confidence {confidence:.3f} sufficient to report.",
            )
        return GateResult(
            decision="DISCARD",
            reason=(
                f"Tool options exhausted with confidence {confidence:.3f} "
                f"and missing coverage {missing_required}."
            ),
        )

    return GateResult(
        decision="GATHER_MORE",
        reason=(
            f"Confidence {confidence:.3f}; coverage gaps remain "
            f"(missing_required={missing_required or 'none'})."
        ),
        next_tool=next_tool,
        next_tool_reason=why,
    )


def _pick_next_tool(
    coverage: dict[str, bool],
    called: set[str],
    confidence: float,
) -> tuple[str | None, str | None]:
    """Deterministic gap-filling priority for GATHER_MORE."""
    order: list[tuple[str, str, str]] = [
        # (coverage_key or "", tool_name, reason)
        ("", "query_prior_findings", "Check prior findings before proposing anything new."),
        ("cell_context", "list_candidate_cells", "Need resolved cells/niche context."),
        ("atlas_mapping", "map_spatial_to_single", "Confirm spatial→atlas identity."),
        ("literature", "search_literature", "Need literature grounding for the hypothesis."),
        ("suggestion", "suggest_perturbations", "Need ranked knockout candidates."),
        ("simulation", "simulate_perturbations", "Need predicted marker deltas from virtual cell."),
    ]

    if "query_prior_findings" not in called:
        return "query_prior_findings", order[0][2]

    for cov_key, tool, reason in order[1:]:
        if tool in called:
            continue
        if cov_key and coverage.get(cov_key):
            continue
        # Don't suggest knockouts until priors checked (already ensured) and we have cells
        if tool == "suggest_perturbations" and not coverage.get("cell_context"):
            if "list_candidate_cells" not in called:
                return "list_candidate_cells", "Resolve candidate cells before suggesting knockouts."
        if tool == "simulate_perturbations" and not coverage.get("suggestion"):
            if "suggest_perturbations" not in called:
                continue  # wait until we have a gene candidate
        return tool, reason

    # If we have suggestions but no sim yet
    if coverage.get("suggestion") and not coverage.get("simulation"):
        if "simulate_perturbations" not in called:
            return "simulate_perturbations", "Simulate the top suggested gene knockout."

    if confidence < REPORT_CONFIDENCE and "search_literature" in called:
        # Allow a second sim or record — but prefer not looping forever
        return None, None

    return None, None
