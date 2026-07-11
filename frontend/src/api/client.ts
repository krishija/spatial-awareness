import type {
  PerturbationResult,
  SampleData,
  SampleMeta,
} from '../types';
import {
  computePerturbation,
  generateSample,
  listSampleMeta,
} from '../data/generate';

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
