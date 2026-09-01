from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Iterable, Optional

from openai import OpenAI

from .config import ModelConfig
from .metrics import MetricsCollector


class OpenAICompatibleLLM:
    """Small provider-neutral adapter with exact response usage accounting."""

    def __init__(self, config: ModelConfig, metrics: MetricsCollector) -> None:
        if not config.model:
            raise ValueError("A model is required. Set --model or BASELINE_MODEL.")
        if not config.api_key:
            raise ValueError("An API key is required. Set --api-key or OPENAI_API_KEY.")
        self.config = config
        self.metrics = metrics
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    def json(self, purpose: str, system: str, user: str) -> Dict[str, Any]:
        text = self.complete(purpose, system, user, json_mode=True)
        return parse_json_object(text)

    def complete(self, purpose: str, system: str, user: str, json_mode: bool = False) -> str:
        started = time.perf_counter()
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        duration = time.perf_counter() - started
        usage = getattr(response, "usage", None)
        prompt_tokens = int(
            getattr(usage, "prompt_tokens", None)
            or getattr(usage, "input_tokens", None)
            or 0
        )
        completion_tokens = int(
            getattr(usage, "completion_tokens", None)
            or getattr(usage, "output_tokens", None)
            or 0
        )
        details = getattr(usage, "prompt_tokens_details", None) or getattr(
            usage, "input_tokens_details", None
        )
        cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
        self.metrics.add_llm_call(
            purpose,
            duration,
            prompt_tokens,
            completion_tokens,
            cached_tokens,
        )
        return str(response.choices[0].message.content or "").strip()


def parse_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise ValueError(f"LLM response does not contain a JSON object: {text[:500]}")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object, got {type(value).__name__}")
    return value


def preview(value: Any, max_chars: int = 6000) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except Exception:
        rendered = repr(value)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[:max_chars] + f"\n... <truncated {len(rendered) - max_chars} chars>"

