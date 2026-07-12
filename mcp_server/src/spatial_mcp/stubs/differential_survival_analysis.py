"""differential_survival_analysis — TCGA bulk cohort association (not validation).

Takes a gene signature + matched cancer type, scores patients (ssGSEA when
available, else z-score mean), splits high vs low, and fits a multivariable
Cox PH model. Returns HR/CI/p with an explicit bulk-aggregation caveat.

Multiple testing: this tool returns *uncorrected* p-values. Session-level FDR
correction belongs in the orchestrator / evidence layer across all calls in a
research session — not inside a single tool invocation. See
``multiple_testing`` in the response.
"""

from __future__ import annotations

from typing import Any

from spatial_mcp.fixtures.tcga_cohort import (
    SUPPORTED_CANCER_TYPES,
    normalize_cancer_type,
)
from spatial_mcp.stubs.survival_math import (
    cox_ph,
    median_split,
    standardize_columns,
    tertile_split,
    try_ssgsea,
    zscore_signature,
)
from spatial_mcp.stubs.tcga_cohort_loader import load_cohort

INTERPRETATION_CAVEAT = (
    "This is a bulk RNA-seq cohort association (one aggregate expression value "
    "per patient across all cell types in the tumor). It does not confirm the "
    "single-cell or spatial mechanism that motivated the signature — only "
    "whether the signature, treated as a bulk-measurable marker, predicts "
    "outcome in an independent population."
)

# Mode / backend naming aligned with simulate_perturbations' ``backend`` field.
MODE_TO_BACKEND = {
    "live_local": "tcga_live_local",
    "live_cbioportal": "tcga_live_cbioportal",
    "fixture": "tcga_fixture",
}


def differential_survival_analysis(args: dict[str, Any]) -> dict[str, Any]:
    genes_raw = args.get("genes") or args.get("signature") or []
    weights_in = args.get("weights") or {}
    cancer_raw = args.get("cancer_type") or ""
    outcome = (args.get("outcome") or "OS").upper()
    expected = (args.get("expected_direction") or "protective").lower()
    prefer_ssgsea = bool(args.get("prefer_ssgsea", True))
    force_fixture = bool(args.get("force_fixture", False))
    split_method = (args.get("split") or "auto").lower()

    genes = [str(g).upper() for g in genes_raw]
    weights = {str(k).upper(): float(v) for k, v in dict(weights_in).items()}

    if not genes:
        return _error(
            "missing_signature",
            "Provide a non-empty gene signature (genes).",
            cancer_type=cancer_raw,
        )

    canonical = normalize_cancer_type(cancer_raw)
    if canonical is None:
        return _error(
            "unsupported_cancer_type",
            (
                f"Cancer type '{cancer_raw}' does not match an available TCGA cohort. "
                f"Supported: {SUPPORTED_CANCER_TYPES} "
                f"(aliases: CRC/COAD/COADREAD, NSCLC/LUAD, MEL/SKCM). "
                "Refusing to run against a mismatched cohort."
            ),
            cancer_type=cancer_raw,
            genes=genes,
        )

    if outcome not in ("OS", "OVERALL_SURVIVAL", "OVERALL"):
        return _error(
            "unsupported_outcome",
            f"Outcome '{outcome}' not supported; only overall survival (OS) is implemented.",
            cancer_type=canonical,
            genes=genes,
        )

    patients, mode, load_notes = load_cohort(
        canonical, genes, force_fixture=force_fixture
    )
    if len(patients) < 10:
        return _error(
            "insufficient_samples",
            f"Fewer than 10 patients with usable data (n={len(patients)}).",
            cancer_type=canonical,
            genes=genes,
            mode=mode,
            backend=MODE_TO_BACKEND[mode],
        )

    expr = {p["patient_id"]: dict(p.get("expression") or {}) for p in patients}
    # Drop patients with no signature genes measured
    usable_ids = [
        pid for pid, e in expr.items() if any(g in e for g in genes)
    ]
    if len(usable_ids) < 10:
        return _error(
            "insufficient_expression_overlap",
            "Too few patients express any signature genes.",
            cancer_type=canonical,
            genes=genes,
            mode=mode,
            backend=MODE_TO_BACKEND[mode],
        )
    expr = {pid: expr[pid] for pid in usable_ids}
    patients = [p for p in patients if p["patient_id"] in usable_ids]

    scoring_method = "zscore_mean"
    scores: dict[str, float] | None = None
    if prefer_ssgsea:
        scores = try_ssgsea(expr, genes)
        if scores is not None:
            scoring_method = "ssgsea"
    if scores is None:
        scores = zscore_signature(expr, genes, weights)

    # Split
    group: dict[str, int]
    split_used = "median"
    if split_method == "tertile" or (split_method == "auto" and len(scores) >= 30):
        t = tertile_split(scores)
        if t is not None and split_method in ("tertile", "auto"):
            # auto: prefer median for stability unless explicitly tertile
            if split_method == "tertile":
                group = t
                split_used = "tertile_high_vs_low"
                patients = [p for p in patients if p["patient_id"] in group]
                scores = {pid: scores[pid] for pid in group}
            else:
                group = median_split(scores)
        else:
            group = median_split(scores)
    else:
        group = median_split(scores)

    # Build Cox design: signature_high + available covariates
    covariate_names = ["signature_high"]
    covariates_included = ["signature_high"]
    covariates_skipped: list[dict[str, str]] = []

    time: list[float] = []
    event: list[int] = []
    rows: list[list[float]] = []
    for p in patients:
        pid = p["patient_id"]
        if pid not in group:
            continue
        row = [float(group[pid])]
        # age
        age = p.get("age")
        if age is None:
            covariates_skipped.append(
                {"covariate": "age", "reason": "missing for one or more patients — column omitted"}
            )
            # If any missing, we'll decide after loop — collect first
        row.append(float(age) if age is not None else float("nan"))
        stage = p.get("stage")
        row.append(float(stage) if stage is not None else float("nan"))
        purity = p.get("purity")
        row.append(float(purity) if purity is not None else float("nan"))
        immune = p.get("immune_infiltration")
        row.append(float(immune) if immune is not None else float("nan"))
        time.append(float(p["os_months"]))
        event.append(int(p["os_event"]))
        rows.append(row)

    # Drop covariate columns that are mostly missing; require ≥70% non-null
    col_defs = [
        ("signature_high", True),  # always keep
        ("age", False),
        ("stage", False),
        ("purity", False),
        ("immune_infiltration", False),
    ]
    keep_idx = [0]
    for j, (name, required) in enumerate(col_defs):
        if j == 0:
            continue
        vals = [r[j] for r in rows]
        n_ok = sum(1 for v in vals if v == v)  # not NaN
        if n_ok >= int(0.7 * len(rows)):
            keep_idx.append(j)
            covariates_included.append(name)
            # Impute remaining NaNs with column median of observed
            obs = sorted(v for v in vals if v == v)
            med = obs[len(obs) // 2] if obs else 0.0
            for r in rows:
                if r[j] != r[j]:
                    r[j] = med
        else:
            reason = {
                "age": "age missing for ≥30% of cohort patients",
                "stage": "pathologic stage missing for ≥30% of cohort patients",
                "purity": (
                    "tumor purity not available in this cohort extract "
                    "(no ABSOLUTE/CPE/PURITY attribute); omitted rather than proxied"
                ),
                "immune_infiltration": (
                    "published immune-infiltration / leukocyte-fraction scores not "
                    "found beside this cohort (set TCGA_DATA_ROOT immune JSON to include); "
                    "omitted so the model is not silently under-adjusted"
                ),
            }[name]
            covariates_skipped.append({"covariate": name, "reason": reason})

    # Deduplicate skip notes for age/stage if we never added them due to partial miss
    # (already handled)

    X = [[r[j] for j in keep_idx] for r in rows]
    X = standardize_columns(X)  # leaves binary signature_high alone

    try:
        fit = cox_ph(time, event, X)
    except Exception as exc:  # noqa: BLE001
        return _error(
            "cox_fit_failed",
            f"{type(exc).__name__}: {exc}",
            cancer_type=canonical,
            genes=genes,
            mode=mode,
            backend=MODE_TO_BACKEND[mode],
        )

    hr = float(fit["hr"][0])
    ci_lo, ci_hi = fit["hr_ci"][0]
    p_value = float(fit["p"][0])
    if hr < 1.0:
        direction = "protective"
    elif hr > 1.0:
        direction = "risk_associated"
    else:
        direction = "null"

    # Polarity vs caller expectation (for evidence layer)
    if expected in ("protective", "higher_signature_better_outcome"):
        association_matches_expectation = direction == "protective"
    elif expected in ("risk_associated", "risk", "higher_signature_worse_outcome"):
        association_matches_expectation = direction == "risk_associated"
    else:
        association_matches_expectation = None

    n = int(fit["n"])
    n_events = int(fit["n_events"])
    n_high = sum(1 for v in group.values() if v == 1)
    n_low = sum(1 for v in group.values() if v == 0)

    # Strength hint for evidence extract (effect size + precision)
    effect_strength = _effect_strength(hr, p_value, n_events)

    return {
        "ok": True,
        "tool": "differential_survival_analysis",
        "analysis_type": "differential_survival_analysis",
        "claim_type": "cohort_association",  # never "validation"
        "cancer_type": canonical,
        "cancer_type_input": cancer_raw,
        "outcome": "OS",
        "genes": genes,
        "weights": weights or None,
        "n_patients": n,
        "n_events": n_events,
        "n_high_signature": n_high,
        "n_low_signature": n_low,
        "split": split_used,
        "scoring_method": scoring_method,
        "hazard_ratio": round(hr, 4),
        "hr_ci_low": round(float(ci_lo), 4),
        "hr_ci_high": round(float(ci_hi), 4),
        "p_value": round(p_value, 6) if p_value == p_value else None,
        "p_value_session_corrected": None,
        "multiple_testing": {
            "status": "uncorrected",
            "method": None,
            "note": (
                "Returned p-value is uncorrected for multiple testing. "
                "Session-level FDR (e.g. Benjamini–Hochberg) must be applied in the "
                "orchestrator / evidence layer across all differential_survival_analysis "
                "calls in the research session — this tool does not correct in isolation."
            ),
        },
        "direction": direction,
        "expected_direction": expected,
        "association_matches_expectation": association_matches_expectation,
        "covariates_included": covariates_included,
        "covariates_skipped": covariates_skipped,
        "covariate_hrs": {
            covariates_included[i]: {
                "hr": round(float(fit["hr"][i]), 4),
                "hr_ci": [
                    round(float(fit["hr_ci"][i][0]), 4),
                    round(float(fit["hr_ci"][i][1]), 4),
                ],
                "p_value": round(float(fit["p"][i]), 6)
                if fit["p"][i] == fit["p"][i]
                else None,
            }
            for i in range(len(covariates_included))
        },
        "mode": mode,
        "backend": MODE_TO_BACKEND[mode],
        "load_notes": load_notes,
        "effect_strength": effect_strength,
        "interpretation_caveat": INTERPRETATION_CAVEAT,
    }


def _effect_strength(hr: float, p: float, n_events: int) -> float:
    """0–1 quality for evidence aggregation — effect size + events, not just p."""
    import math

    if hr != hr or p != p:
        return 0.2
    log_hr = abs(math.log(max(hr, 1e-6)))
    size = min(1.0, log_hr / math.log(2.0))  # HR of 2 → 1.0
    sig = 0.0 if p > 0.1 else (0.5 if p > 0.05 else (0.75 if p > 0.01 else 1.0))
    n_factor = min(1.0, n_events / 40.0)
    return round(max(0.15, min(1.0, 0.45 * size + 0.35 * sig + 0.20 * n_factor)), 3)


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    out = {
        "ok": False,
        "error": code,
        "message": message,
        "claim_type": "cohort_association",
        "interpretation_caveat": INTERPRETATION_CAVEAT,
        "p_value_session_corrected": None,
        "multiple_testing": {
            "status": "uncorrected",
            "method": None,
            "note": (
                "Returned p-value is uncorrected; session-level FDR belongs in the "
                "orchestrator / evidence layer."
            ),
        },
    }
    out.update(extra)
    return out
