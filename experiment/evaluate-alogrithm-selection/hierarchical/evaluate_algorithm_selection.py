#!/usr/bin/env python3
"""Evaluate hierarchical task-type and algorithm selection accuracy."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "engine_config.yaml"
DEFAULT_DATASET_PATH = SCRIPT_DIR.parent / "dataset" / "dataset1.json"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "evaluation2.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to engine_config.yaml.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to algorithm_selection_dataset.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to the detailed evaluation result JSON.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of samples to evaluate from the start of the dataset.",
    )
    parser.add_argument(
        "--filter-correct",
        choices=["all", "incorrect", "correct"],
        default="all",
        help="When the dataset has a 'correct' field, choose whether to evaluate all samples, only correct=false, or only correct=true.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when a sample fails.",
    )
    parser.add_argument(
        "--keep-proxy-env",
        action="store_true",
        help="Do not clear HTTP(S)/ALL_PROXY before importing the reasoner stack.",
    )
    return parser.parse_args()


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Dataset at {path} must be a JSON list.")
    return data


def filter_dataset_by_correct(
    dataset: list[dict[str, Any]],
    filter_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "original_total": len(dataset),
        "with_correct_field": sum(1 for item in dataset if "correct" in item),
        "correct_true": sum(1 for item in dataset if item.get("correct") is True),
        "correct_false": sum(1 for item in dataset if item.get("correct") is False),
    }

    if filter_mode == "all":
        return dataset, stats

    filtered: list[dict[str, Any]] = []
    target_value = filter_mode == "correct"
    for item in dataset:
        if item.get("correct") is target_value:
            filtered.append(item)
    return filtered, stats


def diff_usage(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    operation_names = sorted(
        set((before.get("operations") or {}).keys()) | set((after.get("operations") or {}).keys())
    )
    operations: Dict[str, Dict[str, int]] = {}
    for name in operation_names:
        before_stats = (before.get("operations") or {}).get(name, {})
        after_stats = (after.get("operations") or {}).get(name, {})
        operations[name] = {
            "requests": int(after_stats.get("requests", 0)) - int(before_stats.get("requests", 0)),
            "prompt_tokens": int(after_stats.get("prompt_tokens", 0)) - int(before_stats.get("prompt_tokens", 0)),
            "completion_tokens": int(after_stats.get("completion_tokens", 0)) - int(before_stats.get("completion_tokens", 0)),
            "total_tokens": int(after_stats.get("total_tokens", 0)) - int(before_stats.get("total_tokens", 0)),
        }
    return {
        "requests": int(after.get("requests", 0)) - int(before.get("requests", 0)),
        "prompt_tokens": int(after.get("prompt_tokens", 0)) - int(before.get("prompt_tokens", 0)),
        "completion_tokens": int(after.get("completion_tokens", 0)) - int(before.get("completion_tokens", 0)),
        "total_tokens": int(after.get("total_tokens", 0)) - int(before.get("total_tokens", 0)),
        "operations": operations,
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total_samples = len(results)
    task_type_correct = sum(1 for item in results if item["task_type_correct"])
    algorithm_correct = sum(1 for item in results if item["algorithm_correct"])
    failed_samples = sum(1 for item in results if item.get("error"))

    total_requests = sum(item["token_usage"]["requests"] for item in results)
    total_prompt_tokens = sum(item["token_usage"]["prompt_tokens"] for item in results)
    total_completion_tokens = sum(item["token_usage"]["completion_tokens"] for item in results)
    total_tokens = sum(item["token_usage"]["total_tokens"] for item in results)

    return {
        "total_samples": total_samples,
        "task_type_correct": task_type_correct,
        "task_type_accuracy": (task_type_correct / total_samples) if total_samples else 0.0,
        "algorithm_correct": algorithm_correct,
        "algorithm_accuracy": (algorithm_correct / total_samples) if total_samples else 0.0,
        "failed_samples": failed_samples,
        "token_usage": {
            "requests": total_requests,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        },
    }


def print_summary(summary: dict[str, Any], output_path: Path, dataset_stats: dict[str, int]) -> None:
    print(
        "Dataset stats: "
        f"original_total={dataset_stats['original_total']}, "
        f"with_correct_field={dataset_stats['with_correct_field']}, "
        f"correct_true={dataset_stats['correct_true']}, "
        f"correct_false={dataset_stats['correct_false']}"
    )
    print(f"Total samples: {summary['total_samples']}")
    print(
        "Task type accuracy: "
        f"{summary['task_type_correct']}/{summary['total_samples']} "
        f"({summary['task_type_accuracy']:.4f})"
    )
    print(
        "Algorithm accuracy: "
        f"{summary['algorithm_correct']}/{summary['total_samples']} "
        f"({summary['algorithm_accuracy']:.4f})"
    )
    print(f"Failed samples: {summary['failed_samples']}")
    print(
        "Token usage: "
        f"requests={summary['token_usage']['requests']}, "
        f"prompt_tokens={summary['token_usage']['prompt_tokens']}, "
        f"completion_tokens={summary['token_usage']['completion_tokens']}, "
        f"total_tokens={summary['token_usage']['total_tokens']}"
    )
    print(f"Detailed results saved to: {output_path}")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    if not args.keep_proxy_env:
        for key in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
            os.environ.pop(key, None)

    try:
        from aag.config.engine_config import load_config_from_yaml
        from aag.engine.scheduler import select_algorithm_for_question
        from aag.expert_search_engine.search import ExpertSearchEngine
        from aag.reasoner.model_deployment import Reasoner
    except ModuleNotFoundError as exc:
        missing_name = exc.name or "unknown module"
        if missing_name == "aag":
            raise SystemExit(
                "Cannot import local project package 'aag'. "
                f"Expected project root at {PROJECT_ROOT}. "
                "Run this script from the YiGraph-dev checkout or set PYTHONPATH to the project root."
            ) from exc
        raise SystemExit(
            f"Missing Python dependency: {missing_name}. "
            "Install the project dependencies first, for example: pip install pyyaml openai llama-index"
        ) from exc

    config = load_config_from_yaml(str(args.config))
    reasoner = Reasoner(config.reasoner)
    expert_search_engine = ExpertSearchEngine(config.retrieval)

    dataset = load_dataset(args.dataset)
    dataset, dataset_stats = filter_dataset_by_correct(dataset, args.filter_correct)
    if args.limit is not None:
        dataset = dataset[: max(0, args.limit)]

    logging.info(
        "Loaded dataset=%s | filter_correct=%s | evaluated_samples=%s/%s",
        args.dataset.resolve(),
        args.filter_correct,
        len(dataset),
        dataset_stats["original_total"],
    )

    reasoner.reset_usage()
    results: list[dict[str, Any]] = []

    for index, sample in enumerate(dataset, start=1):
        question = sample["question"]
        logging.info("Evaluating sample %s/%s", index, len(dataset))

        before_usage = reasoner.get_usage_summary()
        selection_result: dict[str, Any] = {}
        error_message = None

        try:
            selection_result = select_algorithm_for_question(
                question=question,
                reasoner=reasoner,
                expert_search_engine=expert_search_engine,
            )
        except Exception as exc:
            error_message = str(exc)
            logging.exception("Sample %s failed", index)
            if args.fail_fast:
                raise
        finally:
            after_usage = reasoner.get_usage_summary()

        sample_usage = diff_usage(before_usage, after_usage)
        predicted_task_type = selection_result.get("selected_task_type_name")
        predicted_algorithm = selection_result.get("selected_algorithm_id")

        result_item = {
            "id": sample.get("id"),
            "question": question,
            "domain": sample.get("domain"),
            "role": sample.get("role"),
            "previous_correct": sample.get("correct"),
            "gold_task_type": sample.get("task_type"),
            "predicted_task_type": predicted_task_type,
            "gold_algorithm": sample.get("algorithm"),
            "predicted_algorithm": predicted_algorithm,
            "task_type_correct": predicted_task_type == sample.get("task_type"),
            "algorithm_correct": predicted_algorithm == sample.get("algorithm"),
            "question_type": selection_result.get("question_type"),
            "question_classification": selection_result.get("question_classification"),
            "selected_task_type_id": selection_result.get("selected_task_type_id"),
            "token_usage": sample_usage,
            "error": error_message,
        }
        results.append(result_item)

    summary = build_summary(results)
    output_payload = {
        "config_path": str(args.config.resolve()),
        "dataset_path": str(args.dataset.resolve()),
        "filter_correct": args.filter_correct,
        "dataset_stats": dataset_stats,
        "summary": summary,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(output_payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print_summary(summary, args.output.resolve(), dataset_stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
