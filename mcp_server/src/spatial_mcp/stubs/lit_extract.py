"""Scoped LLM claim/stance extraction for literature abstracts.

Extracts what the text claims relative to a hypothesis — not whether the claim
is true. Confidence scoring stays in evidence.py.
"""

from __future__ import annotations

import json
import re
from typing import Any


EXTRACT_SYSTEM = """You extract factual claims from scientific abstracts for a research agent.
You do NOT judge whether claims are true. You do NOT assign numerical confidence scores.

Given HYPOTHESIS and SOURCE_TEXT, return ONLY valid JSON:
{
  "claim": "one sentence: subject gene/pathway, relation, object/outcome",
  "biological_context": {
    "cell_type": "string or null",
    "organism": "string or null",
    "setting": "in_vitro | in_vivo | human | unknown",
    "tumor_type": "string or null"
  },
  "stance": "supports | contradicts | tangential",
  "extraction_note": "brief note on how clear the text was for this extraction"
}

stance rules:
- supports: text affirms the hypothesis direction/claim
- contradicts: text denies or reports opposite direction for the same claim
- tangential: right gene/topic but does not bear on the specific hypothesis direction
"""


def extract_claim_stance(
    *,
    hypothesis: str,
    title: str,
    text: str,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run Bedrock extraction; on failure return tangential with note (caller may escalate)."""
    body = (text or "").strip() or (title or "").strip()
    if not body:
        return {
            "claim": None,
            "biological_context": {
                "cell_type": None,
                "organism": None,
                "setting": "unknown",
                "tumor_type": None,
            },
            "stance": "tangential",
            "extraction_note": "No abstract/snippet available for extraction.",
            "extraction_ok": False,
        }

    user = (
        f"HYPOTHESIS:\n{hypothesis}\n\n"
        f"TITLE:\n{title}\n\n"
        f"SOURCE_TEXT:\n{body[:6000]}\n"
    )

    if client is None:
        from spatial_mcp.agent.bedrock import BedrockConverse

        client = BedrockConverse(max_tokens=800)

    raw = client.converse_text(system=EXTRACT_SYSTEM, user=user, max_tokens=800)
    parsed = _parse_json(raw)
    if not parsed:
        return {
            "claim": None,
            "biological_context": {
                "cell_type": None,
                "organism": None,
                "setting": "unknown",
                "tumor_type": None,
            },
            "stance": "tangential",
            "extraction_note": f"LLM returned unparseable extraction: {raw[:200]}",
            "extraction_ok": False,
        }

    stance = str(parsed.get("stance") or "tangential").lower().strip()
    if stance not in ("supports", "contradicts", "tangential"):
        # map common synonyms
        if stance in ("support", "supporting", "agree"):
            stance = "supports"
        elif stance in ("contradict", "contradicting", "oppose", "opposes"):
            stance = "contradicts"
        elif stance in ("unrelated", "neutral", "irrelevant"):
            stance = "tangential"
        else:
            stance = "tangential"

    ctx = parsed.get("biological_context") or {}
    if not isinstance(ctx, dict):
        ctx = {}

    return {
        "claim": parsed.get("claim"),
        "biological_context": {
            "cell_type": ctx.get("cell_type"),
            "organism": ctx.get("organism"),
            "setting": ctx.get("setting") or "unknown",
            "tumor_type": ctx.get("tumor_type"),
        },
        "stance": stance,
        "extraction_note": parsed.get("extraction_note")
        or "Extracted claim and stance from source text.",
        "extraction_ok": True,
    }


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
