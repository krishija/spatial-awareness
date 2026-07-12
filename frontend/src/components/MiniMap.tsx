import { useEffect, useRef } from 'react';
import type { Cell, ColorMode, MarkerGene } from '../types';
import { cellColor, cellTypeColor } from '../data/palettes';

interface Props {
  cells: Cell[];
  selected: Cell;
  colorMode: ColorMode;
  selectedGene: MarkerGene;
}

export function MiniMap({ cells, selected, colorMode, selectedGene }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
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
    ctx.fillStyle = '#ebebe6';
    ctx.fillRect(0, 0, w, h);

    const pad = 4;
    const toPx = (x: number, y: number) => ({
      px: pad + (x / 100) * (w - pad * 2),
      py: pad + (y / 100) * (h - pad * 2),
    });

    const r = 0.9;
    for (const cell of cells) {
      if (cell.id === selected.id) continue;
      const { px, py } = toPx(cell.x, cell.y);
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fillStyle = cellColor(cell, colorMode, selectedGene);
      ctx.globalAlpha = 0.55;
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    const { px, py } = toPx(selected.x, selected.y);
    ctx.beginPath();
    ctx.arc(px, py, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = cellTypeColor(selected.cell_type);
    ctx.fill();
    ctx.strokeStyle = '#1a1a18';
    ctx.lineWidth = 1.25;
    ctx.stroke();
  }, [cells, selected, colorMode, selectedGene]);

  return (
    <div className="mini-map">
      <canvas ref={canvasRef} />
    </div>
  );
}
