import { useEffect, useMemo, useState } from 'react';
import type {
  Cell,
  ColorMode,
  MarkerGene,
  PerturbationResult,
  SuggestionCitationRef,
} from './types';
import { loadAtlasData } from './api/client';
import type { AtlasData } from './data/atlasData';
import { TissueMap } from './components/TissueMap';
import { CellPanel } from './components/CellPanel';
import { HypothesisCard } from './components/HypothesisCard';
import { LiteratureChat } from './components/LiteratureChat';
import './styles.css';

/**
 * The UMAP window — same structural shell as the spatial App (toolbar / map /
 * CellPanel), reused as-is per instruction, but showing the AIFI reference
 * atlas instead of tissue: cell subtypes / infiltration score / selected
 * barcodes, ported from atlas_explorer.html's dropdown. Opened via the
 * spatial window's "UMAP ↗" button (?view=umap), in a new tab.
 */
export default function AtlasApp() {
  const [atlas, setAtlas] = useState<AtlasData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>('cell_type');
  // No gene-expression mode in the atlas window — TissueMap/CellPanel/Legend
  // still take a selectedGene prop, so this is a constant, not state.
  const selectedGene: MarkerGene = 'PDCD1';
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
    loadAtlasData()
      .then(setAtlas)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  const cells: Cell[] = useMemo(() => {
    if (!atlas) return [];
    if (colorMode === 'atlas_score') return atlas.scoreCells;
    if (colorMode === 'atlas_selected') return atlas.selectedCells;
    return atlas.subtypeCells;
  }, [atlas, colorMode]);

  const data = useMemo(() => ({ cells, suggestions: [] }), [cells]);

  const selectedCell = useMemo(() => {
    if (!selectedCellId) return null;
    return cells.find((c) => c.id === selectedCellId) ?? null;
  }, [cells, selectedCellId]);

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

  if (loading) {
    return (
      <div className="loading-screen">
        <div>Loading reference atlas…</div>
        <div className="loading-screen__bar">
          <span />
        </div>
      </div>
    );
  }

  if (error || !atlas) {
    return (
      <div className="loading-screen">
        <div>Couldn't load the atlas ({error ?? 'no data'}).</div>
        <div style={{ fontSize: 12, marginTop: 6 }}>
          Is <code>spatial-api</code> running, and does{' '}
          <code>mcp_server/data/atlas_cells.json</code> exist?
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="toolbar">
        <span className="toolbar__brand">AIFI Reference Atlas</span>
        <span className="toolbar__sample" title="CD4 T cell atlas, healthy-donor PBMC">
          {atlas.nAtlasTotal.toLocaleString()} cells · {atlas.nSelected} selected
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
              Cell Subtypes
            </button>
            <button
              type="button"
              className={`seg__btn${colorMode === 'atlas_score' ? ' seg__btn--active' : ''}`}
              onClick={() => setColorMode('atlas_score')}
            >
              Infiltration Score
            </button>
            <button
              type="button"
              className={`seg__btn${colorMode === 'atlas_selected' ? ' seg__btn--active' : ''}`}
              onClick={() => setColorMode('atlas_selected')}
            >
              Selected Barcodes
            </button>
          </div>
        </div>

        <span className="toolbar__spacer" />

        <a href="/" className="toolbar__back" title="Back to the spatial tissue view">
          ← Spatial view
        </a>

        <button
          type="button"
          className={`toolbar__back${showChat ? ' toolbar__back--active' : ''}`}
          onClick={() => setShowChat((v) => !v)}
        >
          Ask literature
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
