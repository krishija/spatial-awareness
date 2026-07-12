import { useEffect, useMemo, useState } from 'react';
import type {
  Cell,
  ColorMode,
  MarkerGene,
  PerturbationResult,
  RankedSuggestion,
  SampleData,
  SuggestionCitationRef,
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
import { runPerturbation, suggestPerturbations } from '../api/client';
import { MarkerChart } from './MarkerChart';
import { DeltaChart } from './DeltaChart';
import { MiniMap } from './MiniMap';

interface NormalizedSuggestion {
  key: string;
  gene: string;
  rationale: string;
  citations: SuggestionCitationRef['citation'][];
}

type SuggestionsSource = 'you.com' | 'fallback' | 'local' | null;

interface Props {
  sampleId: string;
  data: SampleData;
  selectedCell: Cell | null;
  colorMode: ColorMode;
  selectedGene: MarkerGene;
  perturbation: PerturbationResult | null;
  onPerturbation: (
    result: PerturbationResult | null,
    suggestion?: SuggestionCitationRef,
  ) => void;
  pendingGene?: { gene: string; nonce: number } | null;
}

export function CellPanel({
  sampleId,
  data,
  selectedCell,
  colorMode,
  selectedGene,
  perturbation,
  onPerturbation,
  pendingGene,
}: Props) {
  const [geneInput, setGeneInput] = useState('PDCD1');
  const [selectedSuggestionKey, setSelectedSuggestionKey] = useState<string | null>(
    null,
  );
  const [running, setRunning] = useState(false);
  const [liveSuggestions, setLiveSuggestions] = useState<RankedSuggestion[] | null>(
    null,
  );
  const [suggestionsSource, setSuggestionsSource] = useState<SuggestionsSource>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  const nicheMean = useMemo(() => {
    if (!selectedCell) return null;
    return nicheMeanExpression(data.cells, selectedCell.niche);
  }, [data.cells, selectedCell]);

  // Fixture suggestions (niche-linked, bundled at sample load) — used only as
  // a fallback if the live suggest_perturbations call fails outright.
  const fixtureSuggestions = useMemo(() => {
    if (!selectedCell) return data.suggestions;
    return [...data.suggestions].sort((a, b) => {
      const aMatch = a.linked_niche === selectedCell.niche ? 0 : 1;
      const bMatch = b.linked_niche === selectedCell.niche ? 0 : 1;
      return aMatch - bMatch;
    });
  }, [data.suggestions, selectedCell]);

  useEffect(() => {
    if (!selectedCell) {
      setLiveSuggestions(null);
      setSuggestionsSource(null);
      return;
    }
    let cancelled = false;
    setSuggestionsLoading(true);
    suggestPerturbations(selectedCell.id, selectedCell.cell_type, selectedCell.niche)
      .then((res) => {
        if (cancelled) return;
        setLiveSuggestions(res.suggestions);
        setSuggestionsSource(res.source);
      })
      .catch(() => {
        if (cancelled) return;
        setLiveSuggestions(null);
        setSuggestionsSource('local');
      })
      .finally(() => {
        if (!cancelled) setSuggestionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCell]);

  const normalizedSuggestions: NormalizedSuggestion[] = useMemo(() => {
    if (liveSuggestions) {
      return liveSuggestions.map((s) => ({
        key: `${s.gene}-${s.rank}`,
        gene: s.gene,
        rationale: s.rationale,
        citations: s.citations,
      }));
    }
    return fixtureSuggestions.map((s) => ({
      key: s.id,
      gene: s.gene,
      rationale: s.rationale,
      citations: [s.citation],
    }));
  }, [liveSuggestions, fixtureSuggestions]);

  // Briefly highlights the perturbation form so a suggestion click (here or
  // from the literature chat) visibly lands somewhere, instead of the gene
  // field silently changing off-screen.
  const [flashing, setFlashing] = useState(false);
  const flashPerturbSection = () => {
    setFlashing(true);
    window.setTimeout(() => setFlashing(false), 900);
  };

  // Tracks where the current gene came from, so the hint below the form is
  // accurate whether it was picked here, loaded from the chat, or typed by hand.
  const [geneOrigin, setGeneOrigin] = useState<'suggestion' | 'chat' | 'manual'>(
    'manual',
  );

  // A chat "Use" click drops a gene in from outside this component.
  useEffect(() => {
    if (!pendingGene) return;
    setGeneInput(pendingGene.gene);
    setSelectedSuggestionKey(null);
    setGeneOrigin('chat');
    flashPerturbSection();
  }, [pendingGene]);

  const pickSuggestion = (s: NormalizedSuggestion) => {
    setGeneInput(s.gene);
    setSelectedSuggestionKey(s.key);
    setGeneOrigin('suggestion');
    flashPerturbSection();
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
      const matched =
        normalizedSuggestions.find((s) => s.key === selectedSuggestionKey) ??
        normalizedSuggestions.find(
          (s) => s.gene.toUpperCase() === result.gene.toUpperCase(),
        );
      const sug: SuggestionCitationRef | undefined =
        matched && matched.citations[0]
          ? { gene: matched.gene, citation: matched.citations[0] }
          : undefined;
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
          Click a point on the tissue map to inspect phenotype and marker
          expression, review AI-suggested knockouts grounded in live
          literature, then run one through the virtual cell model.
        </div>
      </aside>
    );
  }

  const step: 'suggest' | 'perturb' | 'result' = perturbation
    ? 'result'
    : running
      ? 'perturb'
      : 'suggest';

  const cell = selectedCell;

  return (
    <aside className="cell-panel">
      <div className="workflow-steps">
        <span className="workflow-steps__step workflow-steps__step--done">Inspect</span>
        <span className="workflow-steps__arrow">→</span>
        <span
          className={`workflow-steps__step${
            step === 'suggest' ? ' workflow-steps__step--active' : ' workflow-steps__step--done'
          }`}
        >
          Suggest
        </span>
        <span className="workflow-steps__arrow">→</span>
        <span
          className={`workflow-steps__step${
            step === 'perturb'
              ? ' workflow-steps__step--active'
              : step === 'result'
                ? ' workflow-steps__step--done'
                : ''
          }`}
        >
          Perturb
        </span>
        <span className="workflow-steps__arrow">→</span>
        <span
          className={`workflow-steps__step${step === 'result' ? ' workflow-steps__step--active' : ''}`}
        >
          Result
        </span>
      </div>
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
          <div className="panel-section__head">
            <h3 className="panel-section__title">2 · AI-suggested knockouts</h3>
            {suggestionsLoading && <span className="source-pill source-pill--loading">searching…</span>}
            {!suggestionsLoading && suggestionsSource === 'you.com' && (
              <span className="source-pill source-pill--good">● via You.com</span>
            )}
            {!suggestionsLoading && suggestionsSource === 'fallback' && (
              <span className="source-pill source-pill--warn">● fallback</span>
            )}
            {!suggestionsLoading && suggestionsSource === 'local' && (
              <span className="source-pill source-pill--warn">● offline fixture</span>
            )}
          </div>
          <p className="panel-section__hint">
            Ranked by live literature mentions for this phenotype &amp; niche. Click a
            card to load it into the perturbation run below.
          </p>
          {normalizedSuggestions.map((s) => (
            <div
              key={s.key}
              className={`suggestion${selectedSuggestionKey === s.key ? ' suggestion--selected' : ''}`}
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
              {s.citations.map((c, i) => (
                <div className="suggestion__cite" key={i}>
                  {c.title} — {c.source}{' '}
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    link
                  </a>
                </div>
              ))}
              <div className="suggestion__footer">
                {selectedSuggestionKey === s.key ? (
                  <span className="suggestion__selected">✓ Loaded into perturbation form below</span>
                ) : (
                  <span className="suggestion__cta">Use in perturbation →</span>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className={`panel-section perturb-section${flashing ? ' perturb-section--flash' : ''}`}>
          <h3 className="panel-section__title">
            3 · Run perturbation <span className="panel-section__subtitle">— virtual cell model (scLDM-CD4)</span>
          </h3>
          <p className="panel-section__hint">
            {geneOrigin === 'suggestion' && `Testing the AI-suggested knockout of ${geneInput}, from the panel above.`}
            {geneOrigin === 'chat' && `Testing the AI-suggested knockout of ${geneInput}, from the literature chat.`}
            {geneOrigin === 'manual' && 'Pick a gene below, or click a suggestion above to load it here.'}
          </p>
          <div className="perturb-form">
            <select
              value={MARKER_GENES.includes(geneInput as MarkerGene) ? geneInput : ''}
              onChange={(e) => {
                if (e.target.value) {
                  setGeneInput(e.target.value);
                  setSelectedSuggestionKey(null);
                  setGeneOrigin('manual');
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
                setSelectedSuggestionKey(null);
                setGeneOrigin('manual');
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
