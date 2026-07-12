import { useId, useRef, useState } from 'react';
import type { Cell, ChatMessage } from '../types';
import { NICHE_LABELS, cellTypeLabel } from '../data/palettes';
import { sendChatMessage } from '../api/client';

interface Props {
  selectedCell: Cell | null;
  onClose: () => void;
  onUseGene: (gene: string) => void;
}

let msgCounter = 0;
function nextId(): string {
  msgCounter += 1;
  return `msg-${msgCounter}`;
}

export function LiteratureChat({ selectedCell, onClose, onUseGene }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [justUsedGene, setJustUsedGene] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputId = useId();

  const scopeLabel = selectedCell
    ? `Scoped to ${cellTypeLabel(selectedCell.cell_type)}${
        selectedCell.niche ? ` · ${NICHE_LABELS[selectedCell.niche]}` : ' (no niche — suggestions unavailable)'
      }`
    : 'No cell selected — general answer only, no knockout suggestions yet';

  const loadGeneIntoForm = (gene: string) => {
    onUseGene(gene);
    setJustUsedGene(gene);
    window.setTimeout(() => setJustUsedGene((g) => (g === gene ? null : g)), 1200);
  };

  const submit = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    const userMsg: ChatMessage = { id: nextId(), role: 'user', text };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);
    try {
      const res = await sendChatMessage(text, {
        cellId: selectedCell?.id,
        phenotype: selectedCell?.cell_type,
        niche: selectedCell?.niche ?? undefined,
      });
      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        text: res.answer,
        citations: res.citations,
        suggestions: res.suggestions,
        warning: res.warning,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        text:
          "Couldn't reach the literature backend. Is the REST proxy running " +
          '(`spatial-api`, http://localhost:8001)?',
        warning: err instanceof Error ? err.message : String(err),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } finally {
      setSending(false);
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
      });
    }
  };

  return (
    <aside className="chat-panel">
      <div className="chat-panel__header">
        <span className="chat-panel__title">Ask the literature</span>
        <button type="button" className="chat-panel__close" onClick={onClose} aria-label="Close chat">
          ×
        </button>
      </div>
      <div className="chat-panel__scope">{scopeLabel}</div>

      <div className="chat-panel__scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-panel__empty">
            Ask a question about CD4 exhaustion, checkpoints, or niches — answers
            are grounded in live You.com literature search. Select a cell first
            to also get ranked knockout gene suggestions.
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-msg chat-msg--${m.role}`}>
            <div className="chat-msg__text">{m.text}</div>

            {m.warning && <div className="chat-msg__warning">{m.warning}</div>}

            {!!m.citations?.length && (
              <div className="chat-msg__citations">
                {m.citations.map((c, i) => (
                  <a
                    key={i}
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                    className="chat-citation"
                    title={c.relevance}
                  >
                    {c.title} — {c.source}
                    {c.relevance ? (
                      <span className="chat-citation__snippet">{c.relevance}</span>
                    ) : null}
                  </a>
                ))}
              </div>
            )}

            {!!m.suggestions?.length && (
              <div className="chat-msg__suggestions">
                <div className="chat-msg__suggestions-title">
                  Ranked knockout candidates
                </div>
                {m.suggestions.map((s) => (
                  <div key={s.rank} className="chat-suggestion">
                    <div className="chat-suggestion__head">
                      <span className="chat-suggestion__rank">#{s.rank}</span>
                      <span className="gene">{s.gene}</span>
                      <button
                        type="button"
                        className={`chat-suggestion__use${justUsedGene === s.gene ? ' chat-suggestion__use--done' : ''}`}
                        onClick={() => loadGeneIntoForm(s.gene)}
                        disabled={!selectedCell}
                        title={
                          selectedCell
                            ? 'Load this gene into the perturbation form'
                            : 'Select a cell to run this perturbation'
                        }
                      >
                        {justUsedGene === s.gene ? 'Loaded ✓' : 'Use'}
                      </button>
                    </div>
                    <div className="chat-suggestion__rationale">{s.rationale}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {sending && <div className="chat-msg chat-msg--assistant chat-msg--pending">Searching literature…</div>}
      </div>

      <form
        className="chat-panel__form"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor={inputId} className="visually-hidden">
          Ask a question
        </label>
        <input
          id={inputId}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. what drives CD4 exhaustion at the tumor margin?"
          disabled={sending}
        />
        <button type="submit" disabled={sending || !input.trim()}>
          Ask
        </button>
      </form>
    </aside>
  );
}
