import type { Cell, MarkerGene } from '../types';
import { MARKER_GENES } from '../types';

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

const coordKey = (p: RawAtlasPoint) => `${p.x}|${p.y}`;

export function adaptAtlasData(raw: AtlasCellsResponse): AtlasData {
  // Shared coordinate frame (derived from the full atlas) so every mode's
  // point cloud lands in the same place on screen when toggled between.
  const norm = normalizer(raw.subtypes);

  // Stable id keyed by (x,y): the same underlying atlas cell has identical
  // UMAP coordinates in every trace, even though there's no shared barcode
  // field across them (verified: 100% coordinate match for score_cells and
  // selected_cells against subtypes). This is what keeps a clicked cell's
  // selection circle on the same cell across all three modes, matching the
  // spatial window's behavior.
  const idByCoord = new Map<string, string>();
  raw.subtypes.forEach((p, i) => idByCoord.set(coordKey(p), `atlas-${i}`));

  const toCell = (p: RawAtlasPoint, id: string, extra: Partial<Cell> = {}): Cell => {
    const { x, y } = norm(p);
    return {
      id,
      x,
      y,
      cell_type: p.subtype,
      niche: null,
      exhaustion_state: 'other',
      expression: ZERO_EXPRESSION,
      ...extra,
    };
  };

  const subtypeCells: Cell[] = raw.subtypes.map((p, i) => toCell(p, `atlas-${i}`));

  const scoreCells: Cell[] = raw.score_cells.map((p, i) =>
    toCell(p, idByCoord.get(coordKey(p)) ?? `atlas-score-${i}`, { score: p.score }),
  );

  // Selected overlay first (so we know which ids to exclude from the
  // background layer) — every atlas cell appears exactly once in
  // selectedCells, either as background or as the red overlay, never both.
  const selectedOverlay: Cell[] = raw.selected_cells.map((p, i) =>
    toCell(p, idByCoord.get(coordKey(p)) ?? `atlas-selected-${i}`, {
      score: p.score,
      selected: true,
    }),
  );
  const selectedIds = new Set(selectedOverlay.map((c) => c.id));
  const background: Cell[] = subtypeCells
    .filter((c) => !selectedIds.has(c.id))
    .map((c) => ({ ...c, selected: false }));

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
