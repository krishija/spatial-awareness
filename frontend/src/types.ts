export type Niche = 'tumor_core' | 'tumor_margin' | 'lymphoid_proximal';

export type ExhaustionState =
  | 'terminally_exhausted'
  | 'progenitor_exhausted'
  | 'effector'
  | 'other';

export type CellType =
  | 'CD4_Tex_term'
  | 'CD4_Tex_prog'
  | 'CD4_Teff'
  | 'CD4_Treg'
  | 'myeloid'
  | 'tumor'
  | 'stromal';

export const MARKER_GENES = [
  'PDCD1',
  'TCF7',
  'TOX',
  'LAG3',
  'GZMB',
  'IL7R',
  'CTLA4',
  'FOXP3',
] as const;

export type MarkerGene = (typeof MARKER_GENES)[number];

export interface Cell {
  id: string;
  x: number;
  y: number;
  cell_type: CellType;
  niche: Niche;
  exhaustion_state: ExhaustionState;
  /** Expression values rounded to 2 decimal places */
  expression: Record<MarkerGene, number>;
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
  nicheCenters: Record<Niche, { x: number; y: number; rx: number; ry: number }>;
}

export type ColorMode = 'cell_type' | 'expression';
