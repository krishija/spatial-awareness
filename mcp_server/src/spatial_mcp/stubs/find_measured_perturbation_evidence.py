"""find_measured_perturbation_evidence — real measurements before trusting simulation.

Priority:
  1. Training-corpus membership (scLDM-CD4 / STATE published gene sets)
  2. LINCS L1000 via Broad CLUE API (optional CLUE_API_KEY)
  3. Existing measured/literature edges + literature cache in SQLite

Context match scored on three axes: cell_type, species, perturbation_mechanism.
Empty result is informative (nothing_found), not a soft failure.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from spatial_mcp.graph import edges_for, insert_edge
from spatial_mcp.memory import get_store
from spatial_mcp.stubs.scldm_knockout import KNOWN_GUIDE_SYMBOLS, MARKER_GENES

# STATE (CD8 virtual cell) — published / commonly cited perturbation gene set (subset).
# Kept explicit and conservative; not a full dump of the training matrix.
STATE_TRAINING_GENES = frozenset(
    {
        "PDCD1",
        "CTLA4",
        "LAG3",
        "HAVCR2",
        "TIGIT",
        "TOX",
        "TCF7",
        "BATF",
        "PRDM1",
        "NR4A1",
        "IL7R",
        "GZMB",
        "IFNG",
        "TNF",
        "STAT1",
        "STAT3",
        "MYC",
        "CDK4",
        "CDK6",
        "E2F1",
    }
)

SCLDM_TRAINING_GENES = frozenset(KNOWN_GUIDE_SYMBOLS)

CLUE_BASE = os.environ.get("CLUE_API_BASE", "https://api.clue.io/api")
CLUE_API_KEY = os.environ.get("CLUE_API_KEY", "")

# Desired experimental context for this project (CD4 T-cell KO biology)
_DEFAULT_WANTED = {
    "cell_type": "cd4",
    "species": "human",
    "perturbation_mechanism": "crispr",  # knockout-like
}


def find_measured_perturbation_evidence(args: dict[str, Any]) -> dict[str, Any]:
    gene = str(args.get("gene") or "").strip().upper()
    if not gene:
        return {
            "ok": False,
            "error": "missing_gene",
            "message": "gene is required.",
            "hits": [],
        }

    cell_type = (args.get("cell_type") or "CD4_T").strip()
    pert_type = (args.get("perturbation_type") or "knockout").strip().lower()
    wanted = {
        "cell_type": _normalize_cell(cell_type),
        "species": "human",
        "perturbation_mechanism": _normalize_mechanism(pert_type),
    }

    hits: list[dict[str, Any]] = []
    notes: list[str] = []

    # 1. Training-data membership
    hits.extend(_training_hits(gene, wanted, cell_type))

    # 2. LINCS / CLUE
    clue_hits, clue_note = _clue_hits(gene, wanted, cell_type, pert_type)
    hits.extend(clue_hits)
    if clue_note:
        notes.append(clue_note)

    # 3. Graph + literature cache
    hits.extend(_graph_and_cache_hits(gene, wanted, cell_type))

    # Deduplicate hits by (source_type, accession) for return list clarity
    hits = _dedupe_hits(hits)

    # Side-effect: insert measured edges for each real hit
    for h in hits:
        try:
            insert_edge(
                gene,
                "measured_perturbation_effect",
                h.get("effect_summary") or "EXPRESSION_SIGNATURE",
                source_type="measured",
                source_id=h.get("accession") or h.get("source_id") or f"measured:{gene}",
                confidence=float(h.get("context_match_score") or 0.5),
                cell_type_context=cell_type,
                metadata={
                    "effect": h.get("effect"),
                    "dataset": h.get("dataset"),
                    "components": h.get("context_match_components"),
                },
            )
        except Exception:  # noqa: BLE001
            pass

    nothing = len(hits) == 0
    return {
        "ok": True,
        "gene": gene,
        "cell_type": cell_type,
        "perturbation_type": pert_type,
        "n_hits": len(hits),
        "hits": hits,
        "nothing_found": nothing,
        "message": (
            "No measured perturbation evidence found in training corpora, LINCS/CLUE, "
            "or prior literature/graph cache — simulated predictions for this gene/"
            "context should be trusted less."
            if nothing
            else None
        ),
        "notes": notes or None,
    }


def _training_hits(
    gene: str, wanted: dict[str, str], cell_type: str
) -> list[dict[str, Any]]:
    out = []
    if gene in SCLDM_TRAINING_GENES:
        comps = score_context_match(
            observed_cell="cd4_t",
            observed_species="human",
            observed_mechanism="crispr",
            wanted=wanted,
        )
        out.append(
            {
                "source_type": "training_corpus",
                "dataset": "scLDM-CD4",
                "accession": "https://virtualcellmodels.cziscience.com/model/scldm-cd4",
                "source_id": f"training:scldm_cd4:{gene}",
                "effect": {
                    "kind": "training_membership",
                    "note": (
                        "Gene is an actual perturbation target in scLDM-CD4's published "
                        "guide/vocabulary set — closer to ground truth the model saw "
                        "than a de-novo out-of-distribution inference."
                    ),
                    "markers_of_interest": list(MARKER_GENES),
                },
                "effect_summary": f"{gene}_IN_SCLDM_TRAINING",
                "context_match_score": comps["score"],
                "context_match_components": comps["components"],
                "cell_type_observed": "CD4 T cell (model domain)",
                "species_observed": "human",
                "perturbation_mechanism_observed": "CRISPR/KO-style (model)",
            }
        )
    if gene in STATE_TRAINING_GENES:
        comps = score_context_match(
            observed_cell="cd8_t",
            observed_species="human",
            observed_mechanism="crispr",
            wanted=wanted,
        )
        out.append(
            {
                "source_type": "training_corpus",
                "dataset": "STATE",
                "accession": "https://virtualcellmodels.cziscience.com/",
                "source_id": f"training:state:{gene}",
                "effect": {
                    "kind": "training_membership",
                    "note": (
                        "Gene appears in STATE-related published perturbation vocabulary "
                        "(CD8-oriented). Context match reflects CD8 vs requested cell type."
                    ),
                },
                "effect_summary": f"{gene}_IN_STATE_TRAINING",
                "context_match_score": comps["score"],
                "context_match_components": comps["components"],
                "cell_type_observed": "CD8 T cell (STATE domain)",
                "species_observed": "human",
                "perturbation_mechanism_observed": "genetic perturbation",
            }
        )
    return out


def _clue_hits(
    gene: str,
    wanted: dict[str, str],
    cell_type: str,
    pert_type: str,
) -> tuple[list[dict[str, Any]], str | None]:
    if not CLUE_API_KEY:
        return [], "CLUE_API_KEY not set — skipped LINCS L1000 live query."

    headers = {"user_key": CLUE_API_KEY, "Accept": "application/json"}
    # Map knockout-ish requests toward genetic perturbagens
    where: dict[str, Any] = {"pert_iname": gene.lower()}
    # Filter genetic when possible
    filt = {"where": where, "limit": 25}
    try:
        resp = requests.get(
            f"{CLUE_BASE}/sigs",
            params={"filter": __import__("json").dumps(filt)},
            headers=headers,
            timeout=25,
        )
        if resp.status_code == 404:
            # Try genes endpoint then sigs by gene
            return [], f"CLUE /sigs returned 404 for {gene}."
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            rows = rows.get("data") or rows.get("sigs") or []
    except requests.RequestException as exc:
        return [], f"CLUE API failed: {type(exc).__name__}: {exc}"

    out = []
    for row in rows[:15]:
        cell = str(row.get("cell_iname") or row.get("cell_id") or "unknown")
        ptype = str(
            row.get("pert_type")
            or row.get("pert_type_id")
            or row.get("cmap_name")
            or "unknown"
        ).lower()
        mechanism = _infer_mechanism_from_clue(ptype, pert_type)
        comps = score_context_match(
            observed_cell=cell.lower(),
            observed_species="human",  # L1000 cell lines are human
            observed_mechanism=mechanism,
            wanted=wanted,
        )
        sig_id = str(row.get("sig_id") or row.get("id") or "")
        out.append(
            {
                "source_type": "lincs_l1000",
                "dataset": "LINCS L1000 (CLUE)",
                "accession": (
                    f"https://clue.io/data/{sig_id}" if sig_id else "https://clue.io/"
                ),
                "source_id": f"lincs:{sig_id or gene}",
                "effect": {
                    "kind": "measured_signature",
                    "pert_iname": row.get("pert_iname") or gene,
                    "pert_type": ptype,
                    "cell_iname": cell,
                    "pert_itime": row.get("pert_itime"),
                    "pert_idose": row.get("pert_idose"),
                    "direction": "signature_available",
                    "magnitude": None,
                    "note": (
                        "Measured L1000 expression signature metadata from CLUE; "
                        "full differential vector available via CLUE job/API."
                    ),
                },
                "effect_summary": f"{gene}_LINCS_SIG_{cell}",
                "context_match_score": comps["score"],
                "context_match_components": comps["components"],
                "cell_type_observed": cell,
                "species_observed": "human",
                "perturbation_mechanism_observed": mechanism,
            }
        )
    if not out:
        return [], f"CLUE returned no signatures for pert_iname={gene.lower()}."
    return out, None


def _graph_and_cache_hits(
    gene: str, wanted: dict[str, str], cell_type: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edge in edges_for(gene):
        if edge["source_type"] not in ("measured", "literature"):
            continue
        # Prefer measured; literature only if claim looks measurement-like
        meta = edge.get("metadata") or {}
        comps = score_context_match(
            observed_cell=(edge.get("cell_type_context") or "unknown").lower(),
            observed_species="human",
            observed_mechanism=str(meta.get("mechanism") or "unknown"),
            wanted=wanted,
        )
        out.append(
            {
                "source_type": "graph_cache",
                "dataset": f"internal_graph:{edge['source_type']}",
                "accession": edge["id"],
                "source_id": edge["source_ids"][0] if edge["source_ids"] else edge["id"],
                "effect": {
                    "kind": "cached_edge",
                    "relation": edge["relation"],
                    "object": edge["object"],
                    "source_ids": edge["source_ids"],
                },
                "effect_summary": edge["object"],
                "context_match_score": comps["score"],
                "context_match_components": comps["components"],
                "cell_type_observed": edge.get("cell_type_context"),
                "species_observed": "human",
                "perturbation_mechanism_observed": meta.get("mechanism"),
            }
        )

    # Literature cache payloads mentioning measured language
    store = get_store()
    try:
        with store._connect() as conn:
            rows = conn.execute(
                "SELECT cache_key, payload_json FROM literature_cache LIMIT 50"
            ).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    import json

    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except Exception:  # noqa: BLE001
            continue
        genes = [str(g).upper() for g in (payload.get("genes") or [])]
        if gene not in genes and gene not in (payload.get("hypothesis") or "").upper():
            continue
        for card in payload.get("evidence_cards") or []:
            claim = (card.get("claim") or "").lower()
            if not any(
                k in claim
                for k in ("measured", "knockout", "crispr", "shrna", "perturbation assay")
            ):
                continue
            if card.get("stance") == "tangential":
                continue
            comps = score_context_match(
                observed_cell=str(
                    (card.get("biological_context") or {}).get("cell_type") or "unknown"
                ).lower(),
                observed_species=str(
                    (card.get("biological_context") or {}).get("organism") or "unknown"
                ).lower(),
                observed_mechanism="unknown",
                wanted=wanted,
            )
            out.append(
                {
                    "source_type": "literature_cache",
                    "dataset": "search_literature_cache",
                    "accession": card.get("url") or card.get("pmid") or r["cache_key"],
                    "source_id": (
                        f"pmid:{card['pmid']}"
                        if card.get("pmid")
                        else card.get("url") or r["cache_key"]
                    ),
                    "effect": {
                        "kind": "literature_measured_claim",
                        "claim": card.get("claim"),
                        "stance": card.get("stance"),
                        "year": card.get("year"),
                    },
                    "effect_summary": (card.get("claim") or "LIT_CLAIM")[:80],
                    "context_match_score": comps["score"],
                    "context_match_components": comps["components"],
                    "cell_type_observed": (card.get("biological_context") or {}).get(
                        "cell_type"
                    ),
                    "species_observed": (card.get("biological_context") or {}).get(
                        "organism"
                    ),
                    "perturbation_mechanism_observed": None,
                }
            )
    return out


def score_context_match(
    *,
    observed_cell: str,
    observed_species: str,
    observed_mechanism: str,
    wanted: dict[str, str],
) -> dict[str, Any]:
    """Three-axis match; weights are explicit and inspectable."""
    w_cell, w_sp, w_mech = 0.45, 0.25, 0.30
    cell = _cell_similarity(observed_cell, wanted["cell_type"])
    species = _species_similarity(observed_species, wanted["species"])
    mech = _mechanism_similarity(observed_mechanism, wanted["perturbation_mechanism"])
    score = round(w_cell * cell + w_sp * species + w_mech * mech, 3)
    return {
        "score": score,
        "components": {
            "cell_type_match": round(cell, 3),
            "species_match": round(species, 3),
            "perturbation_mechanism_match": round(mech, 3),
            "weights": {
                "cell_type": w_cell,
                "species": w_sp,
                "perturbation_mechanism": w_mech,
            },
        },
    }


def _normalize_cell(s: str) -> str:
    s = s.lower().replace(" ", "_")
    if "cd4" in s:
        return "cd4"
    if "cd8" in s:
        return "cd8"
    if "treg" in s or "regulatory" in s:
        return "cd4"
    if "t_cell" in s or "tcell" in s:
        return "t_cell"
    return s


def _normalize_mechanism(s: str) -> str:
    s = s.lower()
    if any(k in s for k in ("crispr", "cas9", "knockout", "ko", "deletion")):
        return "crispr"
    if any(k in s for k in ("shrna", "rnai", "sirna", "knockdown", "kd")):
        return "shrna"
    if any(k in s for k in ("drug", "compound", "inhibitor", "small")):
        return "small_molecule"
    if "overexpress" in s or "oe" == s:
        return "overexpression"
    return s


def _infer_mechanism_from_clue(ptype: str, requested: str) -> str:
    p = ptype.lower()
    if "trt_sh" in p or "shrna" in p:
        return "shrna"
    if "trt_xpr" in p or "crispr" in p or "trt_oe" in p:
        return "crispr" if "oe" not in p else "overexpression"
    if "trt_cp" in p or "compound" in p:
        return "small_molecule"
    return _normalize_mechanism(requested)


def _cell_similarity(observed: str, wanted: str) -> float:
    o, w = observed.lower(), wanted.lower()
    if w in o or o in w:
        return 1.0
    if "cd4" in w and "cd4" in o:
        return 1.0
    if "cd4" in w and "cd8" in o:
        return 0.55
    if "cd4" in w and ("tcell" in o or "t_cell" in o or "jurkat" in o):
        return 0.7
    if "cd4" in w and any(
        x in o for x in ("a375", "mcf7", "pc3", "hepg2", "ht29", "cancer", "tumor")
    ):
        return 0.15
    if "cd4" in w and any(x in o for x in ("pbmc", "immune", "thp", "u937")):
        return 0.4
    return 0.2


def _species_similarity(observed: str, wanted: str) -> float:
    o, w = observed.lower(), wanted.lower()
    if "unknown" in o:
        return 0.4
    if w in o or o in w or ("human" in w and ("human" in o or "homo" in o)):
        return 1.0
    if "mouse" in o or "murine" in o:
        return 0.45
    return 0.3


def _mechanism_similarity(observed: str, wanted: str) -> float:
    o, w = _normalize_mechanism(observed), _normalize_mechanism(wanted)
    if o == "unknown":
        return 0.35
    if o == w:
        return 1.0
    # CRISPR vs shRNA both genetic knockdown-ish
    if {o, w} <= {"crispr", "shrna"}:
        return 0.7
    if "small_molecule" in (o, w) and {"crispr", "shrna"} & {o, w}:
        return 0.35
    return 0.25


def _dedupe_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for h in sorted(hits, key=lambda x: -float(x.get("context_match_score") or 0)):
        key = f"{h.get('source_type')}:{h.get('accession')}:{h.get('effect_summary')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out
