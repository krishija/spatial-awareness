"""search_literature — real implementation backed by the You.com Search API."""

from __future__ import annotations

import os
from urllib.parse import urlparse
from typing import Any

import requests

YOU_API_KEY = os.environ.get("YOU_API_KEY", "")
SEARCH_URL = "https://api.you.com/v1/search"

BIOMED_DOMAINS = [
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "biorxiv.org",
    "nature.com",
    "cell.com",
    "science.org",
]

# Friendly display names for known domains -- falls back to the raw domain
# if it's not one we recognize, so 'source' always reads sensibly.
DOMAIN_TO_SOURCE = {
    "pubmed.ncbi.nlm.nih.gov": "PubMed",
    "ncbi.nlm.nih.gov": "NCBI",
    "biorxiv.org": "bioRxiv",
    "nature.com": "Nature",
    "cell.com": "Cell",
    "science.org": "Science",
}

MAX_CITATIONS = 5


def _source_name(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")
    return DOMAIN_TO_SOURCE.get(domain, domain)


def search_literature(args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    context = args.get("context") or ""
    search_text = f"{query} {context}".strip()

    citations: list[dict[str, Any]] = []
    try:
        resp = requests.get(
            SEARCH_URL,
            headers={"X-API-Key": YOU_API_KEY},
            params={
                "query": search_text,
                "count": MAX_CITATIONS,
                "boost_domains": ",".join(BIOMED_DOMAINS),
            },
            timeout=15,
        )
        resp.raise_for_status()
        web_results = resp.json().get("results", {}).get("web", [])

        for r in web_results[:MAX_CITATIONS]:
            url = r.get("url", "")
            snippet = (r.get("snippets") or [""])[0]
            citations.append({
                "title": r.get("title", "Untitled"),
                "source": _source_name(url),
                "url": url,
                "relevance": snippet[:200] if snippet else "No snippet available.",
            })
    except requests.RequestException as e:
        return {
            "query": query,
            "context": context or None,
            "citations": [],
            "warning": f"Literature search failed: {e}",
        }

    return {"query": query, "context": context or None, "citations": citations}