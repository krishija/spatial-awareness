# Spatial Exhaustion Explorer

Hackathon frontend for exploring single-cell spatial transcriptomics with CD4 T cell exhaustion phenotypes, AI-suggested gene knockouts, and virtual-cell perturbation predictions. Runs entirely on internally consistent dummy data.

## Run

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173).

## Demo flow

1. Select a preloaded sample (or drop any file — demo ignores contents and loads fixtures).
2. Explore the tissue map; toggle **Cell type** / **Expression** coloring and **Show niches**.
3. Click a cell → inspect markers vs niche mean, AI knockout suggestions.
4. Pre-fill a suggestion and **Run** a perturbation → delta chart + hypothesis summary card.

## Backend swap

Replace implementations in [`src/api/client.ts`](src/api/client.ts) only. Components consume the types in [`src/types.ts`](src/types.ts).
