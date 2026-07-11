import { useCallback, useEffect, useRef } from 'react';
import type { Cell, ColorMode, MarkerGene, SampleData } from '../types';
import { NICHE_COLORS, NICHE_STROKE } from '../data/palettes';
import { cellColor, Legend } from './Legend';

interface Props {
  data: SampleData;
  colorMode: ColorMode;
  selectedGene: MarkerGene;
  showNiches: boolean;
  selectedCellId: string | null;
  onSelectCell: (cellId: string | null) => void;
}

function draw(
  canvas: HTMLCanvasElement,
  data: SampleData,
  colorMode: ColorMode,
  selectedGene: MarkerGene,
  showNiches: boolean,
  selectedCellId: string | null,
) {
  const parent = canvas.parentElement;
  if (!parent) return;

  const dpr = window.devicePixelRatio || 1;
  const w = parent.clientWidth;
  const h = parent.clientHeight;
  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  // Tissue coordinate space: [0,100] × [0,100] with padding
  const pad = 16;
  const size = Math.min(w, h) - pad * 2;
  const ox = (w - size) / 2;
  const oy = (h - size) / 2;

  const toPx = (x: number, y: number) => ({
    px: ox + (x / 100) * size,
    py: oy + (y / 100) * size,
  });

  // Background
  ctx.fillStyle = '#f0f0ec';
  ctx.fillRect(ox, oy, size, size);
  ctx.strokeStyle = '#c8c8c2';
  ctx.lineWidth = 1;
  ctx.strokeRect(ox + 0.5, oy + 0.5, size - 1, size - 1);

  if (showNiches) {
    for (const [niche, c] of Object.entries(data.nicheCenters) as Array<
      [keyof typeof data.nicheCenters, (typeof data.nicheCenters)[keyof typeof data.nicheCenters]]
    >) {
      const { px, py } = toPx(c.x, c.y);
      const rx = (c.rx / 100) * size;
      const ry = (c.ry / 100) * size;
      ctx.beginPath();
      ctx.ellipse(px, py, rx, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = NICHE_COLORS[niche];
      ctx.fill();
      ctx.strokeStyle = NICHE_STROKE[niche];
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }

  const r = Math.max(1.2, size / 420);
  let selected: Cell | null = null;

  for (const cell of data.cells) {
    if (cell.id === selectedCellId) {
      selected = cell;
      continue;
    }
    const { px, py } = toPx(cell.x, cell.y);
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fillStyle = cellColor(
      colorMode,
      cell.cell_type,
      cell.expression[selectedGene],
    );
    ctx.globalAlpha = 0.85;
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  if (selected) {
    const { px, py } = toPx(selected.x, selected.y);
    ctx.beginPath();
    ctx.arc(px, py, r + 2.5, 0, Math.PI * 2);
    ctx.strokeStyle = '#1a1a18';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(px, py, r + 0.5, 0, Math.PI * 2);
    ctx.fillStyle = cellColor(
      colorMode,
      selected.cell_type,
      selected.expression[selectedGene],
    );
    ctx.fill();
  }

  // Store transform for hit-testing via canvas dataset
  canvas.dataset.ox = String(ox);
  canvas.dataset.oy = String(oy);
  canvas.dataset.size = String(size);
}

export function TissueMap({
  data,
  colorMode,
  selectedGene,
  showNiches,
  selectedCellId,
  onSelectCell,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cellsRef = useRef(data.cells);
  cellsRef.current = data.cells;

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    draw(canvas, data, colorMode, selectedGene, showNiches, selectedCellId);
  }, [data, colorMode, selectedGene, showNiches, selectedCellId]);

  useEffect(() => {
    redraw();
    const parent = canvasRef.current?.parentElement;
    if (!parent) return;
    const ro = new ResizeObserver(() => redraw());
    ro.observe(parent);
    return () => ro.disconnect();
  }, [redraw]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const ox = Number(canvas.dataset.ox);
    const oy = Number(canvas.dataset.oy);
    const size = Number(canvas.dataset.size);

    const tx = ((mx - ox) / size) * 100;
    const ty = ((my - oy) / size) * 100;

    if (tx < 0 || tx > 100 || ty < 0 || ty > 100) {
      onSelectCell(null);
      return;
    }

    // Nearest-neighbor hit test
    let best: Cell | null = null;
    let bestD = 2.2; // tissue-coordinate threshold
    for (const cell of cellsRef.current) {
      const dx = cell.x - tx;
      const dy = cell.y - ty;
      const d = dx * dx + dy * dy;
      if (d < bestD) {
        bestD = d;
        best = cell;
      }
    }
    onSelectCell(best?.id ?? null);
  };

  return (
    <div className="map-canvas-wrap">
      <canvas ref={canvasRef} onClick={handleClick} />
      <Legend colorMode={colorMode} selectedGene={selectedGene} />
      <div className="map-hint">Click a cell to inspect phenotype & markers</div>
    </div>
  );
}
