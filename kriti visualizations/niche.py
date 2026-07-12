"""
niche.py — spatial neighborhood composition. Modular by design.

The core question: "for cells of type T, what is in their k nearest spatial
neighbours, and is it MORE than you'd expect by chance?"

DESIGN FOR MCP:
  - Build the kNN index ONCE, up to K_MAX. Any k <= K_MAX is then a slice, not
    a rebuild. So an agent can ask for k=5, k=30, k=50 and each answers in ms.
  - Every public function is pure, takes primitives, returns JSON-safe dicts.
  - No global state beyond the cached index.

The enrichment (not the raw fraction) is what matters. Epithelium is 60% of a
tumour section, so EVERY cell type has lots of epithelial neighbours. That is
not a finding. Observed/expected against a permutation null is a finding.

    # build once
    python niche.py --adata /data/work/atera_annotated.h5ad --build

    # then query (or import and call from the MCP server)
    python niche.py --query CD4_T --k 15
"""
from __future__ import annotations

import argparse, json, pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import anndata as ad
from sklearn.neighbors import NearestNeighbors

K_MAX = 50
CACHE = Path("/data/artifacts/niche_index.pkl")


class NicheIndex:
    """Precomputed spatial kNN. Build once, query any k <= K_MAX instantly."""

    def __init__(self, coords: np.ndarray, labels: np.ndarray,
                 section: Optional[np.ndarray] = None, k_max: int = K_MAX,
                 n_perm: int = 200, seed: int = 0):
        self.k_max = k_max
        self.labels = np.asarray(labels).astype(str)
        self.types = sorted(set(self.labels))
        self.t2i = {t: i for i, t in enumerate(self.types)}
        self.section = (np.asarray(section).astype(str) if section is not None
                        else np.zeros(len(labels), dtype=str))
        self.coords = np.asarray(coords, dtype=np.float32)
        self.n = len(self.labels)

        # kNN WITHIN section only. Across sections is meaningless — a "neighbour"
        # on a different slide is not a neighbour.
        self.nbr_idx = np.full((self.n, k_max), -1, dtype=np.int32)
        self.nbr_dist = np.full((self.n, k_max), np.inf, dtype=np.float32)
        for s in np.unique(self.section):
            m = np.where(self.section == s)[0]
            kk = min(k_max + 1, len(m))
            nn = NearestNeighbors(n_neighbors=kk).fit(self.coords[m])
            d, i = nn.kneighbors(self.coords[m])
            self.nbr_idx[m, :kk - 1] = m[i[:, 1:]]      # drop self
            self.nbr_dist[m, :kk - 1] = d[:, 1:]

        # label of every neighbour, as an int code -> composition is a bincount
        self.nbr_code = np.where(
            self.nbr_idx >= 0,
            np.array([self.t2i[t] for t in self.labels])[np.clip(self.nbr_idx, 0, None)],
            -1,
        ).astype(np.int16)

        # background: what a random neighbour looks like, per section.
        # This is the "expected" that enrichment is measured against.
        self.background = {}
        for s in np.unique(self.section):
            m = self.section == s
            c = np.bincount([self.t2i[t] for t in self.labels[m]],
                            minlength=len(self.types)).astype(float)
            self.background[s] = c / c.sum()

        # permutation null: shuffle labels WITHIN section, recompute composition.
        # Within-section preserves density and geometry and destroys ONLY the
        # label-position association. A global shuffle would be a weaker (and
        # dishonestly easier) null.
        #
        # PERF: permute ONCE per iteration and score every cell type against that
        # same permutation. The naive version re-permutes per (type, perm) and is
        # ~n_types times slower for identical statistics.
        rng = np.random.default_rng(seed)
        sel_by_type = {t: np.where(self.labels == t)[0] for t in self.types}
        acc = {t: np.zeros((n_perm, len(self.types)), dtype=np.float32)
               for t in self.types if len(sel_by_type[t])}

        sec_slices = [np.where(self.section == s)[0] for s in np.unique(self.section)]
        base_codes = np.array([self.t2i[x] for x in self.labels], dtype=np.int16)
        valid = self.nbr_idx >= 0
        safe_idx = np.clip(self.nbr_idx, 0, None)

        for p in range(n_perm):
            perm = base_codes.copy()
            for m in sec_slices:
                perm[m] = rng.permutation(perm[m])
            pc_all = np.where(valid, perm[safe_idx], -1)     # (n, k_max)
            for t, sel in sel_by_type.items():
                if len(sel) == 0:
                    continue
                acc[t][p] = _compose(pc_all[sel], len(self.types))
        self.null = acc

    def composition(self, cell_type: str, k: int = 15) -> dict:
        if cell_type not in self.t2i:
            return {"error": f"unknown cell type '{cell_type}'", "available": self.types}
        k = int(np.clip(k, 1, self.k_max))
        sel = np.where(self.labels == cell_type)[0]
        if len(sel) == 0:
            return {"error": f"no cells of type {cell_type}"}

        codes = self.nbr_code[sel, :k]
        obs = _compose(codes, len(self.types))

        # expected = section-weighted background composition
        exp = np.zeros(len(self.types))
        for s, w in pd.Series(self.section[sel]).value_counts(normalize=True).items():
            exp += w * self.background[s]

        null = self.null[cell_type][:, :]        # null built at k_max
        null_mu, null_sd = null.mean(0), null.std(0) + 1e-9
        z = (obs - null_mu) / null_sd
        p = np.array([(np.abs(null[:, j] - null_mu[j]) >= abs(obs[j] - null_mu[j])).mean()
                      for j in range(len(self.types))])

        rows = []
        for j, t in enumerate(self.types):
            rows.append({
                "neighbor_type": t,
                "observed_frac": round(float(obs[j]), 4),
                "expected_frac": round(float(exp[j]), 4),
                "enrichment": round(float(obs[j] / (exp[j] + 1e-9)), 3),
                "z": round(float(z[j]), 2),
                "p": round(float(p[j]), 4),
            })
        rows.sort(key=lambda r: -r["enrichment"])

        return {
            "cell_type": cell_type,
            "k": k,
            "n_cells": int(len(sel)),
            "median_neighbor_dist_um": round(float(np.median(self.nbr_dist[sel, :k])), 1),
            "neighborhood": rows,
            "note": "enrichment = observed/expected. Raw fractions are dominated by "
                    "whatever is abundant in the section; use enrichment, not frac.",
        }

    def per_cell(self, cell_type: str, k: int = 15) -> pd.DataFrame:
        """Per-cell neighbourhood vectors — the input to niche clustering."""
        sel = np.where(self.labels == cell_type)[0] if cell_type != "*" else np.arange(self.n)
        k = int(np.clip(k, 1, self.k_max))
        codes = self.nbr_code[sel, :k]
        out = np.zeros((len(sel), len(self.types)), dtype=np.float32)
        for j in range(len(self.types)):
            out[:, j] = (codes == j).sum(1)
        out /= np.maximum(out.sum(1, keepdims=True), 1)
        return pd.DataFrame(out, columns=self.types, index=sel)


def _compose(codes: np.ndarray, n_types: int) -> np.ndarray:
    flat = codes[codes >= 0]
    c = np.bincount(flat, minlength=n_types).astype(float)
    return c / max(c.sum(), 1)


# ------------------------------------------------------------------ build/query
def build(adata_path: str, label_key: str = "celltype",
          spatial_key: str = "spatial", section_key: Optional[str] = None) -> NicheIndex:
    a = ad.read_h5ad(adata_path)
    idx = NicheIndex(
        coords=a.obsm[spatial_key],
        labels=a.obs[label_key].values,
        section=a.obs[section_key].values if section_key and section_key in a.obs else None,
    )
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(idx, f)
    print(f"built index: {idx.n:,} cells, {len(idx.types)} types, k_max={idx.k_max}")
    print(f"  -> {CACHE}")
    return idx


def load() -> NicheIndex:
    with open(CACHE, "rb") as f:
        return pickle.load(f)


# ---- THIS is the MCP tool. One function, primitives in, JSON out. -------------
def neighborhood_composition(cell_type: str, k: int = 15) -> dict:
    """What surrounds cells of a given type, spatially?

    Returns each neighbouring cell type with its observed fraction, the fraction
    expected from section composition alone, an enrichment ratio, and a p-value
    from a within-section label permutation null.

    Read the ENRICHMENT column, not the fraction. In a tumour section epithelium
    is everywhere, so everything has epithelial neighbours; that is not biology.
    """
    return load().composition(cell_type, k)


def list_cell_types() -> dict:
    idx = load()
    counts = pd.Series(idx.labels).value_counts()
    return {"cell_types": [{"type": t, "n_cells": int(counts.get(t, 0))} for t in idx.types],
            "k_max": idx.k_max}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--adata")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--label-key", default="celltype")
    ap.add_argument("--section-key", default=None)
    ap.add_argument("--query")
    ap.add_argument("--k", type=int, default=15)
    a = ap.parse_args()

    if a.build:
        build(a.adata, label_key=a.label_key, section_key=a.section_key)
    if a.query:
        print(json.dumps(neighborhood_composition(a.query, a.k), indent=2))
