import { useMemo, useState } from 'react';
import type {
  AiSuggestion,
  Cell,
  ColorMode,
  MarkerGene,
  PerturbationResult,
  SampleData,
} from '../types';
import { MARKER_GENES } from '../types';
import {
  CELL_TYPE_COLORS,
  CELL_TYPE_LABELS,
  EXHAUSTION_LABELS,
  NICHE_LABELS,
  formatCoord,
} from '../data/palettes';
import { nicheMeanExpression } from '../data/generate';
import { runPerturbation } from '../api/client';
import { MarkerChart } from './MarkerChart';
import { DeltaChart } from './DeltaChart';
import { MiniMap } from './MiniMap';

interface Props {
  sampleId: string;
  data: SampleData;
  selectedCell: Cell | null;
  colorMode: ColorMode;
  selectedGene: MarkerGene;
  perturbation: PerturbationResult | null;
  onPerturbation: (result: PerturbationResult | null, suggestion?: AiSuggestion) => void;
}

export function CellPanel({
  sampleId,
  data,
  selectedCell,
  colorMode,
  selectedGene,
  perturbation,
  onPerturbation,
}: Props) {
  const [geneInput, setGeneInput] = useState('PDCD1');
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<string | null>(
    null,
  );
  const [running, setRunning] = useState(false);

  const nicheMean = useMemo(() => {
    if (!selectedCell) return null;
    return nicheMeanExpression(data.cells, selectedCell.niche);
  }, [data.cells, selectedCell]);

  const filteredSuggestions = useMemo(() => {
    if (!selectedCell) return data.suggestions;
    // Prefer niche-linked suggestions first
    return [...data.suggestions].sort((a, b) => {
      const aMatch = a.linked_niche === selectedCell.niche ? 0 : 1;
      const bMatch = b.linked_niche === selectedCell.niche ? 0 : 1;
      return aMatch - bMatch;
    });
  }, [data.suggestions, selectedCell]);

  const pickSuggestion = (s: AiSuggestion) => {
    setGeneInput(s.gene);
    setSelectedSuggestionId(s.id);
  };

  const handleRun = async () => {
    if (!selectedCell || !geneInput.trim()) return;
    setRunning(true);
    onPerturbation(null);
    try {
      const result = await runPerturbation(
        sampleId,
        selectedCell.id,
        geneInput.trim(),
      );
      const sug =
        filteredSuggestions.find((s) => s.id === selectedSuggestionId) ??
        filteredSuggestions.find(
          (s) => s.gene.toUpperCase() === result.gene.toUpperCase(),
        );
      onPerturbation(result, sug);
    } finally {
      setRunning(false);
    }
  };

  if (!selectedCell || !nicheMean) {
    return (
      <aside className="cell-panel">
        <div className="cell-panel__empty">
          No cell selected.
          <br />
          Click a point on the tissue map to inspect phenotype, marker
          expression, and AI-suggested knockouts.
        </div>
      </aside>
    );
  }

  const cell = selectedCell;

  return (
    <aside className="cell-panel">
      <div className="cell-panel__scroll">
        <div className="panel-section">
          <h3 className="panel-section__title">Cell</h3>
          <div className="cell-header">
            <span className="badge">
              <span
                className="badge__dot"
                style={{ background: CELL_TYPE_COLORS[cell.cell_type] }}
              />
              {CELL_TYPE_LABELS[cell.cell_type]}
            </span>
            <span className="badge">{NICHE_LABELS[cell.niche]}</span>
          </div>
          <div className="cell-meta">
            <span>
              Exhaustion:{' '}
              {EXHAUSTION_LABELS[cell.exhaustion_state] ?? cell.exhaustion_state}
            </span>
            <span className="num">
              x={formatCoord(cell.x)}, y={formatCoord(cell.y)}
            </span>
            <span className="num">{cell.id}</span>
          </div>
        </div>

        <div className="panel-section">
          <h3 className="panel-section__title">Marker expression vs niche</h3>
          <MarkerChart cellExpr={cell.expression} nicheMean={nicheMean} />
        </div>

        <div className="panel-section">
          <h3 className="panel-section__title">Tissue location</h3>
          <MiniMap
            cells={data.cells}
            selected={cell}
            colorMode={colorMode}
            selectedGene={selectedGene}
          />
        </div>

        <div className="panel-section">
          <h3 className="panel-section__title">AI scientist suggestions</h3>
          {filteredSuggestions.map((s) => (
            <div
              key={s.id}
              className={`suggestion${selectedSuggestionId === s.id ? ' suggestion--selected' : ''}`}
              onClick={() => pickSuggestion(s)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  pickSuggestion(s);
                }
              }}
            >
              <div className="suggestion__gene">
                Knockout <span className="gene">{s.gene}</span>
              </div>
              <div className="suggestion__rationale">{s.rationale}</div>
              <div className="suggestion__cite">
                {s.citation.title} — {s.citation.source}{' '}
                <a
                  href={s.citation.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  link
                </a>
              </div>
            </div>
          ))}
        </div>

        <div className="panel-section">
          <h3 className="panel-section__title">Perturbation</h3>
          <div className="perturb-form">
            <select
              value={MARKER_GENES.includes(geneInput as MarkerGene) ? geneInput : ''}
              onChange={(e) => {
                if (e.target.value) {
                  setGeneInput(e.target.value);
                  setSelectedSuggestionId(null);
                }
              }}
              aria-label="Gene to knockout"
            >
              <option value="" disabled>
                Gene…
              </option>
              {MARKER_GENES.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
            <input
              value={geneInput}
              onChange={(e) => {
                setGeneInput(e.target.value.toUpperCase());
                setSelectedSuggestionId(null);
              }}
              placeholder="or type gene"
              aria-label="Gene symbol"
            />
            <button type="button" onClick={handleRun} disabled={running || !geneInput.trim()}>
              Run
            </button>
          </div>
          {running && (
            <div className="perturb-status">Querying virtual cell model…</div>
          )}
          <DeltaChart result={perturbation} running={running} />
        </div>
      </div>
    </aside>
  );
}
