#!/usr/bin/env python3
"""End-to-end tool sequence on real Atera data + live scLDM (no stubs).

Run on the GPU SageMaker notebook after bootstrap, with:
  export SCLDM_ROOT=/home/ec2-user/SageMaker/scldm_cd4
  export SCLDM_DEVICE=cuda
  export SPATIAL_CELLS_PARQUET=/home/ec2-user/SageMaker/spatial-awareness-data/cells.parquet
  # YOU_API_KEY + AWS_BEARER_TOKEN_BEDROCK in env for lit/agent stance

Writes JSON + markdown under ./e2e_out/
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    # Prefer user-owned e2e_work paths (avoid root-owned lifecycle leftovers)
    default_repo = "/home/ec2-user/SageMaker/e2e_work/spatial-awareness"
    repo = Path(os.environ.get("REPO_ROOT", default_repo))
    src = repo / "mcp_server" / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))

    cells = os.environ.get(
        "SPATIAL_CELLS_PARQUET",
        "/home/ec2-user/SageMaker/e2e_work/data/cells.parquet",
    )
    os.environ.setdefault(
        "SPATIAL_PREREG_PATH",
        "/home/ec2-user/SageMaker/e2e_work/data/preregistrations.jsonl",
    )
    # Point cell_store at real parquet
    os.environ.setdefault("SCLDM_DEVICE", "cuda")
    if not os.environ.get("SCLDM_ROOT"):
        candidate = "/home/ec2-user/SageMaker/e2e_work/scldm_cd4"
        if Path(candidate).is_dir():
            os.environ["SCLDM_ROOT"] = candidate

    from spatial_mcp.stubs import cell_store

    cell_store.CELLS_PARQUET = Path(cells)
    cell_store.reset_cache()

    from spatial_mcp.stubs.list_candidate_cells import list_candidate_cells
    from spatial_mcp.stubs.search_literature import search_literature
    from spatial_mcp.stubs.suggest_perturbations import suggest_perturbations
    from spatial_mcp.stubs.find_measured_perturbation_evidence import (
        find_measured_perturbation_evidence,
    )
    from spatial_mcp.stubs.simulate_perturbations import simulate_perturbations
    from spatial_mcp.stubs.differential_survival_analysis import (
        differential_survival_analysis,
    )
    from spatial_mcp.stubs.recommend_next_experiment import recommend_next_experiment
    from spatial_mcp.memory_tools.record_finding import record_finding
    from spatial_mcp.agent.preregister import (
        append_preregistration,
        make_preregistration,
        resolve_preregistration,
    )
    from spatial_mcp.agent.extract import evidence_from_tool_result
    from spatial_mcp.agent.evidence import aggregate_evidence
    from spatial_mcp.agent.gating import decide_next_action as gate_decide

    out_dir = Path(os.environ.get("E2E_OUT", str(Path.cwd() / "e2e_out")))
    out_dir.mkdir(parents=True, exist_ok=True)
    trace: list[dict] = []

    def step(name: str, fn, args: dict):
        print(f"\n=== {name} ===", flush=True)
        t0 = time.time()
        try:
            result = fn(args)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": "exception", "message": f"{type(exc).__name__}: {exc}"}
        dt = time.time() - t0
        ok = result.get("ok", True) if isinstance(result, dict) else True
        print(f"[{name}] {dt:.1f}s ok={ok}", flush=True)
        if isinstance(result, dict):
            preview = {k: result[k] for k in list(result)[:12]}
            print(json.dumps(preview, indent=2, default=str)[:1500], flush=True)
        trace.append({"tool": name, "seconds": dt, "result": result})
        (out_dir / f"{len(trace):02d}_{name}.json").write_text(
            json.dumps(result, indent=2, default=str)
        )
        return result

    # 0) Pre-register before sim/TCGA/measured
    H = (
        "Knockout of PDCD1 in terminally exhausted CD4 T cells in the tumor core "
        "of atera-cervical-01 increases effector-like marker expression (TCF7/IL7R/GZMB) "
        "relative to non-targeting control under scLDM-CD4 counterfactual inference."
    )
    preregs = {}
    for tool, direction in (
        ("find_measured_perturbation_evidence", "up"),
        ("simulate_perturbations", "up"),
        ("differential_survival_analysis", "protective"),
    ):
        reg = make_preregistration(
            tool=tool,
            gene="PDCD1",
            predicted_direction=direction,
            predicted_magnitude="moderate",
            rationale="E2E commitment before evidence tools",
            hypothesis_claim=H,
        )
        append_preregistration(reg)
        preregs[tool] = reg
        print("preregistered", tool, reg.id, flush=True)
    trace.append({"tool": "preregister", "result": {k: v.to_dict() for k, v in preregs.items()}})

    # 1) Cells
    cells_res = step(
        "list_candidate_cells",
        list_candidate_cells,
        {
            "sample_id": "atera-cervical-01",
            "niche": "tumor_core",
            "cell_type": "CD4_Tex_term",
            "min_exhaustion_score": 0.8,
            "limit": 5,
        },
    )
    if not cells_res.get("ok") or not cells_res.get("cells"):
        # broaden
        cells_res = step(
            "list_candidate_cells_broad",
            list_candidate_cells,
            {"sample_id": "atera-cervical-01", "niche": "tumor_core", "limit": 5},
        )
    cell = (cells_res.get("cells") or [None])[0]
    if not cell:
        print("FATAL: no cells", flush=True)
        (out_dir / "trace.json").write_text(json.dumps(trace, indent=2, default=str))
        return 1
    cell_id = cell["id"]
    phenotype = cell.get("cell_type") or "CD4_Tex_term"
    niche = cell.get("niche") or "tumor_core"
    gene = "PDCD1"

    # 2) Literature
    lit = step(
        "search_literature",
        search_literature,
        {
            "query": (
                f"Does {gene} knockout reverse terminal exhaustion in human CD4 T cells "
                f"in solid tumor / cervical carcinoma niche?"
            ),
            "context": {
                "gene": gene,
                "cell_type": phenotype,
                "niche": niche,
                "hypothesis": H,
            },
        },
    )

    # 3) Suggest
    sug = step(
        "suggest_perturbations",
        suggest_perturbations,
        {
            "cell_id": cell_id,
            "phenotype": phenotype,
            "niche": niche,
            "literature_context": (lit.get("summary") or lit.get("rollup") or "")[:500]
            if isinstance(lit, dict)
            else "",
        },
    )
    if isinstance(sug, dict) and sug.get("suggestions"):
        gene = str(sug["suggestions"][0].get("gene") or gene).upper()

    # 4) Measured evidence
    measured = step(
        "find_measured_perturbation_evidence",
        find_measured_perturbation_evidence,
        {"gene": gene, "cell_type": "CD4_T", "perturbation_type": "knockout"},
    )

    # 5) LIVE GPU simulation
    sim = step(
        "simulate_perturbations",
        simulate_perturbations,
        {"cell_id": cell_id, "gene": gene},
    )

    # 6) TCGA association (not validation)
    surv = step(
        "differential_survival_analysis",
        differential_survival_analysis,
        {
            "genes": [gene, "TCF7", "IL7R"],
            "cancer_type": "CESC",
            "expected_direction": "protective",
        },
    )

    # 7) Recommend next experiment
    rec = step(
        "recommend_next_experiment",
        recommend_next_experiment,
        {
            "sample_id": "atera-cervical-01",
            "gene": gene,
            "cell_type": phenotype,
            "niche": niche,
            "limit": 5,
        },
    )

    # Resolve preregistrations against observed tool results
    for tool, payload in (
        ("find_measured_perturbation_evidence", measured),
        ("simulate_perturbations", sim),
        ("differential_survival_analysis", surv),
    ):
        if tool in preregs and isinstance(payload, dict):
            try:
                resolve_preregistration(preregs[tool], payload)
            except Exception as exc:  # noqa: BLE001
                print("prereg resolve warn", tool, exc, flush=True)

    # 8) Evidence + gate
    tools_called = [
        "list_candidate_cells",
        "search_literature",
        "suggest_perturbations",
        "find_measured_perturbation_evidence",
        "simulate_perturbations",
        "differential_survival_analysis",
        "recommend_next_experiment",
    ]
    try:
        items = []
        for name, args, payload in (
            ("list_candidate_cells", {"sample_id": "atera-cervical-01"}, cells_res),
            ("search_literature", {"query": H}, lit),
            (
                "suggest_perturbations",
                {"cell_id": cell_id, "phenotype": phenotype, "niche": niche},
                sug,
            ),
            ("find_measured_perturbation_evidence", {"gene": gene}, measured),
            ("simulate_perturbations", {"cell_id": cell_id, "gene": gene}, sim),
            (
                "differential_survival_analysis",
                {"genes": [gene], "cancer_type": "CESC"},
                surv,
            ),
            (
                "recommend_next_experiment",
                {"sample_id": "atera-cervical-01", "gene": gene},
                rec,
            ),
        ):
            if not isinstance(payload, dict):
                continue
            try:
                items.extend(
                    evidence_from_tool_result(name, args, payload, focus_gene=gene)
                    or []
                )
            except Exception as exc:  # noqa: BLE001
                print("extract skip", name, exc, flush=True)
        score = aggregate_evidence(items)
        decision = gate_decide(
            evidence_score=score,
            tools_called=tools_called,
            max_iterations=8,
            iteration=7,
        )
        gate_res = {
            "ok": True,
            "confidence": getattr(score, "confidence", None),
            "bits": getattr(score, "log_odds_bits", None),
            "decision": getattr(decision, "decision", decision),
            "reason": getattr(decision, "reason", None),
            "rationale": getattr(score, "rationale", None),
        }
        trace.append({"tool": "epistemics_gate", "result": gate_res})
        (out_dir / "08_epistemics_gate.json").write_text(
            json.dumps(gate_res, indent=2, default=str)
        )
        print("GATE", gate_res, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("epistemics failed", exc, flush=True)
        gate_res = {"ok": False, "message": str(exc)}

    # 9) Record finding
    summary = (
        f"E2E {gene} on cell {cell_id} ({phenotype}/{niche}). "
        f"sim_ok={isinstance(sim, dict) and sim.get('ok') is not False and 'error' not in sim}. "
        f"gate={gate_res.get('decision')}"
    )
    step(
        "record_finding",
        record_finding,
        {
            "sample_id": "atera-cervical-01",
            "finding_summary": summary,
            "cell_id": cell_id,
            "niche": niche,
            "gene": gene,
        },
    )

    (out_dir / "trace.json").write_text(json.dumps(trace, indent=2, default=str))
    md = [
        f"# E2E run — {gene} / {cell_id}",
        "",
        f"- phenotype: {phenotype}",
        f"- niche: {niche}",
        f"- SCLDM_ROOT: {os.environ.get('SCLDM_ROOT')}",
        f"- backend sim: {(sim or {}).get('backend') if isinstance(sim, dict) else None}",
        f"- gate: {gate_res.get('decision')} conf={gate_res.get('confidence')}",
        "",
        "## Hypothesis",
        H,
        "",
        "## Sim deltas",
        "```json",
        json.dumps((sim or {}).get("deltas") if isinstance(sim, dict) else sim, indent=2, default=str)[:2000],
        "```",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(md))
    print("\nWrote", out_dir / "REPORT.md", flush=True)

    # Success criteria: real cells + live sim (or honest fail)
    sim_live = isinstance(sim, dict) and (
        sim.get("backend") == "scldm_live"
        or (sim.get("details") or {}).get("method") == "scldm_cd4_counterfactual"
        or sim.get("ok") is True
        and "before" in sim
    )
    if not cells_res.get("ok"):
        return 2
    if not sim_live:
        print("WARN: simulation was not live scldm — check SCLDM_ROOT/GPU", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
