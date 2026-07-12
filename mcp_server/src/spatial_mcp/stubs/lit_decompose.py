"""Decompose structured literature context into targeted sub-queries."""

from __future__ import annotations

from typing import Any


INTERACTION_HINTS = (
    "synergy",
    "redundant",
    "redundancy",
    "compensat",
    "epistas",
    "combin",
    "dual",
    "together",
    "vs ",
    " versus ",
    " and ",
)


def decompose_queries(args: dict[str, Any], aliases: list[str]) -> list[dict[str, str]]:
    """Build mechanistic / pathway / interaction sub-queries.

    Each item: {kind, text}.
    """
    query = (args.get("query") or "").strip()
    context = (args.get("context") or "").strip()
    hypothesis = (args.get("hypothesis") or query).strip()
    phenotype = (args.get("phenotype") or "").strip()
    niche = (args.get("niche") or "").strip()
    gene = (args.get("gene") or "").strip()
    genes = [str(g).strip() for g in (args.get("genes") or []) if str(g).strip()]
    if gene and gene.upper() not in {g.upper() for g in genes}:
        genes = [gene] + genes

    primary = aliases[0] if aliases else (genes[0] if genes else "")
    alias_clause = " OR ".join(f'"{a}"' for a in aliases[:6]) if aliases else primary

    bio_bits = []
    if phenotype:
        bio_bits.append(phenotype.replace("_", " "))
    if niche:
        bio_bits.append(niche.replace("_", " "))
    if context and context.lower() not in " ".join(bio_bits).lower():
        bio_bits.append(context)
    bio_ctx = " ".join(bio_bits) if bio_bits else "CD4 T cell exhaustion tumor microenvironment"

    sub: list[dict[str, str]] = []

    # 1. Precise mechanistic / claim-shaped
    mech = hypothesis if hypothesis else query
    if primary and primary.upper() not in mech.upper():
        mech = f"{mech} {primary}".strip()
    if bio_ctx and bio_ctx.lower() not in mech.lower():
        mech = f"{mech} {bio_ctx}".strip()
    sub.append({"kind": "mechanistic", "text": mech})

    # 2. Broader pathway / context with alias OR-group
    if alias_clause:
        pathway = (
            f"({alias_clause}) {bio_ctx} immune checkpoint exhaustion "
            f"effector function progenitor"
        )
        sub.append({"kind": "pathway", "text": pathway})

    # 3. Interaction framing when multi-gene or comparison language present
    hay = f"{query} {context} {hypothesis} {' '.join(genes)}".lower()
    wants_interaction = len(genes) >= 2 or any(h in hay for h in INTERACTION_HINTS)
    if wants_interaction:
        g_labels = genes[:3] if genes else aliases[:2]
        if len(g_labels) >= 2:
            inter = (
                f"{g_labels[0]} {g_labels[1]} synergy redundancy compensatory "
                f"epistasis combination {bio_ctx}"
            )
            sub.append({"kind": "interaction", "text": inter})

    # Deduplicate identical texts
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in sub:
        key = item["text"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out
