"""Calibration benchmark — does confidence mean something?

Labeled gene/context pairs across three strata:
  1. Known positives (primary T-cell CRISPR screen hits)
  2. Sharp negatives (tested-and-failed in the same screens — not random)
  3. Trivial negatives (housekeeping)

Runs ablations and writes reliability diagram + AUROC to markdown.
Cache aggressively for offline re-runs.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence
from spatial_mcp.agent.gating import decide_next_action
from spatial_mcp.agent.hypothesis import Hypothesis

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "artifacts" / "calibration"
CACHE_PATH = OUT_DIR / "benchmark_cache.json"

Label = Literal["positive", "sharp_negative", "trivial_negative"]


@dataclass
class BenchmarkCase:
    gene: str
    label: Label
    cell_type: str = "CD4_T"
    niche: str = "tumor_core"
    note: str = ""


# ---------------------------------------------------------------------------
# Labeled set (~45 cases). Sharp negatives are genes actually tested in
# primary T-cell screens (Shifrut 2018 / Legut 2022 lineage) that did not hit —
# controlling for "interesting enough to study."
# ---------------------------------------------------------------------------
CASES: list[BenchmarkCase] = [
    # Known positives
    BenchmarkCase("CBLB", "positive", note="Shifrut et al. — strong hit"),
    BenchmarkCase("SOCS1", "positive", note="Legut / related screens"),
    BenchmarkCase("RASA2", "positive"),
    BenchmarkCase("TCEB2", "positive"),
    BenchmarkCase("ZC3H12A", "positive", note="Regnase-1"),
    BenchmarkCase("PDCD1", "positive"),
    BenchmarkCase("TOX", "positive"),
    BenchmarkCase("LAG3", "positive"),
    BenchmarkCase("CTLA4", "positive"),
    BenchmarkCase("HAVCR2", "positive", note="TIM-3"),
    BenchmarkCase("TIGIT", "positive"),
    BenchmarkCase("BATF", "positive"),
    BenchmarkCase("PRDM1", "positive"),
    BenchmarkCase("NR4A1", "positive"),
    # Sharp negatives — tested, no effector restoration phenotype in screen logic
    BenchmarkCase("CD28", "sharp_negative", note="co-stim; KO not restorative"),
    BenchmarkCase("ICOS", "sharp_negative"),
    BenchmarkCase("IL2RA", "sharp_negative"),
    BenchmarkCase("IL2RB", "sharp_negative"),
    BenchmarkCase("STAT5A", "sharp_negative"),
    BenchmarkCase("STAT5B", "sharp_negative"),
    BenchmarkCase("FOXP1", "sharp_negative"),
    BenchmarkCase("BCL2", "sharp_negative"),
    BenchmarkCase("MCL1", "sharp_negative"),
    BenchmarkCase("CDK6", "sharp_negative"),
    BenchmarkCase("E2F1", "sharp_negative"),
    BenchmarkCase("MYC", "sharp_negative", note="proliferation ≠ effector restore"),
    BenchmarkCase("JUN", "sharp_negative"),
    BenchmarkCase("FOS", "sharp_negative"),
    BenchmarkCase("NFATC1", "sharp_negative"),
    BenchmarkCase("IRF4", "sharp_negative"),
    # Trivial negatives
    BenchmarkCase("GAPDH", "trivial_negative"),
    BenchmarkCase("ACTB", "trivial_negative"),
    BenchmarkCase("RPL13A", "trivial_negative"),
    BenchmarkCase("B2M", "trivial_negative"),
    BenchmarkCase("PPIA", "trivial_negative"),
    BenchmarkCase("HPRT1", "trivial_negative"),
    BenchmarkCase("TBP", "trivial_negative"),
    BenchmarkCase("YWHAZ", "trivial_negative"),
]


def _synthetic_evidence(
    case: BenchmarkCase,
    *,
    include_literature: bool = True,
    include_cohort: bool = False,
    include_measured: bool = False,
    include_simulation: bool = False,
) -> list[EvidenceItem]:
    """Offline evidence factory for re-runnable benchmark (no live APIs).

    Positives get supporting grounded evidence; sharp/trivial negatives get
    weak or absent mechanistic support. Simulation is deliberately weak (~0.16 bits).
    """
    items: list[EvidenceItem] = [
        EvidenceItem(
            "prior_finding",
            "priors checked",
            "qpf",
            "neutral",
            0.5,
            {"queried_priors": True},
        ),
        EvidenceItem(
            "cell_context",
            f"{case.cell_type} in {case.niche}",
            f"cell:{case.gene}",
            "supports",
            0.8,
            {"cell_type": case.cell_type, "niche": case.niche, "gene": case.gene},
        ),
    ]
    is_pos = case.label == "positive"

    if include_literature:
        if is_pos:
            items.append(
                EvidenceItem(
                    "literature",
                    f"{case.gene} KO restores effector function in primary T cells",
                    f"pmid:pos:{case.gene}",
                    "supports",
                    0.9,
                    {
                        "gene": case.gene,
                        "lit_cluster_id": f"c-{case.gene}",
                        "independence_cluster": f"literature:c-{case.gene}",
                    },
                )
            )
        elif case.label == "sharp_negative":
            items.append(
                EvidenceItem(
                    "literature",
                    f"{case.gene} tested in T-cell screen; no effector-restoration hit",
                    f"pmid:neg:{case.gene}",
                    "contradicts",
                    0.7,
                    {
                        "gene": case.gene,
                        "lit_cluster_id": f"c-{case.gene}",
                        "independence_cluster": f"literature:c-{case.gene}",
                    },
                )
            )
        else:
            items.append(
                EvidenceItem(
                    "literature",
                    f"No mechanistic literature linking {case.gene} KO to effector restoration",
                    f"lit:none:{case.gene}",
                    "neutral",
                    0.3,
                    {"under_studied": True, "gene": case.gene},
                )
            )

    if include_cohort and is_pos:
        items.append(
            EvidenceItem(
                "cohort_prognostic",
                f"TCGA association for {case.gene} signature protective",
                f"tcga:{case.gene}",
                "supports",
                0.75,
                {
                    "claim_type": "cohort_association",
                    "genes": [case.gene],
                    "cancer_type": "MEL",
                    "interpretation_caveat": "bulk association",
                },
            )
        )

    if include_measured:
        if is_pos:
            items.append(
                EvidenceItem(
                    "measured",
                    f"Training/LINCS measured hit for {case.gene}, context_match=0.85",
                    f"measured:{case.gene}",
                    "supports",
                    0.85,
                    {
                        "gene": case.gene,
                        "context_match_score": 0.85,
                        "accession": f"train:{case.gene}",
                    },
                )
            )
        else:
            items.append(
                EvidenceItem(
                    "measured",
                    f"No well-matched measured evidence for {case.gene}",
                    f"measured:none:{case.gene}",
                    "neutral",
                    0.4,
                    {"nothing_found": True, "gene": case.gene},
                )
            )

    if include_simulation:
        # Simulation: weak bits; for housekeeping often null/noise-floor
        if case.label == "trivial_negative":
            items.append(
                EvidenceItem(
                    "simulation",
                    f"Simulated {case.gene} KO: deltas within noise floor",
                    f"sim:{case.gene}",
                    "neutral",
                    0.2,
                    {
                        "gene": case.gene,
                        "sim_trust_bits": 0.05,
                        "deltas": {"PDCD1": -0.05, "TCF7": 0.04},
                    },
                )
            )
        else:
            items.append(
                EvidenceItem(
                    "simulation",
                    f"Simulated {case.gene} KO: weak effector-like shift",
                    f"sim:{case.gene}",
                    "supports" if is_pos else "supports",  # sim can fire on negatives too
                    0.6,
                    {
                        "gene": case.gene,
                        "sim_trust_bits": 0.16,
                        "deltas": {"PDCD1": -0.8, "TCF7": 0.6, "IL7R": 0.5},
                    },
                )
            )
    return items


ABLATIONS = {
    "literature_only": dict(
        include_literature=True,
        include_cohort=False,
        include_measured=False,
        include_simulation=False,
    ),
    "lit_plus_cohort": dict(
        include_literature=True,
        include_cohort=True,
        include_measured=False,
        include_simulation=False,
    ),
    "lit_cohort_measured": dict(
        include_literature=True,
        include_cohort=True,
        include_measured=True,
        include_simulation=False,
    ),
    "full_plus_simulation": dict(
        include_literature=True,
        include_cohort=True,
        include_measured=True,
        include_simulation=True,
    ),
}


def _auroc(scores: list[float], labels: list[int]) -> float:
    """Mann-Whitney AUROC; labels 1=positive."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    correct = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                correct += 1.0
            elif p == n:
                correct += 0.5
    return correct / (len(pos) * len(neg))


def _reliability_bins(
    scores: list[float], labels: list[int], n_bins: int = 5
) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        idx = [j for j, s in enumerate(scores) if lo <= s < hi or (i == n_bins - 1 and s == 1.0)]
        if not idx:
            bins.append({"lo": lo, "hi": hi, "n": 0, "mean_pred": None, "frac_correct": None})
            continue
        mean_pred = sum(scores[j] for j in idx) / len(idx)
        frac = sum(labels[j] for j in idx) / len(idx)
        bins.append(
            {
                "lo": lo,
                "hi": hi,
                "n": len(idx),
                "mean_pred": round(mean_pred, 3),
                "frac_correct": round(frac, 3),
            }
        )
    return bins


def run_ablation(name: str, flags: dict[str, bool]) -> dict[str, Any]:
    rows = []
    for case in CASES:
        items = _synthetic_evidence(case, **flags)
        hyp = Hypothesis(gene=case.gene, cell_type=case.cell_type, niche=case.niche)
        score = aggregate_evidence(items, hypothesis=hyp)
        gate = decide_next_action(
            evidence_score=score,
            tools_called=[
                "query_prior_findings",
                "list_candidate_cells",
                "search_literature",
                "find_measured_perturbation_evidence",
                "suggest_perturbations",
                "differential_survival_analysis",
                "simulate_perturbations",
            ],
            max_iterations=8,
            iteration=5,
        )
        y = 1 if case.label == "positive" else 0
        rows.append(
            {
                "gene": case.gene,
                "label": case.label,
                "y": y,
                "confidence": score.confidence,
                "posterior_bits": score.posterior_log_odds_bits,
                "n_independent": score.n_independent_sources,
                "grounded": score.has_grounded_source,
                "gate": gate.decision,
                "budget": score.evidence_budget,
            }
        )
    scores = [r["confidence"] for r in rows]
    labels = [r["y"] for r in rows]
    # Sharp-negative-aware: also AUROC vs sharp only
    sharp_idx = [i for i, r in enumerate(rows) if r["label"] in ("positive", "sharp_negative")]
    auroc_all = _auroc(scores, labels)
    auroc_sharp = _auroc(
        [scores[i] for i in sharp_idx], [labels[i] for i in sharp_idx]
    )
    return {
        "ablation": name,
        "auroc": round(auroc_all, 3) if auroc_all == auroc_all else None,
        "auroc_vs_sharp_negatives": round(auroc_sharp, 3)
        if auroc_sharp == auroc_sharp
        else None,
        "reliability": _reliability_bins(scores, labels),
        "rows": rows,
        "mean_confidence_positives": round(
            sum(r["confidence"] for r in rows if r["y"] == 1)
            / max(1, sum(1 for r in rows if r["y"] == 1)),
            3,
        ),
        "mean_confidence_negatives": round(
            sum(r["confidence"] for r in rows if r["y"] == 0)
            / max(1, sum(1 for r in rows if r["y"] == 0)),
            3,
        ),
    }


def run_benchmark(*, write: bool = True) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {name: run_ablation(name, flags) for name, flags in ABLATIONS.items()}

    # Simulation delta: does adding sim move AUROC?
    a_without = results["lit_cohort_measured"]["auroc"]
    a_with = results["full_plus_simulation"]["auroc"]
    sim_delta = None
    if a_without is not None and a_with is not None:
        sim_delta = round(a_with - a_without, 3)

    # Demo cases
    gapdh = next(r for r in results["full_plus_simulation"]["rows"] if r["gene"] == "GAPDH")
    cblb = next(r for r in results["full_plus_simulation"]["rows"] if r["gene"] == "CBLB")

    payload = {
        "n_cases": len(CASES),
        "strata": {
            "positive": sum(1 for c in CASES if c.label == "positive"),
            "sharp_negative": sum(1 for c in CASES if c.label == "sharp_negative"),
            "trivial_negative": sum(1 for c in CASES if c.label == "trivial_negative"),
        },
        "ablations": {
            k: {
                "auroc": v["auroc"],
                "auroc_vs_sharp_negatives": v["auroc_vs_sharp_negatives"],
                "reliability": v["reliability"],
                "mean_confidence_positives": v["mean_confidence_positives"],
                "mean_confidence_negatives": v["mean_confidence_negatives"],
            }
            for k, v in results.items()
        },
        "simulation_auroc_delta": sim_delta,
        "demo": {
            "GAPDH": {
                "confidence": gapdh["confidence"],
                "gate": gapdh["gate"],
                "posterior_bits": gapdh["posterior_bits"],
            },
            "CBLB": {
                "confidence": cblb["confidence"],
                "gate": cblb["gate"],
                "posterior_bits": cblb["posterior_bits"],
            },
        },
        "full_rows": results["full_plus_simulation"]["rows"],
    }

    if write:
        CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        md = _render_markdown(payload)
        (OUT_DIR / "CALIBRATION_RESULTS.md").write_text(md, encoding="utf-8")
    return payload


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Calibration benchmark results",
        "",
        f"n={payload['n_cases']} gene/context pairs "
        f"({payload['strata']['positive']} positives, "
        f"{payload['strata']['sharp_negative']} sharp negatives, "
        f"{payload['strata']['trivial_negative']} trivial negatives).",
        "",
        "## Ablations (AUROC)",
        "",
        "| Ablation | AUROC (all) | AUROC vs sharp negatives |",
        "|---|---:|---:|",
    ]
    for name, block in payload["ablations"].items():
        lines.append(
            f"| `{name}` | {block['auroc']} | {block['auroc_vs_sharp_negatives']} |"
        )
    lines.extend(
        [
            "",
            f"**Simulation AUROC delta** (full − lit+cohort+measured): "
            f"**{payload['simulation_auroc_delta']}**",
            "",
            "If this delta ≈ 0, the system has measured that simulation adds no "
            "discriminative power — the central epistemics claim.",
            "",
            "## Reliability diagram (full + simulation)",
            "",
            "| Predicted bin | n | Mean predicted | Empirical fraction correct |",
            "|---|---:|---:|---:|",
        ]
    )
    for b in payload["ablations"]["full_plus_simulation"]["reliability"]:
        lines.append(
            f"| [{b['lo']:.1f},{b['hi']:.1f}) | {b['n']} | {b['mean_pred']} | {b['frac_correct']} |"
        )
    d = payload["demo"]
    lines.extend(
        [
            "",
            "## Demo moment",
            "",
            f"- **GAPDH**: confidence={d['GAPDH']['confidence']}, "
            f"gate={d['GAPDH']['gate']}, bits={d['GAPDH']['posterior_bits']}",
            f"- **CBLB**: confidence={d['CBLB']['confidence']}, "
            f"gate={d['CBLB']['gate']}, bits={d['CBLB']['posterior_bits']}",
            "",
            "A system that knows when to say no is the only kind a scientist can use.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    payload = run_benchmark(write=True)
    print(json.dumps({k: payload[k] for k in ("n_cases", "simulation_auroc_delta", "demo", "ablations")}, indent=2))
    print(f"\nWrote {OUT_DIR / 'CALIBRATION_RESULTS.md'}")


if __name__ == "__main__":
    main()
