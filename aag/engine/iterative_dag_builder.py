"""Utilities for task-category-guided iterative DAG planning."""

from __future__ import annotations

from typing import Any, Callable, Dict, List


class IterativePlanningError(ValueError):
    """Raised when an iterative planner response cannot form a valid DAG node."""


PlanNextCallable = Callable[
    [str, List[Dict[str, Any]], List[Dict[str, Any]]],
    Dict[str, Any],
]


def build_iterative_subquery_plan(
    query: str,
    task_types: List[Dict[str, Any]],
    plan_next: PlanNextCallable,
    max_iterations: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build a task-category DAG by consuming one semantic query segment per turn.

    The LLM-facing ``plan_next`` callback only decides the next leaf task, its
    dependencies, and the unconsumed remainder. This function owns identifiers
    and validates that every emitted dependency points backward in the DAG.
    """
    remaining_query = (query or "").strip()
    if not remaining_query:
        raise IterativePlanningError("Cannot plan an empty query")
    if max_iterations < 1:
        raise IterativePlanningError("max_iterations must be positive")

    valid_task_ids = {
        str(task_type.get("id"))
        for task_type in task_types
        if task_type.get("id") is not None
    }
    if not valid_task_ids:
        raise IterativePlanningError("No registered task categories are available")

    subqueries: List[Dict[str, Any]] = []
    seen_segments = set()

    for _ in range(max_iterations):
        normalized_segment = " ".join(remaining_query.lower().split())
        if normalized_segment in seen_segments:
            raise IterativePlanningError(
                "The iterative planner did not consume the remaining query"
            )
        seen_segments.add(normalized_segment)

        response = plan_next(remaining_query, list(subqueries), task_types)
        if not isinstance(response, dict):
            raise IterativePlanningError("The iterative planner must return an object")

        raw_subquery = response.get("subquery")
        if not isinstance(raw_subquery, dict):
            raise IterativePlanningError("Planner response is missing a subquery object")

        question = str(raw_subquery.get("query") or "").strip()
        if not question:
            raise IterativePlanningError("Planner subquery is missing query text")

        task_type_id = str(raw_subquery.get("task_type_id") or "").strip()
        if task_type_id not in valid_task_ids:
            raise IterativePlanningError(
                f"Planner selected unknown task category: {task_type_id or '<empty>'}"
            )

        query_id = f"q{len(subqueries) + 1}"
        existing_ids = {item["id"] for item in subqueries}
        raw_dependencies = raw_subquery.get("depends_on") or []
        if not isinstance(raw_dependencies, list):
            raise IterativePlanningError("subquery.depends_on must be a list")

        dependencies: List[str] = []
        for dependency in raw_dependencies:
            dependency_id = str(dependency).strip()
            if dependency_id not in existing_ids:
                raise IterativePlanningError(
                    f"Subquery {query_id} references unavailable dependency {dependency_id}"
                )
            if dependency_id not in dependencies:
                dependencies.append(dependency_id)

        subqueries.append(
            {
                "id": query_id,
                "query": question,
                "depends_on": dependencies,
                "task_type_id": task_type_id,
            }
        )

        next_remaining = str(response.get("remaining_query") or "").strip()
        done = response.get("done") is True or not next_remaining
        if done:
            return {"subqueries": subqueries}

        remaining_query = next_remaining

    raise IterativePlanningError(
        f"Iterative planning exceeded the {max_iterations}-step safety limit"
    )
