"""MCP client helper — always fetches the live tool list from the server."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class McpToolClient:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self._tools: list[dict[str, Any]] | None = None

    async def list_tools(self, force: bool = False) -> list[dict[str, Any]]:
        if self._tools is None or force:
            result = await self.session.list_tools()
            self._tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema,
                }
                for t in result.tools
            ]
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self.session.call_tool(name, arguments)
        if result.isError:
            text = _content_text(result)
            return {"ok": False, "error": "mcp_tool_error", "message": text}
        if result.structuredContent is not None:
            return dict(result.structuredContent)
        text = _content_text(result)
        try:
            return json.loads(text) if text else {"ok": True, "raw": text}
        except json.JSONDecodeError:
            return {"ok": True, "text": text}


def _content_text(result: Any) -> str:
    parts = []
    for block in result.content or []:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)


@asynccontextmanager
async def connect_mcp(url: str) -> AsyncIterator[McpToolClient]:
    async with streamablehttp_client(url) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield McpToolClient(session)
