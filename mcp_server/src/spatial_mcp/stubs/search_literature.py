"""Stub: search_literature — swap this file for real teammate logic."""

from __future__ import annotations

from typing import Any

# Curated corpus — fake but formatted like real citations, overlapping frontend suggestions
CORPUS: list[dict[str, Any]] = [
    {
        "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
        "source": "Nature Immunology (simulated)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["PDCD1", "PD-1", "exhaustion", "CD4", "effector", "checkpoint"],
    },
    {
        "title": "TOX reinforces the identity and suppresses reprogramming of exhausted T cells",
        "source": "Nature (simulated)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["TOX", "exhaustion", "epigenetic", "terminal", "Tex"],
    },
    {
        "title": "LAG-3 regulates CD4 T cell exhaustion in the tumor microenvironment",
        "source": "Cancer Cell (simulated)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["LAG3", "LAG-3", "exhaustion", "tumor", "core", "checkpoint"],
    },
    {
        "title": "CTLA-4 controls Treg-mediated restraint of CD4 antitumor responses",
        "source": "Immunity (simulated)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["CTLA4", "CTLA-4", "Treg", "margin", "suppression"],
    },
    {
        "title": "TCF1+ progenitor exhausted T cells sustain responses to checkpoint blockade",
        "source": "Nature Medicine (simulated)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["TCF7", "TCF1", "progenitor", "stemness", "IL7R", "margin"],
    },
    {
        "title": "Spatial niches of T cell exhaustion at the tumor invasive margin",
        "source": "Cell (simulated)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["spatial", "niche", "margin", "core", "lymphoid", "exhaustion"],
    },
    {
        "title": "Granzyme B expression marks reactivatable CD4 effectors near tertiary lymphoid structures",
        "source": "Science Immunology (simulated)",
        "url": "https://pubmed.ncbi.nlm.nih.gov/",
        "keywords": ["GZMB", "effector", "lymphoid", "TLS", "IL7R"],
    },
]


def search_literature(args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    context = args.get("context") or ""
    haystack = f"{query} {context}".lower()

    scored: list[tuple[float, dict[str, Any]]] = []
    for paper in CORPUS:
        score = 0.0
        hits = []
        for kw in paper["keywords"]:
            if kw.lower() in haystack:
                score += 1.0
                hits.append(kw)
        # Soft boost for exhaustion / CD4 always relevant in this domain
        if "exhaust" in haystack and "exhaustion" in paper["keywords"]:
            score += 0.3
        if score > 0:
            relevance = (
                f"Matches query terms: {', '.join(hits)}."
                if hits
                else "Broadly relevant to CD4 exhaustion biology."
            )
            if context:
                relevance += f" Context considered: {context[:80]}."
            scored.append(
                (
                    score,
                    {
                        "title": paper["title"],
                        "source": paper["source"],
                        "url": paper["url"],
                        "relevance": relevance,
                        "score": round(score, 2),
                    },
                )
            )

    scored.sort(key=lambda x: x[0], reverse=True)
    citations = [c for _, c in scored[:5]]

    # Always return at least something useful for demo queries
    if not citations:
        citations = [
            {
                "title": CORPUS[5]["title"],
                "source": CORPUS[5]["source"],
                "url": CORPUS[5]["url"],
                "relevance": "Default spatial-exhaustion background hit for unmatched query.",
                "score": 0.1,
            }
        ]

    return {"query": query, "context": context or None, "citations": citations}
