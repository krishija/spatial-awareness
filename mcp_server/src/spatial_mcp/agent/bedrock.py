"""Amazon Bedrock Converse client using bearer-token auth.

Auth: set AWS_BEARER_TOKEN_BEDROCK (Bedrock API key). boto3 detects it for
bedrock-runtime; we also support a direct HTTP path with
Authorization: Bearer <token> as documented by AWS.
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


def load_bearer_token() -> str:
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "").strip().strip('"')
    if not token:
        raise RuntimeError(
            "AWS_BEARER_TOKEN_BEDROCK is not set. Export your Bedrock API key "
            "or place it in the repo .env (loaded by the CLI)."
        )
    return token


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
        try:
            import boto3

            # Ensure env var is set for SDK auto-detection
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = self.token
            self._boto = boto3.client("bedrock-runtime", region_name=self.region)
        except Exception:
            self._boto = None

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
        if self._boto is not None:
            try:
                return self._boto.converse(modelId=self.model_id, **body)
            except Exception:
                # Fall through to HTTP bearer path
                pass
        return self._converse_http(body)

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
