# Calibration results

**Honesty note:** this benchmark constructs evidence items from labeled synthetic
cases (and cached structured evidence), then scores them with the Bayesian
log-odds aggregator. It validates that **aggregation math** separates positives
from negatives — it does **not** prove that the live retrieval / tool pipeline
does. Offline only: no MCP server, GPU, or network required.

n=38 gene/context pairs (14 positives, 16 sharp negatives, 8 trivial negatives).

## Ablations (AUROC)

| Ablation | AUROC (all) | AUROC vs sharp negatives |
|---|---:|---:|
| `literature_only` | 1.0 | 1.0 |
| `lit_plus_cohort` | 1.0 | 1.0 |
| `lit_cohort_measured` | 1.0 | 1.0 |
| `full_plus_simulation` | 1.0 | 1.0 |

**Simulation AUROC delta** (full − lit+cohort+measured): **0.0**

If this delta ≈ 0, the system has measured that simulation adds no discriminative power — the central epistemics claim.

## Reliability diagram (full + simulation)

| Predicted bin | n | Mean predicted | Empirical fraction correct |
|---|---:|---:|---:|
| [0.0,0.2) | 16 | 0.163 | 0.0 |
| [0.2,0.4) | 8 | 0.228 | 0.0 |
| [0.4,0.6) | 0 | None | None |
| [0.6,0.8) | 14 | 0.763 | 1.0 |
| [0.8,1.0) | 0 | None | None |

## Demo moment

- **GAPDH**: confidence=0.228, gate=DISCARD, bits=-1.76
- **CBLB**: confidence=0.763, gate=REPORT, bits=1.686

A system that knows when to say no is the only kind a scientist can use.
