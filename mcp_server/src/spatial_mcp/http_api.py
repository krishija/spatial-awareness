"""Thin REST proxy over the MCP ToolRegistry — for the browser frontend.

The MCP server (server.py) speaks Streamable HTTP for K Pro / MCP clients,
which a browser can't call directly (and shouldn't — it'd need to hold
YOU_API_KEY client-side). This exposes plain JSON endpoints for the subset
of tools the frontend's literature/chat features need, keeping the API key
server-side. Same ToolRegistry, same tool logic — just a different transport.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from spatial_mcp.logging_util import setup_logging
from spatial_mcp.registry import ToolValidationError, UnknownToolError, build_default_registry

setup_logging()

HOST = os.environ.get("SPATIAL_API_HOST", "0.0.0.0")
PORT = int(os.environ.get("SPATIAL_API_PORT", "8001"))
ALLOWED_ORIGINS = os.environ.get("SPATIAL_API_ORIGINS", "http://localhost:5173").split(",")

REGISTRY = build_default_registry()

# ── Real Atera data, for the tissue map (bypasses list_candidate_cells' 200-cell
# agent-context cap — the map needs a denser, visually representative sample).
# cells_full.parquet has ALL 25 raw 10x cell-type labels (unlike cells.parquet,
# which only covers the 13-label CD4-relevant subset) — matches explorer.html's
# "Cell types" dropdown exactly. Gene panel matches explorer.html's gene-paint
# dropdown, not the old marker panel. ──
CELLS_PARQUET = Path(__file__).resolve().parents[2] / "data" / "cells_full.parquet"
ATLAS_JSON = Path(__file__).resolve().parents[2] / "data" / "atlas_cells.json"
MARKER_GENES = ["CTLA4", "FOXP3", "CXCL9", "STAT1", "CXCR4", "IL2RA", "TNFRSF9", "PDCD1"]
REAL_SAMPLE_META = {
    "atera-cervical-01": {
        "id": "atera-cervical-01",
        "name": "Atera-01 · cervical SCC (real, 715k cells)",
        "description": "10x Atera whole-transcriptome in situ, cervical squamous cell carcinoma, one FFPE section (CC BY 4.0)",
    }
}
# Regulatory T Cells capped looser — Treg-niches mode needs enough density to
# read; everything else is backdrop/context and can be capped hard.
CELL_TYPE_CAP = {
    "Regulatory T Cells": 3000,
    "Exhausted T Cells": 1200,
    "Cytotoxic T Cells": 1200,
}
DEFAULT_CAP = 600

_REAL_CELLS_DF = None
_ATLAS_DATA = None


def _load_real_cells():
    global _REAL_CELLS_DF
    if _REAL_CELLS_DF is None and CELLS_PARQUET.exists():
        import pandas as pd

        _REAL_CELLS_DF = pd.read_parquet(CELLS_PARQUET)
    return _REAL_CELLS_DF


def _load_atlas_data():
    global _ATLAS_DATA
    if _ATLAS_DATA is None and ATLAS_JSON.exists():
        import json

        with open(ATLAS_JSON) as f:
            _ATLAS_DATA = json.load(f)
    return _ATLAS_DATA

app = FastAPI(title="spatial-awareness REST proxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _call(name: str, arguments: dict) -> dict:
    try:
        return REGISTRY.call(name, arguments)
    except ToolValidationError as exc:
        return {"ok": False, "error": "validation_error", "message": str(exc), "details": exc.details}
    except UnknownToolError as exc:
        return {"ok": False, "error": "unknown_tool", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 — isolate teammate tool failures
        return {"ok": False, "error": "tool_execution_error", "message": f"{type(exc).__name__}: {exc}"}


class SearchLiteratureRequest(BaseModel):
    query: str
    context: str | None = None


class SuggestPerturbationsRequest(BaseModel):
    cell_id: str
    phenotype: str
    niche: str
    literature_context: str | None = None


class ChatRequest(BaseModel):
    message: str
    cell_id: str | None = None
    phenotype: str | None = None
    niche: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/real_samples")
def real_samples() -> dict:
    df = _load_real_cells()
    if df is None:
        return {"samples": []}
    return {"samples": list(REAL_SAMPLE_META.values())}


@app.get("/api/real_samples/{sample_id}")
def real_sample(sample_id: str) -> dict:
    import numpy as np

    df = _load_real_cells()
    if df is None:
        return {"ok": False, "error": "no_data", "message": "cells_full.parquet not found on server."}
    if sample_id not in REAL_SAMPLE_META:
        return {"ok": False, "error": "unknown_sample", "message": f"Unknown sample_id '{sample_id}'."}

    sub = df[df["sample_id"] == sample_id]

    # Stratified subsample: bulk/backdrop types capped hard, Tregs (the
    # niche-mode story) capped looser, so the map stays dense but readable.
    rng = np.random.default_rng(0)
    parts = []
    for ct, group in sub.groupby("cell_type"):
        cap = CELL_TYPE_CAP.get(ct, DEFAULT_CAP)
        if len(group) > cap:
            idx = rng.choice(len(group), cap, replace=False)
            parts.append(group.iloc[idx])
        else:
            parts.append(group)
    import pandas as pd

    picked = pd.concat(parts, ignore_index=True)

    # Normalize microns -> [0,100] square, preserving aspect ratio.
    x = picked["x"].to_numpy(dtype=float)
    y = picked["y"].to_numpy(dtype=float)
    xmin, ymin = x.min(), y.min()
    span = max(x.max() - xmin, y.max() - ymin) or 1.0
    nx = (x - xmin) / span * 100
    ny = (y - ymin) / span * 100

    cells = []
    for i, row in enumerate(picked.itertuples(index=False)):
        cells.append(
            {
                "id": row.id,
                "x": round(float(nx[i]), 2),
                "y": round(float(ny[i]), 2),
                "cell_type": row.cell_type,
                "niche": row.niche if row.niche is not None else None,
                "exhaustion_state": row.exhaustion_state,
                "expression": {g: round(float(getattr(row, g)), 2) for g in MARKER_GENES},
            }
        )

    return {
        "cells": cells,
        "suggestions": [],
        "nicheCenters": {},
        "n_total": int(len(sub)),
        "n_shown": int(len(picked)),
    }


@app.get("/api/atlas_cells")
def atlas_cells() -> dict:
    data = _load_atlas_data()
    if data is None:
        return {"ok": False, "error": "no_data", "message": "atlas_cells.json not found on server."}
    return data


@app.post("/api/search_literature")
def search_literature(body: SearchLiteratureRequest) -> dict:
    return _call("search_literature", body.model_dump(exclude_none=True))


@app.post("/api/suggest_perturbations")
def suggest_perturbations(body: SuggestPerturbationsRequest) -> dict:
    return _call("suggest_perturbations", body.model_dump(exclude_none=True))


def _extractive_answer(query: str, citations: list[dict]) -> str:
    if not citations:
        return (
            f'No literature results came back for "{query}". Try rephrasing, '
            "or the You.com API may be temporarily unavailable."
        )
    lines = [f'Based on {len(citations)} source(s) for "{query}":']
    for c in citations:
        snippet = c.get("relevance")
        lines.append(
            f"- {c['title']} ({c['source']}): {snippet}" if snippet else f"- {c['title']} ({c['source']})"
        )
    return "\n".join(lines)


@app.post("/api/chat")
def chat(body: ChatRequest) -> dict:
    context_bits = [b for b in (body.phenotype, body.niche) if b]
    context = " in ".join(context_bits) if context_bits else None

    lit_args = {"query": body.message}
    if context:
        lit_args["context"] = context
    lit_result = _call("search_literature", lit_args)
    citations = lit_result.get("citations", [])
    answer = _extractive_answer(body.message, citations)

    suggestions: list[dict] = []
    suggestions_source: str | None = None
    if body.phenotype and body.niche:
        sug_args = {
            "cell_id": body.cell_id or "chat-query",
            "phenotype": body.phenotype,
            "niche": body.niche,
            "literature_context": body.message,
        }
        sug_result = _call("suggest_perturbations", sug_args)
        suggestions = sug_result.get("suggestions", [])
        suggestions_source = sug_result.get("source")

    return {
        "answer": answer,
        "citations": citations,
        "suggestions": suggestions,
        "suggestions_source": suggestions_source,
        "warning": lit_result.get("warning"),
    }


def main() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
