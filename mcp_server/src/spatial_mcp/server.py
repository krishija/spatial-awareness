"""MCP server entrypoint — Streamable HTTP transport for K Pro.

Uses the low-level MCP Server so tool schemas come from our generic registry
(not per-tool FastMCP decorators). Dispatcher has zero biology knowledge.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator
from typing import Any

import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from spatial_mcp.logging_util import setup_logging
from spatial_mcp.registry import (
    ToolValidationError,
    UnknownToolError,
    build_default_registry,
)

setup_logging()

HOST = os.environ.get("SPATIAL_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("SPATIAL_MCP_PORT", "8000"))

# Protocol-level server instructions (InitializeResult.instructions) — not a tool description.
SERVER_INSTRUCTIONS = """\
Spatial-awareness MCP: a research epistemics engine pointed at CD4 T-cell exhaustion.
Confidence is P(H|evidence) in log-odds (bits), not a weighted score. Evidence combines
by independence, not by count. Simulation is optional weak corroboration (~0.16 bits)
and can never be load-bearing for REPORT.

Fail loud: missing data/keys/models → ok:false. Empty literature → under_studied.
Never call TCGA output "validation" (cohort association only).

Typical flow:
1. Resolve cells with list_candidate_cells (needs data/cells.parquet).
2. query_prior_findings before suggest_perturbations; record_finding after results.
3. Gather grounded evidence: search_literature (prefer equal-budget contradiction
   search), find_measured_perturbation_evidence, differential_survival_analysis.
   simulate_perturbations is optional corroboration only.
4. evaluate_evidence (Bayesian budget + optional gate) / decide_next_action.
5. If gating stalls, recommend_next_experiment (prefers reanalyze_existing_data).

REPORT requires: posterior ≥ threshold, ≥2 independent sources, ≥1 grounded source
(measured/cohort/literature — not simulation), priors checked, no unresolved conflict.
map_spatial_to_single is not implemented. Tools write additive graph edges as side effects.\
"""

REGISTRY = build_default_registry()
app = Server("spatial-awareness", instructions=SERVER_INSTRUCTIONS)


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
        )
        for spec in REGISTRY.list_specs()
    ]


@app.call_tool(validate_input=False)
async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch through the registry; return structured JSON content.

    Schema validation is owned by ToolRegistry (not the transport layer) so the
    standalone test harness and MCP clients see the same error shape.
    """
    try:
        result = REGISTRY.call(name, arguments or {})
        return result
    except ToolValidationError as exc:
        # Structured error payload (not a crash) so the agent can recover
        return {
            "ok": False,
            "error": "validation_error",
            "message": str(exc),
            "details": exc.details,
        }
    except UnknownToolError as exc:
        return {"ok": False, "error": "unknown_tool", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 — isolate teammate tool failures
        return {
            "ok": False,
            "error": "tool_execution_error",
            "message": f"{type(exc).__name__}: {exc}",
        }


def create_starlette_app() -> Starlette:
    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        json_response=True,
        stateless=True,
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[Mount("/mcp", app=handle_streamable_http)],
        lifespan=lifespan,
    )
    return CORSMiddleware(
        starlette_app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE"],
        expose_headers=["Mcp-Session-Id"],
    )


def main() -> None:
    uvicorn.run(
        create_starlette_app(),
        host=HOST,
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
