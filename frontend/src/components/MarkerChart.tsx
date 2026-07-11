import type { MarkerGene } from '../types';
import { MARKER_GENES } from '../types';
import { formatExpr } from '../data/palettes';

interface Props {
  cellExpr: Record<MarkerGene, number>;
  nicheMean: Record<MarkerGene, number>;
  maxValue?: number;
}

export function MarkerChart({ cellExpr, nicheMean, maxValue = 5 }: Props) {
  return (
    <div className="marker-chart">
      <div className="marker-chart__legend">
        <span className="marker-chart__legend-item">
          <span className="marker-chart__legend-swatch" />
          This cell
        </span>
        <span className="marker-chart__legend-item">
          <span className="marker-chart__legend-line" />
          Niche mean
        </span>
      </div>
      {MARKER_GENES.map((g) => {
        const v = cellExpr[g];
        const m = nicheMean[g];
        const pct = (v / maxValue) * 100;
        const nichePct = (m / maxValue) * 100;
        return (
          <div key={g} className="marker-chart__row">
            <span className="gene">{g}</span>
            <div className="marker-chart__bars">
              <div
                className="marker-chart__bar"
                style={{ width: `${pct}%` }}
              />
              <div
                className="marker-chart__niche"
                style={{ left: `calc(${nichePct}% - 1px)` }}
                title={`Niche mean ${formatExpr(m)}`}
              />
            </div>
            <span className="num">{formatExpr(v)}</span>
          </div>
        );
      })}
    </div>
  );
}
