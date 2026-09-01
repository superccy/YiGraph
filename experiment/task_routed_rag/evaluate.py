#!/usr/bin/env python3
"""Evaluate task-routed Tool RAG and Documentation RAG."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np
import yaml
from sentence_transformers import SentenceTransformer


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aag.reasoner.prompt_template.llm_prompt_en import select_algorithm_prompt  # noqa: E402


DEFAULT_ALGORITHMS = PROJECT_ROOT / "aag" / "knowledge_base" / "algorithms.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="External evaluation dataset JSON; it is never copied into this package.",
    )
    parser.add_argument("--algorithms", type=Path, default=DEFAULT_ALGORITHMS)
    parser.add_argument(
        "--task-log",
        type=Path,
        required=True,
        help="YiGraph evaluation JSON whose predicted_task_type is reused as stage one.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("tool_rag", "documentation_rag", "both"),
        default="both",
    )
    parser.add_argument(
        "--candidate-policy",
        choices=("top3", "all"),
        required=True,
        help="Use the top 3 retrieved algorithms or all algorithms in the routed task type.",
    )
    parser.add_argument("--embedding-model", default="BAAI/bge-large-en-v1.5")
    parser.add_argument("--embedding-device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL"))
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=6)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_yaml_list(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Expected YAML list: {path}")
    return [item for item in payload if isinstance(item, dict) and item.get("id")]


def textify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, dict):
        return " ".join(
            f"{key}: {textify(subvalue)}"
            for key, subvalue in value.items()
            if textify(subvalue)
        )
    if isinstance(value, list):
        return " ".join(textify(item) for item in value if textify(item))
    return str(value)


def build_tool_text(algorithm: Dict[str, Any]) -> str:
    deployment = algorithm.get("Deployment_method") or {}
    input_schema = deployment.get("input_schema") or {}
    output_schema = deployment.get("output_schema") or {}
    return " ".join(
        part
        for part in (
            f"tool name: {algorithm['id']}",
            f"engine: {deployment.get('support_engine', '')}",
            f"input schema: {textify(input_schema)}",
            f"output schema: {textify(output_schema)}",
            f"graph type: {textify(deployment.get('graph_type'))}",
        )
        if part
    )


def build_documentation_text(algorithm: Dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            f"algorithm: {algorithm['id']}",
            f"application scenario: {textify(algorithm.get('Application_scenario'))}",
            f"principles: {textify(algorithm.get('Principles'))}",
            f"solvable questions: {textify(algorithm.get('solvable_questions'))}",
        )
        if part
    )


def embedding_cache_key(
    algorithms: Sequence[Dict[str, Any]],
    model_name: str,
    mode: str,
) -> str:
    builder = build_tool_text if mode == "tool_rag" else build_documentation_text
    payload = {
        "model": model_name,
        "mode": mode,
        "items": [(item["id"], builder(item)) for item in algorithms],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def encode_corpus(
    model: SentenceTransformer,
    algorithms: Sequence[Dict[str, Any]],
    mode: str,
    cache_dir: Path,
    batch_size: int,
) -> np.ndarray:
    key = embedding_cache_key(algorithms, str(model.model_card_data.model_id), mode)
    cache_path = cache_dir / f"{mode}_{key}.npy"
    if cache_path.exists():
        return np.load(cache_path)
    builder = build_tool_text if mode == "tool_rag" else build_documentation_text
    texts = [builder(item) for item in algorithms]
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(cache_path, np.asarray(embeddings, dtype=np.float32))
    return np.asarray(embeddings, dtype=np.float32)


def retrieve(
    query_embedding: np.ndarray,
    corpus_embeddings: np.ndarray,
    algorithms: Sequence[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    scores = corpus_embeddings @ query_embedding
    order = np.argsort(-scores, kind="stable")[: min(top_k, len(algorithms))]
    return [
        {
            "rank": rank,
            "score": float(scores[int(index)]),
            "algorithm": algorithms[int(index)],
        }
        for rank, index in enumerate(order, start=1)
    ]


def retrieval_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    total = len(rows)
    result: Dict[str, float] = {}
    for k in (1, 3, 5, 10):
        result[f"recall@{k}"] = (
            sum(1 for row in rows if row.get("gold_rank") and row["gold_rank"] <= k) / total
            if total
            else 0.0
        )
    result["mrr"] = (
        sum(1.0 / row["gold_rank"] for row in rows if row.get("gold_rank")) / total
        if total
        else 0.0
    )
    return result


def safe_function_name(algorithm_id: str, used: set[str]) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]", "_", algorithm_id)
    if not name or not re.match(r"^[A-Za-z_]", name):
        name = f"algorithm_{name}"
    name = name[:64]
    base = name
    suffix = 2
    while name in used:
        suffix_text = f"_{suffix}"
        name = base[: 64 - len(suffix_text)] + suffix_text
        suffix += 1
    used.add(name)
    return name


def json_schema_type(type_text: Any) -> str:
    text = str(type_text or "").lower()
    if "bool" in text:
        return "boolean"
    if "int" in text:
        return "integer"
    if "float" in text or "number" in text:
        return "number"
    if "list" in text or "sequence" in text or "set" in text or "nodes" in text:
        return "array"
    if "dict" in text or "graph" in text or "mapping" in text:
        return "object"
    return "string"


def tool_spec(algorithm: Dict[str, Any], used: set[str]) -> tuple[Dict[str, Any], str]:
    algorithm_id = str(algorithm["id"])
    function_name = safe_function_name(algorithm_id, used)
    deployment = algorithm.get("Deployment_method") or {}
    raw_parameters = ((deployment.get("input_schema") or {}).get("parameters") or {})
    properties = {}
    required = []
    if isinstance(raw_parameters, dict):
        for parameter_name, metadata in raw_parameters.items():
            metadata = metadata if isinstance(metadata, dict) else {}
            schema: Dict[str, Any] = {
                "type": json_schema_type(metadata.get("type")),
                "description": str(metadata.get("description", ""))[:500],
            }
            if schema["type"] == "array":
                schema["items"] = {}
            properties[str(parameter_name)] = schema
            if metadata.get("required") is True:
                required.append(str(parameter_name))
    output_description = textify(deployment.get("output_schema"))
    description = (
        f"Graph algorithm {algorithm_id}. "
        f"Engine: {deployment.get('support_engine', 'unknown')}. "
        f"Output: {output_description}"
    )[:1024]
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        parameters["required"] = required
    return (
        {
            "type": "function",
            "function": {
                "name": function_name,
                "description": description,
                "parameters": parameters,
            },
        },
        function_name,
    )


class HttpsChatClient:
    """Small OpenAI-compatible client using the standard library HTTPS stack."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 120.0):
        self.api_key = api_key.strip()
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.timeout = timeout

    def create(self, **payload: Any) -> Dict[str, Any]:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read(2000).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {error.code}: {body}") from error


def usage_dict(response: Dict[str, Any]) -> Dict[str, int]:
    usage = response.get("usage") or {}
    return {
        "requests": 1,
        "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }


def add_usage(left: Dict[str, int], right: Dict[str, int]) -> Dict[str, int]:
    return {
        key: int(left.get(key, 0)) + int(right.get(key, 0))
        for key in ("requests", "prompt_tokens", "completion_tokens", "total_tokens")
    }


def parse_json_content(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def call_with_retry(function, attempts: int):
    last_error = None
    for attempt in range(attempts):
        try:
            return function()
        except Exception as error:
            last_error = error
            if attempt + 1 >= attempts:
                break
            time.sleep(min(30.0, 2**attempt + random.random()))
    raise RuntimeError(f"API request failed after {attempts} attempts: {last_error}")


def select_documentation_rag(
    client,
    args: argparse.Namespace,
    question: str,
    retrieved: Sequence[Dict[str, Any]],
) -> tuple[str | None, Dict[str, int]]:
    algorithm_list = [
        {
            "id": item["algorithm"]["id"],
            "Application_scenario": item["algorithm"].get("Application_scenario"),
            "Principles": item["algorithm"].get("Principles"),
            "solvable_questions": item["algorithm"].get("solvable_questions"),
            "retrieval_score": item["score"],
        }
        for item in retrieved
    ]
    prompt = select_algorithm_prompt.format(
        question=question,
        algorithm_list=algorithm_list,
    )

    def request():
        return client.create(
            model=args.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=args.temperature,
            response_format={"type": "json_object"},
        )

    response = call_with_retry(request, args.max_attempts)
    payload = parse_json_content(response["choices"][0]["message"].get("content", ""))
    return payload.get("id"), usage_dict(response)


def select_tool_rag(
    client,
    args: argparse.Namespace,
    question: str,
    retrieved: Sequence[Dict[str, Any]],
) -> tuple[str | None, Dict[str, int]]:
    used: set[str] = set()
    tools = []
    name_to_id = {}
    for item in retrieved:
        spec, function_name = tool_spec(item["algorithm"], used)
        tools.append(spec)
        name_to_id[function_name] = item["algorithm"]["id"]

    system = (
        "You are a graph algorithm expert. Select exactly one supplied graph-algorithm "
        "tool that best solves the user question. Call the chosen tool. Parameter values "
        "are not evaluated; tool identity is the only objective."
    )

    def request():
        return client.create(
            model=args.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            temperature=args.temperature,
            tools=tools,
            tool_choice="required",
            parallel_tool_calls=False,
        )

    response = call_with_retry(request, args.max_attempts)
    tool_calls = response["choices"][0]["message"].get("tool_calls") or []
    selected = None
    if tool_calls:
        selected = name_to_id.get(tool_calls[0]["function"]["name"])
    return selected, usage_dict(response)


def build_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row.get("algorithm_correct"))
    failed = sum(1 for row in rows if row.get("error"))
    usage = {
        key: sum(int((row.get("token_usage") or {}).get(key, 0)) for row in rows)
        for key in ("requests", "prompt_tokens", "completion_tokens", "total_tokens")
    }
    first_stage_usage = {
        key: sum(int((row.get("first_stage_token_usage") or {}).get(key, 0)) for row in rows)
        for key in ("requests", "prompt_tokens", "completion_tokens", "total_tokens")
    }
    pipeline_usage = add_usage(first_stage_usage, usage)
    return {
        "total_samples": total,
        "task_type_correct": sum(1 for row in rows if row.get("task_type_correct")),
        "task_type_accuracy": (
            sum(1 for row in rows if row.get("task_type_correct")) / total if total else 0.0
        ),
        "algorithm_correct": correct,
        "algorithm_accuracy": correct / total if total else 0.0,
        "failed_samples": failed,
        "candidate_hits": sum(1 for row in rows if row.get("gold_rank") is not None),
        "candidate_recall": (
            sum(1 for row in rows if row.get("gold_rank") is not None) / total
            if total
            else 0.0
        ),
        "retrieval": retrieval_metrics(rows),
        "second_stage_token_usage": usage,
        "first_stage_token_usage": first_stage_usage,
        "pipeline_token_usage": pipeline_usage,
    }


def run_mode(
    args: argparse.Namespace,
    mode: str,
    dataset: Sequence[Dict[str, Any]],
    algorithms: Sequence[Dict[str, Any]],
    query_embeddings: np.ndarray,
    corpus_embeddings: np.ndarray,
    task_routes: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    mode_dir = args.output_dir / mode
    cache_dir = mode_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    retrieval_rows = []
    for sample, query_embedding in zip(dataset, query_embeddings):
        route = task_routes[str(sample["id"])]
        predicted_task_type = route.get("predicted_task_type")
        eligible_indices = [
            index
            for index, algorithm in enumerate(algorithms)
            if predicted_task_type
            and str(algorithm.get("task_type_id")) == str(predicted_task_type)
        ]
        candidate_count = len(eligible_indices)
        limit = min(3, candidate_count) if args.candidate_policy == "top3" else candidate_count
        retrieved = (
            retrieve(
                query_embedding,
                corpus_embeddings[eligible_indices],
                [algorithms[index] for index in eligible_indices],
                limit,
            )
            if limit
            else []
        )
        gold = str(sample["algorithm"])
        gold_rank = next(
            (item["rank"] for item in retrieved if str(item["algorithm"]["id"]) == gold),
            None,
        )
        retrieval_rows.append(
            {
                "id": sample.get("id"),
                "question": sample["question"],
                "gold_task_type": route.get("gold_task_type", sample.get("task_type")),
                "predicted_task_type": predicted_task_type,
                "task_type_correct": bool(route.get("task_type_correct")),
                "candidate_count": candidate_count,
                "first_stage_token_usage": route.get("first_stage_token_usage") or {
                    "requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "gold_algorithm": gold,
                "gold_rank": gold_rank,
                "retrieved": [
                    {
                        "rank": item["rank"],
                        "score": item["score"],
                        "algorithm_id": item["algorithm"]["id"],
                    }
                    for item in retrieved
                ],
                "_retrieved_full": retrieved,
            }
        )

    write_json(
        mode_dir / "retrieval_metrics.json",
        {
            "mode": mode,
            "candidate_policy": args.candidate_policy,
            "metrics": retrieval_metrics(retrieval_rows),
            "results": [
                {key: value for key, value in row.items() if key != "_retrieved_full"}
                for row in retrieval_rows
            ],
        },
    )
    if args.retrieval_only:
        return {
            "mode": mode,
            "retrieval_only": True,
            "total_samples": len(retrieval_rows),
            "retrieval": retrieval_metrics(retrieval_rows),
        }
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not args.base_url or not api_key:
        raise ValueError("--base-url/OPENAI_BASE_URL and OPENAI_API_KEY are required")

    def evaluate_one(row: Dict[str, Any]) -> Dict[str, Any]:
        sample_id = str(row["id"])
        cache_path = cache_dir / f"{sample_id}.json"
        if cache_path.exists() and not args.force:
            cached = load_json(cache_path)
            if cached.get("status") == "ok":
                return cached
        client = HttpsChatClient(api_key=api_key, base_url=args.base_url)
        usage = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        started = time.perf_counter()
        try:
            predicted = None
            select_usage = {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            if row["_retrieved_full"]:
                if mode == "tool_rag":
                    predicted, select_usage = select_tool_rag(
                        client, args, row["question"], row["_retrieved_full"]
                    )
                else:
                    predicted, select_usage = select_documentation_rag(
                        client, args, row["question"], row["_retrieved_full"]
                    )
                usage = add_usage(usage, select_usage)
            result = {
                "status": "ok",
                "id": row["id"],
                "question": row["question"],
                "gold_task_type": row["gold_task_type"],
                "predicted_task_type": row["predicted_task_type"],
                "task_type_correct": row["task_type_correct"],
                "candidate_count": row["candidate_count"],
                "gold_algorithm": row["gold_algorithm"],
                "predicted_algorithm": predicted,
                "algorithm_correct": predicted == row["gold_algorithm"],
                "gold_rank": row["gold_rank"],
                "retrieved": [
                    {
                        "rank": item["rank"],
                        "score": item["score"],
                        "algorithm_id": item["algorithm"]["id"],
                    }
                    for item in row["_retrieved_full"]
                ],
                "token_usage": usage,
                "first_stage_token_usage": row["first_stage_token_usage"],
                "pipeline_token_usage": add_usage(row["first_stage_token_usage"], usage),
                "runtime_seconds": time.perf_counter() - started,
                "error": None,
            }
        except Exception as error:
            result = {
                "status": "error",
                "id": row["id"],
                "question": row["question"],
                "gold_task_type": row["gold_task_type"],
                "predicted_task_type": row["predicted_task_type"],
                "task_type_correct": row["task_type_correct"],
                "candidate_count": row["candidate_count"],
                "gold_algorithm": row["gold_algorithm"],
                "predicted_algorithm": None,
                "algorithm_correct": False,
                "gold_rank": row["gold_rank"],
                "retrieved": [
                    {
                        "rank": item["rank"],
                        "score": item["score"],
                        "algorithm_id": item["algorithm"]["id"],
                    }
                    for item in row["_retrieved_full"]
                ],
                "token_usage": usage,
                "first_stage_token_usage": row["first_stage_token_usage"],
                "pipeline_token_usage": add_usage(row["first_stage_token_usage"], usage),
                "runtime_seconds": time.perf_counter() - started,
                "error": f"{type(error).__name__}: {error}",
            }
        write_json(cache_path, result)
        return result

    completed = 0
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_id = {
            executor.submit(evaluate_one, row): row["id"]
            for row in retrieval_rows
        }
        for future in concurrent.futures.as_completed(future_to_id):
            result = future.result()
            results.append(result)
            completed += 1
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "completed": completed,
                        "total": len(retrieval_rows),
                        "id": result["id"],
                        "status": result["status"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    results.sort(key=lambda item: int(item["id"]))
    summary = build_summary(results)
    payload = {
        "mode": mode,
        "dataset": str(args.dataset),
        "algorithms": str(args.algorithms),
        "model": args.model,
        "temperature": args.temperature,
        "embedding_model": args.embedding_model,
        "candidate_policy": args.candidate_policy,
        "task_log": str(args.task_log),
        "classification_included": False,
        "summary": summary,
        "results": results,
    }
    write_json(mode_dir / "evaluation.json", payload)
    return {"mode": mode, **summary}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset = load_json(args.dataset)
    if args.limit is not None:
        dataset = dataset[: max(0, args.limit)]
    algorithms = load_yaml_list(args.algorithms)
    task_log = load_json(args.task_log)
    task_results = task_log.get("results") if isinstance(task_log, dict) else None
    if not isinstance(task_results, list):
        raise ValueError("--task-log must contain a results list")
    task_routes = {}
    for row in task_results:
        operations = ((row.get("token_usage") or {}).get("operations") or {})
        first_stage_usage = operations.get("execute_prompt") or {
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        task_routes[str(row["id"])] = {
            "gold_task_type": row.get("gold_task_type"),
            "predicted_task_type": row.get("predicted_task_type"),
            "task_type_correct": row.get("task_type_correct"),
            "first_stage_token_usage": first_stage_usage,
        }
    missing_routes = [sample["id"] for sample in dataset if str(sample["id"]) not in task_routes]
    if missing_routes:
        raise ValueError(f"Task log is missing dataset ids: {missing_routes[:10]}")
    logging.info("Loaded %d samples and %d algorithms", len(dataset), len(algorithms))

    model = SentenceTransformer(args.embedding_model, device=args.embedding_device)
    query_embeddings = np.asarray(
        model.encode(
            [sample["question"] for sample in dataset],
            batch_size=args.batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
        ),
        dtype=np.float32,
    )
    modes = (
        ["tool_rag", "documentation_rag"]
        if args.mode == "both"
        else [args.mode]
    )
    summaries = []
    for mode in modes:
        corpus_embeddings = encode_corpus(
            model,
            algorithms,
            mode,
            args.output_dir / "embedding_cache",
            args.batch_size,
        )
        summaries.append(
            run_mode(
                args,
                mode,
                dataset,
                algorithms,
                query_embeddings,
                corpus_embeddings,
                task_routes,
            )
        )
    write_json(args.output_dir / "summary.json", summaries)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
