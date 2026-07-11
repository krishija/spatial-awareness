#!/usr/bin/env python3
"""Per-tool test harness — no MCP transport required.

Usage:
  python scripts/test_tool.py list_candidate_cells --args '{"sample_id":"crc-01","niche":"tumor_core"}'
  python scripts/test_tool.py --list
  python scripts/test_tool.py simulate_perturbations --args '{"cell_id":"crc-01-c0042","gene":"PDCD1"}'
  python scripts/test_tool.py simulate_perturbations --args '{"cell_id":"crc-01-c0042","gene":"NOTAREALGENE"}'
  python scripts/test_tool.py query_prior_findings --args '{"sample_id":"crc-01","gene":"PDCD1"}'

Teammates: import your function, feed example input, confirm output shape.
This script goes through the same registry + schema validation the server uses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running without install: add src/ to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.registry import (  # noqa: E402
    ToolValidationError,
    UnknownToolError,
    build_default_registry,
)


EXAMPLES: dict[str, dict] = {
    "list_candidate_cells": {
        "sample_id": "crc-01",
        "niche": "tumor_core",
        "min_exhaustion_score": 0.7,
    },
    "map_spatial_to_single": {"sample_id": "crc-01"},
    "search_literature": {
        "query": "PD-1 TOX CD4 exhaustion tumor core",
        "context": "CD4_Tex_term in tumor_core",
    },
    "suggest_perturbations": {
        "cell_id": "crc-01-c0042",
        "phenotype": "CD4_Tex_term",
        "niche": "tumor_core",
    },
    "simulate_perturbations": {"cell_id": "crc-01-c0042", "gene": "PDCD1"},
    "record_finding": {
        "sample_id": "crc-01",
        "cell_id": "crc-01-c0042",
        "niche": "tumor_core",
        "gene": "LAG3",
        "finding_summary": "Test harness recorded a LAG3 finding for schema check.",
    },
    "query_prior_findings": {"sample_id": "crc-01", "gene": "PDCD1"},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Test one MCP tool via the registry")
    parser.add_argument("tool", nargs="?", help="Tool name to invoke")
    parser.add_argument(
        "--args",
        default=None,
        help="JSON object of arguments (default: built-in example for the tool)",
    )
    parser.add_argument("--list", action="store_true", help="List registered tools")
    parser.add_argument(
        "--invalid",
        action="store_true",
        help="Call with deliberately invalid args to demo schema rejection",
    )
    args = parser.parse_args()

    registry = build_default_registry()

    if args.list or not args.tool:
        print("Registered tools:\n")
        for spec in registry.list_specs():
            print(f"  {spec.name}")
            print(f"    {spec.description[:100]}…")
        if not args.tool:
            print("\nPass a tool name to invoke it. Examples:")
            for name, ex in EXAMPLES.items():
                print(f"  python scripts/test_tool.py {name}")
            return 0

    if args.invalid:
        arguments: dict = {"not_a_real_field": True}
    elif args.args:
        arguments = json.loads(args.args)
    else:
        if args.tool not in EXAMPLES:
            print(f"No default example for {args.tool}; pass --args '{{...}}'", file=sys.stderr)
            return 1
        arguments = EXAMPLES[args.tool]

    print(f"→ {args.tool}")
    print(f"  args: {json.dumps(arguments)}")
    try:
        result = registry.call(args.tool, arguments)
        print("  status: ok")
        print(json.dumps(result, indent=2, default=str))
        return 0
    except ToolValidationError as exc:
        print("  status: validation_error")
        print(f"  message: {exc}")
        for d in exc.details:
            print(f"    - {d}")
        return 2
    except UnknownToolError as exc:
        print(f"  status: unknown_tool ({exc})")
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"  status: error ({type(exc).__name__}: {exc})")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
