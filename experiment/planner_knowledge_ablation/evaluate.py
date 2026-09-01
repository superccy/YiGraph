#!/usr/bin/env python3
"""Evaluate planner/knowledge variants on the single-task algorithm-selection set.

This evaluator deliberately stops after selection: it does not load a graph, generate
code, or invoke NetworkX.  Every completed sample is appended to JSONL so expensive
API runs can be resumed without repeating earlier requests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import ModelConfig
from core.llm import OpenAICompatibleLLM
from core.metrics import MetricsCollector
from core.retrieval import FlatDocumentationRetriever


SYSTEM = """You are an expert graph-analysis algorithm selector.
Select exactly one task type and one algorithm from the supplied knowledge base.
Use the user's intent, not superficial domain words. Never invent an identifier.
Return one JSON object only, with no Markdown or commentary."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge", choices=("flat", "hierarchical"), required=True)
    parser.add_argument("--planner", choices=("react", "llmcompiler"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="External labelled JSON dataset; no dataset is bundled with this experiment.",
    )
    parser.add_argument("--knowledge-base", type=Path, default=PROJECT_ROOT / "aag" / "knowledge_base")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--flat-mode", choices=("retrieve", "direct"), default="retrieve")
    parser.add_argument("--direct-doc-max-chars", type=int, default=900)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--max-react-steps", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-retries", type=int, default=2)
    return parser.parse_args()


def canonical(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def compact_algorithm(item: Mapping[str, Any], max_chars: int = 2200) -> str:
    principles = item.get("Principles") or {}
    if isinstance(principles, Mapping):
        principles = principles.get("description") or principles
    questions = item.get("solvable_questions") or []
    payload = {
        "algorithm": item.get("id"),
        "task_type": item.get("task_type_id"),
        "principles": principles,
        "application_scenario": item.get("Application_scenario"),
        "solvable_questions": list(questions)[:10] if isinstance(questions, list) else questions,
    }
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).strip()
    return rendered if len(rendered) <= max_chars else rendered[:max_chars] + "\n..."


class Knowledge:
    def __init__(self, root: Path) -> None:
        self.root = root
        task_payload = yaml.safe_load((root / "task_types.yaml").read_text(encoding="utf-8")) or []
        algorithm_payload = yaml.safe_load((root / "algorithms.yaml").read_text(encoding="utf-8")) or []
        self.tasks: List[Dict[str, Any]] = [dict(x) for x in task_payload if isinstance(x, Mapping)]
        self.algorithms: List[Dict[str, Any]] = [dict(x) for x in algorithm_payload if isinstance(x, Mapping)]
        self.task_by_norm = {canonical(x.get("id")): str(x.get("id")) for x in self.tasks}
        self.algorithm_by_norm = {canonical(x.get("id")): str(x.get("id")) for x in self.algorithms}
        self.algorithm_items = {str(x.get("id")): x for x in self.algorithms}
        self.algorithms_by_task: Dict[str, List[Dict[str, Any]]] = {}
        for item in self.algorithms:
            self.algorithms_by_task.setdefault(str(item.get("task_type_id")), []).append(item)
        self.flat: Optional[FlatDocumentationRetriever] = None

    def normalize_task(self, value: Any) -> str:
        return self.task_by_norm.get(canonical(value), str(value or "").strip())

    def normalize_algorithm(self, value: Any) -> str:
        return self.algorithm_by_norm.get(canonical(value), str(value or "").strip())

    def valid_task(self, value: str) -> bool:
        return canonical(value) in self.task_by_norm

    def valid_algorithm(self, value: str) -> bool:
        return canonical(value) in self.algorithm_by_norm

    def task_catalog(self) -> str:
        rows = []
        for task in self.tasks:
            rows.append(
                f"- task_type: {task.get('id')}\n"
                f"  description: {task.get('description', '')}"
            )
        return "\n".join(rows)

    def algorithm_catalog(self, task_type: str) -> str:
        return "\n---\n".join(compact_algorithm(x) for x in self.algorithms_by_task.get(task_type, []))

    def flat_catalog(self, query: str, top_k: int) -> Tuple[str, List[str]]:
        if self.flat is None:
            self.flat = FlatDocumentationRetriever(self.root)
        docs = self.flat.retrieve(query, top_k=top_k)
        items = [self.algorithm_items[d.algorithm_id] for d in docs]
        return "\n---\n".join(compact_algorithm(x) for x in items), [d.algorithm_id for d in docs]

    def direct_flat_catalog(self, max_chars: int) -> str:
        """Serialize every algorithm as one flat, non-retrieved documentation context."""
        return "\n---\n".join(compact_algorithm(x, max_chars=max_chars) for x in self.algorithms)


def call_json(llm: OpenAICompatibleLLM, purpose: str, system: str, prompt: str) -> Dict[str, Any]:
    return llm.json(purpose, system, prompt)


def explicit_flat(
    llm: OpenAICompatibleLLM,
    kb: Knowledge,
    question: str,
    top_k: int,
    flat_mode: str = "retrieve",
    direct_doc_max_chars: int = 900,
) -> Tuple[str, str, Dict[str, Any]]:
    if flat_mode == "direct":
        docs = kb.direct_flat_catalog(direct_doc_max_chars)
        ids = list(kb.algorithm_items)
        source_description = "Complete flat documentation (no retrieval was performed)"
        purpose = "explicit_flat_direct_select"
    else:
        docs, ids = kb.flat_catalog(question, top_k)
        source_description = "Flat retrieved documents"
        purpose = "explicit_flat_select"
    prompt = f"""The fixed plan is: (1) inspect the supplied flat documents; (2) bind the
question to one documented task type and algorithm; (3) return the selection.

Question:
{question}

{source_description}:
{docs}

Return exactly: {{"task_type":"...","algorithm":"..."}}"""
    out = call_json(llm, purpose, SYSTEM, prompt)
    return kb.normalize_task(out.get("task_type")), kb.normalize_algorithm(out.get("algorithm")), {
        "candidate_algorithms": ids,
        "flat_mode": flat_mode,
        "raw": out,
    }


def react_flat_direct(
    llm: OpenAICompatibleLLM,
    kb: Knowledge,
    question: str,
    direct_doc_max_chars: int,
    max_steps: int,
) -> Tuple[str, str, Dict[str, Any]]:
    docs = kb.direct_flat_catalog(direct_doc_max_chars)
    prior_error = ""
    history: List[Dict[str, Any]] = []
    for step in range(1, max_steps + 1):
        prompt = f"""Perform one ReAct reasoning/action step over the supplied flat documentation.
There is no retrieval tool: all 212 algorithm documents are already in the context.
Reason briefly, then finish by returning exactly:
{{"reasoning":"brief reason","action":"finish","task_type":"...","algorithm":"..."}}

Question:
{question}

Complete flat documentation:
{docs}

Previous validation error, if any:
{prior_error or '<none>'}"""
        out = call_json(llm, f"react_flat_direct_step_{step}", SYSTEM, prompt)
        history.append({"step": step, "model": out})
        task = kb.normalize_task(out.get("task_type"))
        algorithm = kb.normalize_algorithm(out.get("algorithm"))
        if canonical(out.get("action")) == "finish" and kb.valid_task(task) and kb.valid_algorithm(algorithm):
            return task, algorithm, {"trace": history, "flat_mode": "direct"}
        prior_error = "Use action=finish and exact task_type/algorithm identifiers from the documents."
    raise RuntimeError(f"Direct-context ReAct did not finish within {max_steps} steps")


def explicit_hierarchical(
    llm: OpenAICompatibleLLM, kb: Knowledge, question: str, top_k: int
) -> Tuple[str, str, Dict[str, Any]]:
    del top_k
    task_prompt = f"""Execute node 1 of this explicit two-node plan:
node_1=select_task_type; node_2=select_algorithm(depends_on=node_1).

Question:
{question}

Hierarchical task-type catalog:
{kb.task_catalog()}

Return exactly: {{"task_type":"..."}}"""
    task_out = call_json(llm, "explicit_hierarchical_task", SYSTEM, task_prompt)
    task = kb.normalize_task(task_out.get("task_type"))
    docs = kb.algorithm_catalog(task)
    algorithm_prompt = f"""Execute node 2 of the explicit plan using node 1's result.

Question:
{question}
Selected parent task type: {task}

Child algorithm documents:
{docs or '<no algorithms found for that task type>'}

Return exactly: {{"task_type":"{task}","algorithm":"..."}}"""
    alg_out = call_json(llm, "explicit_hierarchical_algorithm", SYSTEM, algorithm_prompt)
    return task, kb.normalize_algorithm(alg_out.get("algorithm")), {
        "task_raw": task_out,
        "algorithm_raw": alg_out,
    }


def react_flat(
    llm: OpenAICompatibleLLM,
    kb: Knowledge,
    question: str,
    top_k: int,
    max_steps: int,
) -> Tuple[str, str, Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    observation = "No documents retrieved yet. You must search the flat documentation before finishing."
    for step in range(1, max_steps + 1):
        prompt = f"""Use the ReAct loop to select an algorithm.
Available actions:
1. {{"reasoning":"brief reason","action":"search","query":"retrieval query"}}
2. {{"reasoning":"brief reason","action":"finish","task_type":"...","algorithm":"..."}}
You must search at least once. Use only identifiers appearing in an observation.

Question:
{question}

Prior trace:
{json.dumps(history, ensure_ascii=False)}

Current observation:
{observation}

Return the next action as one JSON object."""
        out = call_json(llm, f"react_flat_step_{step}", SYSTEM, prompt)
        action = canonical(out.get("action"))
        history.append({"step": step, "model": out})
        if action == "search":
            query = str(out.get("query") or question)
            docs, ids = kb.flat_catalog(query, top_k)
            observation = f"Flat search results (valid algorithm IDs: {ids}):\n{docs}"
            history[-1]["retrieved_algorithms"] = ids
            continue
        if action == "finish" and any("retrieved_algorithms" in x for x in history):
            task = kb.normalize_task(out.get("task_type"))
            algorithm = kb.normalize_algorithm(out.get("algorithm"))
            if kb.valid_task(task) and kb.valid_algorithm(algorithm):
                return task, algorithm, {"trace": history}
            observation = "Invalid task_type or algorithm identifier. Search again or finish with valid IDs."
            continue
        observation = "Invalid action. Search first, then finish using the required JSON schema."
    raise RuntimeError(f"ReAct did not finish within {max_steps} steps")


def react_hierarchical(
    llm: OpenAICompatibleLLM,
    kb: Knowledge,
    question: str,
    top_k: int,
    max_steps: int,
) -> Tuple[str, str, Dict[str, Any]]:
    del top_k
    history: List[Dict[str, Any]] = []
    selected_task = ""
    observation = "Hierarchical task-type catalog:\n" + kb.task_catalog()
    for step in range(1, max_steps + 1):
        prompt = f"""Use the ReAct loop over a hierarchical knowledge base.
Available actions:
1. {{"reasoning":"brief reason","action":"open_task_type","task_type":"..."}}
2. {{"reasoning":"brief reason","action":"finish","task_type":"...","algorithm":"..."}}
Open a task type before finishing. The algorithm must be a child of the opened task type.

Question:
{question}

Prior trace:
{json.dumps(history, ensure_ascii=False)}

Current observation:
{observation}

Return the next action as one JSON object."""
        out = call_json(llm, f"react_hierarchical_step_{step}", SYSTEM, prompt)
        action = canonical(out.get("action"))
        history.append({"step": step, "model": out})
        if action == "opentasktype":
            candidate = kb.normalize_task(out.get("task_type"))
            if not kb.valid_task(candidate):
                observation = "Unknown task type. Choose one exact ID from the catalog."
                continue
            selected_task = candidate
            observation = (
                f"Opened task type: {selected_task}\nChild algorithm documents:\n"
                + kb.algorithm_catalog(selected_task)
            )
            history[-1]["opened_task_type"] = selected_task
            continue
        if action == "finish" and selected_task:
            task = kb.normalize_task(out.get("task_type"))
            algorithm = kb.normalize_algorithm(out.get("algorithm"))
            children = {str(x.get("id")) for x in kb.algorithms_by_task.get(selected_task, [])}
            if task == selected_task and algorithm in children:
                return task, algorithm, {"trace": history}
            observation = (
                f"Invalid finish: task_type must be {selected_task} and algorithm must be one of its children.\n"
                + kb.algorithm_catalog(selected_task)
            )
            continue
        observation = "Invalid action. Open one exact task type before finishing."
    raise RuntimeError(f"ReAct did not finish within {max_steps} steps")


def token_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> Dict[str, int]:
    fields = ("requests", "prompt_tokens", "completion_tokens", "cached_prompt_tokens", "total_tokens")
    return {name: int(after["llm"].get(name, 0)) - int(before["llm"].get(name, 0)) for name in fields}


def load_completed(path: Path) -> Dict[int, Dict[str, Any]]:
    completed: Dict[int, Dict[str, Any]] = {}
    if not path.is_file():
        return completed
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        completed[int(item["id"])] = item
    return completed


def write_summary(path: Path, results: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> Dict[str, Any]:
    total = len(results)
    task_correct = sum(bool(x.get("task_correct")) for x in results)
    algorithm_correct = sum(bool(x.get("algorithm_correct")) for x in results)
    summary = {
        "knowledge": args.knowledge,
        "planner": args.planner,
        "flat_mode": args.flat_mode if args.knowledge == "flat" else None,
        "model": args.model,
        "total": total,
        "accuracy": task_correct / total if total else 0.0,
        "accuracy_count": f"{task_correct}/{total}",
        "algorithm_accuracy": algorithm_correct / total if total else 0.0,
        "algorithm_accuracy_count": f"{algorithm_correct}/{total}",
        "token": sum(int(x.get("usage", {}).get("total_tokens", 0)) for x in results),
        "prompt_tokens": sum(int(x.get("usage", {}).get("prompt_tokens", 0)) for x in results),
        "completion_tokens": sum(int(x.get("usage", {}).get("completion_tokens", 0)) for x in results),
        "requests": sum(int(x.get("usage", {}).get("requests", 0)) for x in results),
        "errors": sum(bool(x.get("error")) for x in results),
    }
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "results.jsonl"
    summary_path = args.output_dir / "summary.json"
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    dataset = [x for x in dataset if int(x["id"]) >= args.start_id]
    if args.limit > 0:
        dataset = dataset[: args.limit]
    completed = load_completed(result_path)

    config = ModelConfig(
        model=args.model,
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=args.base_url,
        temperature=0.0,
        timeout_seconds=args.timeout,
        max_retries=args.max_retries,
    )
    metrics = MetricsCollector(config)
    llm = OpenAICompatibleLLM(config, metrics)
    kb = Knowledge(args.knowledge_base)

    selectors = {
        ("flat", "llmcompiler"): lambda q: explicit_flat(
            llm, kb, q, args.top_k, args.flat_mode, args.direct_doc_max_chars
        ),
        ("hierarchical", "llmcompiler"): lambda q: explicit_hierarchical(llm, kb, q, args.top_k),
        ("flat", "react"): lambda q: (
            react_flat_direct(llm, kb, q, args.direct_doc_max_chars, args.max_react_steps)
            if args.flat_mode == "direct"
            else react_flat(llm, kb, q, args.top_k, args.max_react_steps)
        ),
        ("hierarchical", "react"): lambda q: react_hierarchical(
            llm, kb, q, args.top_k, args.max_react_steps
        ),
    }
    selector = selectors[(args.knowledge, args.planner)]

    for index, sample in enumerate(dataset, start=1):
        sample_id = int(sample["id"])
        if sample_id in completed:
            continue
        started = time.perf_counter()
        before = metrics.snapshot()
        predicted_task = ""
        predicted_algorithm = ""
        trace: Dict[str, Any] = {}
        error: Optional[str] = None
        try:
            predicted_task, predicted_algorithm, trace = selector(str(sample["question"]))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        after = metrics.snapshot()
        usage = token_delta(before, after)
        record = {
            "id": sample_id,
            "question": sample["question"],
            "gold_task_type": sample["task_type"],
            "gold_algorithm": sample["algorithm"],
            "predicted_task_type": predicted_task,
            "predicted_algorithm": predicted_algorithm,
            "task_correct": canonical(predicted_task) == canonical(sample["task_type"]),
            "algorithm_correct": canonical(predicted_algorithm) == canonical(sample["algorithm"]),
            "usage": usage,
            "elapsed_seconds": time.perf_counter() - started,
            "error": error,
            "trace": trace,
        }
        with result_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
        completed[sample_id] = record
        relevant = [completed[int(x["id"])] for x in dataset if int(x["id"]) in completed]
        summary = write_summary(summary_path, relevant, args)
        print(
            f"[{index}/{len(dataset)}] id={sample_id} "
            f"task={record['task_correct']} alg={record['algorithm_correct']} "
            f"tokens={usage['total_tokens']} cumulative={summary['token']} error={error or '-'}",
            flush=True,
        )

    relevant = [completed[int(x["id"])] for x in dataset if int(x["id"]) in completed]
    summary = write_summary(summary_path, relevant, args)
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
