"""Independence clustering for evidence.

Principle (load-bearing — do not regress):
  Evidence combines by independence, not by count.

Two simulation seeds are the same systematic bias twice.
Five papers citing one primary experiment are one experimental claim.
Within an independence cluster, only the strongest diagnostic item contributes
its full log-LR; the rest contribute ~0 bits (recorded as redundant).
"""

from __future__ import annotations

from typing import Any, Protocol


class _EvidenceLike(Protocol):
    evidence_type: str
    source_id: str
    polarity: str
    strength: float
    metadata: dict[str, Any]


# Source types grounded in an observation of the world (not a generative guess).
GROUNDED_TYPES = frozenset({"literature", "measured", "cohort_prognostic"})


def independence_key(item: _EvidenceLike) -> str:
    """Cluster key: same key ⇒ treated as conditionally dependent given H."""
    md = item.metadata or {}
    et = item.evidence_type

    if md.get("independence_cluster"):
        return str(md["independence_cluster"])

    if et == "simulation":
        # All sims for the same gene share one cluster — n seeds ≈ 1 draw
        gene = (md.get("gene") or item.source_id or "unk").upper()
        return f"simulation:{gene}"

    if et == "literature":
        if md.get("lit_cluster_id"):
            return f"literature:{md['lit_cluster_id']}"
        pmid = md.get("pmid")
        if not pmid and item.source_id.startswith("pmid:"):
            pmid = item.source_id.replace("pmid:", "", 1)
        if pmid:
            return f"literature:pmid:{pmid}"
        return f"literature:{item.source_id}"

    if et == "measured":
        # Same gene's measured hits are one experimental claim family, not n
        gene = (md.get("gene") or "").upper()
        accession = md.get("accession") or md.get("dataset") or item.source_id
        if gene:
            return f"measured:{gene}:{accession}"
        return f"measured:{accession}"

    if et == "cohort_prognostic":
        cancer = md.get("cancer_type") or "cohort"
        genes = md.get("genes") or []
        gkey = "+".join(str(g).upper() for g in genes[:4]) or "sig"
        return f"cohort:{cancer}:{gkey}"

    if et == "cell_context":
        return f"cell_context:{md.get('sample_id') or item.source_id}"

    if et == "atlas_mapping":
        return f"atlas:{item.source_id}"

    if et == "suggestion":
        return f"suggestion:{md.get('gene') or item.source_id}"

    if et == "prior_finding":
        # Memory reads combine by gene (or the neutral "queried" marker) — not by
        # finding id. Prevents n self-citations counting as n independent sources.
        if md.get("queried_priors") and item.source_id == "query_prior_findings":
            return "prior:query"
        gene = (md.get("gene") or "").upper()
        if gene:
            return f"prior:gene:{gene}"
        return f"prior:{item.source_id}"

    if et == "red_team":
        return f"red_team:{item.source_id}"

    return f"{et}:{item.source_id}"


def item_gene(item: _EvidenceLike) -> str | None:
    """Normalized gene tag on an evidence item, if any."""
    md = item.metadata or {}
    g = md.get("gene")
    if g:
        return str(g).strip().upper() or None
    genes = md.get("genes")
    if isinstance(genes, list) and genes:
        return str(genes[0]).strip().upper() or None
    return None


def gene_matches_hypothesis(item: _EvidenceLike, hyp_gene: str | None) -> bool:
    """True if item has no gene tag, or its gene matches the locked hypothesis gene.

    Untagged scaffolding (cell_context, red_team, neutral query markers) is allowed
    through; gene-tagged evidence for a *different* gene does not support H.
    """
    if not hyp_gene or hyp_gene in ("", "UNSPECIFIED"):
        return True
    tagged = item_gene(item)
    if tagged is None:
        # Cohort may list multiple genes
        md = item.metadata or {}
        genes = md.get("genes")
        if isinstance(genes, list) and genes:
            return hyp_gene.upper() in {str(g).strip().upper() for g in genes}
        return True
    return tagged == hyp_gene.upper()


def is_self_citation_prior(
    item: _EvidenceLike, *, hyp_gene: str | None, hyp_claim: str | None
) -> bool:
    """Prior finding that is our own earlier write of the same hypothesis → 0 bits."""
    if item.evidence_type != "prior_finding":
        return False
    if item.polarity == "neutral":
        return False
    md = item.metadata or {}
    if md.get("self_generated") is True:
        return True
    summary = (item.summary or "").strip()
    gene = item_gene(item)
    if hyp_gene and gene and gene == hyp_gene.upper():
        # Same-gene memory of a recorded agent claim (confidence=… marker from record_finding)
        if "(confidence=" in summary.lower() or summary.lower().startswith("crispr knockout"):
            return True
    if hyp_claim and hyp_claim[:60] and hyp_claim[:60] in summary:
        return True
    return False


def has_external_grounded_source(
    items: list[_EvidenceLike],
    *,
    bits_by_source_id: dict[str, float] | None = None,
    min_abs_bits: float = 0.05,
) -> bool:
    """Grounded observation (lit/measured/cohort) with non-trivial contributing bits.

    Priors and cell_context alone cannot open REPORT.
    """
    for i in items:
        if i.evidence_type not in GROUNDED_TYPES:
            continue
        if i.polarity == "neutral":
            continue
        if bits_by_source_id is not None:
            if abs(bits_by_source_id.get(i.source_id, 0.0)) >= min_abs_bits:
                return True
        else:
            return True
    return False


def cluster_items(items: list[_EvidenceLike]) -> dict[str, list[_EvidenceLike]]:
    clusters: dict[str, list[_EvidenceLike]] = {}
    for it in items:
        clusters.setdefault(independence_key(it), []).append(it)
    return clusters


def count_independent_sources(
    items: list[_EvidenceLike],
    *,
    min_abs_bits: float = 0.05,
    bits_by_source_id: dict[str, float] | None = None,
) -> int:
    """Count independence clusters that carry non-trivial signed bits."""
    clusters = cluster_items(items)
    n = 0
    for _key, members in clusters.items():
        if bits_by_source_id is not None:
            mag = max(abs(bits_by_source_id.get(m.source_id, 0.0)) for m in members)
        else:
            if not any(m.polarity != "neutral" for m in members):
                continue
            mag = max(
                (float(m.strength or 0) for m in members if m.polarity != "neutral"),
                default=0.0,
            )
            mag = max(mag, min_abs_bits)
        if mag >= min_abs_bits:
            n += 1
    return n


def has_grounded_source(items: list[_EvidenceLike]) -> bool:
    return any(
        i.evidence_type in GROUNDED_TYPES and i.polarity != "neutral" for i in items
    )


def summarize_clusters(items: list[_EvidenceLike]) -> dict[str, Any]:
    clusters = cluster_items(items)
    return {
        "n_items": len(items),
        "n_independent_clusters": len(clusters),
        "clusters": [
            {
                "key": k,
                "n": len(v),
                "types": sorted({m.evidence_type for m in v}),
                "source_ids": [m.source_id for m in v],
            }
            for k, v in sorted(clusters.items())
        ],
    }
