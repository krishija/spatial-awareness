import type {
  ChatResponse,
  Niche,
  PerturbationResult,
  SampleData,
  SampleMeta,
  SearchLiteratureResponse,
  SuggestPerturbationsResponse,
} from '../types';
import {
  computePerturbation,
  generateSample,
  listSampleMeta,
} from '../data/generate';

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

function jitter(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

/**
 * Mock data-fetching layer.
 * Swap this file for real HTTP calls when the backend is ready —
 * component code should not need to change.
 */
export async function listSamples(): Promise<SampleMeta[]> {
  await delay(jitter(150, 350));
  return listSampleMeta();
}

export async function loadSample(id: string): Promise<SampleData> {
  await delay(jitter(600, 1000));
  return generateSample(id);
}

export async function runPerturbation(
  sampleId: string,
  cellId: string,
  gene: string,
): Promise<PerturbationResult> {
  await delay(jitter(400, 800));
  return computePerturbation(sampleId, cellId, gene);
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
