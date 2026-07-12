import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
  ColorMode,
  MarkerGene,
  PerturbationResult,
  SampleData,
  SampleMeta,
  SuggestionCitationRef,
} from './types';
import { MARKER_GENES } from './types';
import { listSamples, loadSample } from './api/client';
import { SampleSelect } from './components/SampleSelect';
import { TissueMap } from './components/TissueMap';
import { CellPanel } from './components/CellPanel';
import { HypothesisCard } from './components/HypothesisCard';
import { LiteratureChat } from './components/LiteratureChat';
import './styles.css';

export default function App() {
  const [sampleId, setSampleId] = useState<string | null>(null);
  const [sampleMeta, setSampleMeta] = useState<SampleMeta[]>([]);
  const [data, setData] = useState<SampleData | null>(null);
  const [loadingSample, setLoadingSample] = useState(false);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>('cell_type');
  const [selectedGene, setSelectedGene] = useState<MarkerGene>('PDCD1');
  const [perturbation, setPerturbation] = useState<PerturbationResult | null>(
    null,
  );
  const [activeSuggestion, setActiveSuggestion] =
    useState<SuggestionCitationRef | null>(null);
  const [showChat, setShowChat] = useState(false);
  const [pendingGene, setPendingGene] = useState<{ gene: string; nonce: number } | null>(
    null,
  );

  useEffect(() => {
    listSamples().then(setSampleMeta);
  }, []);

  const selectSample = useCallback(async (id: string) => {
    setSampleId(id);
    setLoadingSample(true);
    setSelectedCellId(null);
    setPerturbation(null);
    setActiveSuggestion(null);
    setData(null);
    try {
      const sample = await loadSample(id);
      setData(sample);
    } finally {
      setLoadingSample(false);
    }
  }, []);

  const resetToSelect = () => {
    setSampleId(null);
    setData(null);
    setSelectedCellId(null);
    setPerturbation(null);
    setActiveSuggestion(null);
  };

  const selectedCell = useMemo(() => {
    if (!data || !selectedCellId) return null;
    return data.cells.find((c) => c.id === selectedCellId) ?? null;
  }, [data, selectedCellId]);

  const currentMeta = sampleMeta.find((s) => s.id === sampleId);

  const handleSelectCell = (id: string | null) => {
    setSelectedCellId(id);
    setPerturbation(null);
    setActiveSuggestion(null);
  };

  const handlePerturbation = (
    result: PerturbationResult | null,
    suggestion?: SuggestionCitationRef,
  ) => {
    setPerturbation(result);
    setActiveSuggestion(suggestion ?? null);
  };

  const handleUseGene = (gene: string) => {
    setPendingGene({ gene, nonce: Date.now() });
  };

  if (!sampleId) {
    return <SampleSelect onSelect={selectSample} />;
  }

  if (loadingSample || !data) {
    return (
      <div className="loading-screen">
        <div>Loading spatial sample…</div>
        <div className="loading-screen__bar">
          <span />
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="toolbar">
        <span className="toolbar__brand">Spatial Exhaustion Explorer</span>
        <span className="toolbar__sample" title={currentMeta?.name}>
          {currentMeta?.name ?? sampleId}
        </span>
        <span className="toolbar__sep" />

        <div className="toolbar__group">
          <span className="toolbar__label">Color</span>
          <div className="seg">
            <button
              type="button"
              className={`seg__btn${colorMode === 'cell_type' ? ' seg__btn--active' : ''}`}
              onClick={() => setColorMode('cell_type')}
            >
              Cell Type
            </button>
            <button
              type="button"
              className={`seg__btn${colorMode === 'treg_niches' ? ' seg__btn--active' : ''}`}
              onClick={() => setColorMode('treg_niches')}
            >
              Treg Niches
            </button>
            <button
              type="button"
              className={`seg__btn${colorMode === 'expression' ? ' seg__btn--active' : ''}`}
              onClick={() => setColorMode('expression')}
            >
              Gene Expression
            </button>
          </div>
          {colorMode === 'expression' && (
            <select
              value={selectedGene}
              onChange={(e) => setSelectedGene(e.target.value as MarkerGene)}
              aria-label="Marker gene"
            >
              {MARKER_GENES.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          )}
        </div>

        <span className="toolbar__spacer" />

        <a
          href="/explorer.html"
          target="_blank"
          rel="noreferrer"
          className="toolbar__back"
          title="Full 715k-cell tissue view (all cell types, Treg niches, gene expression) — opens in a new tab"
        >
          Full tissue view ↗
        </a>

        <a
          href="/?view=umap"
          target="_blank"
          rel="noreferrer"
          className="toolbar__back"
          title="AIFI reference atlas — cell subtypes, infiltration score, selected barcodes — opens in a new tab"
        >
          UMAP ↗
        </a>

        <button
          type="button"
          className={`toolbar__back${showChat ? ' toolbar__back--active' : ''}`}
          onClick={() => setShowChat((v) => !v)}
        >
          Ask literature
        </button>

        <button type="button" className="toolbar__back" onClick={resetToSelect}>
          Change sample
        </button>
      </header>

      <div className="main">
        <div className="map-area">
          <TissueMap
            data={data}
            colorMode={colorMode}
            selectedGene={selectedGene}
            selectedCellId={selectedCellId}
            onSelectCell={handleSelectCell}
          />
          {perturbation && selectedCell && (
            <HypothesisCard
              cell={selectedCell}
              result={perturbation}
              suggestion={activeSuggestion}
            />
          )}
        </div>
        {showChat && (
          <LiteratureChat
            selectedCell={selectedCell}
            onClose={() => setShowChat(false)}
            onUseGene={handleUseGene}
          />
        )}
        <CellPanel
          data={data}
          selectedCell={selectedCell}
          colorMode={colorMode}
          selectedGene={selectedGene}
          perturbation={perturbation}
          onPerturbation={handlePerturbation}
          pendingGene={pendingGene}
        />
      </div>
    </div>
  );
}
