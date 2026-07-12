import type {
  CellType,
  ChatResponse,
  MarkerGene,
  Niche,
  PerturbationResult,
  SampleData,
  SampleMeta,
  SearchLiteratureResponse,
  SuggestPerturbationsResponse,
} from '../types';
import {
  applyPerturbation,
  generateSample,
  listSampleMeta,
} from '../data/generate';
import { adaptAtlasData, type AtlasCellsResponse, type AtlasData } from '../data/atlasData';

/**
 * Real backend base URL — the REST proxy in mcp_server/src/spatial_mcp/http_api.py.
 * Fronts the You.com-backed search_literature / suggest_perturbations MCP tools.
 */
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001';

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

function jitter(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

/**
 * Fixture samples (generate.ts) load instantly, no backend needed. Real
 * samples (e.g. the Atera cervical-01 section) are served by the REST proxy
 * from mcp_server/data/cells.parquet — populated by listSamples() so
 * loadSample() knows which fetch path to take for a given id.
 */
let realSampleIds = new Set<string>();

export async function listSamples(): Promise<SampleMeta[]> {
  const fixtures = listSampleMeta();
  try {
    const real = await getJson<{ samples: SampleMeta[] }>('/api/real_samples');
    realSampleIds = new Set(real.samples.map((s) => s.id));
    return [...fixtures, ...real.samples];
  } catch {
    return fixtures;
  }
}

export async function loadSample(id: string): Promise<SampleData> {
  if (realSampleIds.has(id)) {
    return getJson<SampleData>(`/api/real_samples/${id}`);
  }
  await delay(jitter(600, 1000));
  return generateSample(id);
}

/**
 * Runs the (still-local, not-yet-real virtual-cell-model) perturbation math
 * directly against the cell's current expression — works for both fixture
 * and real-data cells, since it never re-derives the cell via a sample
 * lookup (fixture-only `generateSample` doesn't know real sample ids).
 */
export async function runPerturbation(
  cellId: string,
  gene: string,
  currentExpression: Record<MarkerGene, number>,
  cellType: CellType,
): Promise<PerturbationResult> {
  await delay(jitter(400, 800));
  const before = { ...currentExpression };
  const after = applyPerturbation(before, gene, cellType);
  return { cell_id: cellId, gene: gene.toUpperCase(), before, after };
}

/**
 * Live literature search via the You.com-backed search_literature MCP tool.
 */
export async function searchLiterature(
  query: string,
  context?: string,
): Promise<SearchLiteratureResponse> {
  return postJson<SearchLiteratureResponse>('/api/search_literature', {
    query,
    ...(context ? { context } : {}),
  });
}

/**
 * Live, You.com-grounded knockout gene suggestions for a resolved cell,
 * via the suggest_perturbations MCP tool.
 */
export async function suggestPerturbations(
  cellId: string,
  phenotype: string,
  niche: Niche,
  literatureContext?: string,
): Promise<SuggestPerturbationsResponse> {
  return postJson<SuggestPerturbationsResponse>('/api/suggest_perturbations', {
    cell_id: cellId,
    phenotype,
    niche,
    ...(literatureContext ? { literature_context: literatureContext } : {}),
  });
}

/**
 * Free-text literature chat: an extractive answer grounded in You.com
 * citations, plus ranked knockout gene suggestions when phenotype/niche
 * context is available (e.g. a cell is selected).
 */
export async function sendChatMessage(
  message: string,
  opts?: { cellId?: string; phenotype?: string; niche?: Niche },
): Promise<ChatResponse> {
  return postJson<ChatResponse>('/api/chat', {
    message,
    ...(opts?.cellId ? { cell_id: opts.cellId } : {}),
    ...(opts?.phenotype ? { phenotype: opts.phenotype } : {}),
    ...(opts?.niche ? { niche: opts.niche } : {}),
  });
}

/**
 * AIFI reference atlas data for the UMAP window — extracted once from
 * Kriti's atlas_explorer.html into mcp_server/data/atlas_cells.json, served
 * as-is by the REST proxy.
 */
export async function loadAtlasData(): Promise<AtlasData> {
  const raw = await getJson<AtlasCellsResponse>('/api/atlas_cells');
  return adaptAtlasData(raw);
}
