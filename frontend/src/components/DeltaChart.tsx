import type { PerturbationResult } from '../types';
import { MARKER_GENES } from '../types';
import { formatExpr } from '../data/palettes';

interface Props {
  result: PerturbationResult | null;
  running?: boolean;
}

export function DeltaChart({ result, running }: Props) {
  if (running) {
    return (
      <div className="delta-chart__empty">Running virtual-cell perturbation…</div>
    );
  }

  if (!result) {
    return (
      <div className="delta-chart__empty">
        Run a perturbation to see predicted marker shifts (before → after).
      </div>
    );
  }

  const deltas = MARKER_GENES.map((g) => ({
    gene: g,
    delta: result.after[g] - result.before[g],
    before: result.before[g],
    after: result.after[g],
  }));

  const maxAbs = Math.max(1.5, ...deltas.map((d) => Math.abs(d.delta)));

  return (
    <div className="delta-chart">
      {deltas.map(({ gene, delta, before, after }) => {
        const half = 50;
        const widthPct = (Math.abs(delta) / maxAbs) * half;
        const isUp = delta >= 0;
        return (
          <div key={gene} className="delta-chart__row">
            <span className="gene">{gene}</span>
            <div
              className="delta-chart__track"
              title={`${formatExpr(before)} → ${formatExpr(after)}`}
            >
              <div className="delta-chart__zero" />
              <div
                className={`delta-chart__bar ${isUp ? 'delta-chart__bar--up' : 'delta-chart__bar--down'}`}
                style={
                  isUp
                    ? { left: '50%', width: `${widthPct}%` }
                    : { left: `${50 - widthPct}%`, width: `${widthPct}%` }
                }
              />
            </div>
            <span className="num" style={{ color: isUp ? 'var(--up)' : 'var(--down)' }}>
              {delta >= 0 ? '+' : ''}
              {formatExpr(delta)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
