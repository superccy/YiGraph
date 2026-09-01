from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

import networkx as nx
from langgraph.graph import END, START, StateGraph

from .code_executor import TaskExecutionService
from .config import RunConfig
from .datasets import GraphWorkspace
from .llm import OpenAICompatibleLLM, preview
from .metrics import MetricsCollector
from .models import TaskOutcome, TaskSpec
from .prompts import (
    LLMCOMPILER_JOIN_SYSTEM,
    LLMCOMPILER_PLANNER_SYSTEM,
    REACT_PLANNER_SYSTEM,
)
from .retrieval import FlatDocumentationRetriever


@dataclass
class SharedServices:
    config: RunConfig
    llm: OpenAICompatibleLLM
    metrics: MetricsCollector
    workspace: GraphWorkspace
    retriever: FlatDocumentationRetriever
    executor: TaskExecutionService


def create_services(config: RunConfig, workspace: GraphWorkspace) -> SharedServices:
    metrics = workspace.metrics
    retriever = FlatDocumentationRetriever(config.knowledge_base_dir)
    llm = OpenAICompatibleLLM(config.model, metrics)
    executor = TaskExecutionService(config, llm, metrics, workspace, retriever)
    return SharedServices(config, llm, metrics, workspace, retriever, executor)


class CompilerState(TypedDict, total=False):
    question: str
    round_number: int
    docs: str
    feedback: str
    plan: List[TaskSpec]
    outcomes: List[TaskOutcome]
    latest_outcomes: List[TaskOutcome]
    final_answer: str
    done: bool


class ReActState(TypedDict, total=False):
    question: str
    step: int
    docs: str
    action: Dict[str, Any]
    outcomes: List[TaskOutcome]
    final_answer: str
    done: bool


def build_compiler_graph(services: SharedServices):
    def retrieve(state: CompilerState) -> Dict[str, Any]:
        started = time.perf_counter()
        docs = services.retriever.render(
            services.retriever.retrieve(state["question"], services.config.retrieval_top_k)
        )
        services.metrics.add_event("retrieval", "flat_documentation", time.perf_counter() - started)
        return {"docs": docs, "round_number": 1, "outcomes": [], "feedback": "", "done": False}

    def plan(state: CompilerState) -> Dict[str, Any]:
        prior = _render_outcomes(state.get("outcomes", []))
        previous_ids = {outcome.task.id for outcome in state.get("outcomes", [])}
        next_task_id = max(previous_ids, default=0) + 1
        user = f"""User question:
{state['question']}

Dataset schema:
{json.dumps(services.workspace.describe(), ensure_ascii=False, indent=2)}

Flat retrieved documentation:
{state['docs']}

Completed observations from earlier rounds:
{prior}

Replanning feedback:
{state.get('feedback') or 'None; this is the initial plan.'}

The first new task ID must be {next_task_id}. Dependencies may reference prior task IDs
{sorted(previous_ids)} as well as smaller IDs in the new plan.
"""
        payload = _planner_json_with_validation_retry(
            services,
            "compiler_planning",
            LLMCOMPILER_PLANNER_SYSTEM,
            user,
            external_dependency_ids=previous_ids,
            minimum_task_id=next_task_id,
        )
        tasks = _validate_compiler_plan(
            payload.get("tasks", []),
            external_dependency_ids=previous_ids,
            minimum_task_id=next_task_id,
        )
        _write_json(
            services.config.output_dir
            / "artifacts"
            / "llmcompiler"
            / f"round-{state['round_number']:02d}"
            / "plan.json",
            {"raw": payload, "tasks": [task.to_dict() for task in tasks]},
        )
        return {"plan": tasks}

    def execute_dag(state: CompilerState) -> Dict[str, Any]:
        latest = _execute_task_dag(
            services,
            question=state["question"],
            round_number=state["round_number"],
            tasks=state.get("plan", []),
            previous_outcomes=state.get("outcomes", []),
        )
        return {"latest_outcomes": latest, "outcomes": [*state.get("outcomes", []), *latest]}

    def join(state: CompilerState) -> Dict[str, Any]:
        force_finish = state["round_number"] >= services.config.max_plan_rounds
        user = f"""User question:
{state['question']}

All task observations:
{_render_outcomes(state.get('outcomes', []))}

Current plan round: {state['round_number']} / {services.config.max_plan_rounds}
{('This is the last allowed round. Produce the best grounded final answer now.' if force_finish else '')}
"""
        payload = services.llm.json("compiler_join", LLMCOMPILER_JOIN_SYSTEM, user)
        decision = str(payload.get("decision", "")).lower()
        if decision == "finish" or force_finish:
            answer = str(payload.get("answer") or "Execution ended without a grounded final answer.")
            return {"done": True, "final_answer": answer}
        if decision != "replan":
            raise ValueError(f"Invalid compiler join decision: {decision!r}")
        return {
            "done": False,
            "feedback": str(payload.get("feedback") or "Review observations and plan missing work."),
            "round_number": state["round_number"] + 1,
        }

    graph = StateGraph(CompilerState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("plan", plan)
    graph.add_node("execute_dag", execute_dag)
    graph.add_node("join", join)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "plan")
    graph.add_edge("plan", "execute_dag")
    graph.add_edge("execute_dag", "join")
    graph.add_conditional_edges("join", lambda state: END if state.get("done") else "plan")
    return graph.compile()


def build_react_graph(services: SharedServices):
    def retrieve(state: ReActState) -> Dict[str, Any]:
        started = time.perf_counter()
        docs = services.retriever.render(
            services.retriever.retrieve(state["question"], services.config.retrieval_top_k)
        )
        services.metrics.add_event("retrieval", "flat_documentation", time.perf_counter() - started)
        return {"docs": docs, "step": 0, "outcomes": [], "done": False}

    def reason(state: ReActState) -> Dict[str, Any]:
        next_id = state.get("step", 0) + 1
        force_finish = state.get("step", 0) >= services.config.max_react_steps
        user = f"""User question:
{state['question']}

Dataset schema:
{json.dumps(services.workspace.describe(), ensure_ascii=False, indent=2)}

Flat retrieved documentation:
{state['docs']}

Prior action observations:
{_render_outcomes(state.get('outcomes', []))}

The next task ID, if executing, must be {next_id}.
{('The action limit has been reached. You must choose finish and give the best grounded answer.' if force_finish else '')}
"""
        successful_ids = {outcome.task.id for outcome in state.get("outcomes", []) if outcome.success}
        validation_feedback = ""
        for _ in range(3):
            payload = services.llm.json(
                "react_reasoning", REACT_PLANNER_SYSTEM, user + validation_feedback
            )
            try:
                action = str(payload.get("action", "")).lower()
                if force_finish and action != "finish":
                    raise ValueError("action must be finish because max_react_steps was reached")
                if action == "finish":
                    return {
                        "action": payload,
                        "done": True,
                        "final_answer": str(payload.get("answer") or "No grounded final answer was produced."),
                    }
                if action != "execute" or not isinstance(payload.get("task"), dict):
                    raise ValueError("action must be execute with a task object, or finish with an answer")
                task = TaskSpec.from_dict(payload["task"])
                if task.id != next_id:
                    raise ValueError(f"task id must be {next_id}, got {task.id}")
                if any(dependency not in successful_ids for dependency in task.dependencies):
                    raise ValueError(
                        f"task {task.id} references unavailable dependencies {task.dependencies}"
                    )
                return {"action": {**payload, "task": task}, "done": False}
            except Exception as exc:
                validation_feedback = (
                    f"\nYour previous action was invalid: {exc}. Return a corrected complete JSON object."
                )
        raise ValueError(f"ReAct planner failed validation after 3 attempts: {validation_feedback}")

    def execute(state: ReActState) -> Dict[str, Any]:
        task = state["action"]["task"]
        successful = {
            outcome.task.id: outcome.result
            for outcome in state.get("outcomes", [])
            if outcome.success
        }
        upstream = {dependency: successful[dependency] for dependency in task.dependencies}
        outcome = services.executor.execute(
            "react", state.get("step", 0) + 1, state["question"], task, upstream
        )
        return {
            "step": state.get("step", 0) + 1,
            "outcomes": [*state.get("outcomes", []), outcome],
        }

    graph = StateGraph(ReActState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("reason", reason)
    graph.add_node("execute", execute)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "reason")
    graph.add_conditional_edges("reason", lambda state: END if state.get("done") else "execute")
    graph.add_edge("execute", "reason")
    return graph.compile()


def _validate_compiler_plan(
    raw_tasks: Any,
    external_dependency_ids: Optional[set[int]] = None,
    minimum_task_id: int = 1,
) -> List[TaskSpec]:
    if not isinstance(raw_tasks, list):
        raise ValueError("Compiler planner field 'tasks' must be a list")
    tasks = [TaskSpec.from_dict(item) for item in raw_tasks]
    ids = [task.id for task in tasks]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError(f"Task IDs must be unique and strictly increasing: {ids}")
    if ids and ids[0] < minimum_task_id:
        raise ValueError(f"First new task ID must be at least {minimum_task_id}, got {ids[0]}")
    external_dependency_ids = external_dependency_ids or set()
    id_set = set(ids) | external_dependency_ids
    graph = nx.DiGraph()
    graph.add_nodes_from(id_set)
    for task in tasks:
        for dependency in task.dependencies:
            if dependency not in id_set or dependency >= task.id:
                raise ValueError(f"Task {task.id} has invalid dependency {dependency}")
            graph.add_edge(dependency, task.id)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Compiler plan is not a DAG")
    return tasks


def _planner_json_with_validation_retry(
    services: SharedServices,
    purpose: str,
    system: str,
    user: str,
    external_dependency_ids: Optional[set[int]] = None,
    minimum_task_id: int = 1,
) -> Dict[str, Any]:
    error = ""
    for attempt in range(3):
        payload = services.llm.json(purpose, system, user + error)
        try:
            _validate_compiler_plan(
                payload.get("tasks", []),
                external_dependency_ids=external_dependency_ids,
                minimum_task_id=minimum_task_id,
            )
            return payload
        except Exception as exc:
            error = f"\nYour previous JSON plan was invalid: {exc}. Return a corrected complete JSON object."
    raise ValueError(f"Planner failed validation after 3 attempts: {error}")


def _execute_task_dag(
    services: SharedServices,
    question: str,
    round_number: int,
    tasks: List[TaskSpec],
    previous_outcomes: Optional[List[TaskOutcome]] = None,
) -> List[TaskOutcome]:
    by_id = {task.id: task for task in tasks}
    pending = set(by_id)
    results: Dict[int, TaskOutcome] = {
        outcome.task.id: outcome for outcome in (previous_outcomes or [])
    }
    ordered_outcomes: List[TaskOutcome] = []
    historical_inputs = {
        f"history.{index}.task{outcome.task.id}": outcome.result
        for index, outcome in enumerate(previous_outcomes or [])
        if outcome.success
    }
    while pending:
        blocked = [
            task_id
            for task_id in pending
            if any(dep in results and not results[dep].success for dep in by_id[task_id].dependencies)
        ]
        for task_id in sorted(blocked):
            outcome = TaskOutcome(
                task=by_id[task_id],
                success=False,
                error="A dependency failed; task was not executed and requires replanning.",
            )
            results[task_id] = outcome
            ordered_outcomes.append(outcome)
            pending.remove(task_id)
        ready = [
            by_id[task_id]
            for task_id in sorted(pending)
            if all(dep in results and results[dep].success for dep in by_id[task_id].dependencies)
        ]
        if not ready:
            if pending:
                raise RuntimeError(f"DAG scheduler deadlock with pending tasks: {sorted(pending)}")
            break
        with ThreadPoolExecutor(max_workers=min(services.config.max_parallel_tasks, len(ready))) as pool:
            futures = {}
            for task in ready:
                upstream = dict(historical_inputs)
                upstream.update(
                    {dependency: results[dependency].result for dependency in task.dependencies}
                )
                future = pool.submit(
                    services.executor.execute,
                    "llmcompiler",
                    round_number,
                    question,
                    task,
                    upstream,
                )
                futures[future] = task.id
            wave: Dict[int, TaskOutcome] = {}
            for future in as_completed(futures):
                wave[futures[future]] = future.result()
        for task_id in sorted(wave):
            results[task_id] = wave[task_id]
            ordered_outcomes.append(wave[task_id])
            pending.remove(task_id)
    return ordered_outcomes


def _render_outcomes(outcomes: List[TaskOutcome]) -> str:
    if not outcomes:
        return "[]"
    rendered = []
    for outcome in outcomes:
        rendered.append(
            {
                "task": outcome.task.to_dict(),
                "success": outcome.success,
                "result": preview(outcome.result, 5000) if outcome.success else None,
                "error": outcome.error,
                "attempts": outcome.attempts,
                "duration_seconds": outcome.duration_seconds,
                "artifact_dir": outcome.artifact_dir,
            }
        )
    return json.dumps(rendered, ensure_ascii=False, indent=2)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
