"""TCGA cohort loading: local cache → cBioPortal → fixture.

Mirrors the live-vs-surrogate split used by scldm_knockout / search_literature.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from spatial_mcp.fixtures.tcga_cohort import (
    CANCER_TO_CBIO_STUDY,
    FIXTURE_GENES,
    get_fixture_cohort,
    normalize_cancer_type,
)

CBIO_BASE = os.environ.get("CBIO_API_BASE", "https://www.cbioportal.org/api")
# Prefer hackathon/SageMaker local TCGA extract when present.
_LOCAL_CANDIDATES = [
    os.environ.get("TCGA_DATA_ROOT", ""),
    "/home/ec2-user/SageMaker/tcga",
    "/home/ec2-user/SageMaker/data/tcga",
    str(Path(__file__).resolve().parents[3] / "data" / "tcga"),
]


def _local_root() -> Path | None:
    for raw in _LOCAL_CANDIDATES:
        if not raw:
            continue
        p = Path(raw)
        if p.is_dir():
            return p
    return None


def load_cohort(
    cancer_type: str,
    genes: list[str],
    *,
    force_fixture: bool = False,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Return (patients, mode, notes).

    mode ∈ {"live_local", "live_cbioportal", "fixture"} — same role as
    simulate_perturbations' ``backend`` field.
    """
    notes: list[str] = []
    canonical = normalize_cancer_type(cancer_type)
    if canonical is None:
        raise ValueError(f"unsupported_cancer_type:{cancer_type}")

    if force_fixture or os.environ.get("TCGA_FORCE_FIXTURE", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        notes.append("Forced fixture path (TCGA_FORCE_FIXTURE or force_fixture).")
        return get_fixture_cohort(canonical), "fixture", notes

    local = _local_root()
    if local is not None:
        try:
            patients = _load_local(local, canonical, genes)
            if patients:
                notes.append(f"Loaded local TCGA extract from {local}.")
                return patients, "live_local", notes
            notes.append(f"Local TCGA root {local} present but no usable cohort files.")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Local TCGA load failed ({type(exc).__name__}: {exc}).")

    try:
        patients = _load_cbioportal(canonical, genes)
        if patients:
            notes.append(
                f"Loaded cBioPortal study {CANCER_TO_CBIO_STUDY[canonical]} "
                f"({len(patients)} patients with OS + expression)."
            )
            return patients, "live_cbioportal", notes
        notes.append("cBioPortal returned no usable patients.")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"cBioPortal path failed ({type(exc).__name__}: {exc}).")

    notes.append("Falling back to checked-in synthetic fixture cohort.")
    return get_fixture_cohort(canonical), "fixture", notes


def _load_local(
    root: Path, cancer: str, genes: list[str]
) -> list[dict[str, Any]]:
    """Expect ``{cancer}.json`` or ``cohorts/{cancer}.json`` with patient records."""
    for rel in (f"{cancer}.json", f"cohorts/{cancer}.json", f"{cancer.lower()}.json"):
        path = root / rel
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        patients = data if isinstance(data, list) else data.get("patients") or []
        out = []
        for p in patients:
            expr = p.get("expression") or {}
            # Keep only requested genes when present; allow fixture-shaped full records
            filtered = {g: float(expr[g]) for g in genes if g in expr}
            if len(filtered) < max(1, len(genes) // 2) and expr:
                # If local file has broader matrix, still keep intersection
                filtered = {g: float(v) for g, v in expr.items() if g in genes or not genes}
            rec = dict(p)
            rec["expression"] = filtered or {g: float(expr[g]) for g in expr}
            rec["cancer_type"] = cancer
            out.append(rec)
        if out:
            return out
    return []


def _load_cbioportal(cancer: str, genes: list[str]) -> list[dict[str, Any]]:
    study = CANCER_TO_CBIO_STUDY[cancer]
    profile = f"{study}_rna_seq_v2_mrna"
    timeout = float(os.environ.get("CBIO_TIMEOUT_S", "45"))

    # Resolve Hugo → Entrez
    entrez_map: dict[str, int] = {}
    for g in genes:
        r = requests.get(
            f"{CBIO_BASE}/genes/{g}",
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        if r.status_code == 404:
            continue
        r.raise_for_status()
        entrez_map[g] = int(r.json()["entrezGeneId"])
    if not entrez_map:
        raise RuntimeError("no_genes_resolved")

    mol = requests.post(
        f"{CBIO_BASE}/molecular-data/fetch",
        params={"projection": "SUMMARY"},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json={
            "entrezGeneIds": list(entrez_map.values()),
            "molecularProfileIds": [profile],
        },
        timeout=timeout,
    )
    mol.raise_for_status()
    mol_rows = mol.json() or []

    # sampleId → gene → value; also sample → patient
    expr_by_sample: dict[str, dict[str, float]] = {}
    sample_to_patient: dict[str, str] = {}
    entrez_to_gene = {v: k for k, v in entrez_map.items()}
    for row in mol_rows:
        sid = row.get("sampleId")
        pid = row.get("patientId")
        if not sid or not pid:
            continue
        sample_to_patient[sid] = pid
        gene = entrez_to_gene.get(int(row["entrezGeneId"]))
        if not gene:
            continue
        try:
            val = float(row["value"])
        except (TypeError, ValueError, KeyError):
            continue
        expr_by_sample.setdefault(sid, {})[gene] = val

    # Clinical (patient-level)
    clin = requests.get(
        f"{CBIO_BASE}/studies/{study}/clinical-data",
        params={"clinicalDataType": "PATIENT", "projection": "SUMMARY"},
        headers={"Accept": "application/json"},
        timeout=timeout,
    )
    clin.raise_for_status()
    clin_by_patient: dict[str, dict[str, str]] = {}
    for row in clin.json() or []:
        pid = row.get("patientId")
        attr = row.get("clinicalAttributeId")
        if pid and attr:
            clin_by_patient.setdefault(pid, {})[attr] = str(row.get("value", ""))

    # Sample-level (aneuploidy as weak purity stand-in only if needed — we skip purity
    # unless a real purity attribute appears; check sample clinical for known names)
    samp = requests.get(
        f"{CBIO_BASE}/studies/{study}/clinical-data",
        params={"clinicalDataType": "SAMPLE", "projection": "SUMMARY"},
        headers={"Accept": "application/json"},
        timeout=timeout,
    )
    samp.raise_for_status()
    sample_attrs: dict[str, dict[str, str]] = {}
    for row in samp.json() or []:
        sid = row.get("sampleId")
        attr = row.get("clinicalAttributeId")
        if sid and attr:
            sample_attrs.setdefault(sid, {})[attr] = str(row.get("value", ""))

    # Optional published immune scores beside the install (patient_id → float)
    immune_lookup = _load_immune_lookup(cancer)

    patients: list[dict[str, Any]] = []
    seen_patients: set[str] = set()
    for sid, expr in expr_by_sample.items():
        pid = sample_to_patient.get(sid)
        if not pid or pid in seen_patients:
            continue
        c = clin_by_patient.get(pid) or {}
        os_months = _to_float(c.get("OS_MONTHS"))
        os_status = (c.get("OS_STATUS") or "").upper()
        if os_months is None or os_months <= 0:
            continue
        if "DECEASED" in os_status or os_status.endswith(":DECEASED") or os_status == "1:DECEASED":
            event = 1
        elif "LIVING" in os_status or os_status.endswith(":LIVING") or os_status == "0:LIVING":
            event = 0
        else:
            # Unknown status — skip
            continue
        age = _to_float(c.get("AGE"))
        stage = _stage_to_int(c.get("AJCC_PATHOLOGIC_TUMOR_STAGE") or c.get("STAGE"))
        sa = sample_attrs.get(sid) or {}
        purity = _to_float(
            sa.get("PURITY")
            or sa.get("ABSOLUTE_PURITY")
            or sa.get("CPE")
            or c.get("PURITY")
        )
        immune = immune_lookup.get(pid)
        if immune is None:
            immune = _to_float(
                c.get("LEUKOCYTE_FRACTION")
                or c.get("IMMUNE_SCORE")
                or c.get("ESTIMATE_IMMUNE_SCORE")
            )

        patients.append(
            {
                "patient_id": pid,
                "sample_id": sid,
                "cancer_type": cancer,
                "os_months": os_months,
                "os_event": event,
                "age": age,
                "stage": stage,
                "purity": purity,
                "immune_infiltration": immune,
                "expression": expr,
            }
        )
        seen_patients.add(pid)

    return patients


def _load_immune_lookup(cancer: str) -> dict[str, float]:
    """Load published immune scores if present under TCGA_DATA_ROOT / package data."""
    names = [
        f"immune_scores_{cancer}.json",
        f"leukocyte_fraction_{cancer}.json",
        "immune_scores.json",
    ]
    roots: list[Path] = []
    local = _local_root()
    if local:
        roots.append(local)
    roots.append(Path(__file__).resolve().parents[1] / "fixtures" / "data")
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                raw = json.loads(path.read_text())
                if isinstance(raw, dict):
                    return {str(k): float(v) for k, v in raw.items()}
    return {}


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _stage_to_int(stage: str | None) -> int | None:
    if not stage:
        return None
    s = stage.upper().replace(" ", "")
    for n, token in ((4, "IV"), (3, "III"), (2, "II"), (1, "I")):
        if f"STAGE{token}" in s or s == token or s.startswith(f"{token}A") or s.startswith(
            f"{token}B"
        ):
            return n
    for n in (1, 2, 3, 4):
        if str(n) in s and "STAGE" in s:
            return n
    return None


# Re-export helpers used by the tool
__all__ = [
    "load_cohort",
    "normalize_cancer_type",
    "CANCER_TO_CBIO_STUDY",
    "FIXTURE_GENES",
]
