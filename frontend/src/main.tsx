import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import AtlasApp from './AtlasApp';

// No router dependency — the UMAP window is opened as ?view=umap in a new
// tab (same pattern as the "Full tissue view" static-HTML link), and this
// just picks which top-level app to mount.
const isUmapView = new URLSearchParams(window.location.search).get('view') === 'umap';

createRoot(document.getElementById('root')!).render(
  <StrictMode>{isUmapView ? <AtlasApp /> : <App />}</StrictMode>,
);
