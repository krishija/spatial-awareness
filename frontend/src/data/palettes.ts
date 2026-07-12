import type { Cell, CellType, ColorMode, MarkerGene, Niche } from '../types';

const FALLBACK_COLOR = '#999999';

/** Colorblind-safe qualitative palette (Okabe–Ito inspired) — fixture samples. */
const FIXTURE_CELL_TYPE_COLORS: Record<string, string> = {
  CD4_Tex_term: '#D55E00',
  CD4_Tex_prog: '#E69F00',
  CD4_Teff: '#009E73',
  CD4_Treg: '#CC79A7',
  myeloid: '#56B4E9',
  tumor: '#0072B2',
  stromal: '#999999',
};

const FIXTURE_CELL_TYPE_LABELS: Record<string, string> = {
  CD4_Tex_term: 'CD4 Tex term.',
  CD4_Tex_prog: 'CD4 Tex prog.',
  CD4_Teff: 'CD4 Teff',
  CD4_Treg: 'CD4 Treg',
  myeloid: 'Myeloid',
  tumor: 'Tumor',
  stromal: 'Stromal',
};

/**
 * Real-sample cell types (all 25 raw 10x labels) — colors ported exactly
 * from explorer.html so the two views read as the same data. Label text is
 * the raw label itself (no shortening), per the same parity goal.
 */
const REAL_CELL_TYPE_COLORS: Record<string, string> = {
  'Regulatory T Cells': '#1f77b4',
  'Hypoxic Tumor Cells': '#ff7f0e',
  'Dendritic Cells': '#2ca02c',
  'Exhausted T Cells': '#d62728',
  'Cytotoxic T Cells': '#9467bd',
  'Naive & Memory T Cells': '#8c564b',
  'Metabolic Invasive Basal Cells': '#e377c2',
  Macrophages: '#7f7f7f',
  Neutrophils: '#bcbd22',
  'Stroma & Smooth Muscle': '#17becf',
  'B Cells': '#aec7e8',
  'Plasma Cells': '#ffbb78',
  'OR4F17+ Cells': '#98df8a',
  'Dyskeratotic Tumor Cells': '#ff9896',
  'Mast Cells': '#c5b0d5',
  'Migratory Invasive Basal Cells': '#c49c94',
  'Parabasal Tumor Cells': '#f7b6d2',
  'Proliferative Parabasal Cells': '#c7c7c7',
  'Endothelial Cells': '#dbdb8d',
  'Differentiating Tumor Cells': '#9edae5',
  'Interstitial Fibroblasts': '#393b79',
  'Cancer Associated Fibroblasts': '#637939',
  'Smooth Muscle': '#8c6d31',
  'Endocervical Columnar Cells': '#843c39',
  'Endocervical Ciliated Cells': '#7b4173',
};

/**
 * AIFI atlas CD4 subtypes (the UMAP window's "Cell subtypes" mode) — colors
 * ported exactly from atlas_explorer.html, same parity goal as the spatial
 * cell types above.
 */
const ATLAS_SUBTYPE_COLORS: Record<string, string> = {
  'Core naive CD4 T cell': '#1f77b4',
  'CM CD4 T cell': '#ff7f0e',
  'GZMB- CD27+ EM CD4 T cell': '#2ca02c',
  'GZMB- CD27- EM CD4 T cell': '#d62728',
  'SOX4+ naive CD4 T cell': '#9467bd',
  'Memory CD4 Treg': '#8c564b',
  'KLRF1- GZMB+ CD27- memory CD4 T cell': '#e377c2',
  'Naive CD4 Treg': '#7f7f7f',
  'ISG+ naive CD4 T cell': '#bcbd22',
  'ISG+ memory CD4 T cell': '#17becf',
  'KLRB1+ memory CD4 Treg': '#aec7e8',
  'DN T cell': '#ffbb78',
  'Proliferating T cell': '#98df8a',
  'KLRB1+ memory CD8 Treg': '#ff9896',
  'Memory CD8 Treg': '#c5b0d5',
  'GZMK+ memory CD4 Treg': '#c49c94',
};

export const CELL_TYPE_COLORS: Record<string, string> = {
  ...FIXTURE_CELL_TYPE_COLORS,
  ...REAL_CELL_TYPE_COLORS,
  ...ATLAS_SUBTYPE_COLORS,
};

export const CELL_TYPE_LABELS: Record<string, string> = {
  ...FIXTURE_CELL_TYPE_LABELS,
  ...Object.fromEntries(Object.keys(REAL_CELL_TYPE_COLORS).map((k) => [k, k])),
  ...Object.fromEntries(Object.keys(ATLAS_SUBTYPE_COLORS).map((k) => [k, k])),
};

export function cellTypeColor(ct: CellType): string {
  return CELL_TYPE_COLORS[ct] ?? FALLBACK_COLOR;
}

export function cellTypeLabel(ct: CellType): string {
  return CELL_TYPE_LABELS[ct] ?? ct;
}

/** Cell types treated as "tumor" backdrop in Treg-niches mode — matches
 * explorer.html's ALL_TUMOR / MARGIN_NBRS+CORE_NBRS (plus the fixture
 * samples' own 'tumor' bucket, so the mode works identically on both). */
export const TUMOR_BACKDROP_TYPES = [
  'tumor',
  'Migratory Invasive Basal Cells',
  'Metabolic Invasive Basal Cells',
  'Hypoxic Tumor Cells',
  'Differentiating Tumor Cells',
  'Dyskeratotic Tumor Cells',
  'Parabasal Tumor Cells',
  'Proliferative Parabasal Cells',
];

/** Cell types treated as "the Tregs" in Treg-niches mode (fixture + real). */
export const TREG_TYPES = ['CD4_Treg', 'Regulatory T Cells'];

/** Magma-ish sequential scale, approximating atlas_explorer.html's score colorbar. */
const MAGMA_STOPS = ['#000004', '#721f81', '#cd4071', '#fd9668', '#fcfdbf'];

export function atlasScoreColor(score: number, max = 1): string {
  const t = Math.max(0, Math.min(1, score / max));
  const seg = t * (MAGMA_STOPS.length - 1);
  const i = Math.min(Math.floor(seg), MAGMA_STOPS.length - 2);
  return lerpColor(MAGMA_STOPS[i], MAGMA_STOPS[i + 1], seg - i);
}

export const ATLAS_BG_TYPE = '__atlas_bg__';
export const ATLAS_SELECTED_TYPE = '__atlas_selected__';

/** Shared per-cell color rule for all map modes — used by both the main
 * TissueMap and the MiniMap so they always read as the same data. */
export function cellColor(cell: Cell, colorMode: ColorMode, selectedGene: MarkerGene): string {
  if (colorMode === 'expression') return expressionColor(cell.expression[selectedGene], 5);
  if (colorMode === 'treg_niches') {
    if (cell.niche && TREG_TYPES.includes(cell.cell_type)) return NICHE_DOT_COLORS[cell.niche];
    return '#d5d5d5'; // tumor backdrop
  }
  if (colorMode === 'atlas_score') return atlasScoreColor(cell.score ?? 0);
  if (colorMode === 'atlas_selected') {
    return cell.cell_type === ATLAS_SELECTED_TYPE ? '#c0392b' : '#dcdcdc';
  }
  return cellTypeColor(cell.cell_type);
}

export const NICHE_LABELS: Record<Niche, string> = {
  tumor_core: 'Tumor core',
  tumor_margin: 'Tumor margin',
  lymphoid_proximal: 'Lymphoid-proximal',
};

/** Solid Treg-niche dot colors — exact hex from explorer.html's NICHE_COLOR. */
export const NICHE_DOT_COLORS: Record<Niche, string> = {
  lymphoid_proximal: '#2980b9',
  tumor_margin: '#e74c3c',
  tumor_core: '#8e44ad',
};

export const EXHAUSTION_LABELS: Record<string, string> = {
  terminally_exhausted: 'Terminally exhausted',
  progenitor_exhausted: 'Progenitor exhausted',
  effector: 'Effector',
  other: 'Other',
};

/** Sequential expression scale endpoints (light → dark blue) */
export const EXPRESSION_SCALE = {
  low: '#F0F4F8',
  mid: '#7BA3C9',
  high: '#08306B',
};

/** Diverging delta: down / zero / up */
export const DELTA_COLORS = {
  down: '#2166AC',
  zero: '#F7F7F7',
  up: '#B2182B',
};

export function lerpColor(a: string, b: string, t: number): string {
  const parse = (hex: string) => {
    const h = hex.replace('#', '');
    return [
      parseInt(h.slice(0, 2), 16),
      parseInt(h.slice(2, 4), 16),
      parseInt(h.slice(4, 6), 16),
    ] as const;
  };
  const [r1, g1, b1] = parse(a);
  const [r2, g2, b2] = parse(b);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const bl = Math.round(b1 + (b2 - b1) * t);
  return `rgb(${r},${g},${bl})`;
}

/** Map expression value in [0, max] to sequential color */
export function expressionColor(value: number, max = 5): string {
  const t = Math.max(0, Math.min(1, value / max));
  if (t < 0.5) return lerpColor(EXPRESSION_SCALE.low, EXPRESSION_SCALE.mid, t * 2);
  return lerpColor(EXPRESSION_SCALE.mid, EXPRESSION_SCALE.high, (t - 0.5) * 2);
}

export function formatExpr(v: number): string {
  return v.toFixed(2);
}

export function formatCoord(v: number): string {
  return v.toFixed(1);
}
