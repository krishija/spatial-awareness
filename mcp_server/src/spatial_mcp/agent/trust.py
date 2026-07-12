"""Conditional simulation trust: trust(gene, context, effect_size).

Not a scalar. The simulator is unevenly bad in predictable ways.
Fits a small logistic over calibration pairs from the edges table,
gated on context_match ≥ MIN_CALIBRATION_CONTEXT_MATCH.

Falls back: conditional model → global scalar calibrate_simulation_trust →
documented prior (0.16 bits). Trace always says which tier was used.
"""

from __future__ import annotations

import math
from typing import Any

from spatial_mcp.stubs.find_measured_perturbation_evidence import (
    SCLDM_TRAINING_GENES,
    STATE_TRAINING_GENES,
    _normalize_cell,
    _normalize_mechanism,
    score_context_match,
)
from spatial_mcp.stubs.recommend_next_experiment import (
    MIN_CALIBRATION_CONTEXT_MATCH,
    MIN_CALIBRATION_PAIRS,
    NEUTRAL_SIM_TRUST,
    calibrate_simulation_trust,
)

# Documented prior bits when no calibration data (matches evidence.DOCUMENTED_LR_BITS)
PRIOR_SIM_BITS = 0.16

# Minimum pairs to fit conditional logistic (stricter than global scalar)
MIN_CONDITIONAL_PAIRS = 8


def _effect_size(metadata: dict[str, Any] | None) -> float:
    md = metadata or {}
    if md.get("effect_size") is not None:
        return abs(float(md["effect_size"]))
    deltas = md.get("deltas") or {}
    if deltas:
        return max(abs(float(v)) for v in deltas.values())
    if md.get("delta") is not None:
        return abs(float(md["delta"]))
    return 0.5


def _features(
    gene: str,
    *,
    cell_type_context: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, float]:
    g = (gene or "").upper()
    md = metadata or {}
    in_train = 1.0 if (g in SCLDM_TRAINING_GENES or g in STATE_TRAINING_GENES) else 0.0
    eff = _effect_size(md)
    # Large effects above noise floor (~0.3 marker Δ) are more trustworthy
    large_effect = 1.0 if eff >= 0.3 else 0.0
    cell = (cell_type_context or md.get("cell_type") or "").lower()
    cd4_match = 1.0 if "cd4" in cell else (0.5 if "t" in cell else 0.0)
    # Master-regulator / checkpoint class heuristic
    master = {
        "TOX",
        "PDCD1",
        "CTLA4",
        "TCF7",
        "BATF",
        "PRDM1",
        "MYC",
        "STAT1",
        "STAT3",
    }
    is_master = 1.0 if g in master else 0.0
    return {
        "in_training_set": in_train,
        "large_effect": large_effect,
        "effect_size": min(2.0, eff),
        "cd4_match": cd4_match,
        "is_master_regulator": is_master,
        "bias": 1.0,
    }


def _pair_context_score(sim: dict[str, Any], real: dict[str, Any]) -> float:
    sm = sim.get("metadata") or {}
    rm = real.get("metadata") or {}
    wanted = {
        "cell_type": _normalize_cell(sim.get("cell_type_context") or "cd4"),
        "species": "human",
        "perturbation_mechanism": _normalize_mechanism(
            str(sm.get("mechanism") or "crispr")
        ),
    }
    match = score_context_match(
        observed_cell=(real.get("cell_type_context") or "unknown").lower(),
        observed_species=str(rm.get("species") or rm.get("organism") or "human").lower(),
        observed_mechanism=str(
            rm.get("mechanism") or rm.get("perturbation_mechanism") or "unknown"
        ),
        wanted=wanted,
    )
    return float(match["score"])


def _direction_agrees(sim: dict[str, Any], real: dict[str, Any]) -> bool:
    from spatial_mcp.stubs.recommend_next_experiment import _direction_agrees as _da

    return _da(sim, real)


def _harvest_calibration_rows() -> list[dict[str, Any]]:
    """Context-gated sim↔real pairs for conditional fitting."""
    from spatial_mcp.graph import all_edges

    edges = all_edges()
    sim_edges = [e for e in edges if e["source_type"] == "simulation"]
    real_edges = [e for e in edges if e["source_type"] in ("measured", "literature")]
    real_by_subj: dict[str, list[dict[str, Any]]] = {}
    for e in real_edges:
        real_by_subj.setdefault(e["subject"], []).append(e)

    rows: list[dict[str, Any]] = []
    for se in sim_edges:
        cands = real_by_subj.get(se["subject"]) or []
        if not cands:
            continue
        scored = [(_pair_context_score(se, re), re) for re in cands]
        scored.sort(key=lambda t: -t[0])
        best_score, re = scored[0]
        # CRITICAL: gate before counting — mismatched context must not train trust
        if best_score < MIN_CALIBRATION_CONTEXT_MATCH:
            continue
        feats = _features(
            se["subject"],
            cell_type_context=se.get("cell_type_context"),
            metadata=se.get("metadata"),
        )
        rows.append(
            {
                "gene": se["subject"],
                "y": 1.0 if _direction_agrees(se, re) else 0.0,
                "features": feats,
                "context_match_score": best_score,
            }
        )
    return rows


def _fit_logistic(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, float], str] | None:
    """Tiny batch logistic via gradient ascent. Returns weights or None if too sparse."""
    if len(rows) < MIN_CONDITIONAL_PAIRS:
        return None
    keys = list(rows[0]["features"].keys())
    w = {k: 0.0 for k in keys}
    lr = 0.3
    for _ in range(80):
        grad = {k: 0.0 for k in keys}
        for row in rows:
            x = row["features"]
            z = sum(w[k] * x[k] for k in keys)
            p = 1.0 / (1.0 + math.exp(-z))
            err = row["y"] - p
            for k in keys:
                grad[k] += err * x[k]
        for k in keys:
            w[k] += lr * grad[k] / len(rows)
    return w, (
        f"Conditional logistic fit on {len(rows)} context-matched calibration pairs "
        f"(min_context_match={MIN_CALIBRATION_CONTEXT_MATCH})."
    )


def _predict_prob(weights: dict[str, float], feats: dict[str, float]) -> float:
    z = sum(weights.get(k, 0.0) * feats.get(k, 0.0) for k in feats)
    return 1.0 / (1.0 + math.exp(-z))


def _trust_to_bits(trust: float) -> float:
    """Map agreement-rate-like trust ∈ (0,1) to log₂ LR bits.

    Interpret trust as P(correct | features). Under a simple model where
    false-positive rate ≈ 0.5 (coin-flip under ¬H), LR ≈ trust / 0.5.
    Clamp trust away from 0/1.
    """
    t = min(0.95, max(0.05, float(trust)))
    lr = t / 0.5
    return math.log2(lr)


def simulation_trust(
    gene: str,
    *,
    cell_type_context: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """trust(gene, context, effect_size) → bits + tier for the evidence layer."""
    feats = _features(gene, cell_type_context=cell_type_context, metadata=metadata)
    rows = _harvest_calibration_rows()
    fitted = _fit_logistic(rows)

    if fitted is not None:
        weights, note = fitted
        prob = _predict_prob(weights, feats)
        bits = _trust_to_bits(prob)
        return {
            "trust": round(prob, 3),
            "bits": round(bits, 4),
            "tier": "conditional",
            "features": feats,
            "n_calibration_rows": len(rows),
            "note": note,
            "weights": {k: round(v, 3) for k, v in weights.items()},
        }

    # Global scalar from calibrate_simulation_trust (already context-gated)
    cal = calibrate_simulation_trust()
    if cal["n_pairs"] >= 1 and not cal.get("used_default"):
        trust = float(cal["trust"])
        bits = _trust_to_bits(trust)
        return {
            "trust": trust,
            "bits": round(bits, 4),
            "tier": "global_scalar",
            "features": feats,
            "n_calibration_rows": cal["n_pairs"],
            "note": (
                f"Conditional fit needs ≥{MIN_CONDITIONAL_PAIRS} pairs "
                f"(have {len(rows)}); using global calibrated scalar. {cal['note']}"
            ),
            "calibration": {
                "n_pairs": cal["n_pairs"],
                "empirical_rate": cal["empirical_rate"],
                "n_skipped_low_context": cal.get("n_skipped_low_context"),
            },
        }

    # Documented prior
    return {
        "trust": NEUTRAL_SIM_TRUST,
        "bits": PRIOR_SIM_BITS,
        "tier": "documented_prior",
        "features": feats,
        "n_calibration_rows": len(rows),
        "note": (
            f"No usable calibration pairs (conditional={len(rows)}, "
            f"global min={MIN_CALIBRATION_PAIRS}); using documented prior "
            f"{PRIOR_SIM_BITS} bits (LR≈1.115)."
        ),
    }
