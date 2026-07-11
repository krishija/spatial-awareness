"""JSON schemas and K Pro-facing descriptions for all seven MCP tools.

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
        "cell under a named gene knockdown/knockout using the virtual-cell model. "
        "Returns before/after values for the eight-gene marker panel (PDCD1, TCF7, "
        "TOX, LAG3, GZMB, IL7R, CTLA4, FOXP3) plus per-gene deltas. Fails gracefully "
        "with a structured error if the gene is outside the model's training "
        "vocabulary (known in-vocab genes include the marker panel plus common "
        "checkpoint/effector targets such as HAVCR2, ENTPD1, CXCL13)."
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

ALL_TOOL_SPECS = [
    LIST_CANDIDATE_CELLS,
    MAP_SPATIAL_TO_SINGLE,
    SEARCH_LITERATURE,
    SUGGEST_PERTURBATIONS,
    SIMULATE_PERTURBATIONS,
    RECORD_FINDING,
    QUERY_PRIOR_FINDINGS,
]

TOOL_BY_NAME = {t["name"]: t for t in ALL_TOOL_SPECS}
