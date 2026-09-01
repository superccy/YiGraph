#!/usr/bin/env python3
"""Evaluate dependency resolution on the synthetic dependency dataset."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from aag.models.task_types import GraphAnalysisSubType, GraphAnalysisType


DEFAULT_DATASET_PATH = Path(__file__).resolve().with_name("dependency_resolution_dataset_100_llm.json")
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "engine_config.yaml"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().with_name("report.json")


@dataclass
class LocalOutputField:
    type: str
    field_description: str | None = None


@dataclass
class LocalOutputSchema:
    description: str | None
    type: str
    fields: Dict[str, LocalOutputField]


@dataclass
class LocalStepOutputItem:
    output_id: int
    task_type: GraphAnalysisSubType
    source: str
    output_schema: LocalOutputSchema | None = None
    value: Dict[str, Any] | None = None

    def to_meta(self) -> dict:
        meta = {"output_id": self.output_id, "source": self.source}
        if self.output_schema:
            meta["type"] = self.output_schema.type
            meta["description"] = self.output_schema.description
            meta["fields"] = [
                {
                    "key": key,
                    "type": field.type,
                    "desc": field.field_description,
                }
                for key, field in self.output_schema.fields.items()
            ]
        return meta


class LocalWorkflowStep:
    def __init__(self, step_id: int, question: str, task_type: GraphAnalysisType, graph_algorithm: str | None = None):
        self.step_id = step_id
        self.question = question
        self.task_type = task_type
        self.graph_algorithm = graph_algorithm
        self.status = "pending"
        self.result: Dict[int, LocalStepOutputItem] | None = None
        self.error = None
        self.llm_analysis = None
        self.next_output_id = 1

    def add_output(
        self,
        task_type: GraphAnalysisSubType,
        source: str,
        output_schema: LocalOutputSchema | None = None,
        value: Any = None,
    ) -> LocalStepOutputItem:
        if self.result is None:
            self.result = {}
        item = LocalStepOutputItem(
            output_id=self.next_output_id,
            task_type=task_type,
            source=source,
            output_schema=output_schema,
            value=value,
        )
        self.result[self.next_output_id] = item
        self.next_output_id += 1
        return item

    def get_result_meta(self) -> List[dict]:
        if not self.result:
            return []
        return [item.to_meta() for item in self.result.values()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate dependency_resolver on a labeled JSON dataset.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH, help="Path to dependency dataset JSON")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Engine config YAML path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Where to write the evaluation report JSON")
    parser.add_argument("--max-samples", type=int, default=None, help="Evaluate only the first N samples")
    parser.add_argument("--sample-ids", nargs="*", help="Evaluate only specific sample ids, e.g. dep_001 dep_002")
    parser.add_argument("--dry-run", action="store_true", help="Validate dataset reconstruction only; do not call the LLM")
    parser.add_argument("--verbose-errors", action="store_true", help="Print detailed mismatch examples to stdout")
    parser.add_argument("--keep-proxy-env", action="store_true", help="Do not clear HTTP(S)/ALL_PROXY before importing the reasoner stack")
    return parser.parse_args()


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_output_schema(raw: Dict[str, Any] | None) -> OutputSchema | None:
    if not raw:
        return None
    fields = {
        name: LocalOutputField(
            type=info.get("type", "unknown"),
            field_description=info.get("field_description"),
        )
        for name, info in raw.get("fields", {}).items()
    }
    return LocalOutputSchema(
        description=raw.get("description"),
        type=raw.get("type", "dict"),
        fields=fields,
    )


def to_graph_analysis_type(raw: str | None) -> GraphAnalysisType:
    if raw == GraphAnalysisType.NUMERIC_ANALYSIS.value:
        return GraphAnalysisType.NUMERIC_ANALYSIS
    if raw == GraphAnalysisType.GRAPH_QUERY.value:
        return GraphAnalysisType.GRAPH_QUERY
    return GraphAnalysisType.GRAPH_ALGORITHM


def to_graph_analysis_subtype(raw: str | None) -> GraphAnalysisSubType:
    if raw == GraphAnalysisSubType.POST_PROCESSING.value:
        return GraphAnalysisSubType.POST_PROCESSING
    if raw == GraphAnalysisSubType.LLM_REASONING.value:
        return GraphAnalysisSubType.LLM_REASONING
    if raw == GraphAnalysisSubType.NUMERIC_COMPUTATION.value:
        return GraphAnalysisSubType.NUMERIC_COMPUTATION
    if raw == GraphAnalysisSubType.SUBGRAPH_EXTRACTION.value:
        return GraphAnalysisSubType.SUBGRAPH_EXTRACTION
    return GraphAnalysisSubType.GRAPH_ALGORITHM


def build_workflow_step(raw_step: Dict[str, Any]) -> WorkflowStep:
    step = LocalWorkflowStep(
        step_id=int(raw_step["step_id"]),
        question=raw_step["question"],
        task_type=to_graph_analysis_type(raw_step.get("task_type")),
        graph_algorithm=raw_step.get("graph_algorithm"),
    )
    for output in raw_step.get("outputs", []):
        step.add_output(
            task_type=to_graph_analysis_subtype(output.get("task_subtype")),
            source=output.get("source", ""),
            output_schema=build_output_schema(output.get("output_schema")),
            value=output.get("value"),
        )
    return step


def normalize_dep_tuple(dep_type: str, parent_step_id: int, output_id: int, field_key: str) -> Tuple[str, int, int, str]:
    return (dep_type, int(parent_step_id), int(output_id), field_key)


def gold_dep_set(sample: Dict[str, Any]) -> set[Tuple[str, int, int, str]]:
    items = set()
    for dep in sample["gold"]["graph_dependencies"]:
        items.add(normalize_dep_tuple("graph", dep["parent_step_id"], dep["parent_step_output_id"], dep["field_key"]))
    for dep in sample["gold"]["parameter_dependencies"]:
        items.add(normalize_dep_tuple("parameter", dep["parent_step_id"], dep["parent_step_output_id"], dep["field_key"]))
    return items


def pred_dep_set(result: Dict[str, Any]) -> set[Tuple[str, int, int, str]]:
    items = set()
    for dep in result.get("graph_dependencies", []):
        items.add(normalize_dep_tuple("graph", dep.parent_step_id, dep.parent_step_output_id, dep.field_key))
    for dep in result.get("parameter_dependencies", []):
        items.add(normalize_dep_tuple("parameter", dep.parent_step_id, dep.parent_step_output_id, dep.field_key))
    return items


def pred_type_counts(result: Dict[str, Any]) -> Tuple[int, int]:
    return (
        len(result.get("graph_dependencies", [])),
        len(result.get("parameter_dependencies", [])),
    )


def gold_type_counts(sample: Dict[str, Any]) -> Tuple[int, int]:
    return (
        len(sample["gold"]["graph_dependencies"]),
        len(sample["gold"]["parameter_dependencies"]),
    )


def calc_prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def select_samples(samples: List[Dict[str, Any]], max_samples: int | None, sample_ids: Iterable[str] | None) -> List[Dict[str, Any]]:
    chosen = samples
    if sample_ids:
        wanted = set(sample_ids)
        chosen = [sample for sample in samples if sample["id"] in wanted]
    if max_samples is not None:
        chosen = chosen[:max_samples]
    return chosen


async def evaluate_sample(sample: Dict[str, Any], resolver: EvalDepRendencyResolver) -> Dict[str, Any]:
    steps = [build_workflow_step(raw) for raw in sample["steps"]]
    step_map = {step.step_id: step for step in steps}
    target_step = step_map[int(sample["target_step_id"])]
    raw_target = next(raw for raw in sample["steps"] if int(raw["step_id"]) == int(sample["target_step_id"]))
    parents = [step_map[int(pid)] for pid in sample["data_dependency_parent_ids"]]
    result = await resolver.resolve_dependencies(
        step_id=str(target_step.step_id),
        step=target_step,
        alg_des_info=raw_target.get("tool_metadata"),
        data_dependency_parents=parents,
    )
    gold_items = gold_dep_set(sample)
    pred_items = pred_dep_set(result)
    tp_items = gold_items & pred_items
    fp_items = pred_items - gold_items
    fn_items = gold_items - pred_items
    gold_counts = gold_type_counts(sample)
    pred_counts = pred_type_counts(result)
    return {
        "sample_id": sample["id"],
        "structure": sample["structure"],
        "gold_counts": {"graph": gold_counts[0], "parameter": gold_counts[1]},
        "pred_counts": {"graph": pred_counts[0], "parameter": pred_counts[1]},
        "gold_items": sorted(gold_items),
        "pred_items": sorted(pred_items),
        "tp_items": sorted(tp_items),
        "fp_items": sorted(fp_items),
        "fn_items": sorted(fn_items),
        "count_match": gold_counts == pred_counts,
        "exact_match": gold_items == pred_items,
    }


async def run_evaluation(samples: List[Dict[str, Any]], resolver: EvalDependencyResolver, verbose_errors: bool) -> Dict[str, Any]:
    sample_results: List[Dict[str, Any]] = []
    per_structure = defaultdict(lambda: {"samples": 0, "tp": 0, "fp": 0, "fn": 0, "count_match": 0, "exact_match": 0})

    total_tp = total_fp = total_fn = 0
    count_match = exact_match = 0

    for idx, sample in enumerate(samples, start=1):
        result = await evaluate_sample(sample, resolver)
        sample_results.append(result)
        tp = len(result["tp_items"])
        fp = len(result["fp_items"])
        fn = len(result["fn_items"])
        total_tp += tp
        total_fp += fp
        total_fn += fn
        count_match += int(result["count_match"])
        exact_match += int(result["exact_match"])

        stats = per_structure[result["structure"]]
        stats["samples"] += 1
        stats["tp"] += tp
        stats["fp"] += fp
        stats["fn"] += fn
        stats["count_match"] += int(result["count_match"])
        stats["exact_match"] += int(result["exact_match"])

        if verbose_errors and not result["exact_match"]:
            print(f"[Mismatch] {result['sample_id']} | {result['structure']}")
            print(f"  gold={result['gold_items']}")
            print(f"  pred={result['pred_items']}")

        if idx % 10 == 0:
            print(f"Processed {idx}/{len(samples)} samples")

    overall = calc_prf(total_tp, total_fp, total_fn)
    overall["accuracy"] = round(count_match / len(samples), 6) if samples else 0.0
    overall["exact_match"] = round(exact_match / len(samples), 6) if samples else 0.0
    overall["samples"] = len(samples)
    overall["tp"] = total_tp
    overall["fp"] = total_fp
    overall["fn"] = total_fn

    per_structure_report = {}
    for structure, stats in per_structure.items():
        report = calc_prf(stats["tp"], stats["fp"], stats["fn"])
        report["accuracy"] = round(stats["count_match"] / stats["samples"], 6) if stats["samples"] else 0.0
        report["exact_match"] = round(stats["exact_match"] / stats["samples"], 6) if stats["samples"] else 0.0
        report["samples"] = stats["samples"]
        report["tp"] = stats["tp"]
        report["fp"] = stats["fp"]
        report["fn"] = stats["fn"]
        per_structure_report[structure] = report

    return {
        "overall": overall,
        "per_structure": per_structure_report,
        "mismatch_samples": [item for item in sample_results if not item["exact_match"]],
        "all_samples": sample_results,
    }


def print_summary(report: Dict[str, Any]) -> None:
    overall = report["overall"]
    print("\n=== Overall ===")
    print(json.dumps(overall, ensure_ascii=False, indent=2))
    print("\n=== Per Structure ===")
    for structure, stats in report["per_structure"].items():
        print(f"{structure}: {json.dumps(stats, ensure_ascii=False)}")


async def async_main(args: argparse.Namespace) -> int:
    samples = load_dataset(args.dataset)
    samples = select_samples(samples, args.max_samples, args.sample_ids)
    if not samples:
        raise ValueError("No samples selected")

    if args.dry_run:
        rebuilt = [build_workflow_step(step) for sample in samples for step in sample["steps"]]
        print(f"Dry run OK: rebuilt {len(rebuilt)} workflow steps from {len(samples)} samples")
        return 0

    if not args.keep_proxy_env:
        for key in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
            os.environ.pop(key, None)

    from aag.config.engine_config import load_config_from_yaml
    from aag.engine.dependency_resolver import DataDependencyResolver
    from aag.reasoner.model_deployment import Reasoner

    class EvalDependencyResolver(DataDependencyResolver):
        """Run dependency classification only; skip adapter generation."""

        async def _convert_graph_dependencies(self, current_question: str, graph_items, parent_steps):
            return {"converted_graph": None}

        async def _convert_parameter_dependencies(self, current_question: str, alg_des_doc: str, param_items, parent_steps):
            return {"mapped_params": None}

    config = load_config_from_yaml(str(args.config))
    reasoner = Reasoner(config.reasoner)
    resolver = EvalDependencyResolver(reasoner)
    report = await run_evaluation(samples, resolver, args.verbose_errors)
    print_summary(report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nSaved report to: {args.output}")
    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
