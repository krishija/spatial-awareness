"""Standalone research-agent CLI (K Pro stand-in for the demo)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def _repo_paths() -> tuple[Path, Path]:
    # .../mcp_server/src/spatial_mcp/agent/cli.py → mcp_server, repo root
    mcp_server = Path(__file__).resolve().parents[3]
    return mcp_server, mcp_server.parent


def _load_dotenv() -> None:
    mcp_server, repo = _repo_paths()
    for path in (repo / ".env", mcp_server / ".env", Path.cwd() / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def dry_run_conflict() -> int:
    """Construct conflicting lit vs sim evidence and show score + gate (no Bedrock)."""
    from spatial_mcp.agent.evidence import EvidenceItem, aggregate_evidence
    from spatial_mcp.agent.gating import decide_next_action
    from spatial_mcp.agent.report import build_report, render_markdown

    supporting_only = [
        EvidenceItem(
            "prior_finding", "Priors checked", "qpf", "neutral", 0.5, {"queried_priors": True}
        ),
        EvidenceItem("cell_context", "Tex term in core", "crc-01-c0042", "supports", 0.9),
        EvidenceItem(
            "literature", "PD-1 blockade restores effector function", "lit-1", "supports", 0.9
        ),
        EvidenceItem("simulation", "PDCD1 KO ↑TCF7/IL7R/GZMB", "sim-1", "supports", 0.95),
        EvidenceItem("suggestion", "Suggest PDCD1", "sug-1", "supports", 0.8),
    ]
    conflicting = [
        EvidenceItem(
            "prior_finding", "Priors checked", "qpf", "neutral", 0.5, {"queried_priors": True}
        ),
        EvidenceItem("cell_context", "Tex term in core", "crc-01-c0042", "supports", 0.9),
        EvidenceItem(
            "literature",
            "PD-1 blockade fails to restore effector function in this niche (contradict)",
            "lit-contra",
            "contradicts",
            0.9,
        ),
        EvidenceItem("simulation", "PDCD1 KO ↑TCF7/IL7R/GZMB", "sim-1", "supports", 0.95),
    ]

    s_ok = aggregate_evidence(supporting_only)
    s_bad = aggregate_evidence(conflicting)
    assert s_ok.confidence > s_bad.confidence

    tools_full = [
        "query_prior_findings",
        "list_candidate_cells",
        "search_literature",
        "suggest_perturbations",
        "simulate_perturbations",
    ]
    g_ok = decide_next_action(
        evidence_score=s_ok, tools_called=tools_full, max_iterations=8, iteration=5
    )
    g_bad = decide_next_action(
        evidence_score=s_bad,
        tools_called=[
            "query_prior_findings",
            "list_candidate_cells",
            "search_literature",
            "simulate_perturbations",
        ],
        max_iterations=8,
        iteration=8,
    )

    print("=== supporting evidence ===")
    print(f"confidence={s_ok.confidence} gate={g_ok.decision} — {g_ok.reason}")
    print("=== conflicting evidence ===")
    print(f"confidence={s_bad.confidence} gate={g_bad.decision} — {g_bad.reason}")
    print(f"has_conflict={s_bad.has_conflict}")

    if g_ok.decision == "REPORT":
        report = build_report(
            hypothesis="PDCD1 KO reverts terminal exhaustion in CRC-01 core Tex.",
            confidence=s_ok.confidence,
            rationale=s_ok.rationale,
            contributions=s_ok.contributions,
            cell_id="crc-01-c0042",
            niche="tumor_core",
            gene="PDCD1",
            cell_type="CD4_Tex_term",
            research_question="dry-run supporting",
        )
        print("\n" + render_markdown(report))

    if g_ok.decision != "REPORT" or g_bad.decision == "REPORT" or not s_bad.has_conflict:
        return 1
    print("\nDry-run conflict checks passed.")
    return 0


async def run_live(args: argparse.Namespace) -> int:
    from spatial_mcp.agent.driver import AgentConfig, ResearchAgent

    agent = ResearchAgent(
        AgentConfig(
            mcp_url=args.mcp_url,
            max_iterations=args.max_iterations,
            wall_clock_s=args.wall_clock,
            model_id=args.model,
            region=args.region,
            sample_id_default=args.sample,
            commit_gene=args.commit_gene,
        )
    )
    result = await agent.run(args.question)
    payload = result.to_dict()

    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, default=str))
        print(f"Wrote {args.json}", file=sys.stderr)
    if args.md:
        Path(args.md).write_text(payload.get("markdown") or "")
        print(f"Wrote {args.md}", file=sys.stderr)

    if result.reports:
        print(payload["markdown"])
        return 0

    print("# No reportable hypothesis")
    print(json.dumps(result.discarded, indent=2, default=str))
    if result.final_text:
        print("\n## Model closing text\n")
        print(result.final_text)
    return 2


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Spatial research agent (Bedrock + MCP)")
    parser.add_argument(
        "question",
        nargs="?",
        default=(
            "Which gene knockout would best re-activate terminally exhausted CD4 T cells "
            "in the CRC-01 tumor core?"
        ),
    )
    parser.add_argument(
        "--mcp-url",
        default=os.environ.get("SPATIAL_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--wall-clock", type=float, default=180.0)
    parser.add_argument("--model", default=os.environ.get("BEDROCK_MODEL_ID"))
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("BEDROCK_REGION"),
    )
    parser.add_argument("--sample", default="crc-01")
    parser.add_argument(
        "--commit-gene",
        default=None,
        help="Pre-lock hypothesis gene (skips suggest rank-1 lock). E.g. HAVCR2.",
    )
    parser.add_argument("--json", dest="json", default=None)
    parser.add_argument("--md", default=None)
    parser.add_argument(
        "--dry-run-conflict",
        action="store_true",
        help="No Bedrock/MCP — verify conflicting evidence scoring + gating",
    )
    args = parser.parse_args()
    if args.dry_run_conflict:
        raise SystemExit(dry_run_conflict())
    raise SystemExit(asyncio.run(run_live(args)))


if __name__ == "__main__":
    main()
