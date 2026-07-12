import {
  EXPRESSION_SCALE,
  NICHE_DOT_COLORS,
  NICHE_LABELS,
  cellTypeColor,
  cellTypeLabel,
} from '../data/palettes';
import type { Cell, ColorMode, MarkerGene } from '../types';

const MAGMA_GRADIENT =
  'linear-gradient(90deg, #000004, #721f81, #cd4071, #fd9668, #fcfdbf)';

interface Props {
  colorMode: ColorMode;
  selectedGene: MarkerGene;
  cells: Cell[];
}

export function Legend({ colorMode, selectedGene, cells }: Props) {
  if (colorMode === 'expression') {
    const gradient = `linear-gradient(90deg, ${EXPRESSION_SCALE.low}, ${EXPRESSION_SCALE.mid}, ${EXPRESSION_SCALE.high})`;
    return (
      <div className="legend">
        <div className="legend__title">
          Expression · <span className="gene">{selectedGene}</span>
        </div>
        <div className="legend__scale" style={{ background: gradient }} />
        <div className="legend__ticks">
          <span>0.00</span>
          <span>2.50</span>
          <span>5.00</span>
        </div>
      </div>
    );
  }

  if (colorMode === 'treg_niches') {
    return (
      <div className="legend">
        <div className="legend__title">Treg niches</div>
        <div className="legend__row">
          <span className="legend__swatch" style={{ background: '#d5d5d5' }} />
          <span>Tumour (background)</span>
        </div>
        {(['lymphoid_proximal', 'tumor_margin', 'tumor_core'] as const).map((n) => (
          <div key={n} className="legend__row">
            <span
              className="legend__swatch"
              style={{ background: NICHE_DOT_COLORS[n] }}
            />
            <span>Treg — {NICHE_LABELS[n]}</span>
          </div>
        ))}
      </div>
    );
  }

  if (colorMode === 'atlas_score') {
    return (
      <div className="legend">
        <div className="legend__title">Infiltration score</div>
        <div className="legend__scale" style={{ background: MAGMA_GRADIENT }} />
        <div className="legend__ticks">
          <span>low</span>
          <span>high</span>
        </div>
      </div>
    );
  }

  if (colorMode === 'atlas_selected') {
    const nSelected = cells.filter((c) => c.cell_type === '__atlas_selected__').length;
    return (
      <div className="legend">
        <div className="legend__title">Selected barcodes</div>
        <div className="legend__row">
          <span className="legend__swatch" style={{ background: '#dcdcdc' }} />
          <span>All atlas cells</span>
        </div>
        <div className="legend__row">
          <span className="legend__swatch" style={{ background: '#c0392b' }} />
          <span>Selected (top 5%, {nSelected})</span>
        </div>
      </div>
    );
  }

  // cell_type — only show types actually present in this sample's cells.
  const present = Array.from(new Set(cells.map((c) => c.cell_type))).sort(
    (a, b) => cellTypeLabel(a).localeCompare(cellTypeLabel(b)),
  );

  return (
    <div className="legend legend--scroll">
      <div className="legend__title">Cell type</div>
      {present.map((ct) => (
        <div key={ct} className="legend__row">
          <span
            className="legend__swatch"
            style={{ background: cellTypeColor(ct) }}
          />
          <span>{cellTypeLabel(ct)}</span>
        </div>
      ))}
    </div>
  );
}
