# Hypothesis report (confidence 0.729)

**Question:** Investigate CD4 T-cell exhaustion in sample atera-cervical-01. Resolve candidate cells and check priors. Call suggest_perturbations, then COMMIT to HAVCR2 (TIM-3) — not PDCD1 — even if PDCD1 is rank-1. Gather independent evidence for HAVCR2 across measured, literature (support AND contradiction), and cohort as needed; conclude REPORT/DISCARD when the gate allows. Do not invent evidence; keep honest ok:false results.

**Claim:** CRISPR knockout of HAVCR2 in CD4_Tex_term from niche tumor_core produces a significant increase in effector-function markers (TCF7/IL7R/GZMB) in a primary human T-cell assay.

| Field | Value |
|---|---|
| Gene | `HAVCR2` |
| Cell | `lkcmlagn-1` |
| Cell type | CD4_Tex_term |
| Niche | tumor_core |
| Gate | REPORT |

## Why this confidence

Prior P(H)=0.20 → logit₂=-2.000 bits (skeptical wet-lab claim prior). cell_context from lkcmlagn-1: Documented prior ≈0.3 bits: relevant cells exist — weak for H. → +0.300 bits. literature from https://www.nature.com/articles/s41423-020-00575-7: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. literature from https://www.cell.com/immunity/fulltext/S1074-7613(26)00229-3: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. literature from https://www.nature.com/articles/s41586-023-06733-x: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. literature from https://www.nature.com/articles/s41467-026-71161-0: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. literature from https://pmc.ncbi.nlm.nih.gov/articles/PMC13032746/: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. literature from https://www.cell.com/iscience/fulltext/S2589-0042(23)00561-8: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. literature from https://pmc.ncbi.nlm.nih.gov/articles/PMC11208905/: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. literature from https://pmc.ncbi.nlm.nih.gov/articles/PMC11278172/: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. measured from training:state:HAVCR2: Documented prior ≈2 bits: well context-matched measured perturbation. → +1.879 bits. measured from training:scldm_cd4:HAVCR2: Documented prior ≈2 bits: well context-matched measured perturbation. → +2.000 bits. prior_finding from query_prior_findings: Neutral polarity → LR=1 → 0 bits. → +0.000 bits. red_team from confound:bulk_confound: Contradicts → negative log-LR. Documented prior ≈0.8 bits: unrebutted steelman objection. → -0.280 bits. red_team from confound:compensation: Contradicts → negative log-LR. Documented prior ≈0.8 bits: unrebutted steelman objection. → -0.280 bits. red_team from confound:off_target: Contradicts → negative log-LR. Documented prior ≈0.8 bits: unrebutted steelman objection. → -0.280 bits. suggestion from suggest:HAVCR2: Documented prior ≈0.1 bits: a proposal is not evidence. → +0.090 bits. suggestion from suggest:PDCD1: Gene mismatch: item gene ≠ hypothesis gene HAVCR2 — contributes 0 bits (evidence must bind to H). → +0.000 bits. suggestion from suggest:TCF7: Gene mismatch: item gene ≠ hypothesis gene HAVCR2 — contributes 0 bits (evidence must bind to H). → +0.000 bits. Posterior logit₂=1.429 bits → P(H|E)=0.729 (7 independent sources; grounded=True).

## Evidence (ordered)

1. **cell_context** (`lkcmlagn-1`, Δ+0.300): Resolved 200 cells; top=lkcmlagn-1 CD4_Tex_term in tumor_core (exhaustion_score=1.0).
   - cell_context from lkcmlagn-1: Documented prior ≈0.3 bits: relevant cells exist — weak for H. → +0.300 bits.
2. **literature** (`https://www.nature.com/articles/s41423-020-00575-7`, Δ0): Opposing regulatory functions of the TIM3 (HAVCR2) signalosome ... — Nature: HAVCR2 (TIM3) is expressed on exhausted T cells in chronic viral infection and tumor settings [8 papers → 8 independent experimental claims. primary of cluster litc-1, n=1]
   - literature from https://www.nature.com/articles/s41423-020-00575-7: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
3. **literature** (`https://www.cell.com/immunity/fulltext/S1074-7613(26)00229-3`, Δ0): The transcription factor Eomes drives a stemness program in CD4+ ... — Cell: Eomes drives a stemness/exhaustion program in CD4+ T cells distinct from effector and memory subsets, amplified by 4-1BB stimulation for tumor control [8 papers → 8 independent experimental claims. primary of cluster litc-2, n=1]
   - literature from https://www.cell.com/immunity/fulltext/S1074-7613(26)00229-3: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
4. **literature** (`https://www.nature.com/articles/s41586-023-06733-x`, Δ0): Single-cell CRISPR screens in vivo map T cell fate regulomes in ... — Nature: HAVCR2 knockout in terminally exhausted CD4 T cells increases effector function markers TCF7/IL7R/GZMB [8 papers → 8 independent experimental claims. primary of cluster litc-3, n=1]
   - literature from https://www.nature.com/articles/s41586-023-06733-x: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
5. **literature** (`https://www.nature.com/articles/s41467-026-71161-0`, Δ0): The CD4+ T cell population partners with Tpex CD8+ T cells to mediate ... — Nature: HAVCR2 (TIM-3) expression in terminally exhausted CD4 T cells is associated with reduced effector function markers TCF7, IL7R, and GZMB [8 papers → 8 independent experimental claims. primary of cluster litc-4, n=1]
   - literature from https://www.nature.com/articles/s41467-026-71161-0: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
6. **literature** (`https://pmc.ncbi.nlm.nih.gov/articles/PMC13032746/`, Δ0): Ex vivo expansion of melanoma tumor infiltrating lymphocytes leads ... — NCBI: HAVCR2 knockout in terminally exhausted CD4 T cells affects effector function markers TCF7/IL7R/GZMB [8 papers → 8 independent experimental claims. primary of cluster litc-5, n=1]
   - literature from https://pmc.ncbi.nlm.nih.gov/articles/PMC13032746/: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
7. **literature** (`https://www.cell.com/iscience/fulltext/S2589-0042(23)00561-8`, Δ0): Prioritizing exhausted T cell marker genes highlights immune subtypes ... — Cell: HAVCR2 (TIM3) is upregulated in terminally exhausted T cells in cancer and chronic infection contexts [8 papers → 8 independent experimental claims. primary of cluster litc-6, n=1]
   - literature from https://www.cell.com/iscience/fulltext/S2589-0042(23)00561-8: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
8. **literature** (`https://pmc.ncbi.nlm.nih.gov/articles/PMC11208905/`, Δ0): Revolutionizing tumor immunotherapy: unleashing the power of ... — NCBI: TIM-3 (HAVCR2) upregulation is associated with T cell exhaustion, not increased effector function markers [8 papers → 8 independent experimental claims. primary of cluster litc-7, n=1]
   - literature from https://pmc.ncbi.nlm.nih.gov/articles/PMC11208905/: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
9. **literature** (`https://pmc.ncbi.nlm.nih.gov/articles/PMC11278172/`, Δ0): A Multi-Omics Analysis of an Exhausted T Cells’ Molecular Signature ... — NCBI: HAVCR2 knockout in terminally exhausted CD4 T cells increases effector function markers TCF7/IL7R/GZMB [8 papers → 8 independent experimental claims. primary of cluster litc-8, n=1]
   - literature from https://pmc.ncbi.nlm.nih.gov/articles/PMC11278172/: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
10. **measured** (`training:state:HAVCR2`, Δ+1.879): Measured hit for HAVCR2 via STATE: context_match=0.798 (cell=0.55, species=1.0, mechanism=1.0)
   - measured from training:state:HAVCR2: Documented prior ≈2 bits: well context-matched measured perturbation. → +1.879 bits.
11. **measured** (`training:scldm_cd4:HAVCR2`, Δ+2.000): Measured hit for HAVCR2 via scLDM-CD4: context_match=1.0 (cell=1.0, species=1.0, mechanism=1.0)
   - measured from training:scldm_cd4:HAVCR2: Documented prior ≈2 bits: well context-matched measured perturbation. → +2.000 bits.
12. **prior_finding** (`query_prior_findings`, Δ0): Prior-findings query executed (anti-duplication check).
   - prior_finding from query_prior_findings: Neutral polarity → LR=1 → 0 bits. → +0.000 bits.
13. **red_team** (`confound:bulk_confound`, Δ-0.280): Surviving alternative: TCGA / bulk association reflects tumor-intrinsic or stromal expression, not the CD4 T-cell mechanism under test (ecological inference).
   - red_team from confound:bulk_confound: Contradicts → negative log-LR. Documented prior ≈0.8 bits: unrebutted steelman objection. → -0.280 bits.
14. **red_team** (`confound:compensation`, Δ-0.280): Surviving alternative: Redundant checkpoints compensate for HAVCR2 loss in vivo, so primary assay effects will not translate.
   - red_team from confound:compensation: Contradicts → negative log-LR. Documented prior ≈0.8 bits: unrebutted steelman objection. → -0.280 bits.
15. **red_team** (`confound:off_target`, Δ-0.280): Surviving alternative: Observed phenotype after HAVCR2 perturbation is an off-target CRISPR effect, not on-target loss of function.
   - red_team from confound:off_target: Contradicts → negative log-LR. Documented prior ≈0.8 bits: unrebutted steelman objection. → -0.280 bits.
16. **suggestion** (`suggest:HAVCR2`, Δ+0.090): Suggested KO HAVCR2: Mentioned in 1 retrieved source for CD4_Tex_term in the tumor core, e.g. "Deciphering T-cell exhaustion in the tumor microenvironment: paving ...": In metastatic melanoma, CXCR6 and TIM-3 co-expression on CD4+ T-cells may indicate pembrolizumab treatment failure (190). Additionally, findings from a pan-cancer study revealed predominant expression
   - suggestion from suggest:HAVCR2: Documented prior ≈0.1 bits: a proposal is not evidence. → +0.090 bits.
17. **suggestion** (`suggest:PDCD1`, Δ0): Suggested KO PDCD1: Mentioned in 2 retrieved sources for CD4_Tex_term in the tumor core, e.g. "Exhausted T cells hijacking the cancer-immunity cycle: Assets and ...": TPEX CD8+ TILs are able to control tumor growth and can respond to anti-PD-1 therapy, while terminally exhausted TILs cannot (9). As pre-existing TILs characterized as terminally exhausted have been c
   - suggestion from suggest:PDCD1: Gene mismatch: item gene ≠ hypothesis gene HAVCR2 — contributes 0 bits (evidence must bind to H). → +0.000 bits.
18. **suggestion** (`suggest:TCF7`, Δ0): Suggested KO TCF7: Mentioned in 1 retrieved source for CD4_Tex_term in the tumor core, e.g. "Targeting tumor-draining lymph node to overcome resistance to cancer ...": The process of T cell exhaustion ranges from Tpex cells (PD-1+, TCF1+, CXCR5+), which possess stem-like self-renewal capacity and multilineage differentiation potential, to terminally exhausted T cell
   - suggestion from suggest:TCF7: Gene mismatch: item gene ≠ hypothesis gene HAVCR2 — contributes 0 bits (evidence must bind to H). → +0.000 bits.

## Supporting citation

- Deciphering T-cell exhaustion in the tumor microenvironment: paving ... — pmc.ncbi.nlm.nih.gov
- https://pmc.ncbi.nlm.nih.gov/articles/PMC11996672/
