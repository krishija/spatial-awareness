"""PubMed / NCBI E-utilities enrichment for literature hits."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

import requests

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

PMID_RE = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|pmid[=:]?\s*)(\d{5,9})", re.I)
PMC_RE = re.compile(r"PMC(\d+)", re.I)

DOMAIN_TO_SOURCE = {
    "pubmed.ncbi.nlm.nih.gov": "PubMed",
    "ncbi.nlm.nih.gov": "NCBI",
    "biorxiv.org": "bioRxiv",
    "nature.com": "Nature",
    "cell.com": "Cell",
    "science.org": "Science",
    "sciencedirect.com": "ScienceDirect",
    "onlinelibrary.wiley.com": "Wiley",
}


def source_name(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")
    for key, name in DOMAIN_TO_SOURCE.items():
        if key in domain:
            return name
    return domain or "unknown"


def extract_pmid(url: str, title: str = "") -> str | None:
    for text in (url, title):
        m = PMID_RE.search(text or "")
        if m:
            return m.group(1)
    return None


def canonical_source_key(url: str, title: str, pmid: str | None = None) -> str:
    """Dedup key by underlying paper, not raw URL string."""
    if pmid:
        return f"pmid:{pmid}"
    m = PMC_RE.search(url or "")
    if m:
        return f"pmc:{m.group(1)}"
    # Normalize title
    t = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    if len(t) >= 20:
        return f"title:{t[:120]}"
    path = urlparse(url or "").path.rstrip("/")
    return f"url:{urlparse(url or '').netloc}{path}".lower()


def enrich_pubmed(pmid: str, *, timeout: float = 15.0) -> dict[str, Any] | None:
    """Fetch abstract, year, journal, publication types for a PMID."""
    resp = requests.get(
        NCBI_EFETCH,
        params={
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml",
            "rettype": "abstract",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    article = root.find(".//PubmedArticle")
    if article is None:
        return None

    title_el = article.find(".//ArticleTitle")
    title = "".join(title_el.itertext()).strip() if title_el is not None else ""

    abstract_parts = []
    for abs_el in article.findall(".//Abstract/AbstractText"):
        label = abs_el.attrib.get("Label")
        text = "".join(abs_el.itertext()).strip()
        if label:
            abstract_parts.append(f"{label}: {text}")
        elif text:
            abstract_parts.append(text)
    abstract = "\n".join(abstract_parts)

    journal_el = article.find(".//Journal/Title")
    journal = (journal_el.text or "").strip() if journal_el is not None else ""

    year = None
    for path in (
        ".//PubDate/Year",
        ".//ArticleDate/Year",
        ".//DateCompleted/Year",
    ):
        y = article.find(path)
        if y is not None and y.text:
            year = y.text.strip()
            break
    if year is None:
        medline = article.find(".//PubDate/MedlineDate")
        if medline is not None and medline.text:
            m = re.search(r"(19|20)\d{2}", medline.text)
            if m:
                year = m.group(0)

    pub_types = []
    for pt in article.findall(".//PublicationType"):
        if pt.text:
            pub_types.append(pt.text.strip())

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "year": year,
        "journal": journal,
        "publication_types": pub_types,
        "metadata_confidence": "high",
        "metadata_source": "pubmed_efetch",
    }


def resolve_pmid_from_title(title: str, *, timeout: float = 12.0) -> str | None:
    if not title or len(title) < 15:
        return None
    resp = requests.get(
        NCBI_ESEARCH,
        params={
            "db": "pubmed",
            "term": f"{title}[Title]",
            "retmode": "json",
            "retmax": 1,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    ids = (resp.json().get("esearchresult") or {}).get("idlist") or []
    return ids[0] if ids else None
