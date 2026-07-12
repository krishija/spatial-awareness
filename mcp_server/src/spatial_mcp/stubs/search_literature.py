"""search_literature — You.com Search API with curated biomedical fallback.

Primary path: You.com API via the shared you_client (requires YOU_API_KEY).
If the key is missing or the API fails (e.g. 402), falls back to a curated
corpus so the agent loop stays demoable offline / without billing.
"""

from __future__ import annotations

from typing import Any

from spatial_mcp.you_client import you_search

MAX_CITATIONS = 5

# Curated fallback — same shape as live citations; used when You.com is unavailable.
FALLBACK_CORPUS: list[dict[str, Any]] = [
    {
        "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
        "source": "Nature Immunology (fallback corpus)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["PDCD1", "PD-1", "exhaustion", "CD4", "effector", "checkpoint"],
    },
    {
        "title": "TOX reinforces the identity and suppresses reprogramming of exhausted T cells",
        "source": "Nature (fallback corpus)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["TOX", "exhaustion", "epigenetic", "terminal", "Tex"],
    },
    {
        "title": "LAG-3 regulates CD4 T cell exhaustion in the tumor microenvironment",
        "source": "Cancer Cell (fallback corpus)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["LAG3", "LAG-3", "exhaustion", "tumor", "core", "checkpoint"],
    },
    {
        "title": "CTLA-4 controls Treg-mediated restraint of CD4 antitumor responses",
        "source": "Immunity (fallback corpus)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["CTLA4", "CTLA-4", "Treg", "margin", "suppression"],
    },
    {
        "title": "TCF1+ progenitor exhausted T cells sustain responses to checkpoint blockade",
        "source": "Nature Medicine (fallback corpus)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["TCF7", "TCF1", "progenitor", "stemness", "IL7R", "margin"],
    },
    {
        "title": "Spatial niches of T cell exhaustion at the tumor invasive margin",
        "source": "Cell (fallback corpus)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["spatial", "niche", "margin", "core", "lymphoid", "exhaustion"],
    },
]


def _fallback_search(query: str, context: str) -> list[dict[str, Any]]:
    haystack = f"{query} {context}".lower()
    scored: list[tuple[float, dict[str, Any]]] = []
    for paper in FALLBACK_CORPUS:
        score = 0.0
        hits = []
        for kw in paper["keywords"]:
            if kw.lower() in haystack:
                score += 1.0
                hits.append(kw)
        if "exhaust" in haystack and "exhaustion" in paper["keywords"]:
            score += 0.3
        if score <= 0:
            continue
        scored.append(
            (
                score,
                {
                    "title": paper["title"],
                    "source": paper["source"],
                    "url": paper["url"],
                    "relevance": (
                        f"Fallback corpus match: {', '.join(hits)}."
                        if hits
                        else "Fallback corpus broad match."
                    ),
                    "score": round(score, 2),
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        p = FALLBACK_CORPUS[5]
        return [
            {
                "title": p["title"],
                "source": p["source"],
                "url": p["url"],
                "relevance": "Default spatial-exhaustion fallback hit.",
                "score": 0.1,
            }
        ]
    return [c for _, c in scored[:MAX_CITATIONS]]


def search_literature(args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    context = args.get("context") or ""
    search_text = f"{query} {context}".strip()

    citations, warning = you_search(search_text, count=MAX_CITATIONS)
    if not citations:
        warning = (
            f"{warning} Using curated fallback corpus."
            if warning
            else "You.com returned no results — using curated fallback corpus."
        )
        citations = _fallback_search(query, context)

    out: dict[str, Any] = {
        "query": query,
        "context": context or None,
        "citations": citations,
    }
    if warning:
        out["warning"] = warning
    return out
