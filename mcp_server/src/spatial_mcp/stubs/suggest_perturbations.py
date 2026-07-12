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

from spatial_mcp.stubs.cell_store import get_cell
from spatial_mcp.you_client import you_search

MAX_SUGGESTIONS = 5
SEARCH_COUNT = 8

# Genes this stub will look for in literature results, keyed by the canonical
# symbol simulate_perturbations expects (so a suggested gene can actually be
# run through a perturbation). Biomedical literature/abstracts overwhelmingly
# use the common hyphenated name (PD-1, LAG-3, TIM-3, CD39, ...) rather than
# the bare HGNC symbol, so each gene matches on its common aliases too —
# matching only the bare symbol was silently missing most real mentions.
GENE_ALIASES: dict[str, list[str]] = {
    "PDCD1": ["PDCD1", "PD-1", "PD1"],
    "TCF7": ["TCF7", "TCF-1", "TCF1"],
    "TOX": ["TOX"],
    "LAG3": ["LAG3", "LAG-3"],
    "GZMB": ["GZMB", "Granzyme B", "Granzyme-B"],
    "IL7R": ["IL7R", "IL-7R", "IL7Ra", "CD127"],
    "CTLA4": ["CTLA4", "CTLA-4"],
    "FOXP3": ["FOXP3"],
    "HAVCR2": ["HAVCR2", "TIM-3", "TIM3"],
    "ENTPD1": ["ENTPD1", "CD39"],
    "CXCL13": ["CXCL13"],
    "TIGIT": ["TIGIT"],
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


def _bias_tier(gene: str, phenotype: str) -> int:
    """Secondary sort key: nudge checkpoint genes matching the phenotype ahead
    of equally-cited genes. Literature mention count remains the primary signal.
    """
    if "Tex_term" in phenotype and gene in ("PDCD1", "TOX"):
        return 0
    if "Treg" in phenotype and gene == "CTLA4":
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
        base = sorted(base, key=lambda s: 0 if s["gene"] in ("PDCD1", "TOX") else 1)
    if "Treg" in phenotype:
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
        "source": "fallback",
        "suggestions": suggestions,
    }


def suggest_perturbations(args: dict[str, Any]) -> dict[str, Any]:
    cell_id = args["cell_id"]
    phenotype = args["phenotype"]
    niche = args["niche"]
    literature_context = args.get("literature_context")

    try:
        cell = get_cell(cell_id)
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": "data_missing",
            "message": str(exc),
            "cell_id": cell_id,
            "suggestions": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "data_load_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "cell_id": cell_id,
            "suggestions": [],
        }

    # Phenotype from args wins; cell record fills gaps when present.
    effective_phenotype = phenotype or (cell["cell_type"] if cell else "")
    if not effective_phenotype:
        return {
            "ok": False,
            "error": "cell_not_found",
            "message": (
                f"No cell with id '{cell_id}' in cells.parquet and no phenotype provided."
            ),
            "cell_id": cell_id,
            "suggestions": [],
        }

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
        "ok": True,
        "cell_id": cell_id,
        "phenotype": phenotype,
        "niche": niche,
        "source": "you.com",
        "suggestions": suggestions,
    }
