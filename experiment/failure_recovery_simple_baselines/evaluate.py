#!/usr/bin/env python3
"""Evaluate the three deterministic baselines with node-level micro-F1."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List

from baselines import (
    build_trace_graph,
    failed_node_localization,
    hierarchical_backtracking,
    rule_based_dependency_tracking,
)


def read_json(path: Path):
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_jsonl(path: Path):
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def micro_metrics(rows: Iterable[Dict]) -> Dict[str, float]:
    tp = fp = tn = fn = 0
    row_list = list(rows)
    for row in row_list:
        truth = set(row["truth"])
        predicted = set(row["predicted_steps"])
        universe = set(row["candidate_steps"])
        tp += len(truth & predicted)
        fp += len(predicted - truth)
        fn += len(truth - predicted)
        tn += len(universe - truth - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "mean_predicted_steps": (
            sum(len(row["predicted_steps"]) for row in row_list) / len(row_list)
            if row_list
            else 0.0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--evaluation-manifest",
        type=Path,
        required=True,
        help="JSONL with trace_id, truth, and candidate_steps",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    manifest = {
        str(row["trace_id"]): row for row in read_jsonl(args.evaluation_manifest)
    }
    methods: Dict[str, List[Dict]] = {
        "Failed-Node Localization": [],
        "Rule-based Dependency Tracking": [],
        "Hierarchical Backtracking": [],
    }

    for trace_id in sorted(manifest, key=int):
        item = manifest[trace_id]
        truth = sorted(int(step) for step in item["truth"])
        candidates = set(int(step) for step in item["candidate_steps"])
        trace = read_json(args.dataset / "data" / f"{trace_id}.json")
        graph = build_trace_graph(trace)
        failed = failed_node_localization(graph, candidates)
        rule, rule_evidence = rule_based_dependency_tracking(
            graph, candidates, failed
        )
        heuristic, heuristic_evidence = hierarchical_backtracking(
            graph, candidates, failed
        )
        predictions = {
            "Failed-Node Localization": (failed, {}),
            "Rule-based Dependency Tracking": (rule, rule_evidence),
            "Hierarchical Backtracking": (heuristic, heuristic_evidence),
        }
        for method, (predicted, evidence) in predictions.items():
            methods[method].append(
                {
                    "trace_id": trace_id,
                    "truth": truth,
                    "predicted_steps": sorted(predicted),
                    "candidate_steps": sorted(candidates),
                    "evidence": evidence,
                }
            )

    summary = []
    for method, rows in methods.items():
        summary.append({"method": method, **micro_metrics(rows)})
        filename = method.lower().replace(" ", "_").replace("-", "_")
        with (args.output / f"predictions_{filename}.jsonl").open(
            "w", encoding="utf-8"
        ) as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    (args.output / "metrics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (args.output / "metrics_summary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

