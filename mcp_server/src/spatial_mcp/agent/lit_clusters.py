"""Literature independence clustering — evidence count = clusters, not papers.

Citation cascades: five retrieved papers can trace to one primary experiment.
Signals: shared PMID refs, shared authors, publication type (reviews ≠ new),
shared dataset/accession, and within-set citation links when available.
"""

from __future__ import annotations

from typing import Any


def _norm_author(a: str) -> str:
    return " ".join(a.lower().replace(",", " ").split())


def _pub_types(card: dict[str, Any]) -> list[str]:
    pts = card.get("publication_types") or []
    if card.get("publication_type"):
        pts = list(pts) + [card["publication_type"]]
    return [str(p).lower() for p in pts]


def _is_review(card: dict[str, Any]) -> bool:
    pts = _pub_types(card)
    return any("review" in p and "systematic" not in p for p in pts) and not any(
        "meta-analysis" in p or "systematic" in p for p in pts
    )


def _pmid(card: dict[str, Any]) -> str | None:
    if card.get("pmid"):
        return str(card["pmid"])
    url = str(card.get("url") or "")
    if "pubmed.ncbi.nlm.nih.gov/" in url:
        return url.rstrip("/").split("/")[-1] or None
    return None


def _author_key_safe(card: dict[str, Any]) -> frozenset[str]:
    authors = card.get("authors") or card.get("author_list") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(";") if a.strip()]
    norms = [_norm_author(a) for a in authors if a]
    return frozenset(norms[:5])


def _refs(card: dict[str, Any]) -> frozenset[str]:
    raw = card.get("references") or card.get("cited_pmids") or []
    return frozenset(str(x) for x in raw)


def _accession(card: dict[str, Any]) -> str | None:
    for k in ("accession", "dataset", "geo", "sra"):
        if card.get(k):
            return str(card[k]).upper()
    ctx = card.get("biological_context") or {}
    if ctx.get("accession"):
        return str(ctx["accession"]).upper()
    return None


def cluster_literature_cards(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Cluster cards into independent experimental claims.

    Returns:
      clusters: list of {cluster_id, member_indices, primary_index, is_review_only}
      card_cluster_ids: parallel list of cluster_id per card
      summary: human-readable "N papers → M independent experimental claims"
    """
    n = len(cards)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    pmids = [_pmid(c) for c in cards]
    authors = [_author_key_safe(c) for c in cards]
    refs = [_refs(c) for c in cards]
    accessions = [_accession(c) for c in cards]

    for i in range(n):
        for j in range(i + 1, n):
            # Same PMID
            if pmids[i] and pmids[i] == pmids[j]:
                union(i, j)
                continue
            # Shared accession / dataset
            if accessions[i] and accessions[i] == accessions[j]:
                union(i, j)
                continue
            # Substantial author overlap (≥2 shared)
            if authors[i] and authors[j] and len(authors[i] & authors[j]) >= 2:
                union(i, j)
                continue
            # One cites the other by PMID
            if pmids[i] and pmids[i] in refs[j]:
                union(i, j)
                continue
            if pmids[j] and pmids[j] in refs[i]:
                union(i, j)
                continue
            # Shared reference backbone (≥3 shared cited PMIDs) → likely same lineage
            if refs[i] and refs[j] and len(refs[i] & refs[j]) >= 3:
                union(i, j)
                continue

    # Attach reviews to the primary they cite when possible
    for i, c in enumerate(cards):
        if not _is_review(c):
            continue
        for j in range(n):
            if i == j or _is_review(cards[j]):
                continue
            if pmids[j] and pmids[j] in refs[i]:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    clusters = []
    card_cluster_ids: list[str] = [""] * n
    for rank, (_root, members) in enumerate(sorted(groups.items(), key=lambda x: min(x[1]))):
        cid = f"litc-{rank + 1}"
        # Primary = non-review with highest metadata confidence, else first
        primaries = [m for m in members if not _is_review(cards[m])]
        if not primaries:
            primaries = members
        primary = max(
            primaries,
            key=lambda m: (
                1 if cards[m].get("extraction_ok") else 0,
                1 if cards[m].get("metadata_confidence") == "high" else 0,
                1 if (cards[m].get("stance") or "") == "supports" else 0,
            ),
        )
        for m in members:
            card_cluster_ids[m] = cid
            cards[m]["lit_cluster_id"] = cid
            cards[m]["independence_cluster"] = f"literature:{cid}"
        clusters.append(
            {
                "cluster_id": cid,
                "member_indices": members,
                "primary_index": primary,
                "n_members": len(members),
                "is_review_only": all(_is_review(cards[m]) for m in members),
                "pmids": [pmids[m] for m in members if pmids[m]],
            }
        )

    summary = f"{n} papers → {len(clusters)} independent experimental claims."
    return {
        "n_papers": n,
        "n_independent_claims": len(clusters),
        "clusters": clusters,
        "card_cluster_ids": card_cluster_ids,
        "summary": summary,
    }
