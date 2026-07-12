export type Niche = 'tumor_core' | 'tumor_margin' | 'lymphoid_proximal';

export type ExhaustionState =
  | 'terminally_exhausted'
  | 'progenitor_exhausted'
  | 'effector'
  | 'other';

/**
 * Cell type is an open string, not a closed enum — real samples carry all 25
 * raw 10x labels (Regulatory T Cells, Hypoxic Tumor Cells, ...), matching
 * explorer.html's "Cell types" dropdown exactly, alongside the fixture
 * samples' own small label set. palettes.ts covers both with explicit
 * entries; anything unlisted falls back to a neutral color.
 */
export type CellType = string;

/** Gene panel ported from explorer.html's gene-paint dropdown. */
export const MARKER_GENES = [
  'CTLA4',
  'FOXP3',
  'CXCL9',
  'STAT1',
  'CXCR4',
  'IL2RA',
  'TNFRSF9',
  'PDCD1',
] as const;

export type MarkerGene = (typeof MARKER_GENES)[number];

export interface Cell {
  id: string;
  x: number;
  y: number;
  cell_type: CellType;
  /** Only Tregs carry a niche (matches explorer.html's Treg-niches scope) — null otherwise. */
  niche: Niche | null;
  exhaustion_state: ExhaustionState;
  /** Expression values rounded to 2 decimal places */
  expression: Record<MarkerGene, number>;
  /** Atlas-only: infiltration score (atlas_score mode), unused for spatial cells. */
  score?: number;
  /** Atlas-only: top-5% selected barcode (atlas_selected mode). cell_type
   * always stays the real subtype — this drives coloring, not identity. */
  selected?: boolean;
}

export interface Citation {
  title: string;
  source: string;
  url: string;
  /** Snippet from search_literature / You.com — present on live results. */
  relevance?: string;
}

export interface AiSuggestion {
  id: string;
  gene: string;
  rationale: string;
  citation: Citation;
  linked_cell_id?: string;
  linked_niche?: Niche;
}

export interface PerturbationResult {
  cell_id: string;
  gene: string;
  before: Record<MarkerGene, number>;
  after: Record<MarkerGene, number>;
}

/** Minimal shape HypothesisCard needs — satisfied by both fixture AiSuggestion and live RankedSuggestion. */
export interface SuggestionCitationRef {
  gene: string;
  citation: Citation;
}

/** A gene knockout suggestion ranked from live You.com literature search. */
export interface RankedSuggestion {
  rank: number;
  gene: string;
  rationale: string;
  citations: Citation[];
  linked_cell_id?: string;
  linked_niche?: Niche;
}

export interface SuggestPerturbationsResponse {
  cell_id: string;
  phenotype: string;
  niche: Niche;
  source: 'you.com' | 'fallback';
  suggestions: RankedSuggestion[];
}

export interface SearchLiteratureResponse {
  query: string;
  context: string | null;
  citations: Citation[];
  warning?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  suggestions: RankedSuggestion[];
  suggestions_source: 'you.com' | 'fallback' | null;
  warning: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  suggestions?: RankedSuggestion[];
  warning?: string | null;
}

export interface SampleMeta {
  id: string;
  name: string;
  description: string;
}

export interface SampleData {
  cells: Cell[];
  suggestions: AiSuggestion[];
}

/**
 * Cell Type / Treg Niches / Gene Expression — the spatial window's three map
 * modes, ported from explorer.html's dropdown. atlas_score / atlas_selected
 * are the UMAP window's other two modes (its "cell subtypes" mode reuses
 * cell_type directly, since subtype IS cell_type for atlas points) — ported
 * from atlas_explorer.html's dropdown.
 */
export type ColorMode =
  | 'cell_type'
  | 'treg_niches'
  | 'expression'
  | 'atlas_score'
  | 'atlas_selected';
