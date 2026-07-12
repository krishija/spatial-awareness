"""Shared loader for the Atera cells.parquet — no fixture fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CELLS_PARQUET = DATA_DIR / "cells.parquet"

MARKER_GENES = [
    "PDCD1",
    "TCF7",
    "TOX",
    "LAG3",
    "GZMB",
    "IL7R",
    "CTLA4",
    "FOXP3",
]

_CELLS = None
_LOADED = False
_BY_ID: dict[str, Any] | None = None


def parquet_path() -> Path:
    return CELLS_PARQUET


def require_cells():
    """Return the full dataframe. Raises FileNotFoundError if parquet missing."""
    global _CELLS, _LOADED
    if _LOADED:
        if _CELLS is None:
            raise FileNotFoundError(_missing_msg())
        return _CELLS
    _LOADED = True
    if not CELLS_PARQUET.exists():
        _CELLS = None
        raise FileNotFoundError(_missing_msg())
    import pandas as pd

    _CELLS = pd.read_parquet(CELLS_PARQUET)
    print(f"[cell_store] REAL Atera: {len(_CELLS):,} cells from {CELLS_PARQUET}")
    return _CELLS


def _missing_msg() -> str:
    return (
        f"{CELLS_PARQUET} missing. Fetch with: aws s3 cp "
        "s3://owkin-hackathon26-spatialawareness-raw-data/artifacts/mcp_data/cells.parquet "
        "mcp_server/data/"
    )


def get_cell(cell_id: str) -> dict[str, Any] | None:
    """Look up one cell by id from the parquet. None if not found (data must load)."""
    global _BY_ID
    df = require_cells()
    if _BY_ID is None:
        # Build once; ids may be int or str in parquet
        _BY_ID = {}
        for r in df.itertuples():
            _BY_ID[str(r.id)] = r
    row = _BY_ID.get(str(cell_id))
    if row is None:
        return None
    return {
        "id": str(row.id),
        "x": float(row.x),
        "y": float(row.y),
        "cell_type": str(row.cell_type),
        "niche": str(row.niche),
        "exhaustion_state": str(row.exhaustion_state),
        "exhaustion_score": float(row.exhaustion_score),
        "expression": {g: float(getattr(row, g, 0.0)) for g in MARKER_GENES},
    }


def reset_cache() -> None:
    """Test helper."""
    global _CELLS, _LOADED, _BY_ID
    _CELLS = None
    _LOADED = False
    _BY_ID = None
