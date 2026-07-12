"""Gene / protein alias expansion via NCBI Entrez Gene (human)."""

from __future__ import annotations

import re
from typing import Any

import requests

NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Bootstrap for the genes this project hits most often — used when NCBI is unreachable
# for that symbol, then merged with live lookups when available.
_STATIC_ALIASES: dict[str, list[str]] = {
    "PDCD1": ["PD-1", "PD1", "CD279", "PDCD1"],
    "CTLA4": ["CTLA-4", "CD152", "CTLA4"],
    "LAG3": ["LAG-3", "CD223", "LAG3"],
    "HAVCR2": ["TIM-3", "TIM3", "HAVCR2", "CD366"],
    "TIGIT": ["TIGIT", "VSIG9", "VSTM3"],
    "TOX": ["TOX", "KIAA0808"],
    "TCF7": ["TCF1", "TCF-1", "TCF7"],
    "FOXP3": ["FOXP3", "Scurfin", "JM2"],
    "IL7R": ["IL-7R", "CD127", "IL7R"],
    "GZMB": ["Granzyme B", "GZMB", "CGL1"],
    "ENTPD1": ["CD39", "ENTPD1"],
    "TNFRSF9": ["4-1BB", "CD137", "TNFRSF9"],
}

_GENE_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]{1,10})\b")


_STOP = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER", "WAS", "ONE",
    "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD",
    "SEE", "WAY", "WHO", "BOY", "DID", "ITS", "LET", "PUT", "SAY", "SHE", "TOO", "USE",
    "DOES", "WHAT", "WHEN", "WITH", "THIS", "THAT", "FROM", "HAVE", "BEEN", "WERE",
    "WILL", "INTO", "THAN", "THEN", "THEM", "HELP", "CELL", "CELLS", "TUMOR", "HUMAN",
    "MOUSE", "ROLE", "EFFECT", "INCREASE", "DECREASE", "KNOCKOUT", "KNOCKDOWN",
}


def genes_mentioned(*texts: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        upper = text.upper()
        # Prefer known checkpoint / project genes first
        for sym in _STATIC_ALIASES:
            if re.search(rf"\b{re.escape(sym)}\b", upper) or any(
                re.search(rf"\b{re.escape(a.upper())}\b", upper)
                for a in _STATIC_ALIASES[sym]
                if len(a) >= 3
            ):
                if sym not in seen:
                    seen.add(sym)
                    found.append(sym)
        for m in _GENE_TOKEN.finditer(upper):
            tok = m.group(1)
            if tok in _STOP or len(tok) < 3:
                continue
            # Gene-like: contains digit, or already known, or ends with typical suffixes
            if tok in _STATIC_ALIASES or any(c.isdigit() for c in tok) or tok.endswith(
                ("R", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B")
            ):
                if tok not in seen:
                    seen.add(tok)
                    found.append(tok)
    return found


def expand_aliases(symbols: list[str], *, timeout: float = 12.0) -> dict[str, Any]:
    """Return {symbol: [aliases...], all_aliases: [...], incomplete: bool, notes: [...]}."""
    notes: list[str] = []
    by_symbol: dict[str, list[str]] = {}
    incomplete = False

    for raw in symbols:
        sym = raw.strip().upper()
        if not sym:
            continue
        aliases = set(_STATIC_ALIASES.get(sym, [sym]))
        aliases.add(sym)
        try:
            live = _ncbi_aliases(sym, timeout=timeout)
            if live:
                aliases.update(live)
            else:
                notes.append(f"NCBI returned no aliases for {sym}; used local/bootstrap set.")
                incomplete = True
        except Exception as exc:  # noqa: BLE001
            notes.append(f"NCBI alias lookup failed for {sym}: {type(exc).__name__}: {exc}")
            incomplete = True
        by_symbol[sym] = sorted(aliases)

    all_aliases: list[str] = []
    seen: set[str] = set()
    for vals in by_symbol.values():
        for a in vals:
            key = a.upper()
            if key not in seen:
                seen.add(key)
                all_aliases.append(a)

    return {
        "by_symbol": by_symbol,
        "all_aliases": all_aliases,
        "incomplete": incomplete,
        "notes": notes,
    }


def _ncbi_aliases(symbol: str, *, timeout: float) -> list[str]:
    es = requests.get(
        NCBI_ESEARCH,
        params={
            "db": "gene",
            "term": f"{symbol}[sym] AND human[orgn] AND alive[prop]",
            "retmode": "json",
            "retmax": 1,
        },
        timeout=timeout,
    )
    es.raise_for_status()
    ids = (es.json().get("esearchresult") or {}).get("idlist") or []
    if not ids:
        # Fallback: broader search
        es = requests.get(
            NCBI_ESEARCH,
            params={
                "db": "gene",
                "term": f"{symbol}[Gene Name] AND Homo sapiens[Organism]",
                "retmode": "json",
                "retmax": 1,
            },
            timeout=timeout,
        )
        es.raise_for_status()
        ids = (es.json().get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []

    sm = requests.get(
        NCBI_ESUMMARY,
        params={"db": "gene", "id": ids[0], "retmode": "json"},
        timeout=timeout,
    )
    sm.raise_for_status()
    result = sm.json().get("result") or {}
    doc = result.get(ids[0]) or {}
    out = {symbol}
    name = doc.get("name")
    if name:
        out.add(str(name))
    other = doc.get("otheraliases") or ""
    for part in str(other).split(","):
        p = part.strip()
        if p:
            out.add(p)
    desc = doc.get("description")
    if desc and len(str(desc)) < 40:
        out.add(str(desc))
    return sorted(out)
