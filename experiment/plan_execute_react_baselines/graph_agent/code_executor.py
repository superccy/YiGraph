from __future__ import annotations

import ast
import collections
import json
import math
import pickle
import statistics
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np
import pandas as pd

from .config import RunConfig
from .datasets import GraphWorkspace
from .graph_tools import NetworkXToolRuntime
from .llm import OpenAICompatibleLLM, preview
from .metrics import MetricsCollector
from .models import TaskOutcome, TaskSpec
from .prompts import CODE_GENERATOR_SYSTEM
from .retrieval import AlgorithmDocument, FlatDocumentationRetriever


FORBIDDEN_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
    "vars",
}
FORBIDDEN_ROOTS = {
    "builtins",
    "ctypes",
    "importlib",
    "multiprocessing",
    "os",
    "pathlib",
    "shutil",
    "socket",
    "subprocess",
    "sys",
}


class UnsafeGeneratedCode(ValueError):
    pass


def validate_generated_code(code: str) -> ast.Module:
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise UnsafeGeneratedCode(f"Forbidden syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_ROOTS:
            raise UnsafeGeneratedCode(f"Forbidden name: {node.id}")
        if isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                if root.attr.startswith("__"):
                    raise UnsafeGeneratedCode(f"Forbidden attribute: {root.attr}")
                root = root.value
            if isinstance(root, ast.Name) and root.id in FORBIDDEN_ROOTS:
                raise UnsafeGeneratedCode(f"Forbidden module access: {root.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            raise UnsafeGeneratedCode(f"Forbidden call: {node.func.id}")
    return tree


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "getattr": getattr,
    "hasattr": hasattr,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "Exception": Exception,
    "ValueError": ValueError,
}


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.Lock()

    def save(
        self,
        baseline: str,
        round_number: int,
        outcome: TaskOutcome,
    ) -> Path:
        task_dir = self.root / baseline / f"round-{round_number:02d}" / f"task-{outcome.task.id:03d}"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(
            json.dumps(outcome.task.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if outcome.code is not None:
            (task_dir / "generated.py").write_text(outcome.code, encoding="utf-8")
        metadata = outcome.to_dict(include_result=False)
        metadata["result_preview"] = preview(outcome.result, 20_000) if outcome.success else None
        (task_dir / "outcome.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        if outcome.success:
            with (task_dir / "result.pkl").open("wb") as handle:
                pickle.dump(outcome.result, handle, protocol=pickle.HIGHEST_PROTOCOL)
        return task_dir


class TaskExecutionService:
    """Shared code-generation executor used unchanged by both planners."""

    def __init__(
        self,
        config: RunConfig,
        llm: OpenAICompatibleLLM,
        metrics: MetricsCollector,
        workspace: GraphWorkspace,
        retriever: FlatDocumentationRetriever,
    ) -> None:
        self.config = config
        self.llm = llm
        self.metrics = metrics
        self.workspace = workspace
        self.retriever = retriever
        self.graph_tool = NetworkXToolRuntime(workspace, retriever.algorithm_ids, metrics)
        self.artifacts = ArtifactStore(config.output_dir / "artifacts")

    def execute(
        self,
        baseline: str,
        round_number: int,
        question: str,
        task: TaskSpec,
        upstream: Dict[Any, Any],
    ) -> TaskOutcome:
        started = time.perf_counter()
        documents = self._documents_for_task(question, task)
        previous_code: Optional[str] = None
        last_error: Optional[str] = None
        attempts = 0
        for attempts in range(1, self.config.max_codegen_retries + 2):
            code: Optional[str] = None
            try:
                response = self.llm.json(
                    "code_generation",
                    CODE_GENERATOR_SYSTEM,
                    self._codegen_user_prompt(question, task, upstream, documents, previous_code, last_error),
                )
                code = str(response["code"]).strip()
                result = self._run_code(code, upstream)
                outcome = TaskOutcome(
                    task=task,
                    success=True,
                    result=result,
                    code=code,
                    attempts=attempts,
                    duration_seconds=time.perf_counter() - started,
                )
                path = self.artifacts.save(baseline, round_number, outcome)
                outcome.artifact_dir = str(path)
                self.metrics.add_event(
                    "task_execution", str(task.id), outcome.duration_seconds, success=True, attempts=attempts
                )
                return outcome
            except Exception:
                previous_code = code
                last_error = traceback.format_exc(limit=12)[-8000:]
        outcome = TaskOutcome(
            task=task,
            success=False,
            error=last_error,
            code=previous_code,
            attempts=attempts,
            duration_seconds=time.perf_counter() - started,
        )
        path = self.artifacts.save(baseline, round_number, outcome)
        outcome.artifact_dir = str(path)
        self.metrics.add_event(
            "task_execution", str(task.id), outcome.duration_seconds, success=False, attempts=attempts
        )
        return outcome

    def _documents_for_task(self, question: str, task: TaskSpec) -> List[AlgorithmDocument]:
        documents = self.retriever.retrieve(
            f"{question}\n{task.description}\n{task.algorithm_hint or ''}", self.config.retrieval_top_k
        )
        if task.algorithm_hint:
            hinted = self.retriever.get(task.algorithm_hint)
            if hinted and all(item.algorithm_id != hinted.algorithm_id for item in documents):
                documents = [hinted, *documents[:-1]]
        return documents

    def _codegen_user_prompt(
        self,
        question: str,
        task: TaskSpec,
        upstream: Dict[Any, Any],
        documents: List[AlgorithmDocument],
        previous_code: Optional[str],
        error: Optional[str],
    ) -> str:
        upstream_summary = {key: preview(value, 3500) for key, value in upstream.items()}
        retry = ""
        if error:
            retry = f"\nPrevious code:\n{previous_code}\n\nExecution error:\n{error}\nGenerate corrected code."
        return f"""Original question:
{question}

Current task:
{json.dumps(task.to_dict(), ensure_ascii=False, indent=2)}

Dataset schema and physical columns:
{json.dumps(self.workspace.describe(), ensure_ascii=False, indent=2)}

Upstream results (previews only; full objects are available in inputs):
{json.dumps(upstream_summary, ensure_ascii=False, indent=2)}

Flat retrieved algorithm documentation:
{self.retriever.render(documents)}
{retry}
"""

    def _run_code(self, code: str, upstream: Dict[Any, Any]) -> Any:
        tree = validate_generated_code(code)
        namespace: Dict[str, Any] = {
            "__builtins__": SAFE_BUILTINS,
            "workspace": self.workspace,
            "graph_tool": self.graph_tool,
            "inputs": upstream,
            "pd": pd,
            "np": np,
            "nx": nx,
            "math": math,
            "statistics": statistics,
            "collections": collections,
        }
        started = time.perf_counter()
        exec(compile(tree, "<generated-task>", "exec"), namespace, namespace)
        duration = time.perf_counter() - started
        self.metrics.add_event("python_execution", "generated_code", duration)
        if "result" not in namespace:
            raise ValueError("Generated code did not assign the required variable 'result'")
        return namespace["result"]
