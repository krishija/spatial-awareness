# Frontend — Spatial Exhaustion Explorer

Vite + React UI with two windows:

1. **Spatial map** (default) — tissue sample, niches, markers, knockout suggestions, literature chat
2. **UMAP / atlas** (`?view=umap`) — single-cell atlas exploration; open from the toolbar “UMAP ↗” link

Tissue maps and local perturbation deltas still use **fixture samples** in the
browser. Literature search and ranked knockout suggestions call the live
You.com-backed tools through `spatial-api`. The research agent’s Atera /
scLDM path is separate — they do not have to be wired together for a demo.

## Run

```bash
# terminal 1 — REST proxy (YOU_API_KEY stays server-side)
cd ../mcp_server
source .venv/bin/activate   # or: python3 -m venv .venv && pip install -e .
spatial-api                 # http://localhost:8001

# terminal 2
cd ../frontend
npm install
npm run dev                 # http://localhost:5173
```

Optional: `VITE_API_BASE_URL` (default `http://localhost:8001`). Put `YOU_API_KEY`
in the repo-root `.env`.

Without the proxy, fixture suggestions still work; the literature panel shows a
connection error.

### Full tissue view

The toolbar **Full tissue view ↗** opens `/explorer.html` — a large standalone
Plotly explorer. That file is gitignored (too big for git). Copy it into
`frontend/public/` locally if you have it; otherwise the link 404s and the rest
of the app is fine.

## Layout

```
src/
  main.tsx           # mounts App or AtlasApp from ?view=umap
  App.tsx            # spatial window
  AtlasApp.tsx       # UMAP / atlas window
  types.ts
  api/client.ts      # fixture sample/perturbation + live literature HTTP
  data/
    generate.ts      # seeded dummy tissue
    atlasData.ts     # atlas-side fixtures
    palettes.ts
  components/
    TissueMap.tsx / CellPanel.tsx / LiteratureChat.tsx
    MarkerChart.tsx / MiniMap.tsx / HypothesisCard.tsx / Legend.tsx
    …
  styles.css
```

## Demo flow

1. Pick a preloaded sample
2. Toggle cell-type / expression / niches on the map
3. Click a cell → markers + ranked knockout suggestions
4. Optionally run a fixture perturbation → hypothesis card
5. **Ask literature** → `/api/chat` → `search_literature` (and suggestions when a cell is selected)
6. Open **UMAP ↗** for the atlas window
