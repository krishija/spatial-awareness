"""Pre-registration: commit to predicted direction/magnitude before gathering evidence.

Enforced in the driver loop — the agent may not call an evidence-gathering tool
until a structured prediction is written. Prevents post-hoc rationalization and
generates free calibration data about the agent itself.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Tools that require a pre-registered prediction before invocation
PREREGISTER_REQUIRED = frozenset(
    {
        "differential_survival_analysis",
        "simulate_perturbations",
        "find_measured_perturbation_evidence",
    }
)

_DEFAULT_STORE = (
    Path(__file__).resolve().parents[3] / "data" / "preregistrations.jsonl"
)


def _store_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    override = os.environ.get("SPATIAL_PREREG_PATH")
    if override:
        return Path(override)
    return _DEFAULT_STORE


@dataclass
class PreRegistration:
    id: str
    tool: str
    gene: str | None
    predicted_direction: str  # up | down | null | protective | risk_associated
    predicted_magnitude: str  # small | moderate | large | unknown
    rationale: str
    hypothesis_claim: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Filled after tool returns
    observed_direction: str | None = None
    observed_summary: str | None = None
    confirmed: bool | None = None
    tool_result_ok: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def requires_preregistration(tool_name: str) -> bool:
    return tool_name in PREREGISTER_REQUIRED


def make_preregistration(
    *,
    tool: str,
    gene: str | None,
    predicted_direction: str,
    predicted_magnitude: str = "unknown",
    rationale: str = "",
    hypothesis_claim: str | None = None,
) -> PreRegistration:
    return PreRegistration(
        id=f"prereg-{uuid.uuid4().hex[:10]}",
        tool=tool,
        gene=(gene or "").upper() or None,
        predicted_direction=predicted_direction.lower().strip(),
        predicted_magnitude=predicted_magnitude.lower().strip(),
        rationale=rationale or "agent commitment before tool call",
        hypothesis_claim=hypothesis_claim,
    )


def append_preregistration(
    reg: PreRegistration, path: Path | None = None
) -> Path:
    path = _store_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(reg.to_dict()) + "\n")
    return path


def resolve_preregistration(
    reg: PreRegistration,
    tool_result: dict[str, Any],
    path: Path | None = None,
) -> PreRegistration:
    """Compare commitment to observed outcome; append resolution line."""
    observed = _infer_observed_direction(reg.tool, tool_result)
    reg.observed_direction = observed
    reg.tool_result_ok = tool_result.get("ok") is not False
    reg.observed_summary = str(tool_result.get("message") or observed or "")[:240]
    if observed and reg.predicted_direction:
        # Normalize synonyms
        pred = _norm_dir(reg.predicted_direction)
        obs = _norm_dir(observed)
        reg.confirmed = pred == obs if pred and obs else None
    else:
        reg.confirmed = None
    append_preregistration(reg, path=path)
    return reg


def _norm_dir(d: str) -> str:
    d = d.lower()
    if d in ("up", "increase", "protective", "higher", "supports"):
        return "up"
    if d in ("down", "decrease", "risk_associated", "risk", "lower", "contradicts"):
        return "down"
    if d in ("null", "none", "unchanged"):
        return "null"
    return d


def _infer_observed_direction(tool: str, result: dict[str, Any]) -> str | None:
    if result.get("ok") is False:
        return None
    if tool == "simulate_perturbations":
        deltas = result.get("deltas") or {}
        inhibitory_down = sum(
            1 for g in ("PDCD1", "TOX", "LAG3", "CTLA4") if float(deltas.get(g, 0)) < -0.3
        )
        effector_up = sum(
            1 for g in ("TCF7", "IL7R", "GZMB") if float(deltas.get(g, 0)) > 0.3
        )
        if inhibitory_down and effector_up:
            return "up"  # effector restoration
        if effector_up == 0 and inhibitory_down == 0:
            return "null"
        return "down"
    if tool == "differential_survival_analysis":
        return result.get("direction")
    if tool == "find_measured_perturbation_evidence":
        if result.get("nothing_found"):
            return "null"
        hits = result.get("hits") or []
        if not hits:
            return "null"
        return "up"  # evidence exists
    return None


def load_preregistrations(path: Path | None = None) -> list[dict[str, Any]]:
    path = _store_path(path)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def agent_prediction_accuracy(path: Path | None = None) -> dict[str, Any]:
    rows = load_preregistrations(path)
    resolved = [r for r in rows if r.get("confirmed") is not None]
    if not resolved:
        return {"n": 0, "accuracy": None, "n_confirmed": 0, "n_disconfirmed": 0}
    n_ok = sum(1 for r in resolved if r["confirmed"] is True)
    return {
        "n": len(resolved),
        "accuracy": round(n_ok / len(resolved), 3),
        "n_confirmed": n_ok,
        "n_disconfirmed": len(resolved) - n_ok,
    }
