import {
  CELL_TYPE_COLORS,
  CELL_TYPE_LABELS,
  EXPRESSION_SCALE,
  expressionColor,
} from '../data/palettes';
import type { CellType, ColorMode, MarkerGene } from '../types';

interface Props {
  colorMode: ColorMode;
  selectedGene: MarkerGene;
}

const CELL_TYPES = Object.keys(CELL_TYPE_COLORS) as CellType[];

export function Legend({ colorMode, selectedGene }: Props) {
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

  return (
    <div className="legend">
      <div className="legend__title">Cell type</div>
      {CELL_TYPES.map((ct) => (
        <div key={ct} className="legend__row">
          <span
            className="legend__swatch"
            style={{ background: CELL_TYPE_COLORS[ct] }}
          />
          <span>{CELL_TYPE_LABELS[ct]}</span>
        </div>
      ))}
    </div>
  );
}

export function cellColor(
  colorMode: ColorMode,
  cellType: CellType,
  expression: number,
): string {
  if (colorMode === 'expression') return expressionColor(expression, 5);
  return CELL_TYPE_COLORS[cellType];
}
