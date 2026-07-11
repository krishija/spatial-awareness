# Frontend — Spatial Exhaustion Explorer

Vite + React UI for exploring spatial single-cell data, marker expression, AI knockout suggestions, and virtual-cell perturbation deltas. Uses fixture data only.

## Run

```bash
npm install
npm run dev
```

## Layout

```
src/
  types.ts           # Cell, suggestion, perturbation contracts
  api/client.ts      # Mock data-fetching (only file to swap for a real backend)
  data/
    generate.ts      # Seeded dummy tissue (~2k cells / sample)
    palettes.ts      # Colorblind-safe cell-type + expression colors
  components/
    SampleSelect.tsx
    TissueMap.tsx
    CellPanel.tsx
    MarkerChart.tsx / DeltaChart.tsx / MiniMap.tsx / HypothesisCard.tsx / Legend.tsx
  App.tsx
  styles.css
```

## Demo flow

1. Pick a preloaded sample  
2. Toggle cell-type / expression / niches on the map  
3. Click a cell → markers, suggestions, run a perturbation  
4. Read the hypothesis summary card  
