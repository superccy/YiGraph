from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from log_to_graph import build_graph_from_file
from .features import TextEncoder


EDGE_TYPES = ("time", "dependency", "same_agent", "role_to_step", "action_to_step")
NODE_TYPES = ("step", "role", "action")
CORRECT_ERROR_TASKS = ("all", "arc", "hotpot", "musique", "wikimqa", "math500", "mmlu_pro", "gaia")


@dataclass
class RawTraceExample:
    trace_id: str
    graph: Dict
    annotations: List[Dict]
    error_observed_step: int
    positive_steps: List[int]
    candidate_steps: List[int]
    metadata: Dict = None


@dataclass
class TraceTensor:
    trace_id: str
    node_features: np.ndarray
    edges: np.ndarray
    edge_features: np.ndarray
    edge_times: np.ndarray
    candidate_indices: np.ndarray
    candidate_steps: List[int]
    candidate_pair_features: np.ndarray
    labels: np.ndarray
    error_index: int
    error_observed_step: int
    positive_steps: List[int]
    step_to_node: Dict[int, int]
    node_metadata: List[Dict]
    metadata: Dict = None


@dataclass
class TraceDataset:
    examples: List[TraceTensor]
    input_dim: int
    edge_dim: int
    text_dim: int
    role_vocab: List[str]
    action_vocab: List[str]
    status_vocab: List[str]


def load_raw_examples(
    failure_dir: Path,
    annotation_dir: Path,
    limit: Optional[int] = None,
    candidate_scope: str = "observed",
    error_observed_strategy: str = "auto",
) -> List[RawTraceExample]:
    if candidate_scope not in {"observed", "all"}:
        raise ValueError("candidate_scope must be one of: observed, all")
    if error_observed_strategy not in {"auto", "discovered_at", "last_step"}:
        raise ValueError("error_observed_strategy must be one of: auto, discovered_at, last_step")

    failure_paths = sorted(failure_dir.glob("*.json"), key=lambda path: _numeric_sort_key(path.stem))
    if limit is not None:
        failure_paths = failure_paths[:limit]

    examples: List[RawTraceExample] = []
    missing_annotations: List[str] = []
    for failure_path in failure_paths:
        trace_id = failure_path.stem
        annotation_path = _find_annotation_path(annotation_dir, trace_id)
        if annotation_path is None:
            missing_annotations.append(trace_id)
            continue

        graph = build_graph_from_file(failure_path).to_dict()
        annotations = _load_json_list(annotation_path)
        discovered_values = [int(item["discovered_at"]) for item in annotations if item.get("discovered_at") is not None]
        positive_steps = sorted({int(item["step"]) for item in annotations if item.get("step") is not None})
        nodes_by_step = {int(node["step"]): node for node in graph["nodes"]}
        error_observed_step = _select_error_observed_step(
            nodes_by_step,
            discovered_values,
            positive_steps,
            error_observed_strategy,
        )
        candidate_steps = []
        for step, node in sorted(nodes_by_step.items()):
            if step <= 0:
                continue
            if _is_user_node(node):
                continue
            if candidate_scope == "observed" and step > error_observed_step:
                continue
            candidate_steps.append(step)

        examples.append(
            RawTraceExample(
                trace_id=trace_id,
                graph=graph,
                annotations=annotations,
                error_observed_step=error_observed_step,
                positive_steps=[
                    step
                    for step in positive_steps
                    if step in nodes_by_step and (candidate_scope == "all" or step <= error_observed_step)
                ],
                candidate_steps=candidate_steps,
                metadata={"data_format": "tracegraph"},
            )
        )

    if missing_annotations:
        raise ValueError(f"Missing annotation files for traces: {', '.join(missing_annotations)}")
    return examples


def load_unlabeled_raw_examples(
    data_dir: Path,
    limit: Optional[int] = None,
    candidate_scope: str = "all",
    error_observed_strategy: str = "auto",
) -> List[RawTraceExample]:
    if candidate_scope not in {"observed", "all"}:
        raise ValueError("candidate_scope must be one of: observed, all")
    if error_observed_strategy not in {"auto", "discovered_at", "last_step"}:
        raise ValueError("error_observed_strategy must be one of: auto, discovered_at, last_step")

    source_dir = data_dir / "data" if (data_dir / "data").is_dir() else data_dir
    if not source_dir.is_dir():
        raise ValueError(f"Unlabeled data directory does not exist: {source_dir}")

    data_paths = sorted(source_dir.glob("*.json"), key=lambda path: _numeric_sort_key(path.stem))
    if limit is not None:
        data_paths = data_paths[:limit]

    examples: List[RawTraceExample] = []
    for data_path in data_paths:
        trace_id = data_path.stem
        graph = build_graph_from_file(data_path).to_dict()
        nodes_by_step = {int(node["step"]): node for node in graph["nodes"]}
        if not nodes_by_step:
            continue
        error_observed_step = _select_error_observed_step(
            nodes_by_step,
            discovered_values=[],
            positive_steps=[],
            strategy="last_step" if error_observed_strategy == "auto" else error_observed_strategy,
        )
        candidate_steps = []
        for step, node in sorted(nodes_by_step.items()):
            if step <= 0:
                continue
            if _is_user_node(node):
                continue
            if candidate_scope == "observed" and step > error_observed_step:
                continue
            candidate_steps.append(step)

        examples.append(
            RawTraceExample(
                trace_id=trace_id,
                graph=graph,
                annotations=[],
                error_observed_step=error_observed_step,
                positive_steps=[],
                candidate_steps=candidate_steps,
                metadata={
                    "data_format": "tracegraph_unlabeled",
                    "source_path": str(data_path),
                },
            )
        )
    return examples


def load_correct_error_examples(
    parquet_path: Path,
    task: str = "all",
    limit: Optional[int] = None,
    candidate_scope: str = "all",
    error_observed_strategy: str = "auto",
) -> List[RawTraceExample]:
    if task not in CORRECT_ERROR_TASKS:
        raise ValueError(f"correct_error_task must be one of: {', '.join(CORRECT_ERROR_TASKS)}")
    if candidate_scope not in {"observed", "all"}:
        raise ValueError("candidate_scope must be one of: observed, all")
    if error_observed_strategy not in {"auto", "last_step"}:
        raise ValueError("CORRECT-Error supports error_observed_strategy auto or last_step")
    if not parquet_path.exists():
        raise ValueError(f"CORRECT-Error parquet file does not exist: {parquet_path}")

    examples: List[RawTraceExample] = []
    for row in _iter_correct_error_rows(parquet_path):
        if task != "all" and row.get("dataset") != task:
            continue
        examples.append(
            correct_error_row_to_raw_example(
                row,
                candidate_scope=candidate_scope,
                error_observed_strategy=error_observed_strategy,
            )
        )
        if limit is not None and len(examples) >= limit:
            break
    return examples


def correct_error_row_to_raw_example(
    row: Dict,
    candidate_scope: str = "all",
    error_observed_strategy: str = "auto",
) -> RawTraceExample:
    history = row.get("history") or []
    if not isinstance(history, list):
        raise ValueError(f"{row.get('trajectory_id')}: history must be a list")
    mistake_step = int(row["mistake_step"])
    if mistake_step < 0 or mistake_step >= len(history):
        raise ValueError(f"{row.get('trajectory_id')}: mistake_step {mistake_step} outside history")

    nodes = []
    for step, item in enumerate(history):
        item = item or {}
        role = _clean_correct_error_role(item.get("role", "unknown-role"))
        content = str(item.get("content", "") or "")
        nodes.append(
            {
                "step": step,
                "roles": [role],
                "actions": [role],
                "contexts": [content],
                "summary": content[:200],
                "status": "unknown",
                "is_failed": step == mistake_step,
                "raw_entry_count": 1,
            }
        )

    edges = [
        {
            "source": step,
            "target": step + 1,
            "type": "time",
            "reason": "history order",
        }
        for step in range(max(0, len(nodes) - 1))
    ]
    graph = {
        "role_mapping": {},
        "nodes": nodes,
        "edges": edges,
    }
    nodes_by_step = {int(node["step"]): node for node in nodes}
    error_observed_step = _select_error_observed_step(
        nodes_by_step,
        discovered_values=[],
        positive_steps=[mistake_step],
        strategy="last_step" if error_observed_strategy == "auto" else error_observed_strategy,
    )
    candidate_steps = []
    for step, node in sorted(nodes_by_step.items()):
        if _is_user_node(node) and step != mistake_step:
            continue
        if candidate_scope == "observed" and step > error_observed_step:
            continue
        candidate_steps.append(step)

    annotation = {
        "step": mistake_step,
        "agent": row.get("mistake_agent", ""),
        "reason": row.get("mistake_reason", ""),
    }
    return RawTraceExample(
        trace_id=str(row.get("trajectory_id") or row.get("question_id") or len(history)),
        graph=graph,
        annotations=[annotation],
        error_observed_step=error_observed_step,
        positive_steps=[mistake_step] if mistake_step in candidate_steps else [],
        candidate_steps=candidate_steps,
        metadata={
            "data_format": "correct_error",
            "dataset": row.get("dataset", ""),
            "generator_model": row.get("generator_model", ""),
            "question_id": row.get("question_id", ""),
            "mistake_agent": row.get("mistake_agent", ""),
            "mistake_step": mistake_step,
            "mistake_reason": row.get("mistake_reason", ""),
        },
    )


def validate_raw_examples(examples: Sequence[RawTraceExample]) -> None:
    errors: List[str] = []
    for example in examples:
        steps = {int(node["step"]) for node in example.graph["nodes"]}
        for step in example.positive_steps:
            if step not in steps:
                errors.append(f"{example.trace_id}: positive step {step} not in graph")
            if step > example.error_observed_step:
                errors.append(f"{example.trace_id}: positive step {step} after discovered_at {example.error_observed_step}")
        if not example.candidate_steps:
            errors.append(f"{example.trace_id}: no candidate steps")
        if not set(example.positive_steps) & set(example.candidate_steps):
            errors.append(f"{example.trace_id}: no positive step in candidate set")
    if errors:
        raise ValueError("Trace data validation failed:\n" + "\n".join(errors[:50]))


def _iter_correct_error_rows(parquet_path: Path) -> Iterable[Dict]:
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(parquet_path)
        for row in table.to_pylist():
            yield row
        return
    except ModuleNotFoundError:
        pass

    helper_python = Path("/home/wangzh/miniconda3/envs/autogen/bin/python")
    if not helper_python.exists():
        raise ImportError(
            "Reading CORRECT-Error requires pyarrow. Install pyarrow in this environment "
            "or keep /home/wangzh/miniconda3/envs/autogen/bin/python available."
        )
    script = (
        "import json, sys\n"
        "import pyarrow.parquet as pq\n"
        "table = pq.read_table(sys.argv[1])\n"
        "for row in table.to_pylist():\n"
        "    print(json.dumps(row, ensure_ascii=False))\n"
    )
    result = subprocess.run(
        [str(helper_python), "-c", script, str(parquet_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    for line in result.stdout.splitlines():
        if line.strip():
            yield json.loads(line)


def _clean_correct_error_role(role: object) -> str:
    text = str(role or "unknown-role").strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    return text or "unknown-role"


def build_dataset(raw_examples: Sequence[RawTraceExample], text_encoder: TextEncoder) -> TraceDataset:
    role_vocab = sorted({role for example in raw_examples for node in example.graph["nodes"] for role in node.get("roles", [])})
    action_vocab = sorted({action for example in raw_examples for node in example.graph["nodes"] for action in node.get("actions", [])})
    status_vocab = sorted({node.get("status", "unknown") for example in raw_examples for node in example.graph["nodes"]})
    role_to_idx = {value: index for index, value in enumerate(role_vocab)}
    action_to_idx = {value: index for index, value in enumerate(action_vocab)}
    status_to_idx = {value: index for index, value in enumerate(status_vocab)}
    edge_type_to_idx = {value: index for index, value in enumerate(EDGE_TYPES)}

    all_texts: List[str] = []
    text_slots: List[Tuple[int, int]] = []
    node_records_by_example: List[List[Dict]] = []

    for example_index, example in enumerate(raw_examples):
        node_records = _make_node_records(example)
        node_records_by_example.append(node_records)
        for node_index, record in enumerate(node_records):
            all_texts.append(record["text"])
            text_slots.append((example_index, node_index))

    all_embeddings = text_encoder.encode(all_texts)
    embeddings_by_example: List[List[np.ndarray]] = [[] for _ in raw_examples]
    for (example_index, _), embedding in zip(text_slots, all_embeddings):
        embeddings_by_example[example_index].append(embedding)

    tensors: List[TraceTensor] = []
    for example, node_records, text_embeddings in zip(raw_examples, node_records_by_example, embeddings_by_example):
        node_features = []
        step_to_node = {record["step"]: index for index, record in enumerate(node_records) if record["node_type"] == "step"}
        max_step = max(step_to_node) if step_to_node else 1
        for record, text_embedding in zip(node_records, text_embeddings):
            node_features.append(
                np.concatenate(
                    [
                        text_embedding,
                        _one_hot(record.get("role"), role_to_idx),
                        _one_hot(record.get("action"), action_to_idx),
                        _one_hot(record.get("status", "unknown"), status_to_idx),
                        _one_hot(record["node_type"], {name: i for i, name in enumerate(NODE_TYPES)}),
                        np.asarray(
                            [
                                float(record.get("step", 0)) / max(1.0, float(max_step)),
                                np.log1p(float(record.get("raw_entry_count", 0))) / 4.0,
                            ],
                            dtype=np.float32,
                        ),
                    ]
                ).astype(np.float32)
            )

        edges, edge_features, edge_times = _make_edges(example, node_records, step_to_node, edge_type_to_idx, max_step)
        observed_step = _nearest_observed_step(example.error_observed_step, step_to_node)
        error_index = step_to_node[observed_step]
        candidate_steps = [step for step in example.candidate_steps if step in step_to_node]
        candidate_indices = np.asarray([step_to_node[step] for step in candidate_steps], dtype=np.int64)
        positive_set = set(example.positive_steps)
        labels = np.asarray([1.0 if step in positive_set else 0.0 for step in candidate_steps], dtype=np.float32)
        pair_features = np.stack(
            [
                _candidate_pair_features(step, observed_step, example.graph, max_step)
                for step in candidate_steps
            ]
        ).astype(np.float32)

        tensors.append(
            TraceTensor(
                trace_id=example.trace_id,
                node_features=np.stack(node_features).astype(np.float32),
                edges=edges,
                edge_features=edge_features,
                edge_times=edge_times,
                candidate_indices=candidate_indices,
                candidate_steps=candidate_steps,
                candidate_pair_features=pair_features,
                labels=labels,
                error_index=error_index,
                error_observed_step=example.error_observed_step,
                positive_steps=example.positive_steps,
                step_to_node=step_to_node,
                node_metadata=node_records,
                metadata=example.metadata or {},
            )
        )

    input_dim = int(tensors[0].node_features.shape[1]) if tensors else 0
    edge_dim = len(EDGE_TYPES) + 3
    return TraceDataset(
        examples=tensors,
        input_dim=input_dim,
        edge_dim=edge_dim,
        text_dim=text_encoder.dimension,
        role_vocab=role_vocab,
        action_vocab=action_vocab,
        status_vocab=status_vocab,
    )


def _load_json_list(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list: {path}")
    return [item for item in data if isinstance(item, dict)]


def _numeric_sort_key(value: str) -> Tuple[int, str]:
    match = re.search(r"\d+", value)
    return (int(match.group(0)) if match else 10**9, value)


def _find_annotation_path(annotation_dir: Path, trace_id: str) -> Optional[Path]:
    preferred_names = (
        f"{trace_id}_error_annotation_result.json",
        f"{trace_id}_gpt-5.1_result.json",
    )
    for name in preferred_names:
        path = annotation_dir / name
        if path.exists():
            return path

    matches = sorted(annotation_dir.glob(f"{trace_id}_*_result.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise ValueError(f"Multiple annotation files found for trace {trace_id}: {names}")
    return None


def _select_error_observed_step(
    nodes_by_step: Dict[int, Dict],
    discovered_values: Sequence[int],
    positive_steps: Sequence[int],
    strategy: str,
) -> int:
    if strategy in {"auto", "discovered_at"} and discovered_values:
        return max(discovered_values)

    if strategy in {"auto", "last_step"}:
        non_user_steps = [
            step
            for step, node in nodes_by_step.items()
            if not _is_user_node(node)
        ]
        if non_user_steps:
            return max(non_user_steps)
        return max(nodes_by_step)

    if positive_steps:
        return max(positive_steps)
    return max(nodes_by_step)


def _make_node_records(example: RawTraceExample) -> List[Dict]:
    records: List[Dict] = []
    roles = set()
    actions = set()
    for node in sorted(example.graph["nodes"], key=lambda item: int(item["step"])):
        role = _first(node.get("roles"), "unknown-role")
        action = _first(node.get("actions"), "unknown-action")
        roles.add(role)
        actions.add(action)
        text = " ".join(
            [
                role,
                action,
                node.get("status", "unknown"),
                node.get("summary", ""),
                " ".join(node.get("contexts", [])),
            ]
        )
        records.append(
            {
                "node_type": "step",
                "step": int(node["step"]),
                "role": role,
                "action": action,
                "status": node.get("status", "unknown"),
                "is_failed": bool(node.get("is_failed", False)),
                "raw_entry_count": int(node.get("raw_entry_count", 0)),
                "summary": node.get("summary", ""),
                "content": "\n".join(node.get("contexts", [])),
                "text": text,
            }
        )

    for role in sorted(roles):
        records.append({"node_type": "role", "step": 0, "role": role, "action": "", "status": "unknown", "text": f"role {role}"})
    for action in sorted(actions):
        records.append({"node_type": "action", "step": 0, "role": "", "action": action, "status": "unknown", "text": f"action {action}"})
    return records


def _make_edges(
    example: RawTraceExample,
    node_records: Sequence[Dict],
    step_to_node: Dict[int, int],
    edge_type_to_idx: Dict[str, int],
    max_step: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    virtual_lookup = {
        (record["node_type"], record.get("role") or record.get("action")): index
        for index, record in enumerate(node_records)
        if record["node_type"] != "step"
    }
    node_by_step = {int(node["step"]): node for node in example.graph["nodes"]}
    edge_rows: List[Tuple[int, int]] = []
    edge_features: List[np.ndarray] = []
    edge_times: List[float] = []

    for edge in example.graph["edges"]:
        source = int(edge["source"])
        target = int(edge["target"])
        if source not in step_to_node or target not in step_to_node:
            continue
        edge_type = edge.get("type", "time")
        _append_edge(edge_rows, edge_features, edge_times, step_to_node[source], step_to_node[target], edge_type, target, source, max_step, edge_type_to_idx)

    sorted_steps = sorted(step_to_node)
    previous_by_role: Dict[str, int] = {}
    for step in sorted_steps:
        node = node_by_step[step]
        role = _first(node.get("roles"), "unknown-role")
        action = _first(node.get("actions"), "unknown-action")
        if role in previous_by_role:
            _append_edge(edge_rows, edge_features, edge_times, step_to_node[previous_by_role[role]], step_to_node[step], "same_agent", step, previous_by_role[role], max_step, edge_type_to_idx)
        previous_by_role[role] = step

        role_index = virtual_lookup.get(("role", role))
        action_index = virtual_lookup.get(("action", action))
        if role_index is not None:
            _append_edge(edge_rows, edge_features, edge_times, role_index, step_to_node[step], "role_to_step", step, 0, max_step, edge_type_to_idx)
        if action_index is not None:
            _append_edge(edge_rows, edge_features, edge_times, action_index, step_to_node[step], "action_to_step", step, 0, max_step, edge_type_to_idx)

    if not edge_rows:
        return (
            np.zeros((0, 2), dtype=np.int64),
            np.zeros((0, len(EDGE_TYPES) + 3), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
        )

    order = np.argsort(np.asarray(edge_times, dtype=np.float32), kind="stable")
    return (
        np.asarray(edge_rows, dtype=np.int64)[order],
        np.stack(edge_features).astype(np.float32)[order],
        np.asarray(edge_times, dtype=np.float32)[order],
    )


def _append_edge(
    rows: List[Tuple[int, int]],
    features: List[np.ndarray],
    times: List[float],
    source_index: int,
    target_index: int,
    edge_type: str,
    timestamp: int,
    source_step: int,
    max_step: int,
    edge_type_to_idx: Dict[str, int],
) -> None:
    rows.append((source_index, target_index))
    one_hot = _one_hot(edge_type, edge_type_to_idx)
    structural = np.asarray(
        [
            float(max(0, timestamp - source_step)) / max(1.0, float(max_step)),
            1.0 if edge_type == "same_agent" else 0.0,
            1.0 if edge_type == "dependency" else 0.0,
        ],
        dtype=np.float32,
    )
    features.append(np.concatenate([one_hot, structural]).astype(np.float32))
    times.append(float(timestamp))


def _candidate_pair_features(step: int, observed_step: int, graph: Dict, max_step: int) -> np.ndarray:
    node_by_step = {int(node["step"]): node for node in graph["nodes"]}
    candidate = node_by_step[step]
    observed = node_by_step[observed_step]
    direct_dependency = any(
        int(edge["source"]) == step and int(edge["target"]) == observed_step and edge.get("type") == "dependency"
        for edge in graph["edges"]
    )
    same_role = bool(set(candidate.get("roles", [])) & set(observed.get("roles", [])))
    return np.asarray(
        [
            float(max(0, observed_step - step)) / max(1.0, float(max_step)),
            float(same_role),
            float(direct_dependency),
            float(step) / max(1.0, float(max_step)),
        ],
        dtype=np.float32,
    )


def _nearest_observed_step(error_observed_step: int, step_to_node: Dict[int, int]) -> int:
    valid_steps = [step for step in step_to_node if step <= error_observed_step]
    if not valid_steps:
        return min(step_to_node)
    return max(valid_steps)


def _first(values: Iterable[str] | None, default: str) -> str:
    if not values:
        return default
    for value in values:
        if value:
            return str(value)
    return default


def _is_user_node(node: Dict) -> bool:
    return "user" in {str(role).lower() for role in node.get("roles", [])}


def _one_hot(value: str | None, vocab: Dict[str, int]) -> np.ndarray:
    vector = np.zeros(len(vocab), dtype=np.float32)
    if value in vocab:
        vector[vocab[value]] = 1.0
    return vector
