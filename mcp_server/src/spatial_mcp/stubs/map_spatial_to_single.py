"""map_spatial_to_single — field-aware OT mapping is not implemented.

Fail loud: do not invent atlas couplings from fixtures.
"""

from __future__ import annotations

from typing import Any


def map_spatial_to_single(args: dict[str, Any]) -> dict[str, Any]:
    sample_id = args.get("sample_id")
    atlas = args.get("atlas_reference") or "human_immune_v1"
    return {
        "ok": False,
        "error": "not_implemented",
        "sample_id": sample_id,
        "atlas_reference": atlas,
        "mappings": [],
        "summary": {},
        "message": (
            "map_spatial_to_single (field-aware OT / coupling entropy) is not "
            "implemented. Refusing to invent atlas mappings from fixtures."
        ),
    }
