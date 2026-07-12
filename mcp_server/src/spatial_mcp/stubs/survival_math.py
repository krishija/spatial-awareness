"""Signature scoring + Cox PH for differential survival analysis.

No biology routing — pure stats helpers used by the MCP tool handler.
"""

from __future__ import annotations

import math
from typing import Any, Sequence


def zscore_signature(
    expression_by_patient: dict[str, dict[str, float]],
    genes: list[str],
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Per-patient mean of gene-wise z-scores (population-standardized).

    Missing genes for a patient are skipped; patients with zero overlapping
    genes get score 0.0.
    """
    weights = weights or {}
    # Population mean/sd per gene
    stats: dict[str, tuple[float, float]] = {}
    for g in genes:
        vals = [expr[g] for expr in expression_by_patient.values() if g in expr]
        if len(vals) < 2:
            stats[g] = (0.0, 1.0)
            continue
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)
        sd = math.sqrt(var) if var > 1e-12 else 1.0
        stats[g] = (mu, sd)

    scores: dict[str, float] = {}
    for pid, expr in expression_by_patient.items():
        acc = 0.0
        wsum = 0.0
        for g in genes:
            if g not in expr:
                continue
            mu, sd = stats[g]
            w = float(weights.get(g, 1.0))
            acc += w * ((expr[g] - mu) / sd)
            wsum += abs(w)
        scores[pid] = (acc / wsum) if wsum > 0 else 0.0
    return scores


def try_ssgsea(
    expression_by_patient: dict[str, dict[str, float]],
    genes: list[str],
) -> dict[str, float] | None:
    """Optional ssGSEA via gseapy; returns None if unavailable/fails."""
    try:
        import pandas as pd  # type: ignore
        from gseapy import ssgsea  # type: ignore
    except Exception:
        return None

    # genes × samples matrix
    all_genes = sorted({g for expr in expression_by_patient.values() for g in expr})
    if not all_genes:
        return None
    patients = list(expression_by_patient.keys())
    data = {
        pid: [float(expression_by_patient[pid].get(g, 0.0)) for g in all_genes]
        for pid in patients
    }
    df = pd.DataFrame(data, index=all_genes)
    gene_sets = {"signature": [g for g in genes if g in all_genes]}
    if not gene_sets["signature"]:
        return None
    try:
        res = ssgsea(
            data=df,
            gene_sets=gene_sets,
            sample_norm_method="rank",
            outdir=None,
            no_plot=True,
            verbose=False,
        )
        # gseapy versions differ on result attribute names
        nes = getattr(res, "res2d", None)
        if nes is None:
            return None
        # Expect columns Name/Term, Name/sample, NES/ES
        scores: dict[str, float] = {}
        for _, row in nes.iterrows():
            sample = row.get("Name") or row.get("name")
            if sample is None:
                # wide format: columns are samples
                continue
            val = row.get("NES", row.get("ES", row.get("nes")))
            if val is not None and sample in expression_by_patient:
                scores[str(sample)] = float(val)
        if len(scores) >= max(3, len(patients) // 4):
            return scores
        # Fallback parse: transposed
        if hasattr(nes, "columns"):
            for col in nes.columns:
                if col in expression_by_patient:
                    try:
                        scores[col] = float(nes[col].iloc[0])
                    except Exception:
                        pass
            if scores:
                return scores
    except Exception:
        return None
    return None


def median_split(scores: dict[str, float]) -> dict[str, int]:
    vals = sorted(scores.values())
    if not vals:
        return {}
    mid = vals[len(vals) // 2]
    return {pid: 1 if s >= mid else 0 for pid, s in scores.items()}


def tertile_split(scores: dict[str, float]) -> dict[str, int] | None:
    """High (2) vs low (0), dropping middle tertile. Needs n>=30."""
    items = sorted(scores.items(), key=lambda kv: kv[1])
    n = len(items)
    if n < 30:
        return None
    lo = n // 3
    hi = n - n // 3
    out: dict[str, int] = {}
    for i, (pid, _) in enumerate(items):
        if i < lo:
            out[pid] = 0
        elif i >= hi:
            out[pid] = 1
        # middle dropped
    return out


def _matmul_t(X: list[list[float]], beta: list[float]) -> list[float]:
    return [sum(row[j] * beta[j] for j in range(len(beta))) for row in X]


def _clip(v: float, lo: float = -20.0, hi: float = 20.0) -> float:
    return max(lo, min(hi, v))


def cox_ph(
    time: Sequence[float],
    event: Sequence[int],
    X: list[list[float]],
    *,
    max_iter: int = 40,
    tol: float = 1e-6,
) -> dict[str, Any]:
    """Breslow Cox PH via Newton–Raphson. Returns coefs, SEs, HR, CI, Wald p.

    Designed for small p (≤6) and n up to a few thousand — no numpy required.
    """
    n = len(time)
    p = len(X[0]) if X else 0
    if n == 0 or p == 0:
        raise ValueError("empty design matrix")
    if not (len(event) == n and len(X) == n):
        raise ValueError("time/event/X length mismatch")

    beta = [0.0] * p
    order = sorted(range(n), key=lambda i: (time[i], -event[i]))

    for _ in range(max_iter):
        risk = [math.exp(_clip(sum(X[i][j] * beta[j] for j in range(p)))) for i in range(n)]
        grad = [0.0] * p
        hess = [[0.0] * p for _ in range(p)]

        # Process from longest time to shortest so risk set accumulates
        # Actually Breslow: for each failure time, risk set = {k: t_k >= t_i}
        # Efficient: iterate ascending time, maintain suffix sums from the end.
        # Build suffix risk sums from longest → shortest.
        suffix_r = [0.0] * (n + 1)
        suffix_xr = [[0.0] * p for _ in range(n + 1)]
        # order ascending time; suffix from the end of order
        for pos in range(n - 1, -1, -1):
            i = order[pos]
            suffix_r[pos] = suffix_r[pos + 1] + risk[i]
            for j in range(p):
                suffix_xr[pos][j] = suffix_xr[pos + 1][j] + X[i][j] * risk[i]

        pos = 0
        while pos < n:
            i = order[pos]
            t = time[i]
            # tied failure block
            end = pos
            while end < n and time[order[end]] == t:
                end += 1
            deaths = [order[k] for k in range(pos, end) if event[order[k]] == 1]
            d = len(deaths)
            if d == 0:
                pos = end
                continue
            # Risk set starts at pos (all with time >= t)
            R = max(suffix_r[pos], 1e-15)
            S1 = suffix_xr[pos]
            # Breslow for ties: each death contributes using same risk set
            for di in deaths:
                for j in range(p):
                    grad[j] += X[di][j] - S1[j] / R
                for j in range(p):
                    for k in range(p):
                        # S2 approx: need sum x_j x_k r — compute on the fly for risk set
                        pass
            # Hessian via risk-set second moment (recompute once per distinct time)
            S2 = [[0.0] * p for _ in range(p)]
            for kpos in range(pos, n):
                ii = order[kpos]
                r = risk[ii]
                for j in range(p):
                    for k in range(j, p):
                        S2[j][k] += X[ii][j] * X[ii][k] * r
                        if j != k:
                            S2[k][j] = S2[j][k]
            for _ in range(d):
                for j in range(p):
                    for k in range(p):
                        hess[j][k] -= S2[j][k] / R - (S1[j] / R) * (S1[k] / R)
            pos = end

        # Solve hess * delta = grad  (Newton: beta += -H^{-1} grad, H is negative definite
        # We stored d²ℓ so hess is already negative; solve hess * delta = -grad ⇒ delta = H^{-1} (-grad)
        # With our hess accumulating negative contributions, use: solve (-hess) delta = grad
        A = [[-hess[j][k] for k in range(p)] for j in range(p)]
        b = grad[:]
        try:
            delta = _solve(A, b)
        except ZeroDivisionError:
            break
        step = 1.0
        new_beta = [beta[j] + step * delta[j] for j in range(p)]
        if max(abs(d) for d in delta) < tol:
            beta = new_beta
            break
        beta = new_beta

    # Final SE from observed information at MLE
    risk = [math.exp(_clip(sum(X[i][j] * beta[j] for j in range(p)))) for i in range(n)]
    hess = [[0.0] * p for _ in range(p)]
    suffix_r = [0.0] * (n + 1)
    suffix_xr = [[0.0] * p for _ in range(n + 1)]
    for pos in range(n - 1, -1, -1):
        i = order[pos]
        suffix_r[pos] = suffix_r[pos + 1] + risk[i]
        for j in range(p):
            suffix_xr[pos][j] = suffix_xr[pos + 1][j] + X[i][j] * risk[i]
    pos = 0
    while pos < n:
        t = time[order[pos]]
        end = pos
        while end < n and time[order[end]] == t:
            end += 1
        deaths = [order[k] for k in range(pos, end) if event[order[k]] == 1]
        d = len(deaths)
        if d == 0:
            pos = end
            continue
        R = max(suffix_r[pos], 1e-15)
        S1 = suffix_xr[pos]
        S2 = [[0.0] * p for _ in range(p)]
        for kpos in range(pos, n):
            ii = order[kpos]
            r = risk[ii]
            for j in range(p):
                for k in range(j, p):
                    S2[j][k] += X[ii][j] * X[ii][k] * r
                    if j != k:
                        S2[k][j] = S2[j][k]
        for _ in range(d):
            for j in range(p):
                for k in range(p):
                    hess[j][k] -= S2[j][k] / R - (S1[j] / R) * (S1[k] / R)
        pos = end

    info = [[-hess[j][k] for k in range(p)] for j in range(p)]
    try:
        cov = _invert(info)
    except ZeroDivisionError:
        cov = [[float("nan")] * p for _ in range(p)]

    se = [math.sqrt(max(cov[j][j], 0.0)) if cov[j][j] == cov[j][j] else float("nan") for j in range(p)]
    z = [
        (beta[j] / se[j]) if se[j] and se[j] == se[j] and se[j] > 0 else float("nan")
        for j in range(p)
    ]
    pvals = [_wald_p(zi) for zi in z]
    hrs = [math.exp(_clip(b)) for b in beta]
    ci = [
        (math.exp(_clip(beta[j] - 1.96 * se[j])), math.exp(_clip(beta[j] + 1.96 * se[j])))
        if se[j] == se[j]
        else (float("nan"), float("nan"))
        for j in range(p)
    ]
    return {
        "coef": beta,
        "se": se,
        "z": z,
        "p": pvals,
        "hr": hrs,
        "hr_ci": ci,
        "n": n,
        "n_events": sum(1 for e in event if e == 1),
    }


def _solve(A: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-14:
            raise ZeroDivisionError("singular")
        M[col], M[piv] = M[piv], M[col]
        div = M[col][col]
        for j in range(col, n + 1):
            M[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            factor = M[r][col]
            for j in range(col, n + 1):
                M[r][j] -= factor * M[col][j]
    return [M[i][n] for i in range(n)]


def _invert(A: list[list[float]]) -> list[list[float]]:
    n = len(A)
    M = [A[i][:] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-14:
            raise ZeroDivisionError("singular")
        M[col], M[piv] = M[piv], M[col]
        div = M[col][col]
        for j in range(2 * n):
            M[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            factor = M[r][col]
            for j in range(2 * n):
                M[r][j] -= factor * M[col][j]
    return [row[n:] for row in M]


def _wald_p(z: float) -> float:
    if z != z:  # NaN
        return float("nan")
    # erfc-based two-sided normal p-value
    return math.erfc(abs(z) / math.sqrt(2.0))


def standardize_columns(X: list[list[float]]) -> list[list[float]]:
    """Z-score continuous columns in place-style copy (skip binary 0/1 cols)."""
    if not X:
        return X
    n, p = len(X), len(X[0])
    out = [row[:] for row in X]
    for j in range(p):
        col = [out[i][j] for i in range(n)]
        uniq = set(round(v, 6) for v in col)
        if uniq <= {0.0, 1.0}:
            continue
        mu = sum(col) / n
        var = sum((v - mu) ** 2 for v in col) / max(n - 1, 1)
        sd = math.sqrt(var) if var > 1e-12 else 1.0
        for i in range(n):
            out[i][j] = (out[i][j] - mu) / sd
    return out
