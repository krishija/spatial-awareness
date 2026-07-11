"""Stub: suggest_perturbations — swap this file for real teammate logic."""

from __future__ import annotations

from typing import Any

from spatial_mcp.fixtures.cells import get_cell


SUGGESTIONS_BY_CONTEXT: dict[str, list[dict[str, Any]]] = {
    "tumor_core": [
        {
            "gene": "PDCD1",
            "rationale": (
                "Terminal Tex cells in the core show high PD-1; knockout may restore "
                "TCF7/IL7R stemness programs."
            ),
            "citation": {
                "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
                "source": "Nature Immunology (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "TOX",
            "rationale": (
                "TOX locks the terminal exhaustion epigenetic state; reducing TOX may "
                "reopen progenitor trajectories."
            ),
            "citation": {
                "title": "TOX reinforces the identity and suppresses reprogramming of exhausted T cells",
                "source": "Nature (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "LAG3",
            "rationale": (
                "Co-inhibitory LAG3 is elevated with PDCD1 in core Tex; dual checkpoint "
                "logic suggests LAG3 KO synergy."
            ),
            "citation": {
                "title": "LAG-3 regulates CD4 T cell exhaustion in the tumor microenvironment",
                "source": "Cancer Cell (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
    ],
    "tumor_margin": [
        {
            "gene": "CTLA4",
            "rationale": (
                "Margin Treg enrichment with high CTLA4; KO may relieve local suppression "
                "of progenitor Tex."
            ),
            "citation": {
                "title": "CTLA-4 controls Treg-mediated restraint of CD4 antitumor responses",
                "source": "Immunity (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "PDCD1",
            "rationale": (
                "Progenitor-exhausted cells at the margin retain TCF7; PDCD1 KO may tip "
                "them toward effector differentiation."
            ),
            "citation": {
                "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
                "source": "Nature Immunology (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "TOX",
            "rationale": (
                "Partial TOX elevation at the margin; moderating TOX may preserve "
                "progenitor plasticity."
            ),
            "citation": {
                "title": "TOX reinforces the identity and suppresses reprogramming of exhausted T cells",
                "source": "Nature (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
    ],
    "lymphoid_proximal": [
        {
            "gene": "PDCD1",
            "rationale": (
                "Even near lymphoid structures, residual PD-1 may restrain GZMB+ effectors; "
                "KO may amplify cytotoxicity."
            ),
            "citation": {
                "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
                "source": "Nature Immunology (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "LAG3",
            "rationale": (
                "LAG3 co-expression on lymphoid-proximal Tex progenitors may limit "
                "full effector conversion."
            ),
            "citation": {
                "title": "LAG-3 regulates CD4 T cell exhaustion in the tumor microenvironment",
                "source": "Cancer Cell (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
    ],
}


def suggest_perturbations(args: dict[str, Any]) -> dict[str, Any]:
    cell_id = args["cell_id"]
    phenotype = args["phenotype"]
    niche = args["niche"]
    literature_context = args.get("literature_context")

    cell = get_cell(cell_id)
    base = list(SUGGESTIONS_BY_CONTEXT.get(niche, SUGGESTIONS_BY_CONTEXT["tumor_core"]))

    # Bias ranking if phenotype is terminal Tex — put PDCD1/TOX first
    if "Tex_term" in phenotype or (cell and cell["cell_type"] == "CD4_Tex_term"):
        base = sorted(
            base,
            key=lambda s: 0 if s["gene"] in ("PDCD1", "TOX") else 1,
        )
    if "Treg" in phenotype or (cell and cell["cell_type"] == "CD4_Treg"):
        base = sorted(base, key=lambda s: 0 if s["gene"] == "CTLA4" else 1)

    suggestions = []
    for i, s in enumerate(base):
        item = {
            "rank": i + 1,
            "gene": s["gene"],
            "rationale": s["rationale"],
            "citations": [s["citation"]],
            "linked_cell_id": cell_id,
            "linked_niche": niche,
        }
        if literature_context:
            item["literature_context_used"] = literature_context[:200]
        suggestions.append(item)

    return {
        "cell_id": cell_id,
        "phenotype": phenotype,
        "niche": niche,
        "suggestions": suggestions,
    }
