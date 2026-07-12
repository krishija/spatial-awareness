# Frontend — Spatial Exhaustion Explorer

Vite + React UI for exploring spatial single-cell data, marker expression, AI knockout suggestions, and virtual-cell perturbation deltas.

Tissue maps and perturbation deltas use **fixture data**. Literature search and ranked knockout suggestions call the live You.com-backed `search_literature` / `suggest_perturbations` tools through the MCP server’s REST proxy.

## Run

```bash
# terminal 1 — REST proxy (keeps YOU_API_KEY server-side)
cd ../mcp_server
source .venv/bin/activate   # or: python3 -m venv .venv && pip install -e .
spatial-api                 # http://localhost:8001

# terminal 2 — UI
cd ../frontend
npm install
npm run dev                 # http://localhost:5173
```

Optional: set `VITE_API_BASE_URL` (defaults to `http://localhost:8001`). Put `YOU_API_KEY` in the repo-root `.env`.

Without the proxy running, the demo still works — suggestions fall back to fixture citations and the chat panel shows a connection error.

### "Full tissue view" link

The toolbar's **Full tissue view ↗** button opens `/explorer.html` — Kriti's standalone 715k-cell Plotly explorer (all cell types / Treg niches / gene expression). It's gitignored (27MB, too large for git) so it does **not** come with a fresh clone. To make the button work locally, copy the file into `frontend/public/`:

```bash
cp "path/to/explorer.html" frontend/public/explorer.html
```

Without it, the button just 404s — everything else in the app works fine regardless.

## Layout

```
src/
  types.ts           # Cell, suggestion, literature, chat contracts
  api/client.ts      # Fixture sample/perturbation + live literature HTTP calls
  data/
    generate.ts      # Seeded dummy tissue (~2k cells / sample)
    palettes.ts      # Colorblind-safe cell-type + expression colors
  components/
    SampleSelect.tsx
    TissueMap.tsx
    CellPanel.tsx          # Live suggest_perturbations on cell select
    LiteratureChat.tsx     # Free-text Ask literature → /api/chat → search_literature
    MarkerChart.tsx / DeltaChart.tsx / MiniMap.tsx / HypothesisCard.tsx / Legend.tsx
  App.tsx
  styles.css
```

## Demo flow

1. Pick a preloaded sample  
2. Toggle cell-type / expression / niches on the map  
3. Click a cell → markers + You.com-ranked knockout suggestions  
4. Run a perturbation → hypothesis summary card  
5. **Ask literature** → free-text questions grounded in `search_literature` citations (and ranked KO genes when a cell is selected)  
