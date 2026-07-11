"""Fully implemented memory tool: query_prior_findings."""

from __future__ import annotations

from typing import Any

from spatial_mcp.memory import get_store


def query_prior_findings(args: dict[str, Any]) -> dict[str, Any]:
    store = get_store()
    findings = store.query(
        sample_id=args.get("sample_id"),
        niche=args.get("niche"),
        gene=args.get("gene"),
    )
    return {
        "filters": {
            "sample_id": args.get("sample_id"),
            "niche": args.get("niche"),
            "gene": args.get("gene"),
        },
        "n": len(findings),
        "findings": findings,
    }
