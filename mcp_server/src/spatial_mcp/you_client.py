"""Shared You.com Search API client — used by search_literature and suggest_perturbations."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests

SEARCH_URL = "https://api.you.com/v1/search"
_DOTENV_LOADED = False


def _load_dotenv_once() -> None:
    """Pull YOU_API_KEY from a nearby .env if the process didn't export it.

    Looks at cwd and the repo root (two levels above this package). No
    python-dotenv dependency — just KEY=VALUE lines.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    if os.environ.get("YOU_API_KEY"):
        return
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",  # repo root
        Path(__file__).resolve().parents[2] / ".env",  # mcp_server/
    ]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        break


def _api_key() -> str:
    _load_dotenv_once()
    return os.environ.get("YOU_API_KEY", "")

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


def _source_name(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")
    return DOMAIN_TO_SOURCE.get(domain, domain)


def you_search(query: str, count: int = 5) -> tuple[list[dict[str, Any]], str | None]:
    """Run a You.com search. Returns (citations, warning) — warning is set (and
    citations is []) on any request failure so callers can degrade gracefully
    instead of crashing a live demo.
    """
    try:
        resp = requests.get(
            SEARCH_URL,
            headers={"X-API-Key": _api_key()},
            params={
                "query": query,
                "count": count,
                "boost_domains": ",".join(BIOMED_DOMAINS),
            },
            timeout=15,
        )
        resp.raise_for_status()
        web_results = resp.json().get("results", {}).get("web", [])
    except requests.RequestException as e:
        return [], f"Literature search failed: {e}"

    citations: list[dict[str, Any]] = []
    for r in web_results[:count]:
        url = r.get("url", "")
        snippet = (r.get("snippets") or [""])[0]
        citation: dict[str, Any] = {
            "title": r.get("title", "Untitled"),
            "source": _source_name(url),
            "url": url,
        }
        if snippet:
            citation["relevance"] = snippet[:200]
        citations.append(citation)
    return citations, None
