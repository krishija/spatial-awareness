"""search_literature — structured evidence from literature (not link retrieval).

Pipeline:
  1. Structured context → alias-expanded sub-queries (mechanistic / pathway / interaction)
  2. Parallel You.com search + dedupe by underlying paper (PMID/title), not URL
  3. PubMed E-utilities enrichment when resolvable
  4. Scoped Bedrock extraction: claim + stance (supports|contradicts|tangential)
  5. Session rollup (counts, journals, recency/type splits)
  6. Cache into FindingsStore.literature_cache + optional finding row

Fail-loud on missing YOU_API_KEY or You.com request failure.
Empty-but-informative when search succeeds with zero hits after decomposition
(under-studied claim) — not a soft invented corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from spatial_mcp.memory import get_store
from spatial_mcp.stubs.lit_aliases import expand_aliases, genes_mentioned
from spatial_mcp.stubs.lit_decompose import decompose_queries
from spatial_mcp.stubs.lit_extract import extract_claim_stance
from spatial_mcp.stubs.lit_pubmed import (
    canonical_source_key,
    enrich_pubmed,
    extract_pmid,
    resolve_pmid_from_title,
    source_name,
)

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

MAX_PER_SUBQUERY = 5
MAX_EVIDENCE_CARDS = 8


def search_literature(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    if not query:
        return {
            "ok": False,
            "error": "missing_query",
            "message": "query is required.",
            "evidence_cards": [],
            "sub_queries": [],
        }

    context = (args.get("context") or "").strip()
    hypothesis = (args.get("hypothesis") or query).strip()
    phenotype = args.get("phenotype")
    niche = args.get("niche")
    gene = (args.get("gene") or "").strip() or None
    genes = [str(g).strip() for g in (args.get("genes") or []) if str(g).strip()]
    if gene and gene.upper() not in {g.upper() for g in genes}:
        genes = [gene] + genes
    # Infer genes from free text when not provided
    if not genes:
        genes = genes_mentioned(query, context, hypothesis)[:4]

    if not YOU_API_KEY:
        return {
            "ok": False,
            "error": "missing_api_key",
            "query": query,
            "context": context or None,
            "evidence_cards": [],
            "sub_queries": [],
            "message": "YOU_API_KEY is not set — refusing to invent citations.",
        }

    # Bedrock required for stance extraction
    try:
        from spatial_mcp.agent.bedrock import BedrockConverse, load_bearer_token

        load_bearer_token()
        bedrock = BedrockConverse(max_tokens=800)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": "missing_bedrock_auth",
            "query": query,
            "evidence_cards": [],
            "sub_queries": [],
            "message": (
                "AWS_BEARER_TOKEN_BEDROCK required for claim/stance extraction — "
                f"{type(exc).__name__}: {exc}"
            ),
        }

    alias_info = expand_aliases(genes) if genes else {
        "by_symbol": {},
        "all_aliases": [],
        "incomplete": False,
        "notes": ["No gene symbols provided or inferred — queries use free text only."],
    }
    aliases = alias_info["all_aliases"]

    cache_key = _cache_key(query, hypothesis, aliases, phenotype, niche)
    store = get_store()
    cached = store.get_literature_cache(cache_key)
    if cached and cached.get("ok") is True:
        cached["from_cache"] = True
        return cached

    structured = {
        "query": query,
        "context": context,
        "hypothesis": hypothesis,
        "phenotype": phenotype,
        "niche": niche,
        "gene": gene,
        "genes": genes,
    }
    sub_queries = decompose_queries(structured, aliases)

    # Parallel You.com searches
    raw_hits: list[dict[str, Any]] = []
    search_errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(sub_queries)))) as pool:
        futs = {
            pool.submit(_you_search, sq["text"], sq["kind"]): sq for sq in sub_queries
        }
        for fut in as_completed(futs):
            sq = futs[fut]
            try:
                hits = fut.result()
                for h in hits:
                    h["sub_query_kind"] = sq["kind"]
                    h["sub_query_text"] = sq["text"]
                raw_hits.extend(hits)
            except Exception as exc:  # noqa: BLE001
                search_errors.append(
                    f"{sq['kind']}: {type(exc).__name__}: {exc}"
                )

    if search_errors and not raw_hits:
        return {
            "ok": False,
            "error": "literature_search_failed",
            "query": query,
            "context": context or None,
            "sub_queries": sub_queries,
            "evidence_cards": [],
            "message": "You.com request(s) failed: " + " | ".join(search_errors),
        }

    # Dedupe by underlying source
    merged: dict[str, dict[str, Any]] = {}
    for hit in raw_hits:
        pmid = extract_pmid(hit.get("url") or "", hit.get("title") or "")
        key = canonical_source_key(hit.get("url") or "", hit.get("title") or "", pmid)
        if key not in merged:
            merged[key] = hit
            merged[key]["pmid"] = pmid
            merged[key]["matched_sub_queries"] = [hit.get("sub_query_kind")]
        else:
            kinds = merged[key].setdefault("matched_sub_queries", [])
            k = hit.get("sub_query_kind")
            if k and k not in kinds:
                kinds.append(k)

    # Enrich + extract (bound concurrency)
    cards: list[dict[str, Any]] = []
    items = list(merged.values())[:MAX_EVIDENCE_CARDS]

    def _process(hit: dict[str, Any]) -> dict[str, Any]:
        return _enrich_and_extract(hit, hypothesis=hypothesis, bedrock=bedrock)

    with ThreadPoolExecutor(max_workers=4) as pool:
        cards = list(pool.map(_process, items))

    rollup = _build_rollup(cards)

    # Informative empty result — under-studied, not a soft failure
    if not cards:
        payload = {
            "ok": True,
            "backend": "you_com+pubmed+bedrock",
            "query": query,
            "context": context or None,
            "hypothesis": hypothesis,
            "genes": genes,
            "aliases": alias_info,
            "sub_queries": sub_queries,
            "evidence_cards": [],
            "rollup": rollup,
            "under_studied": True,
            "message": (
                "No literature hits after alias-expanded sub-queries — this specific "
                "claim may be under-studied in indexed sources."
            ),
            "search_errors": search_errors or None,
            "from_cache": False,
        }
        store.put_literature_cache(
            cache_key=cache_key,
            query_norm=hypothesis.lower(),
            aliases=aliases,
            payload=payload,
        )
        return payload

    # Persist rollup into findings for query_prior_findings reuse
    finding_summary = _rollup_summary(hypothesis, rollup, genes)
    try:
        finding = store.record_literature_finding(
            gene=genes[0] if genes else None,
            niche=niche if isinstance(niche, str) else None,
            summary=finding_summary,
            evidence_cards=cards,
            sample_id="literature",
        )
    except Exception:  # noqa: BLE001
        finding = None

    payload = {
        "ok": True,
        "backend": "you_com+pubmed+bedrock",
        "query": query,
        "context": context or None,
        "hypothesis": hypothesis,
        "genes": genes,
        "aliases": alias_info,
        "sub_queries": sub_queries,
        "evidence_cards": cards,
        "rollup": rollup,
        "under_studied": False,
        "finding_id": (finding or {}).get("id"),
        "search_errors": search_errors or None,
        "from_cache": False,
        # Back-compat slim citations list for older callers
        "citations": [
            {
                "title": c.get("title"),
                "source": c.get("source"),
                "url": c.get("url"),
                "relevance": c.get("claim") or c.get("extraction_note"),
                "stance": c.get("stance"),
            }
            for c in cards
        ],
    }
    store.put_literature_cache(
        cache_key=cache_key,
        query_norm=hypothesis.lower(),
        aliases=aliases,
        payload=payload,
    )
    # Additive graph side-effect (does not change return schema)
    try:
        from spatial_mcp.graph import insert_edge

        for card in cards:
            stance = card.get("stance") or "tangential"
            if stance == "tangential":
                continue
            for g in genes[:3] or [None]:
                if not g:
                    continue
                rel = (
                    "literature_supports"
                    if stance == "supports"
                    else "literature_contradicts"
                )
                direction = "up" if stance == "supports" else "down"
                insert_edge(
                    g,
                    rel,
                    (card.get("claim") or hypothesis)[:80],
                    source_type="literature",
                    source_id=(
                        f"pmid:{card['pmid']}"
                        if card.get("pmid")
                        else card.get("url") or f"lit:{card.get('title')}"
                    ),
                    confidence=0.7 if card.get("extraction_ok") else 0.4,
                    cell_type_context=phenotype if isinstance(phenotype, str) else None,
                    sample_context=niche if isinstance(niche, str) else None,
                    metadata={
                        "direction": direction,
                        "stance": stance,
                        "year": card.get("year"),
                    },
                )
    except Exception:  # noqa: BLE001
        pass
    return payload


def _you_search(search_text: str, kind: str) -> list[dict[str, Any]]:
    resp = requests.get(
        SEARCH_URL,
        headers={"X-API-Key": YOU_API_KEY},
        params={
            "query": search_text,
            "count": MAX_PER_SUBQUERY,
            "boost_domains": ",".join(BIOMED_DOMAINS),
        },
        timeout=20,
    )
    resp.raise_for_status()
    web_results = resp.json().get("results", {}).get("web", [])
    out = []
    for r in web_results[:MAX_PER_SUBQUERY]:
        url = r.get("url", "")
        snippet = (r.get("snippets") or [""])[0]
        out.append(
            {
                "title": r.get("title", "Untitled"),
                "url": url,
                "source": source_name(url),
                "snippet": snippet[:500] if snippet else "",
            }
        )
    return out


def _enrich_and_extract(
    hit: dict[str, Any], *, hypothesis: str, bedrock: Any
) -> dict[str, Any]:
    pmid = hit.get("pmid") or extract_pmid(hit.get("url") or "", hit.get("title") or "")
    metadata_confidence = "low"
    year = None
    journal = None
    pub_types: list[str] = []
    abstract = hit.get("snippet") or ""
    title = hit.get("title") or "Untitled"
    meta_source = "search_api_snippet"

    if not pmid and "pubmed" in (hit.get("url") or "").lower():
        try:
            pmid = resolve_pmid_from_title(title)
        except Exception:  # noqa: BLE001
            pmid = None

    if pmid:
        try:
            enriched = enrich_pubmed(pmid)
            if enriched:
                title = enriched.get("title") or title
                abstract = enriched.get("abstract") or abstract
                year = enriched.get("year")
                journal = enriched.get("journal")
                pub_types = enriched.get("publication_types") or []
                metadata_confidence = "high"
                meta_source = "pubmed_efetch"
                if not hit.get("url"):
                    hit["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                hit["source"] = "PubMed"
        except Exception as exc:  # noqa: BLE001
            meta_source = f"pubmed_efetch_failed:{type(exc).__name__}"

    extracted = extract_claim_stance(
        hypothesis=hypothesis,
        title=title,
        text=abstract,
        client=bedrock,
    )

    return {
        "title": title,
        "source": hit.get("source") or source_name(hit.get("url") or ""),
        "url": hit.get("url") or (
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        ),
        "pmid": pmid,
        "year": year,
        "journal": journal,
        "publication_type": pub_types[0] if pub_types else None,
        "publication_types": pub_types,
        "metadata_confidence": metadata_confidence,
        "metadata_source": meta_source,
        "claim": extracted.get("claim"),
        "biological_context": extracted.get("biological_context"),
        "stance": extracted.get("stance") or "tangential",
        "extraction_note": extracted.get("extraction_note"),
        "extraction_ok": extracted.get("extraction_ok", False),
        "matched_sub_queries": hit.get("matched_sub_queries") or [],
        "snippet": (hit.get("snippet") or "")[:240],
    }


def _build_rollup(cards: list[dict[str, Any]]) -> dict[str, Any]:
    supports = [c for c in cards if c.get("stance") == "supports"]
    contradicts = [c for c in cards if c.get("stance") == "contradicts"]
    tangential = [c for c in cards if c.get("stance") == "tangential"]

    journals = sorted(
        {
            (c.get("journal") or c.get("source") or "unknown")
            for c in cards
            if c.get("stance") in ("supports", "contradicts")
        }
    )

    def _years(group: list[dict[str, Any]]) -> list[int]:
        ys = []
        for c in group:
            y = c.get("year")
            if y and str(y).isdigit():
                ys.append(int(y))
        return ys

    def _types(group: list[dict[str, Any]]) -> list[str]:
        out = []
        for c in group:
            for t in c.get("publication_types") or []:
                out.append(t)
            if c.get("publication_type") and c["publication_type"] not in out:
                out.append(c["publication_type"])
        return sorted(set(out))

    sy, cy = _years(supports), _years(contradicts)
    narrative_bits = []
    if supports and contradicts:
        narrative_bits.append(
            f"{len(supports)} supporting vs {len(contradicts)} contradicting sources"
        )
        if sy and cy:
            narrative_bits.append(
                f"support median year ~{_median(sy)}, contradict median year ~{_median(cy)}"
            )
        st, ct = _types(supports), _types(contradicts)
        if st or ct:
            narrative_bits.append(
                f"support types={st or ['unspecified']}; contradict types={ct or ['unspecified']}"
            )
    elif supports:
        narrative_bits.append(f"{len(supports)} supporting source(s), no contradictions retrieved")
    elif contradicts:
        narrative_bits.append(
            f"{len(contradicts)} contradicting source(s), no supporting sources retrieved"
        )
    else:
        narrative_bits.append(
            "No sources with clear support/contradict stance — mostly tangential or empty"
        )

    return {
        "n_total": len(cards),
        "n_supports": len(supports),
        "n_contradicts": len(contradicts),
        "n_tangential": len(tangential),
        "independent_venues": journals,
        "n_independent_venues": len(journals),
        "support_years": sy,
        "contradict_years": cy,
        "support_publication_types": _types(supports),
        "contradict_publication_types": _types(contradicts),
        "narrative": "; ".join(narrative_bits) + ".",
    }


def _median(vals: list[int]) -> int:
    s = sorted(vals)
    return s[len(s) // 2]


def _rollup_summary(hypothesis: str, rollup: dict[str, Any], genes: list[str]) -> str:
    g = ",".join(genes[:3]) if genes else "unspecified"
    return (
        f"Literature evidence for [{g}] / «{hypothesis[:160]}»: "
        f"{rollup.get('n_supports', 0)} support, {rollup.get('n_contradicts', 0)} contradict, "
        f"{rollup.get('n_tangential', 0)} tangential across "
        f"{rollup.get('n_independent_venues', 0)} venues. {rollup.get('narrative', '')}"
    )


def _cache_key(
    query: str,
    hypothesis: str,
    aliases: list[str],
    phenotype: Any,
    niche: Any,
) -> str:
    blob = json.dumps(
        {
            "q": query.strip().lower(),
            "h": hypothesis.strip().lower(),
            "a": sorted({a.upper() for a in aliases}),
            "p": (phenotype or ""),
            "n": (niche or ""),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:40]
