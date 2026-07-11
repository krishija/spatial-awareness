#!/usr/bin/env python3
"""Minimal MCP mock client — connects the way K Pro would.

Prereq: start the server first:
  cd mcp_server && spatial-mcp
  # or: python -m spatial_mcp.server

Then:
  python scripts/mock_client.py
  python scripts/mock_client.py --url http://localhost:8000/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


async def run(url: str) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    print(f"Connecting to {url} …\n")

    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("=== initialize ===")
            print(f"  server: {init.serverInfo.name} {init.serverInfo.version}")
            print(f"  protocol: {init.protocolVersion}\n")

            print("=== list_tools ===")
            tools = await session.list_tools()
            for t in tools.tools:
                print(f"  - {t.name}")
            print()

            async def call(name: str, arguments: dict) -> None:
                print(f"=== call_tool {name} ===")
                print(f"  request: {json.dumps(arguments)}")
                result = await session.call_tool(name, arguments)
                # Prefer structured content / text
                if result.structuredContent is not None:
                    print("  response (structured):")
                    print(json.dumps(result.structuredContent, indent=2, default=str))
                else:
                    for block in result.content:
                        text = getattr(block, "text", None)
                        if text:
                            print("  response (text):")
                            try:
                                print(json.dumps(json.loads(text), indent=2))
                            except json.JSONDecodeError:
                                print(text)
                if result.isError:
                    print("  [isError=True]")
                print()

            # Trace that mirrors a plausible K Pro agent loop
            await call("query_prior_findings", {"sample_id": "crc-01", "gene": "PDCD1"})
            await call(
                "list_candidate_cells",
                {
                    "sample_id": "crc-01",
                    "niche": "tumor_core",
                    "min_exhaustion_score": 0.8,
                },
            )
            await call(
                "search_literature",
                {
                    "query": "PDCD1 TOX exhaustion CD4 tumor core",
                    "context": "CD4_Tex_term in tumor_core",
                },
            )
            await call(
                "suggest_perturbations",
                {
                    "cell_id": "crc-01-c0042",
                    "phenotype": "CD4_Tex_term",
                    "niche": "tumor_core",
                },
            )
            await call(
                "simulate_perturbations",
                {"cell_id": "crc-01-c0042", "gene": "PDCD1"},
            )
            # Out-of-vocabulary error path
            await call(
                "simulate_perturbations",
                {"cell_id": "crc-01-c0042", "gene": "FAKEGENE999"},
            )
            await call(
                "record_finding",
                {
                    "sample_id": "crc-01",
                    "cell_id": "crc-01-c0042",
                    "niche": "tumor_core",
                    "gene": "PDCD1",
                    "finding_summary": (
                        "Mock-client session: PDCD1 KO on crc-01-c0042 predicted "
                        "effector-like marker shift; recorded for cross-session memory."
                    ),
                },
            )
            await call("query_prior_findings", {"sample_id": "crc-01", "gene": "PDCD1"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/mcp",
        help="Streamable HTTP MCP endpoint",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.url))
    except Exception as exc:  # noqa: BLE001
        print(f"Client failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "Is the server running?  cd mcp_server && spatial-mcp",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
