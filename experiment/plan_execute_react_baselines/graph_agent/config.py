from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTION_FILE = Path(
    os.getenv("BASELINE_QUESTION_FILE", str(PACKAGE_ROOT.parent / "questions_75.jsonl"))
)
DEFAULT_KNOWLEDGE_BASE = Path(
    os.getenv("BASELINE_KNOWLEDGE_BASE", str(PACKAGE_ROOT / "knowledge_base"))
)
DEFAULT_EXTERNAL_DATASETS = Path(
    os.getenv("BASELINE_DATASETS_ROOT", str(PACKAGE_ROOT / "datasets"))
)


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    data_dir: Path
    schema_path: Path


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


@dataclass
class RunConfig:
    model: ModelConfig
    output_dir: Path
    knowledge_base_dir: Path = DEFAULT_KNOWLEDGE_BASE
    retrieval_top_k: int = 12
    max_plan_rounds: int = 4
    max_react_steps: int = 16
    max_codegen_retries: int = 2
    max_parallel_tasks: int = 4
    edge_chunksize: int = 250_000
    graph_cache_dir: Optional[Path] = None


def dataset_configs(root: Path = DEFAULT_EXTERNAL_DATASETS) -> Dict[str, DatasetConfig]:
    return {
        "AMLSim1M": DatasetConfig(
            name="AMLSim1M",
            data_dir=root / "data" / "AMLSim1M",
            schema_path=root / "dataset_schemas" / "AMLSim1M" / "graph_schemas.yaml",
        ),
        "Twitter_SignedGraphs": DatasetConfig(
            name="Twitter_SignedGraphs",
            data_dir=root / "data" / "Twitter_SignedGraphs",
            schema_path=root
            / "dataset_schemas"
            / "Twitter_SignedGraphs"
            / "graph_schemas.yaml",
        ),
        "ogbn_proteins": DatasetConfig(
            name="ogbn_proteins",
            data_dir=root / "data" / "ogbn_proteins",
            schema_path=root
            / "dataset_schemas"
            / "ogbn_proteins"
            / "graph_schemas.yaml",
        ),
    }


def dataset_for_domain(domain: str, root: Path = DEFAULT_EXTERNAL_DATASETS) -> DatasetConfig:
    dataset_names = {
        "finance": "AMLSim1M",
        "social": "Twitter_SignedGraphs",
        "protein": "ogbn_proteins",
    }
    normalized = str(domain).strip().lower()
    try:
        name = dataset_names[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(dataset_names))
        raise ValueError(f"Unsupported question domain {domain!r}; expected one of: {supported}") from exc
    return dataset_configs(root)[name]
