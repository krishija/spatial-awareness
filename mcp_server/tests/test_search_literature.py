"""Unit tests for literature decomposition, aliases, pubmed keys, rollup helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spatial_mcp.agent.extract import evidence_from_tool_result
from spatial_mcp.stubs.lit_aliases import expand_aliases, genes_mentioned
from spatial_mcp.stubs.lit_decompose import decompose_queries
from spatial_mcp.stubs.lit_pubmed import canonical_source_key
from spatial_mcp.stubs.search_literature import _build_rollup, search_literature


def test_decompose_includes_mechanistic_and_pathway():
    subs = decompose_queries(
        {
            "query": "Does PDCD1 knockdown restore effector function?",
            "hypothesis": "PDCD1 knockdown increases reactivation in progenitor-exhausted CD4 cells",
            "gene": "PDCD1",
            "phenotype": "CD4_Tex_prog",
            "niche": "tumor_margin",
        },
        aliases=["PDCD1", "PD-1", "CD279"],
    )
    kinds = {s["kind"] for s in subs}
    assert "mechanistic" in kinds
    assert "pathway" in kinds
    assert any("PD-1" in s["text"] or "PDCD1" in s["text"] for s in subs)


def test_decompose_adds_interaction_for_two_genes():
    subs = decompose_queries(
        {
            "query": "PDCD1 and TOX combined knockout",
            "genes": ["PDCD1", "TOX"],
        },
        aliases=["PDCD1", "PD-1", "TOX"],
    )
    assert any(s["kind"] == "interaction" for s in subs)
    inter = next(s for s in subs if s["kind"] == "interaction")
    assert "synergy" in inter["text"].lower() or "redundancy" in inter["text"].lower()


def test_static_alias_expansion_includes_pd1():
    info = expand_aliases(["PDCD1"])
    aliases_upper = {a.upper() for a in info["all_aliases"]}
    assert "PDCD1" in aliases_upper
    assert "PD-1" in aliases_upper or "PD1" in aliases_upper


def test_genes_mentioned_from_text():
    assert "PDCD1" in genes_mentioned("Does PDCD1 KO help Tex cells?")


def test_canonical_key_dedupes_pubmed_urls():
    a = canonical_source_key(
        "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "Some Title",
        "12345678",
    )
    b = canonical_source_key(
        "https://www.ncbi.nlm.nih.gov/pubmed/12345678",
        "Other mirror title",
        "12345678",
    )
    assert a == b == "pmid:12345678"


def test_rollup_counts_stances():
    cards = [
        {"stance": "supports", "journal": "Nature", "year": "2020", "publication_types": ["Review"]},
        {"stance": "supports", "journal": "Cell", "year": "2022", "publication_types": ["Journal Article"]},
        {"stance": "contradicts", "journal": "Nature", "year": "2024", "publication_types": ["Clinical Trial"]},
        {"stance": "tangential", "journal": "bioRxiv", "year": "2021", "publication_types": []},
    ]
    r = _build_rollup(cards)
    assert r["n_supports"] == 2
    assert r["n_contradicts"] == 1
    assert r["n_tangential"] == 1
    assert r["n_independent_venues"] >= 2
    assert "supporting" in r["narrative"].lower() or "support" in r["narrative"].lower()


def test_extract_uses_stance_from_cards():
    result = {
        "ok": True,
        "evidence_cards": [
            {
                "title": "Paper A",
                "source": "Nature",
                "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                "pmid": "1",
                "claim": "PD-1 blockade restores effectors",
                "stance": "supports",
                "metadata_confidence": "high",
                "extraction_ok": True,
                "publication_types": ["Journal Article"],
            },
            {
                "title": "Paper B",
                "source": "Cell",
                "url": "https://pubmed.ncbi.nlm.nih.gov/2/",
                "pmid": "2",
                "claim": "PD-1 blockade fails in this niche",
                "stance": "contradicts",
                "metadata_confidence": "high",
                "extraction_ok": True,
                "publication_types": ["Journal Article"],
            },
            {
                "title": "Paper C",
                "source": "bioRxiv",
                "url": "https://biorxiv.org/x",
                "claim": "Mentions PDCD1 in passing",
                "stance": "tangential",
                "metadata_confidence": "low",
                "extraction_ok": True,
            },
        ],
        "rollup": {"narrative": "mixed"},
    }
    items = evidence_from_tool_result("search_literature", {"gene": "PDCD1"}, result)
    pols = {i.polarity for i in items}
    assert "supports" in pols
    assert "contradicts" in pols
    assert "neutral" in pols  # tangential


def test_search_literature_fails_without_you_key(monkeypatch):
    monkeypatch.setattr(
        "spatial_mcp.stubs.search_literature.YOU_API_KEY", ""
    )
    out = search_literature({"query": "PDCD1 exhaustion"})
    assert out["ok"] is False
    assert out["error"] == "missing_api_key"
