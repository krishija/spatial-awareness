"""Standalone research-agent orchestration driver.

Belt-and-suspenders: Bedrock proposes tool calls; code enforces max iterations,
prior-before-suggest, confidence floor, and wall-clock budget. Programmatic
confidence from evidence.py is the only score we trust — never the model's
self-reported confidence prose.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from spatial_mcp.agent.bedrock import (
    BedrockConverse,
    assistant_message_from_response,
    extract_text,
    extract_tool_uses,
    tool_result_message,
)
from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence
from spatial_mcp.agent.extract import evidence_from_tool_result
from spatial_mcp.agent.gating import decide_next_action
from spatial_mcp.agent.hypothesis import Hypothesis
from spatial_mcp.agent.mcp_client import McpToolClient, connect_mcp
from spatial_mcp.agent.preregister import (
    make_preregistration,
    requires_preregistration,
    resolve_preregistration,
)
from spatial_mcp.agent.report import HypothesisReport, build_report, render_markdown
from spatial_mcp.agent.trace import ReasoningTrace

SYSTEM_PROMPT = """You are an autonomous spatial immunology research agent for CD4 T-cell exhaustion.

You have MCP tools for resolving spatial cells, searching literature, suggesting gene
knockouts, simulating perturbations, differential survival analysis in matched TCGA
bulk cohorts (cohort association — not cell-level validation), and recording/querying findings.

Hard rules you must follow:
1. Call query_prior_findings BEFORE suggest_perturbations.
2. Prefer sample_id atera-cervical-01 when real Atera data is available; call list_candidate_cells
   with cell_type alone first to read niche_composition, then narrow with niche=.
3. When calling search_literature, pass structured fields (gene/genes, phenotype, niche,
   hypothesis) — not just a flat query string — so stance-labeled evidence cards are useful.
4. After gathering enough evidence, stop calling tools and write a short conclusion.
5. Do NOT invent confidence numbers — a separate scoring module computes confidence.
6. Prefer exhausted CD4 cells when exploring checkpoint knockouts (PDCD1, TOX, LAG3);
   for Tregs prefer margin-adjacent populations and CTLA4.

Work efficiently: few high-value tool calls, not exhaustive exploration.
"""


@dataclass
class AgentConfig:
    mcp_url: str = "http://127.0.0.1:8000/mcp"
    max_iterations: int = 8
    wall_clock_s: float = 180.0
    model_id: str | None = None
    region: str | None = None
    sample_id_default: str = "atera-cervical-01"


@dataclass
class AgentResult:
    research_question: str
    reports: list[HypothesisReport] = field(default_factory=list)
    discarded: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    final_text: str = ""
    gate_summary: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_question": self.research_question,
            "reports": [r.to_dict() for r in self.reports],
            "discarded": self.discarded,
            "gate_summary": self.gate_summary,
            "final_text": self.final_text,
            "trace": self.trace,
            "markdown": "\n\n---\n\n".join(render_markdown(r) for r in self.reports),
        }


class ResearchAgent:
    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()

    async def run(self, research_question: str) -> AgentResult:
        trace = ReasoningTrace(research_question)
        t0 = time.perf_counter()
        evidence_bank: list[EvidenceItem] = []
        tools_called: list[str] = []
        gate_summary: list[dict[str, Any]] = []
        focus = {
            "sample_id": self.config.sample_id_default,
            "cell_id": None,
            "niche": None,
            "gene": None,
            "cell_type": None,
            "citation": None,
            "perturbation": None,
        }

        async with connect_mcp(self.config.mcp_url) as mcp:
            tools = await mcp.list_tools(force=True)
            # Domain tools for the LLM — exclude meta evaluate/decide to avoid recursion
            llm_tools = [
                t
                for t in tools
                if t["name"]
                not in ("evaluate_evidence", "decide_next_action", "record_finding")
            ]
            trace.log("tools_fetched", n=len(tools), names=[t["name"] for t in tools])

            bedrock = BedrockConverse(
                model_id=self.config.model_id, region=self.config.region
            )
            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                f"Research question: {research_question}\n\n"
                                f"Default sample if unspecified: {self.config.sample_id_default}.\n"
                                "Begin by checking prior findings, then resolve candidate cells."
                            )
                        }
                    ],
                }
            ]

            final_text = ""
            last_gate = None

            for iteration in range(1, self.config.max_iterations + 1):
                elapsed = time.perf_counter() - t0
                if elapsed > self.config.wall_clock_s:
                    trace.log(
                        "wall_clock_exceeded",
                        elapsed_s=round(elapsed, 2),
                        budget_s=self.config.wall_clock_s,
                    )
                    last_gate = decide_next_action(
                        evidence_score=aggregate_evidence(evidence_bank),
                        tools_called=tools_called,
                        max_iterations=self.config.max_iterations,
                        iteration=self.config.max_iterations,
                    )
                    gate_summary.append(last_gate.to_dict())
                    break

                trace.log("llm_turn_start", iteration=iteration)
                try:
                    response = bedrock.converse(
                        messages=messages,
                        system=SYSTEM_PROMPT,
                        tools=llm_tools,
                    )
                except Exception as exc:  # noqa: BLE001
                    trace.log("llm_error", error=f"{type(exc).__name__}: {exc}")
                    # Do not kill the session — stop with what we have
                    last_gate = decide_next_action(
                        evidence_score=aggregate_evidence(evidence_bank),
                        tools_called=tools_called,
                        max_iterations=self.config.max_iterations,
                        iteration=self.config.max_iterations,
                    )
                    gate_summary.append(last_gate.to_dict())
                    break

                stop_reason = response.get("stopReason")
                assistant = assistant_message_from_response(response)
                messages.append(assistant)
                text = extract_text(response)
                if text:
                    final_text = text
                    trace.log("llm_text", text=text[:500])

                tool_uses = extract_tool_uses(response)
                if not tool_uses or stop_reason == "end_turn":
                    score = aggregate_evidence(evidence_bank)
                    last_gate = decide_next_action(
                        evidence_score=score,
                        tools_called=tools_called,
                        max_iterations=self.config.max_iterations,
                        iteration=iteration,
                    )
                    gate_summary.append(last_gate.to_dict())
                    trace.log(
                        "model_end_turn",
                        stop_reason=stop_reason,
                        gate=last_gate.to_dict(),
                        confidence=score.confidence,
                    )
                    # If model stopped early but gating says gather more, force one hint
                    if (
                        last_gate.decision == "GATHER_MORE"
                        and last_gate.next_tool
                        and iteration < self.config.max_iterations
                    ):
                        messages.append(
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "text": (
                                            f"Gating policy requires more evidence before reporting. "
                                            f"Next tool to call: {last_gate.next_tool}. "
                                            f"Reason: {last_gate.next_tool_reason}"
                                        )
                                    }
                                ],
                            }
                        )
                        continue
                    break

                # Soft-enforce prior-before-suggest before executing
                tool_results_payload: list[tuple[str, dict[str, Any], bool]] = []
                for tu in tool_uses:
                    name = tu["name"]
                    args = dict(tu.get("input") or {})
                    if (
                        name == "suggest_perturbations"
                        and "query_prior_findings" not in tools_called
                    ):
                        blocked = {
                            "ok": False,
                            "error": "policy_blocked",
                            "message": (
                                "Hard policy: call query_prior_findings before "
                                "suggest_perturbations."
                            ),
                        }
                        trace.log(
                            "tool_blocked",
                            tool=name,
                            arguments=args,
                            result=blocked,
                        )
                        tool_results_payload.append(
                            (tu["toolUseId"], blocked, True)
                        )
                        continue

                    # W5: pre-register predicted direction before evidence-gathering tools
                    prereg = None
                    if requires_preregistration(name):
                        gene = (
                            args.get("gene")
                            or (args.get("genes") or [None])[0]
                            or focus.get("gene")
                        )
                        # Direction from tool args / focus — code commits, not free prose
                        predicted = (
                            args.get("expected_direction")
                            or args.get("predicted_direction")
                            or focus.get("predicted_direction")
                            or "up"
                        )
                        prereg = make_preregistration(
                            tool=name,
                            gene=str(gene) if gene else None,
                            predicted_direction=str(predicted),
                            predicted_magnitude=str(
                                args.get("predicted_magnitude") or "moderate"
                            ),
                            rationale=(
                                f"Pre-registration before {name} "
                                f"(agent may not narrate this result post-hoc)."
                            ),
                            hypothesis_claim=_compose_hypothesis(
                                focus, research_question
                            ),
                        )
                        from spatial_mcp.agent.preregister import append_preregistration

                        append_preregistration(prereg)
                        trace.log(
                            "preregistration",
                            id=prereg.id,
                            tool=name,
                            predicted_direction=prereg.predicted_direction,
                            gene=prereg.gene,
                        )

                    try:
                        raw = await mcp.call_tool(name, args)
                        is_error = bool(raw.get("ok") is False and raw.get("error"))
                    except Exception as exc:  # noqa: BLE001
                        raw = {
                            "ok": False,
                            "error": "tool_call_exception",
                            "message": f"{type(exc).__name__}: {exc}",
                        }
                        is_error = True

                    if prereg is not None:
                        resolve_preregistration(prereg, raw)
                        trace.log(
                            "preregistration_resolved",
                            id=prereg.id,
                            confirmed=prereg.confirmed,
                            observed=prereg.observed_direction,
                        )

                    tools_called.append(name)
                    trace.log(
                        "tool_call",
                        tool=name,
                        arguments=args,
                        result_preview=_preview(raw),
                        is_error=is_error,
                    )

                    new_items = evidence_from_tool_result(
                        name, args, raw, focus_gene=focus.get("gene")
                    )
                    evidence_bank.extend(new_items)
                    _update_focus(focus, name, args, raw, new_items)

                    hyp = Hypothesis.from_focus(focus)
                    score = aggregate_evidence(evidence_bank, hypothesis=hyp)
                    gate = decide_next_action(
                        evidence_score=score,
                        tools_called=tools_called,
                        max_iterations=self.config.max_iterations,
                        iteration=iteration,
                    )
                    last_gate = gate
                    gate_summary.append(gate.to_dict())
                    trace.log(
                        "aggregate_and_gate",
                        confidence=score.confidence,
                        posterior_log_odds_bits=score.posterior_log_odds_bits,
                        n_independent_sources=score.n_independent_sources,
                        has_grounded_source=score.has_grounded_source,
                        has_conflict=score.has_conflict,
                        coverage=score.coverage,
                        gate=gate.to_dict(),
                        evidence_budget=score.evidence_budget[:12],
                        rationale=score.rationale[:400],
                        hypothesis=hyp.to_dict(),
                    )

                    # Feed programmatic score back so the model sees constraints
                    enriched = {
                        "tool_result": raw,
                        "programmatic_confidence": score.confidence,
                        "posterior_log_odds_bits": score.posterior_log_odds_bits,
                        "evidence_budget": score.evidence_budget,
                        "gate_decision": gate.decision,
                        "gate_reason": gate.reason,
                        "suggested_next_tool": gate.next_tool,
                        "hypothesis": hyp.to_dict(),
                    }
                    tool_results_payload.append(
                        (tu["toolUseId"], enriched, is_error)
                    )

                    if gate.decision in ("REPORT", "DISCARD"):
                        # Still append tool results so conversation stays valid, then stop
                        messages.append(tool_result_message(tool_results_payload))
                        tool_results_payload = []
                        trace.log("forced_stop", gate=gate.to_dict())
                        break

                if tool_results_payload:
                    messages.append(tool_result_message(tool_results_payload))

                if last_gate and last_gate.decision in ("REPORT", "DISCARD"):
                    break

            score = aggregate_evidence(evidence_bank)
            if last_gate is None:
                last_gate = decide_next_action(
                    evidence_score=score,
                    tools_called=tools_called,
                    max_iterations=self.config.max_iterations,
                    iteration=self.config.max_iterations,
                )
                gate_summary.append(last_gate.to_dict())

            # W3: confound enumeration — surviving alternatives subtract bits (not a tool checklist)
            hyp = Hypothesis.from_focus(focus)
            from spatial_mcp.agent.red_team import (
                enumerate_confounds,
                surviving_alternatives,
                update_confound_status,
            )

            confounds = update_confound_status(
                enumerate_confounds(hyp),
                evidence_types_present={i.evidence_type for i in evidence_bank},
                measured_context_match=next(
                    (
                        float(i.metadata.get("context_match_score") or 0)
                        for i in evidence_bank
                        if i.evidence_type == "measured"
                        and i.metadata.get("context_match_score") is not None
                    ),
                    None,
                ),
                cohort_present=any(
                    i.evidence_type == "cohort_prognostic" for i in evidence_bank
                ),
            )
            surviving = surviving_alternatives(confounds)
            for alt in surviving:
                evidence_bank.append(
                    EvidenceItem(
                        evidence_type="red_team",
                        summary=f"Surviving alternative: {alt['explanation']}",
                        source_id=f"confound:{alt['id']}",
                        polarity="contradicts",
                        strength=0.35,  # partial — enumerated, not steelmanned
                        metadata={"confound_id": alt["id"], "red_team": True},
                    )
                )
            score = aggregate_evidence(evidence_bank, hypothesis=hyp)
            last_gate = decide_next_action(
                evidence_score={
                    **score.to_dict(),
                    "surviving_alternative_explanations": surviving,
                },
                tools_called=tools_called,
                max_iterations=self.config.max_iterations,
                iteration=self.config.max_iterations,
            )
            gate_summary.append(last_gate.to_dict())
            trace.log(
                "red_team_confounds",
                n_confounds=len(confounds),
                n_surviving=len(surviving),
                surviving=[c["id"] for c in surviving],
                posterior_after=score.confidence,
            )

            reports: list[HypothesisReport] = []
            discarded: list[dict[str, Any]] = []

            hypothesis = hyp.claim
            if last_gate.decision == "REPORT":
                reports.append(
                    build_report(
                        hypothesis=hypothesis,
                        confidence=score.confidence,
                        rationale=score.rationale,
                        contributions=score.contributions,
                        cell_id=focus.get("cell_id"),
                        niche=focus.get("niche"),
                        gene=focus.get("gene"),
                        cell_type=focus.get("cell_type"),
                        citation=focus.get("citation"),
                        perturbation=focus.get("perturbation"),
                        gate_decision="REPORT",
                        research_question=research_question,
                    )
                )
                trace.log(
                    "report_epistemics",
                    evidence_budget=score.evidence_budget,
                    surviving_alternative_explanations=surviving,
                    posterior_log_odds_bits=score.posterior_log_odds_bits,
                )
                # Persist finding for cross-session memory
                try:
                    await mcp.call_tool(
                        "record_finding",
                        {
                            "sample_id": focus.get("sample_id")
                            or self.config.sample_id_default,
                            "cell_id": focus.get("cell_id"),
                            "niche": focus.get("niche"),
                            "gene": focus.get("gene"),
                            "finding_summary": (
                                f"{hypothesis} (confidence={score.confidence:.3f})"
                            ),
                            "citations": [focus["citation"]]
                            if focus.get("citation")
                            else [],
                        },
                    )
                    trace.log("finding_recorded", gene=focus.get("gene"))
                except Exception as exc:  # noqa: BLE001
                    trace.log("record_finding_failed", error=str(exc))
            else:
                discarded.append(
                    {
                        "hypothesis": hypothesis,
                        "confidence": score.confidence,
                        "gate": last_gate.to_dict(),
                        "rationale": score.rationale,
                    }
                )

            result = AgentResult(
                research_question=research_question,
                reports=reports,
                discarded=discarded,
                trace=trace.to_dict(),
                final_text=final_text,
                gate_summary=gate_summary,
            )
            trace.log(
                "run_complete",
                n_reports=len(reports),
                n_discarded=len(discarded),
                confidence=score.confidence,
                decision=last_gate.decision,
                elapsed_s=round(time.perf_counter() - t0, 2),
            )
            return result


def _preview(raw: dict[str, Any], limit: int = 600) -> Any:
    text = json.dumps(raw, default=str)
    if len(text) <= limit:
        return raw
    return text[:limit] + "…"


def _update_focus(
    focus: dict[str, Any],
    tool: str,
    args: dict[str, Any],
    raw: dict[str, Any],
    items: list[EvidenceItem],
) -> None:
    if tool == "list_candidate_cells" and (raw.get("cells") or []):
        c = raw["cells"][0]
        focus["cell_id"] = c.get("id")
        focus["niche"] = c.get("niche")
        focus["cell_type"] = c.get("cell_type")
        focus["sample_id"] = raw.get("sample_id") or args.get("sample_id")
    if tool == "suggest_perturbations" and (raw.get("suggestions") or []):
        s = raw["suggestions"][0]
        focus["gene"] = s.get("gene")
        focus["cell_id"] = focus.get("cell_id") or raw.get("cell_id")
        focus["niche"] = focus.get("niche") or raw.get("niche")
        focus["cell_type"] = focus.get("cell_type") or raw.get("phenotype")
        cites = s.get("citations") or []
        if cites:
            focus["citation"] = cites[0]
    if tool == "simulate_perturbations" and raw.get("ok") is not False:
        focus["gene"] = raw.get("gene") or args.get("gene") or focus.get("gene")
        focus["cell_id"] = raw.get("cell_id") or focus.get("cell_id")
        focus["niche"] = raw.get("niche") or focus.get("niche")
        focus["cell_type"] = raw.get("cell_type") or focus.get("cell_type")
        focus["perturbation"] = {
            "cell_id": raw.get("cell_id"),
            "gene": raw.get("gene"),
            "before": raw.get("before"),
            "after": raw.get("after"),
            "deltas": raw.get("deltas"),
        }
    if tool == "search_literature":
        cites = raw.get("citations") or []
        if cites and not focus.get("citation"):
            focus["citation"] = {
                "title": cites[0].get("title"),
                "source": cites[0].get("source"),
                "url": cites[0].get("url"),
            }
    for it in items:
        md = it.metadata or {}
        for k in ("cell_id", "niche", "gene", "cell_type", "sample_id"):
            if md.get(k) and not focus.get(k):
                focus[k] = md[k]
        if md.get("citation") and not focus.get("citation"):
            focus["citation"] = md["citation"]


def _compose_hypothesis(focus: dict[str, Any], question: str) -> str:
    return Hypothesis.from_focus(focus).claim
