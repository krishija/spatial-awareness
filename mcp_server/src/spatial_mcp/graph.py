"""Knowledge-graph edges on top of the existing SQLite FindingsStore.

Not a graph engine — structured relationship rows with BFS (≤2 hops).
Edges dedupe on (subject, relation, object) and accumulate source_ids.
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Literal

from spatial_mcp.memory import FindingsStore, get_store

SourceType = Literal["literature", "simulation", "measured", "cohort"]

VALID_SOURCE_TYPES = frozenset({"literature", "simulation", "measured", "cohort"})


def _norm(entity: str) -> str:
    return (entity or "").strip().upper()


def _ensure_edges_table(store: FindingsStore) -> None:
    with store._connect() as conn:
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation)"
        )
        conn.commit()


def insert_edge(
    subject: str,
    relation: str,
    object_: str,
    *,
    source_type: str,
    source_id: str,
    confidence: float | None = None,
    cell_type_context: str | None = None,
    sample_context: str | None = None,
    metadata: dict[str, Any] | None = None,
    store: FindingsStore | None = None,
) -> dict[str, Any]:
    """Insert or merge an edge. Same (s,r,o) consolidates source_ids — no double-count."""
    store = store or get_store()
    _ensure_edges_table(store)

    subj = _norm(subject)
    obj = _norm(object_)
    rel = (relation or "").strip().lower().replace(" ", "_")
    if not subj or not obj or not rel:
        raise ValueError("subject, relation, and object are required")
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}, got {source_type!r}"
        )
    if not source_id:
        raise ValueError("source_id is required for traceability")

    created_at = datetime.now(timezone.utc).isoformat()
    with store._connect() as conn:
        row = conn.execute(
            """
            SELECT id, source_ids_json, confidence, cell_type_context, sample_context,
                   metadata_json, source_type
            FROM edges
            WHERE subject = ? AND relation = ? AND object = ?
            """,
            (subj, rel, obj),
        ).fetchone()

        if row is None:
            edge_id = f"edge-{uuid.uuid4().hex[:10]}"
            conn.execute(
                """
                INSERT INTO edges (
                    id, subject, relation, object, source_type, source_ids_json,
                    confidence, cell_type_context, sample_context, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge_id,
                    subj,
                    rel,
                    obj,
                    source_type,
                    json.dumps([source_id]),
                    confidence,
                    cell_type_context,
                    sample_context,
                    json.dumps(metadata or {}),
                    created_at,
                ),
            )
            conn.commit()
            return {
                "id": edge_id,
                "subject": subj,
                "relation": rel,
                "object": obj,
                "source_type": source_type,
                "source_ids": [source_id],
                "confidence": confidence,
                "cell_type_context": cell_type_context,
                "sample_context": sample_context,
                "metadata": metadata or {},
                "created_at": created_at,
                "merged": False,
            }

        # Merge: accumulate source_ids; keep max confidence; union metadata lightly
        source_ids = json.loads(row["source_ids_json"] or "[]")
        if source_id not in source_ids:
            source_ids.append(source_id)
        new_conf = row["confidence"]
        if confidence is not None:
            if new_conf is None:
                new_conf = confidence
            else:
                new_conf = max(float(new_conf), float(confidence))
        meta = json.loads(row["metadata_json"] or "{}")
        if metadata:
            # Keep list of source_types seen
            seen_types = set(meta.get("source_types") or [row["source_type"]])
            seen_types.add(source_type)
            meta["source_types"] = sorted(seen_types)
            meta.update({k: v for k, v in metadata.items() if k != "source_types"})
        else:
            seen_types = set(meta.get("source_types") or [row["source_type"]])
            seen_types.add(source_type)
            meta["source_types"] = sorted(seen_types)

        cell_ctx = row["cell_type_context"] or cell_type_context
        sample_ctx = row["sample_context"] or sample_context
        # Prefer measured > literature > cohort > simulation as primary source_type label
        rank = {"measured": 4, "literature": 3, "cohort": 2, "simulation": 1}
        primary = row["source_type"]
        if rank.get(source_type, 0) > rank.get(primary, 0):
            primary = source_type

        conn.execute(
            """
            UPDATE edges SET
                source_ids_json = ?,
                confidence = ?,
                cell_type_context = ?,
                sample_context = ?,
                metadata_json = ?,
                source_type = ?
            WHERE id = ?
            """,
            (
                json.dumps(source_ids),
                new_conf,
                cell_ctx,
                sample_ctx,
                json.dumps(meta),
                primary,
                row["id"],
            ),
        )
        conn.commit()
        return {
            "id": row["id"],
            "subject": subj,
            "relation": rel,
            "object": obj,
            "source_type": primary,
            "source_ids": source_ids,
            "confidence": new_conf,
            "cell_type_context": cell_ctx,
            "sample_context": sample_ctx,
            "metadata": meta,
            "merged": True,
        }


def _row_to_edge(r: Any) -> dict[str, Any]:
    return {
        "id": r["id"],
        "subject": r["subject"],
        "relation": r["relation"],
        "object": r["object"],
        "source_type": r["source_type"],
        "source_ids": json.loads(r["source_ids_json"] or "[]"),
        "confidence": r["confidence"],
        "cell_type_context": r["cell_type_context"],
        "sample_context": r["sample_context"],
        "metadata": json.loads(r["metadata_json"] or "{}"),
        "created_at": r["created_at"],
    }


def edges_for(
    entity: str,
    *,
    store: FindingsStore | None = None,
    as_subject: bool = True,
    as_object: bool = True,
) -> list[dict[str, Any]]:
    store = store or get_store()
    _ensure_edges_table(store)
    ent = _norm(entity)
    clauses = []
    params: list[Any] = []
    if as_subject:
        clauses.append("subject = ?")
        params.append(ent)
    if as_object:
        clauses.append("object = ?")
        params.append(ent)
    if not clauses:
        return []
    sql = f"SELECT * FROM edges WHERE {' OR '.join(clauses)}"
    with store._connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_edge(r) for r in rows]


def find_related(
    entity: str,
    *,
    max_hops: int = 2,
    store: FindingsStore | None = None,
) -> dict[str, Any]:
    """BFS over undirected edges up to max_hops (default 2)."""
    store = store or get_store()
    _ensure_edges_table(store)
    start = _norm(entity)
    max_hops = max(1, min(int(max_hops), 2))  # cap at 2 by design

    visited: set[str] = {start}
    # node -> (hop, path of edge ids, via entity chain)
    paths: dict[str, dict[str, Any]] = {
        start: {"hops": 0, "path": [], "via": [start]}
    }
    q: deque[tuple[str, int]] = deque([(start, 0)])

    while q:
        node, hop = q.popleft()
        if hop >= max_hops:
            continue
        for edge in edges_for(node, store=store):
            nxt = edge["object"] if edge["subject"] == node else edge["subject"]
            if nxt in visited:
                continue
            visited.add(nxt)
            prev = paths[node]
            paths[nxt] = {
                "hops": hop + 1,
                "path": prev["path"] + [edge],
                "via": prev["via"] + [nxt],
            }
            q.append((nxt, hop + 1))

    related = [
        {
            "entity": ent,
            "hops": info["hops"],
            "via": info["via"],
            "edges": info["path"],
        }
        for ent, info in paths.items()
        if ent != start
    ]
    related.sort(key=lambda x: (x["hops"], x["entity"]))
    return {"seed": start, "max_hops": max_hops, "n": len(related), "related": related}


def all_edges(*, store: FindingsStore | None = None) -> list[dict[str, Any]]:
    store = store or get_store()
    _ensure_edges_table(store)
    with store._connect() as conn:
        rows = conn.execute("SELECT * FROM edges").fetchall()
    return [_row_to_edge(r) for r in rows]


def clear_edges(*, store: FindingsStore | None = None) -> None:
    """Test helper."""
    store = store or get_store()
    _ensure_edges_table(store)
    with store._connect() as conn:
        conn.execute("DELETE FROM edges")
        conn.commit()
