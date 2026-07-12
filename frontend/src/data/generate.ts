import type {
  AiSuggestion,
  Cell,
  CellType,
  ExhaustionState,
  MarkerGene,
  Niche,
  PerturbationResult,
  SampleData,
  SampleMeta,
} from '../types';
import { MARKER_GENES } from '../types';

/** Mulberry32 seeded PRNG */
function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randn(rng: () => number): number {
  // Box-Muller
  const u = 1 - rng();
  const v = 1 - rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function round2(v: number) {
  return Math.round(v * 100) / 100;
}

type ExpressionBase = Record<MarkerGene, number>;

const PHENOTYPE_BASE: Record<CellType, ExpressionBase> = {
  CD4_Tex_term: {
    PDCD1: 4.2,
    CTLA4: 2.4,
    FOXP3: 0.5,
    CXCL9: 2.8,
    STAT1: 3.5,
    CXCR4: 0.5,
    IL2RA: 0.4,
    TNFRSF9: 1.5,
  },
  CD4_Tex_prog: {
    PDCD1: 2.4,
    CTLA4: 1.2,
    FOXP3: 0.3,
    CXCL9: 1.5,
    STAT1: 1.8,
    CXCR4: 1.8,
    IL2RA: 1.0,
    TNFRSF9: 1.2,
  },
  CD4_Teff: {
    PDCD1: 0.7,
    CTLA4: 0.5,
    FOXP3: 0.2,
    CXCL9: 0.6,
    STAT1: 1.0,
    CXCR4: 2.0,
    IL2RA: 1.5,
    TNFRSF9: 3.0,
  },
  CD4_Treg: {
    PDCD1: 1.3,
    CTLA4: 3.8,
    FOXP3: 4.3,
    CXCL9: 0.5,
    STAT1: 1.0,
    CXCR4: 1.8,
    IL2RA: 3.5,
    TNFRSF9: 1.0,
  },
  myeloid: {
    PDCD1: 0.3,
    CTLA4: 0.3,
    FOXP3: 0.1,
    CXCL9: 2.2,
    STAT1: 1.5,
    CXCR4: 1.2,
    IL2RA: 0.3,
    TNFRSF9: 0.4,
  },
  tumor: {
    PDCD1: 0.2,
    CTLA4: 0.2,
    FOXP3: 0.1,
    CXCL9: 0.4,
    STAT1: 0.8,
    CXCR4: 0.5,
    IL2RA: 0.1,
    TNFRSF9: 0.1,
  },
  stromal: {
    PDCD1: 0.15,
    CTLA4: 0.1,
    FOXP3: 0.1,
    CXCL9: 0.3,
    STAT1: 0.6,
    CXCR4: 0.4,
    IL2RA: 0.1,
    TNFRSF9: 0.1,
  },
};

const NICHE_EXPR_BIAS: Record<Niche, Partial<ExpressionBase>> = {
  tumor_core: { PDCD1: 0.35, STAT1: 0.3, CXCL9: 0.3, CXCR4: -0.2 },
  tumor_margin: { CXCR4: 0.2, TNFRSF9: 0.15 },
  lymphoid_proximal: { IL2RA: 0.3, CXCR4: 0.15, PDCD1: -0.2 },
};

function exhaustionForType(ct: CellType): ExhaustionState {
  switch (ct) {
    case 'CD4_Tex_term':
      return 'terminally_exhausted';
    case 'CD4_Tex_prog':
      return 'progenitor_exhausted';
    case 'CD4_Teff':
      return 'effector';
    default:
      return 'other';
  }
}

function pickCellType(niche: Niche, rng: () => number): CellType {
  const r = rng();
  if (niche === 'tumor_core') {
    if (r < 0.32) return 'tumor';
    if (r < 0.48) return 'CD4_Tex_term';
    if (r < 0.58) return 'CD4_Tex_prog';
    if (r < 0.68) return 'myeloid';
    if (r < 0.78) return 'stromal';
    if (r < 0.88) return 'CD4_Treg';
    return 'CD4_Teff';
  }
  if (niche === 'tumor_margin') {
    if (r < 0.18) return 'tumor';
    if (r < 0.36) return 'CD4_Tex_prog';
    if (r < 0.52) return 'CD4_Teff';
    if (r < 0.64) return 'CD4_Tex_term';
    if (r < 0.76) return 'myeloid';
    if (r < 0.88) return 'stromal';
    return 'CD4_Treg';
  }
  // lymphoid_proximal
  if (r < 0.28) return 'CD4_Teff';
  if (r < 0.48) return 'CD4_Tex_prog';
  if (r < 0.60) return 'CD4_Treg';
  if (r < 0.72) return 'myeloid';
  if (r < 0.82) return 'stromal';
  if (r < 0.90) return 'CD4_Tex_term';
  return 'tumor';
}

function makeExpression(
  cellType: CellType,
  niche: Niche,
  rng: () => number,
): Record<MarkerGene, number> {
  const base = PHENOTYPE_BASE[cellType];
  const bias = NICHE_EXPR_BIAS[niche];
  const expr = {} as Record<MarkerGene, number>;
  for (const g of MARKER_GENES) {
    const noise = randn(rng) * 0.35;
    const b = bias[g] ?? 0;
    expr[g] = round2(clamp(base[g] + b + noise, 0.05, 5.0));
  }
  return expr;
}

function sampleInEllipse(
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  rng: () => number,
): { x: number; y: number } {
  // Rejection-free elliptical Gaussian-ish
  const angle = rng() * 2 * Math.PI;
  const radius = Math.sqrt(rng());
  return {
    x: round2(cx + Math.cos(angle) * rx * radius),
    y: round2(cy + Math.sin(angle) * ry * radius),
  };
}

type NicheCenters = Record<Niche, { x: number; y: number; rx: number; ry: number }>;

function assignNiche(
  x: number,
  y: number,
  centers: NicheCenters,
): Niche {
  let best: Niche = 'tumor_core';
  let bestD = Infinity;
  for (const niche of Object.keys(centers) as Niche[]) {
    const c = centers[niche];
    const dx = (x - c.x) / c.rx;
    const dy = (y - c.y) / c.ry;
    const d = dx * dx + dy * dy;
    if (d < bestD) {
      bestD = d;
      best = niche;
    }
  }
  return best;
}

const SAMPLE_CONFIGS: Array<{
  meta: SampleMeta;
  seed: number;
  nCells: number;
  centers: NicheCenters;
}> = [
  {
    meta: {
      id: 'crc-01',
      name: 'CRC-01 · colorectal adenocarcinoma',
      description: 'Primary tumor section, CD4-rich infiltrate near invasive margin',
    },
    seed: 42,
    nCells: 2100,
    centers: {
      tumor_core: { x: 48, y: 52, rx: 28, ry: 24 },
      tumor_margin: { x: 55, y: 48, rx: 42, ry: 38 },
      lymphoid_proximal: { x: 78, y: 30, rx: 18, ry: 16 },
    },
  },
  {
    meta: {
      id: 'nsclc-03',
      name: 'NSCLC-03 · lung adenocarcinoma',
      description: 'Dense core exhaustion signature; sparse lymphoid aggregate at edge',
    },
    seed: 107,
    nCells: 1950,
    centers: {
      tumor_core: { x: 42, y: 45, rx: 26, ry: 22 },
      tumor_margin: { x: 50, y: 50, rx: 40, ry: 36 },
      lymphoid_proximal: { x: 22, y: 72, rx: 16, ry: 14 },
    },
  },
  {
    meta: {
      id: 'mel-07',
      name: 'MEL-07 · cutaneous melanoma',
      description: 'Mixed Tex progenitor / effector along margin; Treg-enriched stroma',
    },
    seed: 314,
    nCells: 2200,
    centers: {
      tumor_core: { x: 55, y: 58, rx: 24, ry: 26 },
      tumor_margin: { x: 50, y: 50, rx: 38, ry: 40 },
      lymphoid_proximal: { x: 28, y: 25, rx: 20, ry: 15 },
    },
  },
];

const SUGGESTION_TEMPLATES: Array<Omit<AiSuggestion, 'id'>> = [
  {
    gene: 'PDCD1',
    rationale:
      'Terminal Tex cells in the core show high PD-1; knockout may restore effector programs.',
    citation: {
      title: 'PD-1 blockade restores effector function in exhausted CD4 T cells',
      source: 'Nature Immunology (simulated)',
      url: 'https://pubmed.ncbi.nlm.nih.gov/',
    },
    linked_niche: 'tumor_core',
  },
  {
    gene: 'STAT1',
    rationale:
      'STAT1-driven interferon signaling reinforces the terminal exhaustion program; knockout may relieve chronic IFN pressure.',
    citation: {
      title: 'STAT1 sustains a terminal exhaustion transcriptional state',
      source: 'Nature (simulated)',
      url: 'https://pubmed.ncbi.nlm.nih.gov/',
    },
    linked_niche: 'tumor_core',
  },
  {
    gene: 'CXCL9',
    rationale:
      'CXCL9 marks the IFN-γ-driven core niche and co-elevates with PDCD1 in terminal Tex; dual-target logic suggests CXCL9 KO synergy.',
    citation: {
      title: 'CXCL9 shapes the exhausted T cell niche in the tumor core',
      source: 'Cancer Cell (simulated)',
      url: 'https://pubmed.ncbi.nlm.nih.gov/',
    },
    linked_niche: 'tumor_core',
  },
  {
    gene: 'CTLA4',
    rationale:
      'Margin Treg enrichment with high CTLA4; KO may relieve local suppression of progenitor Tex.',
    citation: {
      title: 'CTLA-4 controls Treg-mediated restraint of CD4 antitumor responses',
      source: 'Immunity (simulated)',
      url: 'https://pubmed.ncbi.nlm.nih.gov/',
    },
    linked_niche: 'tumor_margin',
  },
];

/** Deterministic perturbation shifts by KO gene × phenotype class */
export function applyPerturbation(
  before: Record<MarkerGene, number>,
  gene: string,
  cellType: CellType,
): Record<MarkerGene, number> {
  const after = { ...before };
  const g = gene.toUpperCase();
  const isTex =
    cellType === 'CD4_Tex_term' ||
    cellType === 'CD4_Tex_prog' ||
    cellType === 'CD4_Teff';
  const isTreg = cellType === 'CD4_Treg';

  const bump = (key: MarkerGene, delta: number) => {
    after[key] = round2(clamp(after[key] + delta, 0.05, 5.0));
  };

  if (g === 'PDCD1') {
    bump('PDCD1', -2.2);
    if (isTex) {
      bump('STAT1', -0.8);
      bump('CXCL9', -0.6);
      bump('CXCR4', 1.2);
      bump('TNFRSF9', 1.0);
    }
  } else if (g === 'STAT1') {
    bump('STAT1', -2.0);
    if (isTex) {
      bump('PDCD1', -0.6);
      bump('CXCL9', -0.9);
      bump('CXCR4', 0.8);
    }
  } else if (g === 'CXCL9') {
    bump('CXCL9', -2.0);
    if (isTex) {
      bump('PDCD1', -0.5);
      bump('STAT1', -0.6);
    }
  } else if (g === 'CTLA4') {
    bump('CTLA4', -2.0);
    if (isTreg) {
      bump('FOXP3', -0.8);
      bump('IL2RA', -0.6);
    }
    if (isTex) {
      bump('TNFRSF9', 0.8);
      bump('CXCR4', 0.5);
    }
  } else if (g === 'FOXP3') {
    bump('FOXP3', -2.0);
    if (isTreg) {
      bump('CTLA4', -0.8);
      bump('IL2RA', -0.9);
    }
  } else if (MARKER_GENES.includes(g as MarkerGene)) {
    bump(g as MarkerGene, -1.8);
  } else {
    // Unknown gene: modest generic shift toward effector-like
    bump('PDCD1', -0.4);
    bump('CXCR4', 0.3);
    bump('TNFRSF9', 0.3);
  }

  return after;
}

const cache = new Map<string, SampleData>();

export function listSampleMeta(): SampleMeta[] {
  return SAMPLE_CONFIGS.map((c) => c.meta);
}

export function generateSample(sampleId: string): SampleData {
  const cached = cache.get(sampleId);
  if (cached) return cached;

  const cfg = SAMPLE_CONFIGS.find((c) => c.meta.id === sampleId);
  if (!cfg) throw new Error(`Unknown sample: ${sampleId}`);

  const rng = mulberry32(cfg.seed);
  const cells: Cell[] = [];
  const nicheOrder: Niche[] = ['tumor_core', 'tumor_margin', 'lymphoid_proximal'];
  const nicheWeights = [0.4, 0.4, 0.2];

  for (let i = 0; i < cfg.nCells; i++) {
    const r = rng();
    let niche: Niche = 'tumor_core';
    let acc = 0;
    for (let j = 0; j < nicheOrder.length; j++) {
      acc += nicheWeights[j];
      if (r < acc) {
        niche = nicheOrder[j];
        break;
      }
    }
    const c = cfg.centers[niche];
    const { x, y } = sampleInEllipse(c.x, c.y, c.rx, c.ry, rng);
    // Soft reassignment if closer to another niche centroid (ring effect for margin)
    const assigned = assignNiche(x, y, cfg.centers);
    const cellType = pickCellType(assigned, rng);
    cells.push({
      id: `${sampleId}-c${i.toString().padStart(4, '0')}`,
      x: clamp(x, 0, 100),
      y: clamp(y, 0, 100),
      cell_type: cellType,
      niche: assigned,
      exhaustion_state: exhaustionForType(cellType),
      expression: makeExpression(cellType, assigned, rng),
    });
  }

  const suggestions: AiSuggestion[] = SUGGESTION_TEMPLATES.slice(0, 4).map(
    (t, i) => ({
      ...t,
      id: `${sampleId}-sug-${i}`,
    }),
  );

  const data: SampleData = {
    cells,
    suggestions,
  };
  cache.set(sampleId, data);
  return data;
}

export function computePerturbation(
  sampleId: string,
  cellId: string,
  gene: string,
): PerturbationResult {
  const data = generateSample(sampleId);
  const cell = data.cells.find((c) => c.id === cellId);
  if (!cell) throw new Error(`Cell not found: ${cellId}`);
  const before = { ...cell.expression };
  const after = applyPerturbation(before, gene, cell.cell_type);
  return { cell_id: cellId, gene: gene.toUpperCase(), before, after };
}

export function nicheMeanExpression(
  cells: Cell[],
  niche: Niche,
): Record<MarkerGene, number> {
  const subset = cells.filter((c) => c.niche === niche);
  const means = {} as Record<MarkerGene, number>;
  for (const g of MARKER_GENES) {
    if (subset.length === 0) {
      means[g] = 0;
      continue;
    }
    const sum = subset.reduce((acc, c) => acc + c.expression[g], 0);
    means[g] = round2(sum / subset.length);
  }
  return means;
}
