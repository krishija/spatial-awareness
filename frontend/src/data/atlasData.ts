import type { Cell, MarkerGene } from '../types';
import { MARKER_GENES } from '../types';
import { ATLAS_BG_TYPE, ATLAS_SELECTED_TYPE } from './palettes';

interface RawAtlasPoint {
  x: number;
  y: number;
  subtype: string;
  score?: number;
}

export interface AtlasCellsResponse {
  subtype_colors: Record<string, string>;
  subtypes: RawAtlasPoint[];
  score_cells: RawAtlasPoint[];
  selected_cells: RawAtlasPoint[];
  n_atlas_total: number;
  n_scored: number;
  n_selected: number;
}

export interface AtlasData {
  /** "Cell subtypes" mode — colored via CellType coloring (subtype = cell_type). */
  subtypeCells: Cell[];
  /** "Infiltration score" mode. */
  scoreCells: Cell[];
  /** "Selected barcodes" mode — all-atlas gray background + the top-5% highlighted red. */
  selectedCells: Cell[];
  subtypeColors: Record<string, string>;
  nAtlasTotal: number;
  nScored: number;
  nSelected: number;
}

const ZERO_EXPRESSION: Record<MarkerGene, number> = Object.fromEntries(
  MARKER_GENES.map((g) => [g, 0]),
) as Record<MarkerGene, number>;

function normalizer(points: RawAtlasPoint[]): (p: RawAtlasPoint) => { x: number; y: number } {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xmin = Math.min(...xs);
  const ymin = Math.min(...ys);
  const span = Math.max(Math.max(...xs) - xmin, Math.max(...ys) - ymin) || 1;
  return (p) => ({
    x: ((p.x - xmin) / span) * 100,
    y: ((p.y - ymin) / span) * 100,
  });
}

export function adaptAtlasData(raw: AtlasCellsResponse): AtlasData {
  // Shared coordinate frame (derived from the full atlas) so every mode's
  // point cloud lands in the same place on screen when toggled between.
  const norm = normalizer(raw.subtypes);

  const subtypeCells: Cell[] = raw.subtypes.map((p, i) => {
    const { x, y } = norm(p);
    return {
      id: `atlas-sub-${i}`,
      x,
      y,
      cell_type: p.subtype,
      niche: null,
      exhaustion_state: 'other',
      expression: ZERO_EXPRESSION,
    };
  });

  const scoreCells: Cell[] = raw.score_cells.map((p, i) => {
    const { x, y } = norm(p);
    return {
      id: `atlas-score-${i}`,
      x,
      y,
      cell_type: p.subtype,
      niche: null,
      exhaustion_state: 'other',
      expression: ZERO_EXPRESSION,
      score: p.score,
    };
  });

  const background: Cell[] = raw.subtypes.map((p, i) => {
    const { x, y } = norm(p);
    return {
      id: `atlas-bg-${i}`,
      x,
      y,
      cell_type: ATLAS_BG_TYPE,
      niche: null,
      exhaustion_state: 'other',
      expression: ZERO_EXPRESSION,
    };
  });
  const selectedOverlay: Cell[] = raw.selected_cells.map((p, i) => {
    const { x, y } = norm(p);
    return {
      id: `atlas-selected-${i}`,
      x,
      y,
      cell_type: ATLAS_SELECTED_TYPE,
      niche: null,
      exhaustion_state: 'other',
      expression: ZERO_EXPRESSION,
      score: p.score,
    };
  });

  return {
    subtypeCells,
    scoreCells,
    selectedCells: [...background, ...selectedOverlay],
    subtypeColors: raw.subtype_colors,
    nAtlasTotal: raw.n_atlas_total,
    nScored: raw.n_scored,
    nSelected: raw.n_selected,
  };
}
