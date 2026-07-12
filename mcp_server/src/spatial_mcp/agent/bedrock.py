"""Amazon Bedrock Converse client.

Auth (exactly one path — no fallbacks):
- If AWS_BEARER_TOKEN_BEDROCK is set → bearer HTTP Converse only.
- Else → boto3 with the ambient AWS credential chain (env / instance role) only.

Fail loud on auth or invoke errors. Do not silently switch auth modes.
"""

from __future__ import annotations

import json
import os
from typing import Any

import urllib.error
import urllib.request


DEFAULT_MODEL = os.environ.get(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-6",
)
DEFAULT_REGION = os.environ.get("AWS_REGION") or os.environ.get(
    "BEDROCK_REGION", "us-west-2"
)


def load_bearer_token() -> str | None:
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "").strip().strip('"')
    return token or None


def mcp_tools_to_bedrock(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP tool defs {name,description,inputSchema} → Bedrock toolSpec list."""
    out = []
    for t in tools:
        schema = t.get("inputSchema") or t.get("input_schema") or {"type": "object", "properties": {}}
        out.append(
            {
                "toolSpec": {
                    "name": t["name"],
                    "description": t.get("description") or t["name"],
                    "inputSchema": {"json": schema},
                }
            }
        )
    return out


class BedrockConverse:
    def __init__(
        self,
        *,
        model_id: str | None = None,
        region: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model_id = model_id or DEFAULT_MODEL
        self.region = region or DEFAULT_REGION
        self.max_tokens = max_tokens
        self.token = load_bearer_token()
        self._boto = None
        if self.token is None:
            import boto3

            self._boto = boto3.client("bedrock-runtime", region_name=self.region)

    def converse(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        body = {
            "messages": messages,
            "system": [{"text": system}],
            "inferenceConfig": {"maxTokens": self.max_tokens, "temperature": 0.2},
            "toolConfig": {"tools": mcp_tools_to_bedrock(tools)},
        }
        if self.token is not None:
            return self._converse_http(body)
        if self._boto is None:
            raise RuntimeError(
                "No Bedrock auth configured. Set AWS_BEARER_TOKEN_BEDROCK "
                "or provide AWS credentials for boto3."
            )
        return self._boto.converse(modelId=self.model_id, **body)

    def converse_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int | None = None,
    ) -> str:
        """Plain text completion (no tools). Same exclusive auth as converse()."""
        body = {
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "system": [{"text": system}],
            "inferenceConfig": {
                "maxTokens": max_tokens or self.max_tokens,
                "temperature": 0.2,
            },
        }
        if self.token is not None:
            resp = self._converse_http(body)
        elif self._boto is not None:
            resp = self._boto.converse(modelId=self.model_id, **body)
        else:
            raise RuntimeError(
                "No Bedrock auth configured. Set AWS_BEARER_TOKEN_BEDROCK "
                "or provide AWS credentials for boto3."
            )
        return extract_text(resp)

    def _converse_http(self, body: dict[str, Any]) -> dict[str, Any]:
        url = (
            f"https://bedrock-runtime.{self.region}.amazonaws.com"
            f"/model/{self.model_id}/converse"
        )
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Bedrock Converse HTTP {exc.code}: {err_body}"
            ) from exc


def extract_tool_uses(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Return [{toolUseId, name, input}, ...] from a Converse response."""
    output = response.get("output") or {}
    message = output.get("message") or {}
    uses = []
    for block in message.get("content") or []:
        tu = block.get("toolUse")
        if tu:
            uses.append(
                {
                    "toolUseId": tu.get("toolUseId"),
                    "name": tu.get("name"),
                    "input": tu.get("input") or {},
                }
            )
    return uses


def extract_text(response: dict[str, Any]) -> str:
    output = response.get("output") or {}
    message = output.get("message") or {}
    parts = []
    for block in message.get("content") or []:
        if "text" in block:
            parts.append(block["text"])
    return "\n".join(parts).strip()


def assistant_message_from_response(response: dict[str, Any]) -> dict[str, Any]:
    return (response.get("output") or {}).get("message") or {
        "role": "assistant",
        "content": [],
    }


def tool_result_message(
    results: list[tuple[str, dict[str, Any], bool]],
) -> dict[str, Any]:
    """Build a user message containing toolResult blocks.

    results: list of (toolUseId, payload_dict, is_error)
    """
    content = []
    for tool_use_id, payload, is_error in results:
        content.append(
            {
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": [{"json": payload}],
                    "status": "error" if is_error else "success",
                }
            }
        )
    return {"role": "user", "content": content}
