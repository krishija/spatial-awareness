"""First-class structured reasoning trace — used by driver, report, and demos."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TraceEvent:
    step: int
    event: str
    payload: dict[str, Any]
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReasoningTrace:
    def __init__(self, research_question: str) -> None:
        self.research_question = research_question
        self.events: list[TraceEvent] = []
        self._step = 0

    def log(self, event: str, **payload: Any) -> TraceEvent:
        self._step += 1
        ev = TraceEvent(step=self._step, event=event, payload=payload)
        self.events.append(ev)
        # Demo-friendly stderr stream
        print(json.dumps(ev.to_dict(), default=str), file=sys.stderr, flush=True)
        return ev

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_question": self.research_question,
            "n_events": len(self.events),
            "events": self.to_list(),
        }
