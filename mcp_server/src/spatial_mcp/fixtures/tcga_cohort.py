"""Checked-in TCGA-shaped fixture cohorts for offline differential survival analysis.

Synthetic patients with expression, OS, stage, age, purity, and a published-style
immune-infiltration score. Clearly labeled as fixture data in tool responses —
not real TCGA observations.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

# Cancer types accepted by the tool (aliases → canonical key).
CANCER_TYPE_ALIASES: dict[str, str] = {
    "CRC": "CRC",
    "COAD": "CRC",
    "READ": "CRC",
    "COADREAD": "CRC",
    "COLORECTAL": "CRC",
    "NSCLC": "NSCLC",
    "LUAD": "NSCLC",
    "LUSC": "NSCLC",
    "LUNG": "NSCLC",
    "MEL": "MEL",
    "SKCM": "MEL",
    "MELANOMA": "MEL",
}

# Canonical type → cBioPortal PanCancer Atlas study id (live path).
CANCER_TO_CBIO_STUDY: dict[str, str] = {
    "CRC": "coadread_tcga_pan_can_atlas_2018",
    "NSCLC": "luad_tcga_pan_can_atlas_2018",
    "MEL": "skcm_tcga_pan_can_atlas_2018",
}

SUPPORTED_CANCER_TYPES = sorted(set(CANCER_TYPE_ALIASES.values()))

# Genes used in fixture expression matrices (signature ∪ immune panel).
FIXTURE_GENES = [
    "PDCD1",
    "TCF7",
    "TOX",
    "LAG3",
    "GZMB",
    "IL7R",
    "CTLA4",
    "FOXP3",
    "CD8A",
    "GZMA",
    "PRF1",
    "CXCL13",
    "CXCL9",
    "CXCL10",
    "MKI67",
    "BATF",
    "HAVCR2",
    "TIGIT",
    "ENTPD1",
    "PTPRC",
]


def normalize_cancer_type(raw: str) -> str | None:
    key = (raw or "").strip().upper().replace("-", "").replace(" ", "")
    # Allow crc / nsclc / mel style from sample ids
    if key.startswith("CRC"):
        return "CRC"
    if key.startswith("NSCLC") or key.startswith("LUAD") or key.startswith("LUSC"):
        return "NSCLC"
    if key.startswith("MEL") or key.startswith("SKCM"):
        return "MEL"
    return CANCER_TYPE_ALIASES.get(key)


def _rng(seed: str) -> float:
    """Deterministic U(0,1) from a string seed."""
    h = hashlib.sha256(seed.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _expr(patient_id: str, gene: str, base: float, noise: float = 0.35) -> float:
    u = _rng(f"{patient_id}:{gene}")
    # Box-Muller-ish via two uniforms
    u2 = _rng(f"{patient_id}:{gene}:b")
    z = math.sqrt(-2.0 * math.log(max(u, 1e-9))) * math.cos(2 * math.pi * u2)
    return round(max(0.0, base + noise * z), 4)


def _build_cohort(cancer: str, n: int = 48) -> list[dict[str, Any]]:
    """Plant a known protective association for the cytotoxic gene set.

    High mean(CD8A, GZMA, PRF1, CXCL9) → longer OS / lower hazard in fixture,
    independent of immune_infiltration covariate noise, so Cox can recover
    a protective HR for that signature as a sanity check.
    """
    patients: list[dict[str, Any]] = []
    for i in range(n):
        pid = f"FIX-{cancer}-{i:03d}"
        # Latent "cytotoxic activity" drives both signature genes and survival
        latent = _rng(f"{pid}:latent")
        age = 40 + int(50 * _rng(f"{pid}:age"))
        stage_r = _rng(f"{pid}:stage")
        stage = 1 if stage_r < 0.25 else 2 if stage_r < 0.55 else 3 if stage_r < 0.85 else 4
        purity = round(0.25 + 0.6 * _rng(f"{pid}:purity"), 3)
        # Immune infiltrate correlated with latent but not identical
        immune = round(0.15 + 0.7 * (0.55 * latent + 0.45 * _rng(f"{pid}:imm")), 3)

        expr: dict[str, float] = {}
        for g in FIXTURE_GENES:
            if g in ("CD8A", "GZMA", "PRF1", "CXCL9", "CXCL10", "GZMB"):
                base = 1.5 + 4.0 * latent
            elif g in ("PDCD1", "TOX", "LAG3", "HAVCR2", "TIGIT"):
                base = 3.5 - 2.0 * latent
            elif g in ("MKI67",):
                base = 2.0 + 1.5 * (stage / 4.0)
            else:
                base = 1.5 + 2.0 * _rng(f"{pid}:{g}:base")
            expr[g] = _expr(pid, g, base)

        # Survival: higher latent → longer time, lower event rate (protective)
        # Also worse stage / older age shorten survival.
        risk = (
            -1.4 * latent
            + 0.35 * (stage - 1)
            + 0.015 * (age - 60)
            - 0.2 * immune
            + 0.4 * _rng(f"{pid}:risk")
        )
        # Approximate exponential time from risk
        u = max(_rng(f"{pid}:t"), 1e-6)
        os_months = round(min(120.0, max(1.0, -math.log(u) * math.exp(-risk) * 28.0)), 2)
        event = 1 if (_rng(f"{pid}:event") < (0.25 + 0.55 / (1.0 + math.exp(-risk)))) else 0
        # Censor some long survivors
        if os_months > 90 and _rng(f"{pid}:censor") > 0.4:
            event = 0

        patients.append(
            {
                "patient_id": pid,
                "sample_id": f"{pid}-01",
                "cancer_type": cancer,
                "os_months": os_months,
                "os_event": event,  # 1=death, 0=censored
                "age": age,
                "stage": stage,
                "purity": purity,
                "immune_infiltration": immune,
                "expression": expr,
            }
        )
    return patients


# Pre-build once at import for stable demo fixtures.
FIXTURE_COHORTS: dict[str, list[dict[str, Any]]] = {
    cancer: _build_cohort(cancer) for cancer in SUPPORTED_CANCER_TYPES
}


def get_fixture_cohort(cancer: str) -> list[dict[str, Any]]:
    canonical = normalize_cancer_type(cancer)
    if canonical is None:
        raise KeyError(cancer)
    return FIXTURE_COHORTS[canonical]
