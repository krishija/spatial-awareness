"""Stopping / gating policy — independence + groundedness, not tool checklist.

Simulation is optional weak corroboration and can never be load-bearing.
REPORT requires posterior mass, ≥2 independent sources, ≥1 *external* grounded
source (measured / cohort / literature with non-zero gene-bound bits),
≥2 distinct grounded *modalities* (measured alone is not enough — need
literature and/or cohort as an independent check), no unresolved contradiction,
priors checked, and a locked hypothesis gene.
Priors and cell_context alone cannot open REPORT.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from spatial_mcp.agent.evidence import EvidenceScore

GateDecision = Literal["REPORT", "GATHER_MORE", "DISCARD"]

# Posterior P(H|E) floor for REPORT — same numeric band as before, now a probability.
REPORT_CONFIDENCE = 0.70
DISCARD_CONFIDENCE = 0.30
MIN_INDEPENDENT_SOURCES = 2
# Distinct evidence *kinds* that can carry a claim. Two measured hits from the
# same tool are one modality. REPORT needs a second check (lit and/or cohort).
GROUNDED_MODALITIES = ("literature", "measured", "cohort_prognostic")
MIN_GROUNDED_MODALITIES = 2


@dataclass
class GateResult:
    decision: GateDecision
    reason: str
    next_tool: str | None = None
    next_tool_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score_fields(evidence_score: EvidenceScore | dict[str, Any]) -> dict[str, Any]:
    if isinstance(evidence_score, dict):
        coverage = dict(evidence_score.get("coverage") or {})
        return {
            "confidence": float(evidence_score.get("confidence", 0.0)),
            "coverage": coverage,
            "has_conflict": bool(evidence_score.get("has_conflict", False)),
            "n_independent": int(
                evidence_score.get("n_independent_sources")
                or (2 if coverage.get("independent_ge_2") else 0)
            ),
            "grounded": bool(
                evidence_score.get("has_grounded_source")
                or coverage.get("grounded")
                or coverage.get("literature")
                or coverage.get("measured")
                or coverage.get("cohort_prognostic")
            ),
            "external_grounded": bool(
                coverage.get("external_grounded")
                or evidence_score.get("has_external_grounded_source")
            ),
            "surviving_alternatives": list(
                evidence_score.get("surviving_alternative_explanations") or []
            ),
            "red_team_done": bool(
                coverage.get("red_team")
                or evidence_score.get("red_team_complete")
            ),
            "symmetric_search_done": bool(
                evidence_score.get("symmetric_search_complete")
                or coverage.get("symmetric_search")
            ),
            "hypothesis_gene": coverage.get("hypothesis_gene"),
        }
    coverage = dict(evidence_score.coverage)
    return {
        "confidence": evidence_score.confidence,
        "coverage": coverage,
        "has_conflict": evidence_score.has_conflict,
        "n_independent": evidence_score.n_independent_sources,
        "grounded": evidence_score.has_grounded_source or bool(coverage.get("grounded")),
        "external_grounded": bool(coverage.get("external_grounded")),
        "surviving_alternatives": [],
        "red_team_done": bool(coverage.get("red_team")),
        "symmetric_search_done": bool(coverage.get("symmetric_search")),
        "hypothesis_gene": coverage.get("hypothesis_gene"),
    }


def _grounded_modalities(coverage: dict[str, Any]) -> list[str]:
    return [m for m in GROUNDED_MODALITIES if coverage.get(m)]


def _report_ready(f: dict[str, Any], called: set[str]) -> tuple[bool, str]:
    """Structural REPORT checklist (code, not LLM)."""
    if f["confidence"] < REPORT_CONFIDENCE:
        return False, f"posterior {f['confidence']:.3f} < {REPORT_CONFIDENCE}"
    if f["n_independent"] < MIN_INDEPENDENT_SOURCES:
        return (
            False,
            f"only {f['n_independent']} independent sources "
            f"(need ≥{MIN_INDEPENDENT_SOURCES})",
        )
    if not f["grounded"]:
        return (
            False,
            "no grounded source (need measured / cohort / literature — "
            "simulation alone cannot carry REPORT)",
        )
    # Memory reads + cell_context cannot open REPORT — need lit/measured/cohort
    # that actually contributed bits (gene-bound).
    if not f.get("external_grounded"):
        return (
            False,
            "no external grounded evidence with non-zero bits "
            "(need literature / measured / cohort for the hypothesis gene — "
            "priors and cell_context alone cannot open REPORT)",
        )
    modalities = _grounded_modalities(f["coverage"])
    if len(modalities) < MIN_GROUNDED_MODALITIES:
        return (
            False,
            f"only {len(modalities)} grounded modality(ies) {modalities or '[]'} "
            f"(need ≥{MIN_GROUNDED_MODALITIES} of {list(GROUNDED_MODALITIES)}; "
            "two measured hits are still one modality — gather literature or cohort)",
        )
    if f["has_conflict"]:
        return False, "unresolved contradiction between grounded sources"
    if "query_prior_findings" not in called and not f["coverage"].get("queried_priors"):
        return False, "priors not checked"
    gene = f.get("hypothesis_gene") or f["coverage"].get("hypothesis_gene")
    if not gene or gene == "UNSPECIFIED":
        return False, "hypothesis gene not locked — cannot REPORT without a bound gene"
    return True, "ok"


def decide_next_action(
    *,
    evidence_score: EvidenceScore | dict[str, Any],
    tools_called: list[str],
    max_iterations: int,
    iteration: int,
    force_prior_before_suggest: bool = True,
) -> GateResult:
    """Decide REPORT / GATHER_MORE / DISCARD.

    Hard constraints (code, not prompt):
    - Never REPORT below REPORT_CONFIDENCE posterior.
    - Never REPORT without ≥2 independent sources and ≥1 grounded source.
    - Simulation is never sufficient alone.
    - Enforce query_prior_findings before suggest_perturbations.
    - DISCARD when iterations exhausted and posterior still weak.
    """
    f = _score_fields(evidence_score)
    confidence = f["confidence"]
    coverage = f["coverage"]
    has_conflict = f["has_conflict"]
    called = set(tools_called)
    exhausted = iteration >= max_iterations

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

    ready, ready_why = _report_ready(f, called)
    if ready:
        # Workflow completeness (NOT an evidence bar): run virtual-cell once so the
        # trace shows scLDM deltas or ok:false. Simulation still cannot carry REPORT.
        if "simulate_perturbations" not in called and not exhausted:
            return GateResult(
                decision="GATHER_MORE",
                reason=(
                    "Evidence bar met, but canonical workflow still needs "
                    "simulate_perturbations once (non-load-bearing calibration check) "
                    "before REPORT."
                ),
                next_tool="simulate_perturbations",
                next_tool_reason=(
                    "Call scLDM on the committed gene + cell; note real deltas or "
                    "ok:false. Do not treat simulation as grounded evidence."
                ),
            )
        return GateResult(
            decision="REPORT",
            reason=(
                f"Posterior P(H|E)={confidence:.3f} ≥ {REPORT_CONFIDENCE}; "
                f"{f['n_independent']} independent sources; grounded evidence present; "
                f"priors checked; no unresolved conflict."
            ),
        )

    if has_conflict and not exhausted:
        if "query_prior_findings" not in called:
            return GateResult(
                decision="GATHER_MORE",
                reason=(
                    f"Grounded contradiction with posterior {confidence:.3f}; "
                    "check prior findings before discarding or reporting."
                ),
                next_tool="query_prior_findings",
                next_tool_reason="Priors may resolve whether this gene/niche was already ruled out.",
            )
        if confidence < REPORT_CONFIDENCE:
            return GateResult(
                decision="GATHER_MORE" if iteration < max_iterations - 1 else "DISCARD",
                reason=(
                    f"Unresolved contradiction; posterior {confidence:.3f} "
                    f"below report floor {REPORT_CONFIDENCE}."
                ),
                next_tool="search_literature"
                if "search_literature" not in called
                else "find_measured_perturbation_evidence",
                next_tool_reason="Seek grounded evidence to resolve the conflict."
                if iteration < max_iterations - 1
                else None,
            )

    if exhausted:
        if ready:
            return GateResult(
                decision="REPORT",
                reason=(
                    f"Iteration budget reached ({iteration}/{max_iterations}) but "
                    f"posterior and independence/groundedness criteria are met."
                ),
            )
        return GateResult(
            decision="DISCARD",
            reason=(
                f"Evidence exhausted after {iteration} iterations; "
                f"posterior {confidence:.3f}; not report-ready ({ready_why})."
            ),
        )

    next_tool, why = _pick_next_tool(coverage, called, confidence, f)
    if next_tool is None:
        if confidence < DISCARD_CONFIDENCE:
            return GateResult(
                decision="DISCARD",
                reason=(
                    f"No remaining useful tools and posterior {confidence:.3f} "
                    f"< discard floor {DISCARD_CONFIDENCE}."
                ),
            )
        if ready:
            return GateResult(
                decision="REPORT",
                reason=f"No gaps left; posterior {confidence:.3f} sufficient to report.",
            )
        return GateResult(
            decision="DISCARD",
            reason=(
                f"Tool options exhausted with posterior {confidence:.3f}; "
                f"not report-ready ({ready_why})."
            ),
        )

    return GateResult(
        decision="GATHER_MORE",
        reason=(
            f"Posterior {confidence:.3f}; not yet report-ready ({ready_why})."
        ),
        next_tool=next_tool,
        next_tool_reason=why,
    )


def _pick_next_tool(
    coverage: dict[str, bool],
    called: set[str],
    confidence: float,
    fields: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Deterministic gap-filling: priors → cells → suggest (lock gene) → lit → measured → cohort → sim."""
    if "query_prior_findings" not in called:
        return "query_prior_findings", "Check prior findings before proposing anything new."

    if not coverage.get("cell_context") and "list_candidate_cells" not in called:
        return "list_candidate_cells", "Need resolved cells/niche context."

    # Lock a gene via suggest before gene-bound evidence gathering.
    if not coverage.get("suggestion") and "suggest_perturbations" not in called:
        return (
            "suggest_perturbations",
            "Lock a candidate gene before gathering gene-bound evidence.",
        )

    # External grounded evidence is required for REPORT — not optional.
    if not coverage.get("external_grounded"):
        if "search_literature" not in called:
            return (
                "search_literature",
                "Need literature grounding for the locked gene (required for REPORT).",
            )
        if "find_measured_perturbation_evidence" not in called:
            return (
                "find_measured_perturbation_evidence",
                "Need measured perturbation evidence for the locked gene.",
            )
        if "differential_survival_analysis" not in called:
            return (
                "differential_survival_analysis",
                "Cohort association can supply external grounded evidence.",
            )

    if not coverage.get("literature") and "search_literature" not in called:
        return "search_literature", "Need literature grounding (symmetric search preferred)."

    if not coverage.get("measured") and "find_measured_perturbation_evidence" not in called:
        return (
            "find_measured_perturbation_evidence",
            "Check for real measured perturbation evidence before trusting simulation.",
        )

    # Measured-only is one modality — force a second check before REPORT.
    modalities = _grounded_modalities(coverage)
    if len(modalities) < MIN_GROUNDED_MODALITIES:
        if "search_literature" not in called:
            return (
                "search_literature",
                "Need a second grounded modality (literature) — measured alone cannot REPORT.",
            )
        if "differential_survival_analysis" not in called:
            return (
                "differential_survival_analysis",
                "Need a second grounded modality (cohort) — measured alone cannot REPORT.",
            )

    if (
        not coverage.get("cohort_prognostic")
        and "differential_survival_analysis" not in called
    ):
        return (
            "differential_survival_analysis",
            "Cohort association can add grounded prognostic evidence.",
        )

    # Simulation is optional corroboration only
    if (
        not coverage.get("simulation")
        and "simulate_perturbations" not in called
        and coverage.get("suggestion")
        and confidence < REPORT_CONFIDENCE
    ):
        return (
            "simulate_perturbations",
            "Optional weak corroboration from virtual-cell model (not load-bearing).",
        )

    if confidence < REPORT_CONFIDENCE and not fields.get("external_grounded"):
        if "search_literature" not in called:
            return "search_literature", "Still need external grounded literature."
        if "find_measured_perturbation_evidence" not in called:
            return (
                "find_measured_perturbation_evidence",
                "Still need external grounded measured evidence.",
            )
        return None, None

    if confidence < REPORT_CONFIDENCE:
        if "recommend_next_experiment" not in called:
            return (
                "recommend_next_experiment",
                "Posterior stuck — ask which experiment cheapest resolves the gap.",
            )
        return None, None

    return None, None
