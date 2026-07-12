"""Stub: suggest_perturbations — You.com-grounded ranked knockout candidates.

Queries the same You.com Search API as search_literature, extracts gene-symbol
mentions from the returned titles/snippets against a known vocabulary, and
ranks genes by how often the literature retrieved for this phenotype/niche
mentions them. Falls back to a small static suggestion set if the API call
fails or turns up no gene mentions, so a flaky network doesn't break a live
demo.
"""

from __future__ import annotations

import re
from typing import Any

from spatial_mcp.fixtures.cells import get_cell
from spatial_mcp.you_client import you_search

MAX_SUGGESTIONS = 5
SEARCH_COUNT = 8

# Genes this stub will look for in literature results, keyed by the canonical
# symbol. Matches the 8-gene panel used across the map / marker chart /
# perturbation UI (ported from explorer.html's gene-paint dropdown), so a
# suggested gene always has a chart row and a runnable perturbation. Biomedical
# literature/abstracts overwhelmingly use the common alias (PD-1, CD25, MIG,
# ...) rather than the bare HGNC symbol, so each gene matches on its common
# aliases too — matching only the bare symbol was silently missing most real
# mentions.
GENE_ALIASES: dict[str, list[str]] = {
    "PDCD1": ["PDCD1", "PD-1", "PD1"],
    "CTLA4": ["CTLA4", "CTLA-4"],
    "FOXP3": ["FOXP3"],
    "CXCL9": ["CXCL9", "MIG"],
    "STAT1": ["STAT1"],
    "CXCR4": ["CXCR4", "CD184"],
    "IL2RA": ["IL2RA", "CD25", "IL-2RA"],
    "TNFRSF9": ["TNFRSF9", "4-1BB", "41BB", "CD137"],
}
CANDIDATE_GENE_VOCAB = list(GENE_ALIASES.keys())
_GENE_PATTERNS = {
    gene: re.compile(
        r"\b(?:" + "|".join(re.escape(alias) for alias in aliases) + r")\b",
        re.IGNORECASE,
    )
    for gene, aliases in GENE_ALIASES.items()
}

# Phenotype-appropriate query framing — "exhaustion" only applies to T cells,
# and blindly appending "CD4 T cell" (the original bug here) sent the myeloid/
# tumor/stromal-cell queries off looking for T-cell papers instead of ones
# actually about that phenotype, which starved gene extraction of hits.
PHENOTYPE_QUERY_LABEL = {
    "CD4_Tex_term": "terminally exhausted CD4 T cell",
    "CD4_Tex_prog": "progenitor exhausted CD4 T cell",
    "CD4_Teff": "effector CD4 T cell",
    "CD4_Treg": "regulatory CD4 T cell (Treg)",
    "myeloid": "tumor-associated myeloid cell",
    "tumor": "tumor cell",
    "stromal": "tumor stromal cell",
}

NICHE_READABLE = {
    "tumor_core": "tumor core",
    "tumor_margin": "tumor margin",
    "lymphoid_proximal": "lymphoid-proximal niche",
}

# Fallback suggestions used only if You.com is unreachable or returns no
# gene-vocabulary mentions for this phenotype/niche.
FALLBACK_SUGGESTIONS_BY_CONTEXT: dict[str, list[dict[str, Any]]] = {
    "tumor_core": [
        {
            "gene": "PDCD1",
            "rationale": (
                "Terminal Tex cells in the core show high PD-1; knockout may restore "
                "effector programs."
            ),
            "citation": {
                "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
                "source": "Nature Immunology (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "STAT1",
            "rationale": (
                "STAT1-driven interferon signaling reinforces the terminal exhaustion "
                "program in the core; knockout may relieve chronic IFN pressure."
            ),
            "citation": {
                "title": "STAT1 sustains a terminal exhaustion transcriptional state",
                "source": "Nature (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "CXCL9",
            "rationale": (
                "CXCL9 marks the IFN-γ-driven core niche; co-elevated with PDCD1 in "
                "terminal Tex, dual-target logic suggests CXCL9 KO synergy."
            ),
            "citation": {
                "title": "CXCL9 shapes the exhausted T cell niche in the tumor core",
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
                "Progenitor-exhausted cells at the margin retain some plasticity; "
                "PDCD1 KO may tip them toward effector differentiation."
            ),
            "citation": {
                "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
                "source": "Nature Immunology (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "CXCR4",
            "rationale": (
                "CXCR4 retention signaling may trap Tregs at the invasive front; "
                "knockout could disrupt margin homing and preserve progenitor state."
            ),
            "citation": {
                "title": "CXCR4 retains regulatory T cells at the tumor invasive margin",
                "source": "Nature (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
    ],
    "lymphoid_proximal": [
        {
            "gene": "FOXP3",
            "rationale": (
                "Lymphoid-proximal Tregs are FOXP3-high; knockout tests whether "
                "identity loss relieves local suppression of nearby effectors."
            ),
            "citation": {
                "title": "FOXP3 stability determines regulatory T cell suppressive capacity",
                "source": "Immunity (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
        {
            "gene": "IL2RA",
            "rationale": (
                "IL2RA (CD25) sustains Treg fitness in the lymphoid aggregate; "
                "knockout may reduce IL-2 competition with effector T cells."
            ),
            "citation": {
                "title": "CD25 controls regulatory T cell competitive fitness for IL-2",
                "source": "Nature Immunology (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            },
        },
    ],
}


def _bias_tier(gene: str, phenotype: str) -> int:
    """Secondary sort key: nudge checkpoint genes matching the phenotype ahead
    of equally-cited genes. Literature mention count remains the primary signal.
    """
    if "Tex_term" in phenotype and gene in ("PDCD1", "STAT1"):
        return 0
    if "Treg" in phenotype and gene in ("CTLA4", "FOXP3"):
        return 0
    return 1


def _extract_gene_mentions(
    citations: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    mentions: dict[str, list[dict[str, Any]]] = {}
    for c in citations:
        text = f"{c.get('title', '')} {c.get('relevance', '')}"
        for gene, pattern in _GENE_PATTERNS.items():
            if pattern.search(text):
                mentions.setdefault(gene, []).append(c)
    return mentions


def _fallback(cell_id: str, phenotype: str, niche: str, literature_context: str | None) -> dict[str, Any]:
    base = list(FALLBACK_SUGGESTIONS_BY_CONTEXT.get(niche, FALLBACK_SUGGESTIONS_BY_CONTEXT["tumor_core"]))
    if "Tex_term" in phenotype:
        base = sorted(base, key=lambda s: 0 if s["gene"] in ("PDCD1", "STAT1") else 1)
    if "Treg" in phenotype:
        base = sorted(base, key=lambda s: 0 if s["gene"] in ("CTLA4", "FOXP3") else 1)

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
        "source": "fallback",
        "suggestions": suggestions,
    }


def suggest_perturbations(args: dict[str, Any]) -> dict[str, Any]:
    cell_id = args["cell_id"]
    phenotype = args["phenotype"]
    niche = args["niche"]
    literature_context = args.get("literature_context")

    # cell lookup is best-effort context only — a cell_id that doesn't resolve
    # (e.g. a demo cell from a synthetic tissue map) shouldn't block suggestions,
    # since ranking is driven by phenotype/niche + literature, not the cell record.
    cell = get_cell(cell_id)
    effective_phenotype = phenotype or (cell["cell_type"] if cell else "")

    phenotype_label = PHENOTYPE_QUERY_LABEL.get(effective_phenotype, effective_phenotype or "cell")
    query = (
        f"{phenotype_label} {NICHE_READABLE.get(niche, niche)} tumor "
        f"immunosuppressive gene knockout target"
    )
    citations, warning = you_search(query, count=SEARCH_COUNT)
    if warning or not citations:
        return _fallback(cell_id, phenotype, niche, literature_context)

    mentions = _extract_gene_mentions(citations)
    if not mentions:
        return _fallback(cell_id, phenotype, niche, literature_context)

    ranked_genes = sorted(
        mentions.keys(),
        key=lambda g: (-len(mentions[g]), _bias_tier(g, effective_phenotype), g),
    )[:MAX_SUGGESTIONS]

    suggestions = []
    for i, gene in enumerate(ranked_genes):
        gene_citations = mentions[gene]
        top = gene_citations[0]
        n = len(gene_citations)
        source_word = "source" if n == 1 else "sources"
        rationale = (
            f'Mentioned in {n} retrieved {source_word} for {effective_phenotype or "this phenotype"} '
            f'in the {NICHE_READABLE.get(niche, niche)}, e.g. "{top["title"]}": {top["relevance"]}'
        )
        item = {
            "rank": i + 1,
            "gene": gene,
            "rationale": rationale,
            "citations": gene_citations,
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
        "source": "you.com",
        "suggestions": suggestions,
    }
