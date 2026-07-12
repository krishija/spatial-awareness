"""MCP wrapper: decide_next_action — same logic as agent.gating.decide_next_action."""

from __future__ import annotations

from typing import Any

from spatial_mcp.agent.gating import decide_next_action


def decide_next_action_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = decide_next_action(
        evidence_score=args.get("evidence_score") or {},
        tools_called=args.get("tools_called") or [],
        max_iterations=int(args.get("max_iterations") or 8),
        iteration=int(args.get("iteration") or 1),
        force_prior_before_suggest=bool(args.get("force_prior_before_suggest", True)),
    )
    return {"ok": True, **result.to_dict()}
