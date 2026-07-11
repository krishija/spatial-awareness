"""Structured logging for every tool call."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("spatial_mcp")
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = setup_logging()


def log_tool_call(
    *,
    name: str,
    arguments: dict[str, Any],
    status: str,
    duration_ms: float,
    result: Any = None,
    error: str | None = None,
) -> None:
    """Emit one JSON line per tool call (demo-friendly, machine-readable)."""
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "tool_call",
        "tool": name,
        "arguments": arguments,
        "status": status,
        "duration_ms": round(duration_ms, 2),
    }
    if error is not None:
        payload["error"] = error
    elif result is not None:
        # Keep logs readable: summarize large arrays
        if isinstance(result, dict) and "cells" in result and isinstance(result["cells"], list):
            payload["result_summary"] = {
                "n_cells": len(result["cells"]),
                "keys": list(result.keys()),
            }
        elif isinstance(result, dict) and "findings" in result:
            payload["result_summary"] = {"n_findings": len(result["findings"])}
        elif isinstance(result, dict) and "citations" in result:
            payload["result_summary"] = {"n_citations": len(result["citations"])}
        elif isinstance(result, dict) and "suggestions" in result:
            payload["result_summary"] = {
                "n_suggestions": len(result["suggestions"]),
                "genes": [s.get("gene") for s in result["suggestions"]],
            }
        else:
            payload["result"] = result
    log.info(json.dumps(payload, default=str))
