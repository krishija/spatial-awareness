import { useCallback, useEffect, useState } from 'react';
import type { SampleMeta } from '../types';
import { listSamples } from '../api/client';

interface Props {
  onSelect: (sampleId: string) => void;
}

export function SampleSelect({ onSelect }: Props) {
  const [samples, setSamples] = useState<SampleMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listSamples().then((list) => {
      if (!cancelled) {
        setSamples(list);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      // Demo: accept any drop and load the first preloaded sample
      if (samples[0]) onSelect(samples[0].id);
    },
    [onSelect, samples],
  );

  if (loading) {
    return (
      <div className="loading-screen">
        <div>Loading sample catalog…</div>
        <div className="loading-screen__bar">
          <span />
        </div>
      </div>
    );
  }

  return (
    <div className="sample-select">
      <div className="sample-select__inner">
        <h1 className="sample-select__title">Spatial Exhaustion Explorer</h1>
        <p className="sample-select__sub">
          Select a preloaded spatial transcriptomics sample to explore CD4 T cell
          exhaustion in situ.
        </p>

        <ul className="sample-list">
          {samples.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className="sample-list__item"
                onClick={() => onSelect(s.id)}
              >
                <span className="sample-list__name">{s.name}</span>
                <span className="sample-list__desc">{s.description}</span>
              </button>
            </li>
          ))}
        </ul>

        <div
          className={`dropzone${dragOver ? ' dropzone--active' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => samples[0] && onSelect(samples[0].id)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if ((e.key === 'Enter' || e.key === ' ') && samples[0]) {
              e.preventDefault();
              onSelect(samples[0].id);
            }
          }}
        >
          Drop a Visium / Xenium file here, or click to use the first sample
          <div className="dropzone__note">
            Demo mode: file contents are not parsed — preloaded fixtures are used.
          </div>
        </div>
      </div>
    </div>
  );
}
