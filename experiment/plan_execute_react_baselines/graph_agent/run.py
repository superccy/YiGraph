from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .config import (
    DEFAULT_EXTERNAL_DATASETS,
    DEFAULT_KNOWLEDGE_BASE,
    DEFAULT_QUESTION_FILE,
    ModelConfig,
    RunConfig,
    dataset_for_domain,
)
from .datasets import GraphWorkspace
from .metrics import MetricsCollector
from .retrieval import FlatDocumentationRetriever
from .workflows import build_compiler_graph, build_react_graph, create_services


def load_questions(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Question file not found: {path}")

    questions: Dict[str, Dict[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Question line {line_number} must contain a JSON object")
            question_id = str(payload.get("question_id") or "").strip()
            question = str(payload.get("question") or "").strip()
            domain = str(payload.get("domain") or "").strip().lower()
            if not question_id or not question or not domain:
                raise ValueError(
                    f"Question line {line_number} requires non-empty question_id, question, and domain"
                )
            if question_id in questions:
                raise ValueError(f"Duplicate question_id {question_id!r} on line {line_number}")
            questions[question_id] = {
                "question_id": question_id,
                "question": question,
                "domain": domain,
            }
    if not questions:
        raise ValueError(f"No JSONL questions found in {path}")
    return questions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run comparable LangGraph LLMCompiler and ReAct graph-analysis baselines."
    )
    parser.add_argument("--baseline", choices=["compiler", "react", "both"], default="both")
    selection = parser.add_mutually_exclusive_group(required=False)
    selection.add_argument("--question-id", action="append", dest="question_ids")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--question-file", type=Path, default=DEFAULT_QUESTION_FILE)
    parser.add_argument("--datasets-root", type=Path, default=DEFAULT_EXTERNAL_DATASETS)
    parser.add_argument("--knowledge-base", type=Path, default=DEFAULT_KNOWLEDGE_BASE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "runs",
    )
    parser.add_argument("--model", default=os.getenv("BASELINE_MODEL", ""))
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--input-price-per-million", type=float)
    parser.add_argument("--cached-input-price-per-million", type=float)
    parser.add_argument("--output-price-per-million", type=float)
    parser.add_argument("--retrieval-top-k", type=int, default=12)
    parser.add_argument("--max-plan-rounds", type=int, default=4)
    parser.add_argument("--max-react-steps", type=int, default=16)
    parser.add_argument("--max-codegen-retries", type=int, default=2)
    parser.add_argument("--max-parallel-tasks", type=int, default=4)
    parser.add_argument("--edge-chunksize", type=int, default=250_000)
    parser.add_argument("--graph-cache-dir", type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate questions, schemas, paths, and flat documentation without calling a model or loading a full graph.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    questions = load_questions(args.question_file)
    question_ids = list(questions) if args.all else (args.question_ids or [next(iter(questions))])
    missing = [item for item in question_ids if item not in questions]
    if missing:
        raise ValueError(f"Question IDs not found: {missing}")

    if args.validate_only:
        report = validate_inputs(args, question_ids, questions)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if not args.model or not args.api_key:
        raise ValueError(
            "Model API is not configured. Provide --model and --api-key (or BASELINE_MODEL and OPENAI_API_KEY). "
            "Use --validate-only before API credentials are available."
        )

    baselines = ["compiler", "react"] if args.baseline == "both" else [args.baseline]
    failures = 0
    for question_id in question_ids:
        for baseline in baselines:
            try:
                run_one(args, baseline, questions[question_id])
            except Exception as exc:
                failures += 1
                print(f"[{baseline} q{question_id}] failed: {exc}", file=sys.stderr)
    return 1 if failures else 0


def validate_inputs(
    args: argparse.Namespace,
    question_ids: Iterable[str],
    questions: Dict[str, Dict[str, str]],
) -> Dict[str, Any]:
    retriever = FlatDocumentationRetriever(args.knowledge_base)
    model_config = ModelConfig(model=args.model or "validation-only", api_key=args.api_key)
    items = []
    for question_id in question_ids:
        record = questions[question_id]
        metrics = MetricsCollector(model_config)
        dataset = dataset_for_domain(record["domain"], args.datasets_root)
        workspace = GraphWorkspace(dataset, metrics, args.edge_chunksize, args.graph_cache_dir)
        retrieved = retriever.retrieve(record["question"], args.retrieval_top_k)
        items.append(
            {
                "question_id": question_id,
                "domain": record["domain"],
                "dataset": workspace.describe(),
                "retrieved_algorithms": [item.algorithm_id for item in retrieved],
            }
        )
    return {
        "valid": True,
        "question_file": str(args.question_file),
        "knowledge_base": str(args.knowledge_base),
        "algorithm_count": len(retriever.algorithm_ids),
        "items": items,
    }


def run_one(args: argparse.Namespace, baseline: str, record: Dict[str, str]) -> Path:
    question_id = record["question_id"]
    question = record["question"]
    domain = record["domain"]
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    safe_question_id = re.sub(r"[^A-Za-z0-9._-]+", "_", question_id).strip("._-")
    if not safe_question_id:
        raise ValueError(f"question_id cannot be used as an output path: {question_id!r}")
    run_dir = args.output_dir / safe_question_id / baseline / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    model = ModelConfig(
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        temperature=args.temperature,
        input_price_per_million=args.input_price_per_million,
        cached_input_price_per_million=args.cached_input_price_per_million,
        output_price_per_million=args.output_price_per_million,
    )
    config = RunConfig(
        model=model,
        output_dir=run_dir,
        knowledge_base_dir=args.knowledge_base,
        retrieval_top_k=args.retrieval_top_k,
        max_plan_rounds=args.max_plan_rounds,
        max_react_steps=args.max_react_steps,
        max_codegen_retries=args.max_codegen_retries,
        max_parallel_tasks=args.max_parallel_tasks,
        edge_chunksize=args.edge_chunksize,
        graph_cache_dir=args.graph_cache_dir,
    )
    metrics = MetricsCollector(model)
    dataset = dataset_for_domain(domain, args.datasets_root)
    workspace = GraphWorkspace(dataset, metrics, args.edge_chunksize, args.graph_cache_dir)
    services = create_services(config, workspace)
    graph = build_compiler_graph(services) if baseline == "compiler" else build_react_graph(services)
    state: Dict[str, Any]
    try:
        recursion_limit = max(
            50,
            2 * config.max_react_steps + 10,
            3 * config.max_plan_rounds + 10,
        )
        state = graph.invoke(
            {"question": question}, config={"recursion_limit": recursion_limit}
        )
        result = {
            "question_id": question_id,
            "question": question,
            "domain": domain,
            "baseline": baseline,
            "dataset": dataset.name,
            "answer": state.get("final_answer"),
            "outcomes": [outcome.to_dict(include_result=False) for outcome in state.get("outcomes", [])],
            "metrics": metrics.snapshot(),
            "config": _public_config(config),
        }
        (run_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        (run_dir / "answer.md").write_text(str(state.get("final_answer") or ""), encoding="utf-8")
        print(f"[{baseline} q{question_id}] {run_dir}")
        return run_dir
    except Exception as exc:
        (run_dir / "error.json").write_text(
            json.dumps(
                {
                    "question_id": question_id,
                    "domain": domain,
                    "baseline": baseline,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        raise
    finally:
        metrics.write(run_dir / "metrics.json")


def _public_config(config: RunConfig) -> Dict[str, Any]:
    payload = asdict(config)
    payload["model"].pop("api_key", None)
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
