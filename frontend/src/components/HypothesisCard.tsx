import type { Cell, PerturbationResult, SuggestionCitationRef } from '../types';
import {
  NICHE_LABELS,
  cellTypeLabel,
  formatExpr,
} from '../data/palettes';
import { MARKER_GENES } from '../types';

interface Props {
  cell: Cell;
  result: PerturbationResult;
  suggestion?: SuggestionCitationRef | null;
}

function summarizeEffect(result: PerturbationResult): string {
  const deltas = MARKER_GENES.map((g) => ({
    gene: g,
    d: result.after[g] - result.before[g],
  })).sort((a, b) => Math.abs(b.d) - Math.abs(a.d));

  const top = deltas.slice(0, 3);
  const parts = top.map((t) => {
    const sign = t.d >= 0 ? '↑' : '↓';
    return `${sign}${t.gene} (${t.d >= 0 ? '+' : ''}${formatExpr(t.d)})`;
  });
  return parts.join(', ');
}

export function HypothesisCard({ cell, result, suggestion }: Props) {
  const effect = summarizeEffect(result);
  const cite = suggestion?.citation;
  const nicheText = cell.niche ? NICHE_LABELS[cell.niche] : null;

  return (
    <div className="hypothesis-slot">
      <div className="hypothesis-card">
        <div className="hypothesis-card__eyebrow">Hypothesis summary</div>
        <p className="hypothesis-card__claim">
          In a <strong>{cellTypeLabel(cell.cell_type)}</strong> cell
          {nicheText && (
            <>
              {' '}
              within the <strong>{nicheText.toLowerCase()}</strong>
            </>
          )}
          , knockout of <span className="gene">{result.gene}</span> is
          predicted to shift the marker profile toward a less exhausted /
          more effector-like state ({effect}).
        </p>
        <div className="hypothesis-card__meta">
          <span>
            Cell <span className="num">{cell.id}</span>
          </span>
          <span>
            Perturbation <span className="gene">{result.gene}</span> KO
          </span>
          {nicheText && <span>{nicheText}</span>}
        </div>
        {cite && (
          <div className="hypothesis-card__cite">
            Supporting literature: {cite.title} — {cite.source}.{' '}
            <a href={cite.url} target="_blank" rel="noreferrer">
              Open
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
