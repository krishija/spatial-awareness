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
You MUST ground every claim in SOURCE_TEXT. Never restate the HYPOTHESIS as the claim
unless SOURCE_TEXT literally says the same thing.

Given HYPOTHESIS and SOURCE_TEXT, return ONLY valid JSON:
{
  "claim": "one sentence paraphrasing what SOURCE_TEXT actually asserts (gene/pathway, relation, outcome)",
  "biological_context": {
    "cell_type": "string or null",
    "organism": "string or null",
    "setting": "in_vitro | in_vivo | human | unknown",
    "tumor_type": "string or null"
  },
  "stance": "supports | contradicts | tangential",
  "extraction_note": "brief note: quote or point to the SOURCE_TEXT phrase that justifies stance"
}

stance rules (be decisive — do NOT default to tangential when the text speaks to direction):
- supports: SOURCE_TEXT reports that loss/knockout/depletion/inhibition of the hypothesis
  gene improves effector function, reverses exhaustion, or otherwise affirms the
  hypothesized direction. Also supports if text shows the gene drives exhaustion and
  implies targeting it would help.
- contradicts: SOURCE_TEXT reports that loss/knockout/depletion of the gene fails to
  help, harms fitness, or produces the opposite of the hypothesized direction.
- tangential: SOURCE_TEXT mentions the gene or topic but does NOT report a perturbation
  outcome or directional result bearing on the hypothesis (e.g. marker expression only,
  unrelated pathway, different cell type with no transferable claim).

Hard constraints:
1. If you cannot find a directional perturbation/outcome in SOURCE_TEXT, stance MUST be
   tangential AND claim MUST describe what the text actually says (expression, marker
   status, etc.) — never invent a knockout result.
2. If SOURCE_TEXT clearly states a knockout/depletion result matching or opposing the
   hypothesis, stance MUST be supports or contradicts — not tangential.
3. Never copy the HYPOTHESIS wording into "claim" unless those words appear in SOURCE_TEXT.
"""


_SUPPORT_PATTERNS = [
    re.compile(
        r"(knockout|ko|deletion|depletion|inhibits?|blockade|loss of)\b.{0,60}"
        r"(increases?|restores?|reinvigorat\w*|rescues?|improves?|enhances?|"
        r"upregulat\w*\s+effector|effector function)",
        re.I,
    ),
    re.compile(
        r"(increases?|restores?|reinvigorat\w*|rescues?|improves?)\b.{0,40}"
        r"(effector|tcf7|il7r|gzmb|cytotoxic)",
        re.I,
    ),
]
_CONTRA_PATTERNS = [
    re.compile(
        r"(knockout|ko|deletion|depletion|loss of)\b.{0,60}"
        r"(fails?|no benefit|impairs?|worsens?|essential|required|harms?|"
        r"decreases? effector|reduces? effector)",
        re.I,
    ),
    re.compile(
        r"(not|no)\b.{0,20}(increased?|restored?|reinvigorat\w*)\b.{0,30}effector",
        re.I,
    ),
    re.compile(
        r"upregulation\b.{0,40}(exhaustion|exhausted).{0,40}not\b.{0,20}effector",
        re.I,
    ),
]


def refine_stance(
    *,
    hypothesis: str,
    claim: str | None,
    title: str,
    source_text: str,
    stance: str,
    extraction_note: str | None = None,
) -> tuple[str, str | None]:
    """Correct over-conservative / hallucinated extractions.

    Returns (stance, claim). If claim echoes the hypothesis while the note admits
    the source does not address it, clear the claim. Keyword stance upgrades use
    SOURCE_TEXT (and title), not a possibly-hallucinated claim.
    """
    stance = (stance or "tangential").lower().strip()
    claim_s = (claim or "").strip()
    hyp = (hypothesis or "").strip()
    note_l = (extraction_note or "").lower()
    admits_gap = any(
        p in note_l
        for p in (
            "does not address",
            "does not mention",
            "does not discuss",
            "no mention",
            "not mention",
            "without addressing",
            "does not report",
            "but does not",
        )
    )

    # Hallucinated claim: restates H while extractor admits the paper doesn't
    if claim_s and hyp and admits_gap and (
        _near_paraphrase(claim_s, hyp, threshold=0.28)
        or _hypothesis_echo(claim_s, hyp)
    ):
        claim_s = _fallback_claim_from_source(title, source_text) or claim_s
        return "tangential", claim_s

    if claim_s and hyp and stance == "tangential" and _hypothesis_echo(claim_s, hyp):
        # Echo without a gap note — still refuse to treat as directional literature
        # unless SOURCE_TEXT itself has directional language.
        if not (
            _matches_any(source_text or "", _SUPPORT_PATTERNS)
            or _matches_any(source_text or "", _CONTRA_PATTERNS)
        ):
            claim_s = _fallback_claim_from_source(title, source_text) or claim_s
            return "tangential", claim_s

    # Decisive keyword stance from title + source (not claim) when model said tangential
    blob = f"{title}\n{(source_text or '')[:2000]}"
    if stance == "tangential":
        if _matches_any(blob, _CONTRA_PATTERNS):
            stance = "contradicts"
        elif _matches_any(blob, _SUPPORT_PATTERNS):
            stance = "supports"
        # If claim itself (and not a hyp-echo) has clear direction, trust it
        elif claim_s and not _hypothesis_echo(claim_s, hyp):
            if _matches_any(claim_s, _CONTRA_PATTERNS):
                stance = "contradicts"
            elif _matches_any(claim_s, _SUPPORT_PATTERNS):
                stance = "supports"
    elif stance not in ("supports", "contradicts", "tangential"):
        stance = "tangential"

    return stance, claim_s or None


def _hypothesis_echo(claim: str, hypothesis: str) -> bool:
    """True when claim looks like a restatement of H (shared gene + KO + effector cues)."""
    c, h = claim.lower(), hypothesis.lower()
    gene_tokens = {t for t in _tokenize(hypothesis) if t in {
        "havcr2", "pdcd1", "tox", "tcf7", "lag3", "ctla4", "tigit", "tim3", "tim",
    } or t.startswith("cd")}
    # gene symbol often first token of hyp claim after knockout of X
    for m in re.finditer(r"\b([A-Z][A-Z0-9]{2,})\b", hypothesis):
        gene_tokens.add(m.group(1).lower())
    has_gene = any(g in c for g in gene_tokens) if gene_tokens else False
    has_ko = any(k in c for k in ("knockout", "knock-out", "deletion", "depletion", "crispr"))
    has_eff = any(k in c for k in ("effector", "tcf7", "il7r", "gzmb", "reinvigorat"))
    has_up = any(k in c for k in ("increase", "increases", "restore", "rescue", "enhance"))
    return bool(has_gene and has_ko and has_eff and has_up)


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
        # Deterministic fallback from title+snippet when LLM JSON fails
        stance, claim = refine_stance(
            hypothesis=hypothesis,
            claim=None,
            title=title,
            source_text=body,
            stance="tangential",
            extraction_note="parse_failed",
        )
        # Keyword pass on body alone
        if stance == "tangential":
            if _matches_any(body, _CONTRA_PATTERNS):
                stance = "contradicts"
            elif _matches_any(body, _SUPPORT_PATTERNS):
                stance = "supports"
        return {
            "claim": claim or _fallback_claim_from_source(title, body),
            "biological_context": {
                "cell_type": None,
                "organism": None,
                "setting": "unknown",
                "tumor_type": None,
            },
            "stance": stance,
            "extraction_note": f"LLM returned unparseable extraction; used text heuristics. Raw: {raw[:160]}",
            "extraction_ok": False,
        }

    stance = str(parsed.get("stance") or "tangential").lower().strip()
    if stance not in ("supports", "contradicts", "tangential"):
        if stance in ("support", "supporting", "agree", "affirm", "affirms"):
            stance = "supports"
        elif stance in (
            "contradict",
            "contradicting",
            "oppose",
            "opposes",
            "against",
            "refute",
            "refutes",
        ):
            stance = "contradicts"
        elif stance in ("unrelated", "neutral", "irrelevant", "unclear"):
            stance = "tangential"
        else:
            stance = "tangential"

    claim = parsed.get("claim")
    note = parsed.get("extraction_note") or "Extracted claim and stance from source text."
    stance, claim = refine_stance(
        hypothesis=hypothesis,
        claim=str(claim) if claim else None,
        title=title,
        source_text=body,
        stance=stance,
        extraction_note=str(note),
    )

    ctx = parsed.get("biological_context") or {}
    if not isinstance(ctx, dict):
        ctx = {}

    return {
        "claim": claim,
        "biological_context": {
            "cell_type": ctx.get("cell_type"),
            "organism": ctx.get("organism"),
            "setting": ctx.get("setting") or "unknown",
            "tumor_type": ctx.get("tumor_type"),
        },
        "stance": stance,
        "extraction_note": note,
        "extraction_ok": True,
    }


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text or "") for p in patterns)


def _tokenize(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def _near_paraphrase(a: str, b: str, *, threshold: float = 0.72) -> bool:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, len(ta | tb))
    return overlap >= threshold


def _fallback_claim_from_source(title: str, text: str) -> str | None:
    snippet = (text or "").strip().split(". ")[0].strip()
    if snippet and len(snippet) > 40:
        return snippet[:240]
    t = (title or "").strip()
    return t[:240] if t else None


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
