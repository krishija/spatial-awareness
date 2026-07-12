"""Fail-loud behavior for tools that used to soft-fallback."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.stubs.cell_store import reset_cache
from spatial_mcp.stubs.list_candidate_cells import list_candidate_cells
from spatial_mcp.stubs.map_spatial_to_single import map_spatial_to_single
from spatial_mcp.stubs.scldm_knockout import evaluate_knockout, scldm_available
from spatial_mcp.stubs.search_literature import search_literature
from spatial_mcp.stubs.simulate_perturbations import simulate_perturbations


def test_list_candidate_fails_without_parquet(monkeypatch, tmp_path):
    reset_cache()
    missing = tmp_path / "nope.parquet"
    monkeypatch.setattr(
        "spatial_mcp.stubs.cell_store.CELLS_PARQUET", missing
    )
    # force reload path
    import spatial_mcp.stubs.cell_store as cs

    cs._LOADED = False
    cs._CELLS = None
    out = list_candidate_cells(
        {"sample_id": "atera-cervical-01", "cell_type": "CD4_Treg"}
    )
    assert out["ok"] is False
    assert out["error"] == "data_missing"
    assert out["cells"] == []


def test_search_literature_fails_without_key(monkeypatch):
    monkeypatch.setattr(
        "spatial_mcp.stubs.search_literature.YOU_API_KEY", ""
    )
    out = search_literature({"query": "PD-1 exhaustion CD4"})
    assert out["ok"] is False
    assert out["error"] == "missing_api_key"
    assert out.get("evidence_cards") == [] or out.get("citations") == []


def test_map_spatial_fixture_mode_without_parquet():
    out = map_spatial_to_single({"sample_id": "crc-01"})
    assert out.get("ok") is not False
    assert out.get("mappings")
    assert "FIXTURE MODE" in (out.get("warning") or "")


def test_simulate_fails_without_scldm_or_data(monkeypatch, tmp_path):
    reset_cache()
    missing = tmp_path / "nope.parquet"
    monkeypatch.setattr("spatial_mcp.stubs.cell_store.CELLS_PARQUET", missing)
    import spatial_mcp.stubs.cell_store as cs

    cs._LOADED = False
    cs._CELLS = None
    out = simulate_perturbations({"cell_id": "x", "gene": "PDCD1"})
    assert out["ok"] is False
    assert out["error"] in ("data_missing", "simulation_failed", "data_load_failed")


def test_evaluate_knockout_fails_without_scldm():
    if scldm_available():
        return  # environment has live model — skip negative path
    try:
        evaluate_knockout("PDCD1")
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "scLDM not available" in str(exc)
    assert raised
