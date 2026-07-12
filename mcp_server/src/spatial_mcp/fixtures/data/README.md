# Optional published TCGA immune / leukocyte scores

Place JSON files here (or under `TCGA_DATA_ROOT`) so
`differential_survival_analysis` can include an immune-infiltration covariate:

- `immune_scores_CRC.json`
- `immune_scores_NSCLC.json`
- `immune_scores_MEL.json`

Format: `{ "TCGA-XX-XXXX": 0.42, ... }` mapping patient ID → score
(e.g. Thorsson leukocyte fraction or ESTIMATE ImmuneScore).

When absent, the Cox model skips this covariate and records why in
`covariates_skipped` — it does not invent deconvolution scores.
