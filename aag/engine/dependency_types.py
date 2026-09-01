from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from aag.expert_search_engine.database.datatype import GraphData


class RuntimeDependencyValueType(str, Enum):
    GRAPH = "graph"
    NODE_SET = "node_set"
    EDGE_SET = "edge_set"
    MAPPING = "mapping"
    SEQUENCE = "sequence"
    SCALAR = "scalar"
    UNKNOWN = "unknown"


def classify_runtime_dependency_value(
    value: Any,
    *,
    field_key: str = "",
    declared_type: Any = None,
) -> RuntimeDependencyValueType:
    key = (field_key or "").lower()
    declared = str(declared_type or "").lower()

    if isinstance(value, GraphData):
        return RuntimeDependencyValueType.GRAPH
    if isinstance(value, Mapping):
        keys = set(value)
        if {"nodes", "edges"} <= keys or {"vertices", "edges"} <= keys:
            return RuntimeDependencyValueType.GRAPH
        return RuntimeDependencyValueType.MAPPING
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if not items:
            if "edge" in key or "edge" in declared:
                return RuntimeDependencyValueType.EDGE_SET
            if any(token in key for token in ("node", "path", "community", "neighbor")):
                return RuntimeDependencyValueType.NODE_SET
            return RuntimeDependencyValueType.SEQUENCE
        first = items[0]
        if isinstance(first, Mapping) and ({"src", "dst"} <= set(first) or {"source", "target"} <= set(first)):
            return RuntimeDependencyValueType.EDGE_SET
        if isinstance(first, (list, tuple)) and len(first) == 2 and "communit" not in key:
            return RuntimeDependencyValueType.EDGE_SET
        if "edge" in key or "edge" in declared:
            return RuntimeDependencyValueType.EDGE_SET
        if any(token in key for token in ("node", "path", "community", "neighbor", "component")):
            return RuntimeDependencyValueType.NODE_SET
        return RuntimeDependencyValueType.SEQUENCE
    if value is None:
        return RuntimeDependencyValueType.UNKNOWN
    return RuntimeDependencyValueType.SCALAR


def can_use_as_graph(value_type: RuntimeDependencyValueType) -> bool:
    return value_type in {
        RuntimeDependencyValueType.GRAPH,
        RuntimeDependencyValueType.NODE_SET,
        RuntimeDependencyValueType.EDGE_SET,
        RuntimeDependencyValueType.SEQUENCE,
    }
