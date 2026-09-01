"""Deterministic baselines for failure root-cause localization.

This module does not read annotations. Ground-truth labels are intentionally
restricted to the separate evaluation entry point.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple


EXPLICIT_FAILURE_ACTION = re.compile(r"(?:^|_)failed$", re.IGNORECASE)
EXPLICIT_FAILURE_TEXT = re.compile(
    r"(?:"
    r"traceback|\bexception\b|\btimeout\b|"
    r"\b(?:execution|analysis|processing|validation|task|attempt) failed\b|"
    r"\bfailed (?:after|again|due to|to find|on attempt)\b|"
    r"\ball (?:attempts )?failed\b|"
    r"missing required (?:field|parameter)|"
    r"(?:task|execution|analysis|processing|validation|calling|"
    r"调用|执行|处理|解析|验证|任务)失败|"
    r"缺少字段|找不到字段|错误[:：]"
    r")",
    re.IGNORECASE,
)

RULE_PATTERNS = {
    "missing_field_or_parameter": re.compile(
        r"(?:"
        r"(?:missing|required|缺少|找不到|未找到|failed to find).{0,40}"
        r"(?:field|字段|parameter|参数)|"
        r"(?:field|字段|parameter|参数).{0,40}"
        r"(?:missing|缺少|not found|找不到|未找到)|"
        r"argument validation failed|invalid argument format"
        r")",
        re.IGNORECASE,
    ),
    "type_or_structure": re.compile(
        r"(?:"
        r"object has no attribute|nonetype|not iterable|"
        r"not enough values to unpack|too many values to unpack|"
        r"\btypeerror\b|\battributeerror\b|"
        r"类型(?:不匹配|错误)|结构(?:不匹配|错误)"
        r")",
        re.IGNORECASE,
    ),
    "graph_or_schema_compatibility": re.compile(
        r"(?:"
        r"not implemented for (?:multi)?(?:di)?graph type|"
        r"undefined for (?:the )?null graph|"
        r"graph is not strongly connected|not in (?:the )?(?:di)?graph|"
        r"target node .{0,80} not found|source node .{0,80} not found|"
        r"schema (?:mismatch|violation)|"
        r"不满足.{0,30}(?:schema|inputspec|outputspec)|"
        r"(?:schema|inputspec|outputspec).{0,30}不满足"
        r")",
        re.IGNORECASE,
    ),
    "dependency_resolution": re.compile(
        r"(?:"
        r"dependency (?:analysis|resolution).{0,80}failed|"
        r"analyze_dependency.{0,80}failed|"
        r"依赖(?:分析|解析).{0,80}失败"
        r")",
        re.IGNORECASE,
    ),
}

REPORTER_ACTIONS = ("finalize", "report", "summary", "generate_report")


@dataclass(frozen=True)
class Event:
    step: int
    roles: Tuple[str, ...]
    actions: Tuple[str, ...]
    contexts: Tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join((*self.actions, *self.contexts))


@dataclass(frozen=True)
class Edge:
    source: int
    target: int
    edge_type: str


@dataclass(frozen=True)
class TraceGraph:
    events: Mapping[int, Event]
    edges: Tuple[Edge, ...]


def parse_events(raw_trace: Sequence[Mapping]) -> Dict[int, Event]:
    """Aggregate raw log entries by integer step."""
    grouped: Dict[int, Dict[str, List[str]]] = defaultdict(
        lambda: {"roles": [], "actions": [], "contexts": []}
    )
    for item in raw_trace:
        if not isinstance(item, Mapping) or "step" not in item:
            continue
        try:
            step = int(item["step"])
        except (TypeError, ValueError):
            continue
        grouped[step]["roles"].append(str(item.get("role", "")))
        grouped[step]["actions"].append(str(item.get("action", "")))
        grouped[step]["contexts"].append(str(item.get("context", "")))

    return {
        step: Event(
            step=step,
            roles=tuple(values["roles"]),
            actions=tuple(values["actions"]),
            contexts=tuple(values["contexts"]),
        )
        for step, values in grouped.items()
    }


def build_trace_graph(raw_trace: Sequence[Mapping]) -> TraceGraph:
    """Build chronological and explicitly declared dependency edges."""
    events = parse_events(raw_trace)
    steps = sorted(events)
    edge_keys: Set[Tuple[int, int, str]] = set()

    for source, target in zip(steps, steps[1:]):
        edge_keys.add((source, target, "time"))

    dependency_patterns = (
        r"parents?=\[([^\]]+)\]",
        r"parent[s]?[:：]\s*([0-9,，、\s]+)",
        r"上游节点[:：]\s*([0-9,，、\s]+)",
        r"依赖于步骤\[([^\]]+)\]",
        r"depends_on[:=]\s*\[([^\]]+)\]",
        r"from_step[:=]\s*(\d+)",
    )
    for target, event in events.items():
        for pattern in dependency_patterns:
            for match in re.finditer(pattern, event.text, flags=re.IGNORECASE):
                for number in re.findall(r"\d+", match.group(1)):
                    source = int(number)
                    if source in events and source != target:
                        edge_keys.add((source, target, "dependency"))

    return TraceGraph(
        events=events,
        edges=tuple(Edge(*key) for key in sorted(edge_keys)),
    )


def failed_node_localization(
    graph: TraceGraph, candidate_steps: Iterable[int]
) -> Set[int]:
    """Return every candidate node with an explicit failure signal."""
    candidates = set(candidate_steps)
    failed = set()
    for step in candidates:
        event = graph.events.get(step)
        if event is None:
            continue
        action_failed = any(
            EXPLICIT_FAILURE_ACTION.search(action.strip()) for action in event.actions
        )
        text_failed = bool(EXPLICIT_FAILURE_TEXT.search(event.text))
        only_zero_failures = (
            bool(re.search(r"失败\s*0\s*条", event.text)) and not action_failed
        )
        if action_failed or (text_failed and not only_zero_failures):
            failed.add(step)
    return failed


def _is_reporter_only(event: Event) -> bool:
    roles = " ".join(event.roles).lower()
    actions = " ".join(event.actions).lower()
    return "reporter" in roles or any(token in actions for token in REPORTER_ACTIONS)


def rule_based_dependency_tracking(
    graph: TraceGraph,
    candidate_steps: Iterable[int],
    failed_steps: Iterable[int] | None = None,
) -> Tuple[Set[int], Dict[int, List[str]]]:
    """Select nodes with explicit contract/dependency violation evidence."""
    candidates = set(candidate_steps)
    failed = (
        set(failed_steps)
        if failed_steps is not None
        else failed_node_localization(graph, candidates)
    )
    eligible = {step for step in candidates if failed and step <= max(failed)}
    selected: Set[int] = set()
    evidence: Dict[int, List[str]] = {}

    for step in eligible:
        event = graph.events.get(step)
        if event is None or _is_reporter_only(event):
            continue
        matched = [
            name for name, pattern in RULE_PATTERNS.items() if pattern.search(event.text)
        ]
        if matched:
            selected.add(step)
            evidence[step] = matched

    if not selected:
        selected = set(failed)
        evidence = {step: ["failed_node_fallback"] for step in sorted(selected)}
    return selected, evidence


def hierarchical_backtracking(
    graph: TraceGraph,
    candidate_steps: Iterable[int],
    failed_steps: Iterable[int] | None = None,
) -> Tuple[Set[int], Dict]:
    """Retain failed nodes and add exactly one upstream error layer.

    All explicit failed nodes form the base candidates. The latest failed node
    is the current layer L1. Reverse breadth-first traversal then finds the
    first upstream layer containing another explicit failure signal. All nodes
    in that one layer are added; intermediate layers are excluded.
    """
    candidates = set(candidate_steps)
    failed = (
        set(failed_steps)
        if failed_steps is not None
        else failed_node_localization(graph, candidates)
    )
    if not failed:
        return set(), {"selected_depth": None, "fallback": "no_explicit_failure"}

    reverse: Dict[int, Set[int]] = defaultdict(set)
    for edge in graph.edges:
        if edge.edge_type in {"time", "dependency"}:
            reverse[edge.target].add(edge.source)

    base = set(failed)
    frontier = {max(failed)}
    visited = set(frontier)
    depth = 1
    while frontier:
        next_layer: Set[int] = set()
        for step in frontier:
            next_layer.update(reverse.get(step, set()))
        next_layer = (next_layer - visited) & candidates
        if not next_layer:
            break
        depth += 1
        if next_layer & failed:
            return base | next_layer, {
                "selected_depth": depth,
                "trigger_failed_nodes": sorted(next_layer & failed),
                "selected_upstream_layer": sorted(next_layer),
                "fallback": None,
            }
        visited.update(next_layer)
        frontier = next_layer

    return base, {
        "selected_depth": 1,
        "trigger_failed_nodes": [max(failed)],
        "selected_upstream_layer": [],
        "fallback": "no_upstream_layer_with_explicit_failure",
    }

