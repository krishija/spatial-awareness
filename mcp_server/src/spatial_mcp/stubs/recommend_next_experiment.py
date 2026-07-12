"""recommend_next_experiment + calibrate_simulation_trust.

Two candidate lanes:
  1. Open / GATHER_MORE-style findings from SQLite
  2. Graph BFS (1–2 hops) from sample genes → mechanistically related genes

Always checks find_measured_perturbation_evidence before proposing wet-lab work.
Simulation trust uses empirical agreement from the graph, not a hardcoded discount.
"""

from __future__ import annotations

from typing import Any

from spatial_mcp.agent.evidence import BASE_WEIGHT
from spatial_mcp.graph import all_edges, find_related, insert_edge
from spatial_mcp.memory import get_store
from spatial_mcp.stubs.find_measured_perturbation_evidence import (
    _normalize_cell,
    _normalize_mechanism,
    find_measured_perturbation_evidence,
    score_context_match,
)

# Minimum calibration pairs before trusting empirical rate over neutral default
MIN_CALIBRATION_PAIRS = 5
NEUTRAL_SIM_TRUST = 0.55
# Same bar as reanalyze preference: low-context LINCS/cancer-line hits can still
# surface from find_measured_perturbation_evidence, but must not move this rate.
MIN_CALIBRATION_CONTEXT_MATCH = 0.45

# Assay cost tiers (higher = more expensive → lower priority score)
COST_REANALYZE = 0.15
COST_CHEAP_ASSAY = 1.0
COST_EXPENSIVE_ASSAY = 3.0

# Genes commonly co-mentioned / compensatory with checkpoints (bootstrap relations
# only used when graph is sparse — still recorded as literature-style edges if inserted)
_COMPENSATORY_HINTS: dict[str, list[str]] = {
    "PDCD1": ["LAG3", "HAVCR2", "TIGIT", "CTLA4", "TOX"],
    "CTLA4": ["PDCD1", "ICOS", "CD28"],
    "TOX": ["TCF7", "PDCD1", "NR4A1", "BATF"],
    "LAG3": ["PDCD1", "HAVCR2"],
    "TCF7": ["TOX", "IL7R", "PDCD1"],
}


def calibrate_simulation_trust(
    *,
    min_pairs: int = MIN_CALIBRATION_PAIRS,
    min_context_match: float = MIN_CALIBRATION_CONTEXT_MATCH,
) -> dict[str, Any]:
    """Empirical agreement between simulation edges and measured/literature edges.

    Only pairs whose three-axis context_match_score is ≥ min_context_match enter
    the rate. A LINCS cancer-line hit can still be returned by
    find_measured_perturbation_evidence (with its low score labeled) but must not
    move this number — mismatched-context calibration is false confidence.

    Agreement = same direction token when comparable; disagreement lowers the
    rate and is counted, not averaged away.
    """
    edges = all_edges()
    sim_edges = [e for e in edges if e["source_type"] == "simulation"]
    real_edges = [e for e in edges if e["source_type"] in ("measured", "literature")]

    pairs: list[dict[str, Any]] = []
    skipped_low_context: list[dict[str, Any]] = []
    agreements = 0
    disagreements = 0

    real_by_subj: dict[str, list[dict[str, Any]]] = {}
    for e in real_edges:
        real_by_subj.setdefault(e["subject"], []).append(e)

    for se in sim_edges:
        candidates = real_by_subj.get(se["subject"]) or []
        if not candidates:
            continue

        scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for re in candidates:
            match = _pair_context_match(se, re)
            scored.append((float(match["score"]), re, match))

        # Prefer the best-matched real edge for this simulation
        scored.sort(key=lambda t: -t[0])
        best_score, re, match = scored[0]
        if best_score < min_context_match:
            skipped_low_context.append(
                {
                    "gene": se["subject"],
                    "simulation_edge_id": se["id"],
                    "real_edge_id": re["id"],
                    "real_source_type": re["source_type"],
                    "context_match_score": best_score,
                    "context_match_components": match["components"],
                    "reason": "below_min_context_match",
                }
            )
            continue

        agree = _direction_agrees(se, re)
        pairs.append(
            {
                "gene": se["subject"],
                "simulation_edge_id": se["id"],
                "real_edge_id": re["id"],
                "real_source_type": re["source_type"],
                "context_match_score": best_score,
                "context_match_components": match["components"],
                "agrees": agree,
            }
        )
        if agree:
            agreements += 1
        else:
            disagreements += 1

    n = len(pairs)
    if n == 0:
        skip_n = len(skipped_low_context)
        note = (
            f"No context-matched simulation↔measured/literature pairs "
            f"(min_context_match={min_context_match}"
            + (f"; skipped {skip_n} low-context candidate(s)" if skip_n else "")
            + ") — using neutral default."
        )
        return {
            "trust": NEUTRAL_SIM_TRUST,
            "n_pairs": 0,
            "n_agree": 0,
            "n_disagree": 0,
            "n_skipped_low_context": skip_n,
            "empirical_rate": None,
            "used_default": True,
            "min_pairs_required": min_pairs,
            "min_context_match": min_context_match,
            "note": note,
            "pairs": [],
            "skipped_low_context": skipped_low_context,
        }

    rate = agreements / n
    if n < min_pairs:
        # Shrink toward neutral
        blend = n / min_pairs
        trust = blend * rate + (1 - blend) * NEUTRAL_SIM_TRUST
        used_default = False
        note = (
            f"Only {n} context-matched calibration pairs (<{min_pairs}); blending "
            f"empirical rate {rate:.2f} toward neutral {NEUTRAL_SIM_TRUST}."
        )
    else:
        trust = rate
        used_default = False
        note = (
            f"Empirical agreement rate over {n} pairs with "
            f"context_match≥{min_context_match}."
        )

    return {
        "trust": round(trust, 3),
        "n_pairs": n,
        "n_agree": agreements,
        "n_disagree": disagreements,
        "n_skipped_low_context": len(skipped_low_context),
        "empirical_rate": round(rate, 3),
        "used_default": used_default,
        "min_pairs_required": min_pairs,
        "min_context_match": min_context_match,
        "note": note,
        "pairs": pairs,
        "skipped_low_context": skipped_low_context,
    }


def recommend_next_experiment(args: dict[str, Any]) -> dict[str, Any]:
    sample_id = args.get("sample_id")
    niche = args.get("niche")
    top_k = int(args.get("top_k") or 5)
    cell_type = args.get("cell_type") or "CD4_T"

    store = get_store()
    findings = store.query(sample_id=sample_id, niche=niche)

    cal = calibrate_simulation_trust()
    sim_trust = float(cal["trust"])

    candidates: list[dict[str, Any]] = []

    # Lane 1: open findings / genes already under investigation
    for f in findings:
        gene = (f.get("gene") or "").upper()
        if not gene:
            continue
        gap = _infer_missing_evidence(f)
        candidates.append(
            {
                "gene": gene,
                "origin": "open_finding",
                "finding_id": f.get("id"),
                "finding_summary": f.get("finding_summary"),
                "sample_id": f.get("sample_id"),
                "niche": f.get("niche"),
                "missing_evidence_type": gap,
                "graph_path": None,
            }
        )

    # Lane 2: graph-discovered related genes (1–2 hops)
    seed_genes = sorted(
        { (f.get("gene") or "").upper() for f in findings if f.get("gene") }
    )
    # Bootstrap sparse graphs with compensatory hints as literature-shaped edges
    # only for traversal discovery (idempotent merge via insert_edge)
    for g in seed_genes:
        for other in _COMPENSATORY_HINTS.get(g, []):
            try:
                insert_edge(
                    g,
                    "compensatory_or_pathway",
                    other,
                    source_type="literature",
                    source_id=f"hint:compensatory:{g}:{other}",
                    confidence=0.4,
                    cell_type_context=cell_type,
                    sample_context=sample_id,
                    metadata={"hint": True},
                )
            except Exception:  # noqa: BLE001
                pass

    seen_genes = {c["gene"] for c in candidates}
    for g in seed_genes:
        related = find_related(g, max_hops=2)
        for item in related["related"]:
            ent = item["entity"]
            # Skip non-gene-like tokens
            if not ent.isalpha() and not any(c.isdigit() for c in ent):
                if len(ent) < 3:
                    continue
            if ent in seen_genes or ent in seed_genes:
                continue
            # Only keep gene-like related entities that appear as gene subjects elsewhere
            # or look like Hugo symbols
            if len(ent) > 12:
                continue
            seen_genes.add(ent)
            path_edges = item.get("edges") or []
            candidates.append(
                {
                    "gene": ent,
                    "origin": "graph_traversal",
                    "finding_id": None,
                    "finding_summary": None,
                    "sample_id": sample_id,
                    "niche": niche,
                    "missing_evidence_type": "simulation",  # never simulated if graph-only
                    "graph_path": {
                        "via": item.get("via"),
                        "hops": item.get("hops"),
                        "relations": [e.get("relation") for e in path_edges],
                        "seed": g,
                    },
                }
            )

    if not candidates:
        return {
            "ok": True,
            "n": 0,
            "recommendations": [],
            "calibration": cal,
            "message": (
                "No candidate genes from findings or graph. "
                "Record findings or run search_literature first."
            ),
        }

    # Score each candidate; always check measured evidence first
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        gene = cand["gene"]
        measured = find_measured_perturbation_evidence(
            {
                "gene": gene,
                "cell_type": cell_type,
                "perturbation_type": "knockout",
            }
        )
        best_hit = None
        if measured.get("hits"):
            best_hit = max(
                measured["hits"],
                key=lambda h: float(h.get("context_match_score") or 0),
            )

        gap = cand["missing_evidence_type"]
        gap_weight = float(BASE_WEIGHT.get(gap, 0.15))

        # Load-bearing: how many other candidates share graph connectivity to this gene
        load_bearing = _load_bearing_bonus(gene, candidates)

        if best_hit and float(best_hit.get("context_match_score") or 0) >= 0.45:
            rec_type = "reanalyze_existing_data"
            cost = COST_REANALYZE
            context_match = best_hit.get("context_match_score")
            context_components = best_hit.get("context_match_components")
            sim_mult = 1.0  # not relying on simulation
            score = (gap_weight * 1.2 + load_bearing) / cost
            rationale = (
                f"Measured evidence exists ({best_hit.get('dataset')}) with "
                f"context_match={context_match} — reuse before new wet-lab."
            )
        elif gap == "simulation" and not _has_simulation_edge(gene):
            # Nothing measured well; simulation not attempted
            if measured.get("nothing_found"):
                rec_type = "await_simulation"
                cost = COST_CHEAP_ASSAY
                context_match = None
                context_components = None
                sim_mult = sim_trust
                score = (gap_weight * sim_mult + load_bearing) / cost
                rationale = (
                    "No well-matched measured dataset; simulation not yet run — "
                    f"await_simulation (calibrated sim trust={sim_trust})."
                )
            else:
                # Weak measured hits only
                rec_type = "run_new_wet_lab_assay"
                cost = COST_CHEAP_ASSAY
                context_match = (best_hit or {}).get("context_match_score")
                context_components = (best_hit or {}).get("context_match_components")
                sim_mult = sim_trust
                score = (gap_weight * 0.9 + load_bearing) / cost
                rationale = "Weak/partial measured hits — cheap new assay may resolve gap."
        else:
            rec_type = "run_new_wet_lab_assay"
            # Expensive if gap is literature-heavy and no measurement
            cost = (
                COST_EXPENSIVE_ASSAY
                if measured.get("nothing_found") and gap == "literature"
                else COST_CHEAP_ASSAY
            )
            context_match = (best_hit or {}).get("context_match_score")
            context_components = (best_hit or {}).get("context_match_components")
            sim_mult = sim_trust if gap == "simulation" else 1.0
            score = (gap_weight * sim_mult + load_bearing) / cost
            rationale = (
                f"Propose new assay to fill missing '{gap}' evidence "
                f"(sim_trust_mult={sim_mult})."
            )

        scored.append(
            {
                "gene": gene,
                "recommendation_type": rec_type,
                "score": round(score, 4),
                "score_breakdown": {
                    "missing_evidence_weight": gap_weight,
                    "missing_evidence_type": gap,
                    "simulation_trust_multiplier": sim_mult,
                    "load_bearing_bonus": round(load_bearing, 4),
                    "assay_cost_divisor": cost,
                    "formula": "(gap_weight * sim_mult + load_bearing) / cost",
                },
                "evidence_gap": gap,
                "origin": cand["origin"],
                "graph_path": cand.get("graph_path"),
                "finding_id": cand.get("finding_id"),
                "context_match_score": context_match,
                "context_match_components": context_components,
                "measured_evidence": {
                    "n_hits": measured.get("n_hits"),
                    "nothing_found": measured.get("nothing_found"),
                    "best_hit": best_hit,
                },
                "rationale": rationale,
                "sample_id": cand.get("sample_id"),
                "niche": cand.get("niche"),
            }
        )

    scored.sort(key=lambda x: -x["score"])
    top = scored[:top_k]

    return {
        "ok": True,
        "n": len(top),
        "n_candidates_considered": len(scored),
        "recommendations": top,
        "calibration": {
            "trust": cal["trust"],
            "n_pairs": cal["n_pairs"],
            "n_agree": cal["n_agree"],
            "n_disagree": cal["n_disagree"],
            "n_skipped_low_context": cal.get("n_skipped_low_context"),
            "empirical_rate": cal["empirical_rate"],
            "min_context_match": cal.get("min_context_match"),
            "note": cal["note"],
        },
    }


def _infer_missing_evidence(finding: dict[str, Any]) -> str:
    summary = (finding.get("finding_summary") or "").lower()
    if "simulat" in summary or "knockout" in summary or "ko " in summary:
        # Has simulation narrative — may still need literature or cohort
        if "literature" not in summary and "pubmed" not in summary:
            return "literature"
        return "cohort_prognostic"
    if "tcga" in summary or "survival" in summary or "hazard" in summary:
        return "simulation"
    return "simulation"


def _load_bearing_bonus(gene: str, candidates: list[dict[str, Any]]) -> float:
    """How many other open hypotheses this gene touches via shared graph neighborhood."""
    bonus = 0.0
    related = find_related(gene, max_hops=2)
    related_set = {r["entity"] for r in related["related"]} | {gene}
    for c in candidates:
        if c["gene"] == gene:
            continue
        if c["gene"] in related_set:
            bonus += 0.08
        # Graph-origin candidates that share seed path
        gp = c.get("graph_path") or {}
        if gene in (gp.get("via") or []):
            bonus += 0.05
    return min(0.4, bonus)


def _has_simulation_edge(gene: str) -> bool:
    from spatial_mcp.graph import edges_for

    return any(e["source_type"] == "simulation" for e in edges_for(gene))


def _pair_context_match(sim: dict[str, Any], real: dict[str, Any]) -> dict[str, Any]:
    """Three-axis match of measured/literature context vs the simulation setting.

    Wanted = simulation edge context (project default CD4 / human / crispr when
    missing). Observed = real edge cell/species/mechanism fields.
    """
    sm = sim.get("metadata") or {}
    rm = real.get("metadata") or {}

    wanted_cell = _normalize_cell(sim.get("cell_type_context") or "cd4")
    wanted_mech = _normalize_mechanism(
        str(sm.get("mechanism") or sm.get("perturbation_mechanism") or "crispr")
    )
    wanted = {
        "cell_type": wanted_cell,
        "species": "human",
        "perturbation_mechanism": wanted_mech,
    }

    observed_cell = (real.get("cell_type_context") or "unknown").lower()
    observed_species = str(
        rm.get("species") or rm.get("organism") or "human"
    ).lower()
    observed_mech = str(
        rm.get("mechanism")
        or rm.get("perturbation_mechanism")
        or "unknown"
    )

    return score_context_match(
        observed_cell=observed_cell,
        observed_species=observed_species,
        observed_mechanism=observed_mech,
        wanted=wanted,
    )


def _direction_agrees(sim: dict[str, Any], real: dict[str, Any]) -> bool:
    """Compare coarse direction tokens; disagreement returns False (not averaged)."""
    sm = sim.get("metadata") or {}
    rm = real.get("metadata") or {}
    sd = str(sm.get("direction") or sim.get("object") or "").lower()
    rd = str(rm.get("direction") or real.get("object") or "").lower()

    def _bucket(text: str) -> str | None:
        if any(k in text for k in ("up", "increase", "activate", "restore", "higher")):
            return "up"
        if any(k in text for k in ("down", "decrease", "inhibit", "suppress", "lower", "exhaust")):
            return "down"
        if "protect" in text:
            return "up"
        if "risk" in text:
            return "down"
        return None

    sb, rb = _bucket(sd), _bucket(rd)
    if sb is None or rb is None:
        # Same relation name counts as weak agreement
        return sim.get("relation") == real.get("relation")
    return sb == rb
