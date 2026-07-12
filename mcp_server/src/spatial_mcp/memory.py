"""SQLite-backed persistent store for agent findings."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default DB lives under mcp_server/data/
_DEFAULT_DB = (
    Path(__file__).resolve().parents[2] / "data" / "findings.db"
)


def default_db_path() -> Path:
    override = os.environ.get("SPATIAL_MCP_DB")
    return Path(override) if override else _DEFAULT_DB


SEED_FINDINGS: list[dict[str, Any]] = [
    {
        "sample_id": "crc-01",
        "cell_id": "crc-01-c0042",
        "niche": "tumor_core",
        "gene": "PDCD1",
        "finding_summary": (
            "In CRC-01 core CD4_Tex_term cell crc-01-c0042, simulated PDCD1 KO predicted "
            "↓PDCD1/TOX and ↑TCF7/IL7R/GZMB, consistent with partial reversion from "
            "terminal exhaustion toward a progenitor/effector-like marker profile."
        ),
        "citations": [
            {
                "title": "PD-1 blockade restores effector function in exhausted CD4 T cells",
                "source": "Nature Immunology (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            }
        ],
    },
    {
        "sample_id": "crc-01",
        "cell_id": "crc-01-c0401",
        "niche": "tumor_margin",
        "gene": "CTLA4",
        "finding_summary": (
            "Margin CD4_Treg crc-01-c0401: CTLA4 KO predicted ↓CTLA4/FOXP3. Recorded as "
            "a candidate local-suppression relief axis; not yet compared to PDCD1 KO on "
            "neighboring Tex progenitors."
        ),
        "citations": [
            {
                "title": "CTLA-4 controls Treg-mediated restraint of CD4 antitumor responses",
                "source": "Immunity (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            }
        ],
    },
    {
        "sample_id": "nsclc-03",
        "cell_id": "nsclc-03-c0015",
        "niche": "tumor_core",
        "gene": "TOX",
        "finding_summary": (
            "NSCLC-03 core Tex terminal cell: TOX KO shifted markers toward higher TCF7 "
            "and IL7R. Flagged as already investigated — avoid re-proposing TOX for this "
            "sample/niche without new spatial context."
        ),
        "citations": [
            {
                "title": "TOX reinforces the identity and suppresses reprogramming of exhausted T cells",
                "source": "Nature (simulated)",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            }
        ],
    },
]


class FindingsStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    sample_id TEXT NOT NULL,
                    cell_id TEXT,
                    niche TEXT,
                    gene TEXT,
                    finding_summary TEXT NOT NULL,
                    citations_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_findings_sample ON findings(sample_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_findings_niche ON findings(niche)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_findings_gene ON findings(gene)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS literature_cache (
                    cache_key TEXT PRIMARY KEY,
                    query_norm TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lit_cache_query ON literature_cache(query_norm)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    object TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    confidence REAL,
                    cell_type_context TEXT,
                    sample_context TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(subject, relation, object)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_subject ON edges(subject)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_object ON edges(object)"
            )
            count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            if count == 0:
                for seed in SEED_FINDINGS:
                    self._insert(conn, seed)
            conn.commit()

    def _insert(self, conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
        finding_id = data.get("id") or f"finding-{uuid.uuid4().hex[:10]}"
        created_at = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        gene = data.get("gene")
        if gene:
            gene = gene.upper()
        citations = data.get("citations") or []
        conn.execute(
            """
            INSERT INTO findings (
                id, sample_id, cell_id, niche, gene, finding_summary, citations_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                data["sample_id"],
                data.get("cell_id"),
                data.get("niche"),
                gene,
                data["finding_summary"],
                json.dumps(citations),
                created_at,
            ),
        )
        return {
            "id": finding_id,
            "sample_id": data["sample_id"],
            "cell_id": data.get("cell_id"),
            "niche": data.get("niche"),
            "gene": gene,
            "finding_summary": data["finding_summary"],
            "citations": citations,
            "created_at": created_at,
        }

    def record(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            row = self._insert(conn, data)
            conn.commit()
            return row

    def query(
        self,
        *,
        sample_id: str | None = None,
        niche: str | None = None,
        gene: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if sample_id is not None:
            clauses.append("sample_id = ?")
            params.append(sample_id)
        if niche is not None:
            clauses.append("niche = ?")
            params.append(niche)
        if gene is not None:
            clauses.append("UPPER(gene) = ?")
            params.append(gene.upper())

        sql = "SELECT * FROM findings"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            results.append(
                {
                    "id": r["id"],
                    "sample_id": r["sample_id"],
                    "cell_id": r["cell_id"],
                    "niche": r["niche"],
                    "gene": r["gene"],
                    "finding_summary": r["finding_summary"],
                    "citations": json.loads(r["citations_json"] or "[]"),
                    "created_at": r["created_at"],
                }
            )
        return results

    def get_literature_cache(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, created_at FROM literature_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["_cache_hit"] = True
        payload["_cached_at"] = row["created_at"]
        return payload

    def put_literature_cache(
        self,
        *,
        cache_key: str,
        query_norm: str,
        aliases: list[str],
        payload: dict[str, Any],
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO literature_cache
                    (cache_key, query_norm, aliases_json, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    query_norm,
                    json.dumps(sorted(set(aliases))),
                    json.dumps(payload),
                    created_at,
                ),
            )
            conn.commit()

    def record_literature_finding(
        self,
        *,
        gene: str | None,
        niche: str | None,
        summary: str,
        evidence_cards: list[dict[str, Any]],
        sample_id: str = "literature",
    ) -> dict[str, Any]:
        """Persist a literature rollup as a finding so query_prior_findings can surface it."""
        citations = [
            {
                "title": c.get("title") or "Untitled",
                "source": c.get("source") or "unknown",
                "url": c.get("url") or "",
                "relevance": c.get("claim") or c.get("stance") or "",
            }
            for c in evidence_cards[:10]
        ]
        return self.record(
            {
                "sample_id": sample_id,
                "niche": niche,
                "gene": gene,
                "finding_summary": summary,
                "citations": citations,
            }
        )


# Process-wide store (one DB file; path overridable via SPATIAL_MCP_DB)
_store: FindingsStore | None = None


def get_store() -> FindingsStore:
    global _store
    if _store is None:
        _store = FindingsStore()
    return _store


def reset_store(db_path: Path | None = None) -> FindingsStore:
    """Replace the process-wide store (tests / isolated DBs)."""
    global _store
    _store = FindingsStore(db_path) if db_path is not None else FindingsStore()
    return _store
