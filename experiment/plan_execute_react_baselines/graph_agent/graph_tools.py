from __future__ import annotations

import inspect
import time
from typing import Any, Callable, Dict, Iterable, Optional

import networkx as nx

from .networkx_registry import (
    ALGORITHMS_TO_EXCLUDE,
    MODULES_TO_SCAN,
    UNDIRECTED_ONLY_ALGORITHMS,
)

from .datasets import GraphWorkspace
from .metrics import MetricsCollector


class NetworkXToolRuntime:
    """Programmatic facade over the same NetworkX functions as the MCP registry."""

    def __init__(
        self,
        workspace: GraphWorkspace,
        allowed_algorithm_ids: Iterable[str],
        metrics: MetricsCollector,
    ) -> None:
        self.workspace = workspace
        self.allowed = set(allowed_algorithm_ids)
        self.metrics = metrics
        self.functions = self._discover_functions()

    @staticmethod
    def _discover_functions() -> Dict[str, Callable[..., Any]]:
        discovered: Dict[str, Callable[..., Any]] = {}
        for module in MODULES_TO_SCAN:
            for name, function in inspect.getmembers(module, inspect.isfunction):
                if name.startswith("_") or name in ALGORITHMS_TO_EXCLUDE or name in discovered:
                    continue
                try:
                    if "G" not in inspect.signature(function).parameters:
                        continue
                except (TypeError, ValueError):
                    continue
                discovered[name] = function
        return discovered

    def __call__(
        self,
        algorithm: str,
        *,
        graph: Optional[nx.Graph] = None,
        **parameters: Any,
    ) -> Any:
        if algorithm.startswith("run_"):
            algorithm = algorithm[4:]
        if algorithm not in self.allowed:
            raise ValueError(f"Algorithm '{algorithm}' is outside algorithms.yaml")
        function = self.functions.get(algorithm)
        if function is None:
            raise ValueError(f"Algorithm '{algorithm}' is documented but not registered by the NetworkX tool registry")
        selected_graph = graph if graph is not None else self.workspace.graph()
        function = self._adapt_function(algorithm, selected_graph, function)
        if algorithm in UNDIRECTED_ONLY_ALGORITHMS and selected_graph.is_directed():
            if UNDIRECTED_ONLY_ALGORITHMS[algorithm] is None:
                selected_graph = selected_graph.to_undirected()
        signature = inspect.signature(function)
        kwargs = {key: value for key, value in parameters.items() if key in signature.parameters}
        kwargs["G"] = selected_graph
        started = time.perf_counter()
        try:
            return function(**kwargs)
        finally:
            self.metrics.add_event(
                "graph_tool",
                algorithm,
                time.perf_counter() - started,
                parameters=sorted(parameters),
                nodes=selected_graph.number_of_nodes(),
                edges=selected_graph.number_of_edges(),
            )

    def _adapt_function(
        self,
        algorithm: str,
        graph: nx.Graph,
        function: Callable[..., Any],
    ) -> Callable[..., Any]:
        if algorithm not in UNDIRECTED_ONLY_ALGORITHMS or not graph.is_directed():
            return function
        alternative = UNDIRECTED_ONLY_ALGORITHMS[algorithm]
        if alternative:
            replacement = self.functions.get(alternative)
            if replacement is None:
                replacement = getattr(nx.algorithms.components, alternative, None)
            if replacement is not None:
                return replacement
        return function

    def describe(self, algorithm: str) -> Dict[str, Any]:
        function = self.functions.get(algorithm.removeprefix("run_"))
        if function is None:
            raise KeyError(algorithm)
        return {
            "algorithm": algorithm.removeprefix("run_"),
            "signature": str(inspect.signature(function)),
            "description": inspect.getdoc(function) or "",
        }
