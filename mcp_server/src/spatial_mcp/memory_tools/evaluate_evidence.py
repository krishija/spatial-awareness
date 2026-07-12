"""MCP wrapper: evaluate_evidence — same logic as agent.evidence.aggregate_evidence."""

from __future__ import annotations

from typing import Any

from spatial_mcp.agent.evidence import aggregate_evidence


def evaluate_evidence(args: dict[str, Any]) -> dict[str, Any]:
    items = args.get("evidence") or []
    score = aggregate_evidence(items)
    return {"ok": True, **score.to_dict()}
