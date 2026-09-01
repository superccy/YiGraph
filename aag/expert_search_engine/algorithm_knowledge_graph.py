"""Algorithm knowledge graph traversal and executable-candidate selection."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a", "all", "also", "an", "and", "any", "are", "as", "at", "be", "between",
    "based", "by", "can", "compute", "current", "data", "default", "does",
    "calculate", "each", "find", "for", "from", "g", "given", "graph", "graphs",
    "has", "have", "how", "identify", "if", "in", "is", "it", "method",
    "network", "networks", "node",
    "nodes", "of", "on", "or", "output", "result", "return", "returns", "the",
    "their", "this", "to", "two", "using", "value", "values", "where", "which", "with",
}


@dataclass(frozen=True)
class AlgorithmEdge:
    target: str
    similarity: float


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _tokens(value: Any) -> Set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(_flatten_text(value).lower().replace("_", " "))
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _algorithm_id_tokens(algorithm: Mapping[str, Any]) -> Set[str]:
    return _tokens(algorithm.get("id", ""))


def _algorithm_body_tokens(algorithm: Mapping[str, Any]) -> Set[str]:
    return _tokens(
        {
            "scenario": algorithm.get("Application_scenario"),
            "principles": algorithm.get("Principles"),
            "questions": algorithm.get("solvable_questions"),
        }
    )


def semantic_similarity(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> float:
    """Estimate a semantic edge weight from registered algorithm metadata."""
    id_similarity = _jaccard(_algorithm_id_tokens(left), _algorithm_id_tokens(right))
    body_similarity = _jaccard(
        _algorithm_body_tokens(left),
        _algorithm_body_tokens(right),
    )
    return 0.6 * id_similarity + 0.4 * body_similarity


def query_relevance(question: str, algorithm: Mapping[str, Any]) -> float:
    """Return a lexical relevance score with extra weight on algorithm names."""
    query_tokens = _tokens(question)
    if not query_tokens:
        return 0.0
    id_matches = len(query_tokens & _algorithm_id_tokens(algorithm))
    body_matches = len(query_tokens & _algorithm_body_tokens(algorithm))
    return (3.0 * id_matches + body_matches) / (3.0 * len(query_tokens))


def algorithm_complexity(algorithm: Mapping[str, Any]) -> str:
    principles = algorithm.get("Principles")
    if isinstance(principles, Mapping):
        complexity = principles.get("time_complexity")
        if complexity:
            return str(complexity)
    if isinstance(principles, str):
        return principles
    complexity = algorithm.get("time_complexity")
    return str(complexity) if complexity else ""


def complexity_rank(
    complexity: str,
    weighted: Optional[bool] = None,
) -> Tuple[float, int, int]:
    """Map heterogeneous Big-O descriptions to a stable asymptotic ordering."""
    text = (complexity or "").lower()
    if weighted is False and "for unweighted" in text:
        text = text.split("for unweighted", 1)[0]
    elif weighted is True and "for weighted" in text:
        weighted_prefix = text.split("for weighted", 1)[0]
        text = weighted_prefix.rsplit(",", 1)[-1]
    text = text.replace("|", "").replace("**", "^").replace("·", "*")
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return (math.inf, 1, 0)

    has_big_o = "o(" in compact
    if "factorial" in text or re.search(r"\bn\s*!", text):
        return (11.0, 0, len(text))
    if "exponential" in text or re.search(r"(?:2|3)\s*\^\s*\(?[vn]", text):
        return (10.0, 0, len(text))

    explicit_powers = [
        float(power)
        for power in re.findall(r"(?:v|e|n|m)\^([0-9]+(?:\.[0-9]+)?)", compact)
    ]
    degree = max(explicit_powers, default=0.0)

    if re.search(r"(?:v|n)\^2\*(?:e|m)|(?:e|m)\^2\*(?:v|n)", compact):
        degree = max(degree, 3.0)
    elif re.search(r"(?:v|n)\*(?:e|m)|(?:e|m)\*(?:v|n)", compact):
        degree = max(degree, 2.0)
    elif re.search(r"(?:v|n)\*\((?:v|n)\+(?:e|m)\)", compact):
        degree = max(degree, 2.0)
    elif re.search(r"o\((?:n|v)(?:m|e)\)", compact):
        degree = max(degree, 2.0)

    if "cubic" in text:
        degree = max(degree, 3.0)
    elif "quadratic" in text:
        degree = max(degree, 2.0)
    elif "linear" in text:
        degree = max(degree, 1.0)

    contains_size_variable = bool(re.search(r"(?:^|[^a-z])(?:v|e|n|m)(?:[^a-z]|$)", text))
    if degree == 0.0 and contains_size_variable:
        degree = 1.0
    if "log" in text and degree > 0.0:
        degree += 0.5
    if re.search(r"o\(1\)", compact):
        degree = 0.0

    unknown_phrases = (
        "does not state",
        "not explicitly state",
        "depends on",
        "computationally expensive",
        "cost is dominated",
    )
    is_unknown = not has_big_o and any(phrase in text for phrase in unknown_phrases)
    if is_unknown or (degree == 0.0 and not re.search(r"o\(1\)", compact)):
        return (math.inf, 1, len(text))
    return (degree, 0, len(text))


def _constraint_accepts(actual: bool, requirement: Any, exact: bool) -> bool:
    if requirement is None:
        return True
    if isinstance(requirement, str):
        normalized = requirement.strip().lower()
        if normalized in {"both", "any", "supported"}:
            return True
        if normalized == "true":
            requirement = True
        elif normalized == "false":
            requirement = False
        else:
            return True
    if not isinstance(requirement, bool):
        return True
    if exact:
        return actual == requirement
    return not actual or requirement


class AlgorithmKnowledgeGraph:
    """Directed k-nearest-neighbor graph over algorithms in each task category."""

    def __init__(
        self,
        task_index: Mapping[str, Mapping[str, Any]],
        algorithm_index: Mapping[str, Mapping[str, Any]],
        max_neighbors: int = 5,
    ) -> None:
        self.task_index = task_index
        self.algorithm_index = algorithm_index
        self.max_neighbors = max(1, max_neighbors)
        self.adjacency: Dict[str, List[AlgorithmEdge]] = {}
        self._build_edges()

    def _build_edges(self) -> None:
        for task in self.task_index.values():
            algorithm_ids = [
                algorithm_id
                for algorithm_id in task.get("algorithm", [])
                if algorithm_id in self.algorithm_index
            ]
            for source_id in algorithm_ids:
                source = self.algorithm_index[source_id]
                scored = []
                for target_id in algorithm_ids:
                    if source_id == target_id:
                        continue
                    score = semantic_similarity(source, self.algorithm_index[target_id])
                    if score > 0.0:
                        scored.append(AlgorithmEdge(target_id, score))
                scored.sort(key=lambda edge: (-edge.similarity, edge.target))
                self.adjacency[source_id] = scored[: self.max_neighbors]

    def most_relevant_algorithm(self, task_type_id: str, question: str) -> Optional[str]:
        algorithm_ids = self.task_index.get(task_type_id, {}).get("algorithm", [])
        candidates = [
            algorithm_id
            for algorithm_id in algorithm_ids
            if algorithm_id in self.algorithm_index
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda algorithm_id: (
                query_relevance(question, self.algorithm_index[algorithm_id]),
                -candidates.index(algorithm_id),
            ),
        )

    def dfs_candidates(
        self,
        task_type_id: str,
        seed_algorithm_id: str,
        question: str,
        max_depth: int = 3,
        max_candidates: int = 12,
    ) -> List[Dict[str, Any]]:
        """Traverse relevant semantic branches from an initial algorithm seed."""
        category_ids = {
            algorithm_id
            for algorithm_id in self.task_index.get(task_type_id, {}).get("algorithm", [])
            if algorithm_id in self.algorithm_index
        }
        if seed_algorithm_id not in category_ids:
            return []

        seed = self.algorithm_index[seed_algorithm_id]
        seed_relevance = query_relevance(question, seed)
        relevance_floor = max(0.04, seed_relevance * 0.35)
        query_tokens = _tokens(question)
        seed_tokens = _algorithm_id_tokens(seed) | _algorithm_body_tokens(seed)
        query_anchors = query_tokens & seed_tokens
        stack: List[Tuple[str, int]] = [(seed_algorithm_id, 0)]
        visited: Set[str] = set()
        candidates: List[Dict[str, Any]] = []

        while stack and len(candidates) < max_candidates:
            algorithm_id, depth = stack.pop()
            if algorithm_id in visited:
                continue
            visited.add(algorithm_id)
            candidates.append(dict(self.algorithm_index[algorithm_id]))
            if depth >= max_depth:
                continue

            relevant_neighbors = []
            for edge in self.adjacency.get(algorithm_id, []):
                if edge.target in visited or edge.target not in category_ids:
                    continue
                neighbor = self.algorithm_index[edge.target]
                relevance = query_relevance(question, neighbor)
                seed_similarity = semantic_similarity(seed, neighbor)
                neighbor_tokens = (
                    _algorithm_id_tokens(neighbor) | _algorithm_body_tokens(neighbor)
                )
                anchor_coverage = (
                    len(query_anchors & neighbor_tokens) / len(query_anchors)
                    if query_anchors
                    else 0.0
                )
                if query_anchors:
                    branch_is_relevant = anchor_coverage >= 0.8
                else:
                    branch_is_relevant = (
                        relevance >= relevance_floor and seed_similarity >= 0.1
                    )
                if branch_is_relevant:
                    relevant_neighbors.append((edge.target, depth + 1, relevance, edge.similarity))

            relevant_neighbors.sort(key=lambda item: (item[2], item[3], item[0]))
            for target_id, next_depth, _, _ in relevant_neighbors:
                stack.append((target_id, next_depth))

        return candidates

    def filter_by_graph_constraints(
        self,
        candidates: Sequence[Mapping[str, Any]],
        graph_schema: Optional[Mapping[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
        """Apply graph-type and optional engine constraints to DFS candidates."""
        if not graph_schema:
            return [dict(candidate) for candidate in candidates], {}

        properties = graph_schema.get("graph_properties") or {}
        available_engines = {
            str(engine).lower() for engine in graph_schema.get("available_engines", [])
        }
        feasible: List[Dict[str, Any]] = []
        rejected: Dict[str, List[str]] = {}

        for candidate in candidates:
            algorithm_id = str(candidate.get("id", ""))
            deployment = candidate.get("Deployment_method") or {}
            graph_type = deployment.get("graph_type") or {}
            reasons: List[str] = []

            directed = bool(properties.get("directed", False))
            if not _constraint_accepts(directed, graph_type.get("directed"), exact=True):
                reasons.append("directed")
            for property_name in ("multigraph", "weighted", "heterogeneous"):
                actual = bool(properties.get(property_name, False))
                if not _constraint_accepts(
                    actual,
                    graph_type.get(property_name),
                    exact=False,
                ):
                    reasons.append(property_name)

            support_engine = str(deployment.get("support_engine") or "").lower()
            if available_engines and support_engine and support_engine not in available_engines:
                reasons.append("support_engine")

            if reasons:
                rejected[algorithm_id] = reasons
            else:
                feasible.append(dict(candidate))

        return feasible, rejected

    @staticmethod
    def select_lowest_complexity(
        candidates: Sequence[Mapping[str, Any]],
        graph_schema: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        graph_properties = (graph_schema or {}).get("graph_properties") or {}
        weighted = graph_properties.get("weighted")
        weighted = weighted if isinstance(weighted, bool) else None
        _, selected = min(
            enumerate(candidates),
            key=lambda item: (
                complexity_rank(
                    algorithm_complexity(item[1]),
                    weighted=weighted,
                )[:2],
                item[0],
            ),
        )
        return dict(selected)
