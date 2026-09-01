from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelConfig:
    model: str = field(default_factory=lambda: os.getenv("BASELINE_MODEL", ""))
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    temperature: float = 0.0
    timeout_seconds: float = 180.0
    max_retries: int = 2
    input_price_per_million: Optional[float] = None
    cached_input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None

