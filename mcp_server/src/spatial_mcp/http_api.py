"""Thin REST proxy over the MCP ToolRegistry — for the browser frontend.

The MCP server (server.py) speaks Streamable HTTP for K Pro / MCP clients,
which a browser can't call directly (and shouldn't — it'd need to hold
YOU_API_KEY client-side). This exposes plain JSON endpoints for the subset
of tools the frontend's literature/chat features need, keeping the API key
server-side. Same ToolRegistry, same tool logic — just a different transport.
"""

from __future__ import annotations

import os

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
        lines.append(f"- {c['title']} ({c['source']}): {c['relevance']}")
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
