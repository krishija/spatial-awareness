"""Fully implemented memory tool: record_finding."""

from __future__ import annotations

from typing import Any

from spatial_mcp.memory import get_store


def record_finding(args: dict[str, Any]) -> dict[str, Any]:
    store = get_store()
    record = store.record(
        {
            "sample_id": args["sample_id"],
            "finding_summary": args["finding_summary"],
            "cell_id": args.get("cell_id"),
            "niche": args.get("niche"),
            "gene": args.get("gene"),
            "citations": args.get("citations") or [],
        }
    )
    return {"ok": True, "finding": record}
