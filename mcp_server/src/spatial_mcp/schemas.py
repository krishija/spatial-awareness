"""JSON schemas and K Pro-facing descriptions for all MCP tools.

Descriptions are the primary routing signal for the agent — keep them precise.
"""

from __future__ import annotations

from typing import Any

# Shared enums aligned with the frontend fixture vocabulary
NICHES = ["tumor_core", "tumor_margin", "lymphoid_proximal"]
CELL_TYPES = [
    "CD4_Tex_term",
    "CD4_Tex_prog",
    "CD4_Teff",
    "CD4_Treg",
    "myeloid",
    "tumor",
    "stromal",
]
EXHAUSTION_STATES = [
    "terminally_exhausted",
    "progenitor_exhausted",
    "effector",
    "other",
]
MARKER_GENES = [
    "PDCD1",
    "TCF7",
    "TOX",
    "LAG3",
    "GZMB",
    "IL7R",
    "CTLA4",
    "FOXP3",
]

EXPRESSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Marker-gene expression values on a 0–5 scale, two decimal places.",
    "properties": {g: {"type": "number"} for g in MARKER_GENES},
    "required": MARKER_GENES,
    "additionalProperties": False,
}

CELL_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "cell_type": {"type": "string", "enum": CELL_TYPES},
        "niche": {"type": "string", "enum": NICHES},
        "exhaustion_state": {"type": "string", "enum": EXHAUSTION_STATES},
        "exhaustion_score": {
            "type": "number",
            "description": "0–1 continuous exhaustion score derived from the phenotype.",
        },
        "expression": EXPRESSION_SCHEMA,
    },
    "required": [
        "id",
        "x",
        "y",
        "cell_type",
        "niche",
        "exhaustion_state",
        "exhaustion_score",
        "expression",
    ],
}

CITATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "source": {"type": "string"},
        "url": {"type": "string"},
        "relevance": {
            "type": "string",
            "description": "One-line relevance snippet for the current query/context.",
        },
    },
    "required": ["title", "source", "url"],
}

# ── Tool contracts ──────────────────────────────────────────────────────────

LIST_CANDIDATE_CELLS = {
    "name": "list_candidate_cells",
    "description": (
        "Return resolved single-cell records for a spatial transcriptomics sample, "
        "optionally filtered by tissue niche, cell type, and/or a minimum continuous "
        "exhaustion score (0–1). Use this to discover which cells are worth inspecting "
        "before suggesting or simulating a gene perturbation. Each record includes "
        "spatial coordinates (x, y), cell_type, niche, exhaustion_state, exhaustion_score, "
        "and the eight-gene marker expression panel (PDCD1, TCF7, TOX, LAG3, GZMB, IL7R, "
        "CTLA4, FOXP3)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sample_id": {
                "type": "string",
                "description": "Sample identifier, e.g. 'crc-01', 'nsclc-03', 'mel-07'.",
            },
            "niche": {
                "type": "string",
                "enum": NICHES,
                "description": "Optional tissue niche filter.",
            },
            "cell_type": {
                "type": "string",
                "enum": CELL_TYPES,
                "description": "Optional cell-type filter.",
            },
            "min_exhaustion_score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Optional lower bound on continuous exhaustion score.",
            },
        },
        "required": ["sample_id"],
        "additionalProperties": False,
    },
}

MAP_SPATIAL_TO_SINGLE = {
    "name": "map_spatial_to_single",
    "description": (
        "Resolve the mapping between raw spatial transcriptomics spots/cells for a "
        "sample and a single-cell reference atlas identity. Returns per-cell atlas "
        "labels, confidence scores, and a sample-level summary of how many cells "
        "mapped to each atlas lineage. Call this when the agent needs to confirm "
        "that a spatial sample has been deconvolved / labeled before filtering "
        "candidates or proposing perturbations. Optional atlas_reference selects "
        "which reference atlas to use (default: 'human_immune_v1')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sample_id": {
                "type": "string",
                "description": "Sample identifier to map.",
            },
            "atlas_reference": {
                "type": "string",
                "description": "Optional atlas name; defaults to 'human_immune_v1'.",
            },
        },
        "required": ["sample_id"],
        "additionalProperties": False,
    },
}

SEARCH_LITERATURE = {
    "name": "search_literature",
    "description": (
        "Search the scientific literature for papers relevant to a free-text query "
        "about CD4 T-cell exhaustion, spatial niches, immune checkpoints, or gene "
        "perturbations. Returns a ranked array of citations (title, source, url, "
        "one-line relevance snippet). Pass optional context (e.g. cell phenotype or "
        "niche) to bias ranking toward papers that ground a subsequent "
        "suggest_perturbations call. Prefer calling this (and query_prior_findings) "
        "before proposing new knockouts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free-text literature search query.",
            },
            "context": {
                "type": "string",
                "description": (
                    "Optional biological context, e.g. 'CD4_Tex_term in tumor_core'."
                ),
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

SUGGEST_PERTURBATIONS = {
    "name": "suggest_perturbations",
    "description": (
        "Propose ranked candidate gene knockouts for a specific resolved cell given "
        "its phenotype and niche. Each suggestion includes the gene symbol, a "
        "one-sentence mechanistic rationale, and supporting citation(s). Intended "
        "agent pattern: call query_prior_findings first to avoid re-proposing work "
        "already recorded, optionally call search_literature for grounding, then "
        "call this tool, then simulate_perturbations on a chosen gene. Optional "
        "literature_context may carry a short summary or citation titles from a "
        "prior search_literature call."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cell_id": {
                "type": "string",
                "description": "Resolved cell id, e.g. 'crc-01-c0042'.",
            },
            "phenotype": {
                "type": "string",
                "description": "Cell phenotype / cell_type label for the target cell.",
            },
            "niche": {
                "type": "string",
                "enum": NICHES,
                "description": "Tissue niche of the target cell.",
            },
            "literature_context": {
                "type": "string",
                "description": "Optional summary of literature already retrieved.",
            },
        },
        "required": ["cell_id", "phenotype", "niche"],
        "additionalProperties": False,
    },
}

SIMULATE_PERTURBATIONS = {
    "name": "simulate_perturbations",
    "description": (
        "Simulate the predicted marker-gene expression shift for a specific resolved "
        "cell under a named gene knockdown/knockout using the scLDM-CD4 virtual-cell "
        "model (counterfactual KO vs non-targeting control → pseudobulk Δ, as in "
        "evaluate_knockout_effect.ipynb). Returns before/after values for the "
        "eight-gene marker panel (PDCD1, TCF7, TOX, LAG3, GZMB, IL7R, CTLA4, FOXP3) "
        "plus per-gene deltas and top genome-wide effects when live weights are "
        "available. Fails gracefully with gene_out_of_vocabulary if the gene is "
        "outside the model's guide set. Set SCLDM_ROOT to enable live inference; "
        "otherwise a notebook-faithful surrogate is used."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cell_id": {
                "type": "string",
                "description": "Resolved cell id to perturb.",
            },
            "gene": {
                "type": "string",
                "description": "Gene symbol to knock down / knock out (e.g. 'PDCD1').",
            },
        },
        "required": ["cell_id", "gene"],
        "additionalProperties": False,
    },
}

DIFFERENTIAL_SURVIVAL_ANALYSIS = {
    "name": "differential_survival_analysis",
    "description": (
        "Differential survival analysis (cohort association) of a gene signature in a "
        "matched TCGA bulk RNA-seq cohort — NOT mechanistic validation. TCGA provides "
        "one aggregate expression value per patient across all cell types; a significant "
        "HR means the signature predicts outcome as a bulk marker in an independent "
        "population, not that the upstream single-cell / spatial mechanism is confirmed. "
        "Scores patients (ssGSEA when gseapy is available, else per-patient z-score mean), "
        "splits high vs low (median; tertiles if requested and n≥30), and fits a "
        "multivariable Cox PH model with available covariates among stage, age, tumor "
        "purity, and published immune-infiltration scores. Cancer-type matching is hard "
        "validation — unsupported types are rejected. Returns HR, 95% CI, uncorrected "
        "p-value, direction, scoring method, covariates included/skipped, mode/backend "
        "(live_local | live_cbioportal | fixture), and a required interpretation_caveat. "
        "Multiple testing: p-values are intentionally UNCORRECTED; apply session-level "
        "FDR in the orchestrator/evidence layer across all calls this session. Prefer "
        "cancer_type matching the spatial sample (CRC, NSCLC, MEL)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "genes": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Gene signature (Hugo symbols) to score in the bulk cohort.",
            },
            "cancer_type": {
                "type": "string",
                "description": (
                    "Cancer type that must match an available TCGA cohort. "
                    "Accepted: CRC/COAD/COADREAD, NSCLC/LUAD, MEL/SKCM (and aliases)."
                ),
            },
            "weights": {
                "type": "object",
                "additionalProperties": {"type": "number"},
                "description": (
                    "Optional per-gene weights / directionality for z-score scoring "
                    "(ignored by ssGSEA). Positive = up in the signature."
                ),
            },
            "outcome": {
                "type": "string",
                "description": "Survival endpoint; only overall survival (OS) is supported.",
                "default": "OS",
            },
            "expected_direction": {
                "type": "string",
                "enum": [
                    "protective",
                    "risk_associated",
                    "higher_signature_better_outcome",
                    "higher_signature_worse_outcome",
                ],
                "description": (
                    "What high signature scores are hypothesized to mean for outcome. "
                    "Used only to set association_matches_expectation for evidence polarity."
                ),
                "default": "protective",
            },
            "split": {
                "type": "string",
                "enum": ["auto", "median", "tertile"],
                "description": "Patient split on signature score (default median via auto).",
                "default": "auto",
            },
            "prefer_ssgsea": {
                "type": "boolean",
                "description": "Try ssGSEA first when gseapy is installed (default true).",
                "default": True,
            },
            "force_fixture": {
                "type": "boolean",
                "description": "Force synthetic fixture cohort (offline / unit tests).",
                "default": False,
            },
        },
        "required": ["genes", "cancer_type"],
        "additionalProperties": False,
    },
}

FIND_MEASURED_PERTURBATION_EVIDENCE = {
    "name": "find_measured_perturbation_evidence",
    "description": (
        "Look up *measured* (not simulated) perturbation evidence for a gene before "
        "trusting virtual-cell deltas. Checks training-corpus membership (scLDM-CD4 / "
        "STATE), optional LINCS/CLUE (CLUE_API_KEY), and prior measured/literature "
        "edges in SQLite. Returns hits with a 3-axis context_match_score "
        "(cell_type, species, perturbation_mechanism). Empty hits with "
        "nothing_found=true is informative — do not invent measurements. Prefer "
        "calling this before or alongside simulate_perturbations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "gene": {
                "type": "string",
                "description": "Hugo gene symbol to look up (e.g. PDCD1, LCP2).",
            },
            "cell_type": {
                "type": "string",
                "description": "Requested cell-type context (default CD4_T).",
                "default": "CD4_T",
            },
            "perturbation_type": {
                "type": "string",
                "description": "Perturbation mechanism (default knockout).",
                "default": "knockout",
            },
        },
        "required": ["gene"],
        "additionalProperties": False,
    },
}

RECOMMEND_NEXT_EXPERIMENT = {
    "name": "recommend_next_experiment",
    "description": (
        "Given current findings / graph neighborhood for a gene and optional "
        "sample_id / niche / cell_type, recommend the next wet-lab or analysis "
        "step. Prefers reanalyze-existing-data over new assays when justified; "
        "includes calibrated simulation-trust notes. Call when evidence is thin "
        "or the gate suggests GATHER_MORE with no clear tool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sample_id": {
                "type": "string",
                "description": "Spatial sample under investigation (e.g. atera-cervical-01).",
            },
            "gene": {
                "type": "string",
                "description": "Focus gene (Hugo symbol).",
            },
            "niche": {
                "type": "string",
                "description": "Optional niche filter (tumor_core / tumor_margin / lymphoid_proximal).",
            },
            "cell_type": {
                "type": "string",
                "description": "Optional cell-type context (default CD4_T).",
                "default": "CD4_T",
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "default": 5,
                "description": "Max recommendations to return.",
            },
        },
        "required": ["gene"],
        "additionalProperties": False,
    },
}

RECORD_FINDING = {
    "name": "record_finding",
    "description": (
        "Persist a scientific finding from the current investigation so it can be "
        "retrieved in later turns or sessions via query_prior_findings. Store a "
        "concise finding_summary plus optional sample_id, cell_id, niche, gene, and "
        "citations. Call this after a successful simulate_perturbations (or after "
        "deciding a suggestion is unsupported) so the agent does not re-propose the "
        "same knockout. Returns the stored record including a generated finding id "
        "and ISO-8601 timestamp."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sample_id": {
                "type": "string",
                "description": "Sample the finding belongs to.",
            },
            "finding_summary": {
                "type": "string",
                "description": "One-to-three sentence claim capturing the finding.",
            },
            "cell_id": {
                "type": "string",
                "description": "Optional cell id the finding is about.",
            },
            "niche": {
                "type": "string",
                "enum": NICHES,
                "description": "Optional niche the finding is about.",
            },
            "gene": {
                "type": "string",
                "description": "Optional gene symbol the finding is about.",
            },
            "citations": {
                "type": "array",
                "items": CITATION_SCHEMA,
                "description": "Optional supporting citations.",
            },
        },
        "required": ["sample_id", "finding_summary"],
        "additionalProperties": False,
    },
}

QUERY_PRIOR_FINDINGS = {
    "name": "query_prior_findings",
    "description": (
        "Retrieve previously recorded findings filtered by any combination of "
        "sample_id, niche, and/or gene. Call this BEFORE suggest_perturbations "
        "(and ideally before proposing any new knockout) to check whether the "
        "agent or a prior session has already investigated this sample/niche/gene "
        "combination — this is the intended anti-duplication pattern, not an "
        "optional step. Returns matching finding records newest-first. Omitting "
        "all filters returns all stored findings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sample_id": {
                "type": "string",
                "description": "Optional sample filter.",
            },
            "niche": {
                "type": "string",
                "enum": NICHES,
                "description": "Optional niche filter.",
            },
            "gene": {
                "type": "string",
                "description": "Optional gene filter (case-insensitive).",
            },
        },
        "additionalProperties": False,
    },
}

EVALUATE_EVIDENCE = {
    "name": "evaluate_evidence",
    "description": (
        "Aggregate multiple evidence items about the same candidate hypothesis into a "
        "single calibrated confidence score (0–1) plus an inspectable rationale. "
        "Uses explicit weights: literature, simulation, cohort_prognostic (population-level "
        "TCGA survival association — not cell-level validation), prior findings, cell "
        "context, atlas mapping, and suggestions; independent literature+simulation "
        "agreement raises confidence; duplicate same-type sources are discounted; "
        "lit↔sim conflicts apply a visible penalty rather than averaging away. Call this "
        "after gathering evidence and BEFORE deciding to report. Do not treat the LLM's "
        "prose confidence as a substitute for this score."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "evidence": {
                "type": "array",
                "description": "Evidence items to aggregate.",
                "items": {
                    "type": "object",
                    "properties": {
                        "evidence_type": {
                            "type": "string",
                            "enum": [
                                "literature",
                                "simulation",
                                "cohort_prognostic",
                                "measured",
                                "prior_finding",
                                "cell_context",
                                "atlas_mapping",
                                "suggestion",
                                "recommend",
                            ],
                        },
                        "summary": {"type": "string"},
                        "source_id": {"type": "string"},
                        "polarity": {
                            "type": "string",
                            "enum": ["supports", "contradicts", "neutral"],
                        },
                        "strength": {"type": "number", "minimum": 0, "maximum": 1},
                        "metadata": {"type": "object"},
                    },
                    "required": ["evidence_type", "summary", "source_id"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["evidence"],
        "additionalProperties": False,
    },
}

DECIDE_NEXT_ACTION = {
    "name": "decide_next_action",
    "description": (
        "Given a programmatic evidence_score (from evaluate_evidence) and the list of "
        "tools already called, decide REPORT, GATHER_MORE, or DISCARD using explicit "
        "thresholds — not LLM discretion alone. Enforces: posterior confidence floor for "
        "REPORT, ≥2 independent sources, ≥1 grounded source (literature / measured / "
        "cohort — not simulation alone), query_prior_findings before "
        "suggest_perturbations, and iteration budget. When GATHER_MORE, returns the "
        "recommended next_tool and why. A real K Pro session can call this to bound "
        "its own loop; the standalone demo driver uses the same function."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "evidence_score": {
                "type": "object",
                "description": "Output of evaluate_evidence (confidence, coverage, has_conflict).",
                "properties": {
                    "confidence": {"type": "number"},
                    "coverage": {"type": "object"},
                    "has_conflict": {"type": "boolean"},
                    "rationale": {"type": "string"},
                },
                "required": ["confidence"],
            },
            "tools_called": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool names already invoked this session, in order.",
            },
            "max_iterations": {"type": "integer", "minimum": 1, "default": 8},
            "iteration": {"type": "integer", "minimum": 1, "default": 1},
            "force_prior_before_suggest": {"type": "boolean", "default": True},
        },
        "required": ["evidence_score", "tools_called"],
        "additionalProperties": False,
    },
}

ALL_TOOL_SPECS = [
    LIST_CANDIDATE_CELLS,
    MAP_SPATIAL_TO_SINGLE,
    SEARCH_LITERATURE,
    SUGGEST_PERTURBATIONS,
    SIMULATE_PERTURBATIONS,
    DIFFERENTIAL_SURVIVAL_ANALYSIS,
    FIND_MEASURED_PERTURBATION_EVIDENCE,
    RECOMMEND_NEXT_EXPERIMENT,
    RECORD_FINDING,
    QUERY_PRIOR_FINDINGS,
    EVALUATE_EVIDENCE,
    DECIDE_NEXT_ACTION,
]

TOOL_BY_NAME = {t["name"]: t for t in ALL_TOOL_SPECS}
