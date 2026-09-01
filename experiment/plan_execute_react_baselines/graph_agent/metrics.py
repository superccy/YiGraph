from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ModelConfig


@dataclass
class LLMCallMetric:
    purpose: str
    model: str
    duration_seconds: float
    prompt_tokens: int
    completion_tokens: int
    cached_prompt_tokens: int
    total_tokens: int
    cost_usd: Optional[float]


@dataclass
class EventMetric:
    kind: str
    name: str
    duration_seconds: float
    metadata: Dict[str, Any]


class MetricsCollector:
    """Thread-safe token, cost, latency, and executor event accounting."""

    def __init__(self, model_config: ModelConfig) -> None:
        self.model_config = model_config
        self.started_at = time.time()
        self._llm_calls: List[LLMCallMetric] = []
        self._events: List[EventMetric] = []
        self._lock = threading.Lock()

    def add_llm_call(
        self,
        purpose: str,
        duration_seconds: float,
        prompt_tokens: int,
        completion_tokens: int,
        cached_prompt_tokens: int = 0,
    ) -> None:
        uncached = max(0, prompt_tokens - cached_prompt_tokens)
        prices = self.model_config
        cost: Optional[float] = None
        if prices.input_price_per_million is not None and prices.output_price_per_million is not None:
            cached_price = (
                prices.cached_input_price_per_million
                if prices.cached_input_price_per_million is not None
                else prices.input_price_per_million
            )
            cost = (
                uncached * prices.input_price_per_million
                + cached_prompt_tokens * cached_price
                + completion_tokens * prices.output_price_per_million
            ) / 1_000_000
        call = LLMCallMetric(
            purpose=purpose,
            model=prices.model,
            duration_seconds=duration_seconds,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
        )
        with self._lock:
            self._llm_calls.append(call)

    def add_event(self, kind: str, name: str, duration_seconds: float, **metadata: Any) -> None:
        with self._lock:
            self._events.append(EventMetric(kind, name, duration_seconds, metadata))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            calls = list(self._llm_calls)
            events = list(self._events)
        known_costs = [item.cost_usd for item in calls if item.cost_usd is not None]
        return {
            "wall_time_seconds": time.time() - self.started_at,
            "llm": {
                "requests": len(calls),
                "prompt_tokens": sum(item.prompt_tokens for item in calls),
                "completion_tokens": sum(item.completion_tokens for item in calls),
                "cached_prompt_tokens": sum(item.cached_prompt_tokens for item in calls),
                "total_tokens": sum(item.total_tokens for item in calls),
                "cost_usd": sum(known_costs) if len(known_costs) == len(calls) else None,
                "cost_note": (
                    None
                    if len(known_costs) == len(calls)
                    else "Price was not configured; token counts are exact but cost is intentionally null."
                ),
                "calls": [asdict(item) for item in calls],
            },
            "events": [asdict(item) for item in events],
            "event_time_by_kind": self._sum_events(events),
        }

    @staticmethod
    def _sum_events(events: List[EventMetric]) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for item in events:
            totals[item.kind] = totals.get(item.kind, 0.0) + item.duration_seconds
        return totals

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")

