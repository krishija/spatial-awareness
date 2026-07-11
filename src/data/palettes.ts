import type { CellType, Niche } from '../types';

/** Colorblind-safe qualitative palette (Okabe–Ito inspired) */
export const CELL_TYPE_COLORS: Record<CellType, string> = {
  CD4_Tex_term: '#D55E00',
  CD4_Tex_prog: '#E69F00',
  CD4_Teff: '#009E73',
  CD4_Treg: '#CC79A7',
  myeloid: '#56B4E9',
  tumor: '#0072B2',
  stromal: '#999999',
};

export const CELL_TYPE_LABELS: Record<CellType, string> = {
  CD4_Tex_term: 'CD4 Tex term.',
  CD4_Tex_prog: 'CD4 Tex prog.',
  CD4_Teff: 'CD4 Teff',
  CD4_Treg: 'CD4 Treg',
  myeloid: 'Myeloid',
  tumor: 'Tumor',
  stromal: 'Stromal',
};

export const NICHE_LABELS: Record<Niche, string> = {
  tumor_core: 'Tumor core',
  tumor_margin: 'Tumor margin',
  lymphoid_proximal: 'Lymphoid-proximal',
};

export const NICHE_COLORS: Record<Niche, string> = {
  tumor_core: 'rgba(180, 40, 40, 0.14)',
  tumor_margin: 'rgba(200, 140, 40, 0.12)',
  lymphoid_proximal: 'rgba(40, 100, 180, 0.14)',
};

export const NICHE_STROKE: Record<Niche, string> = {
  tumor_core: 'rgba(140, 30, 30, 0.35)',
  tumor_margin: 'rgba(160, 110, 30, 0.3)',
  lymphoid_proximal: 'rgba(30, 80, 150, 0.35)',
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
