from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    import networkx as nx
except ImportError:  # pragma: no cover
    nx = None


DEFAULT_ROLE_MAPPING = {
    "Task planner": "任务理解与DAG规划Agent",
    "Algorithm expert": "算法匹配Agent",
    "Executor": "节点执行编排Agent",
    "Dependency Resolver": "依赖解析与数据适配Agent",
    "Reporter": "结果综合与报告生成Agent",
}

FAILURE_PATTERNS = (
    r"\bfailed\b",
    r"\berror\b",
    r"\bexception\b",
    r"失败(?!\s*0\s*条)",
    r"异常",
    r"not found",
    r"缺少字段",
)

SUCCESS_PATTERNS = (
    r"\bsuccess\b",
    r"completed",
    r"完成",
    r"executed successfully",
    r"生成成功",
)


@dataclass
class LogNode:
    step: int
    roles: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    contexts: List[str] = field(default_factory=list)
    raw_entries: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    status: str = "unknown"
    is_failed: bool = False


@dataclass
class LogEdge:
    source: int
    target: int
    edge_type: str
    reason: str = ""


class WorkflowLogGraph:
    """把 JSON 日志转换成按 step 聚合的图。"""

    def __init__(
        self,
        role_mapping: Optional[Dict[str, str]] = None,
        use_llm: bool = False,
        llm_client: Any = None,
    ) -> None:
        self.role_mapping = dict(DEFAULT_ROLE_MAPPING)
        if role_mapping:
            self.role_mapping.update(role_mapping)

        self.use_llm = use_llm
        self.llm_client = llm_client

        self.role_map_record: Dict[str, str] = {}
        self.nodes: Dict[int, LogNode] = {}
        self.edges: List[LogEdge] = []
        self.raw_entries: List[Dict[str, Any]] = []

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        role_mapping: Optional[Dict[str, str]] = None,
        use_llm: bool = False,
        llm_client: Any = None,
    ) -> "WorkflowLogGraph":
        graph = cls(role_mapping=role_mapping, use_llm=use_llm, llm_client=llm_client)
        return graph.build(load_log_entries(file_path))

    def build(self, entries: Sequence[Dict[str, Any]]) -> "WorkflowLogGraph":
        self.raw_entries = [entry for entry in entries if isinstance(entry, dict)]
        self.role_map_record = {}
        self.nodes = {}
        self.edges = []

        for entry in self.raw_entries:
            if "step" not in entry:
                self._merge_role_mapping(entry)
                continue

            step = self._safe_int(entry.get("step"))
            if step is None:
                continue

            node = self.nodes.setdefault(step, LogNode(step=step))
            role = self._normalize_role(entry.get("role"))
            action = self._normalize_action(entry.get("action"), entry.get("context"))
            context = self._clean_text(entry.get("context"))

            if role:
                node.roles.append(role)
            if action:
                node.actions.append(action)
            if context:
                node.contexts.append(context)
            node.raw_entries.append(entry)

        for node in self.nodes.values():
            node.roles = self._deduplicate_preserve_order(node.roles)
            node.actions = self._deduplicate_preserve_order(node.actions)
            node.contexts = self._deduplicate_preserve_order(node.contexts)
            node.is_failed = self._has_failure_signal("\n".join(node.actions), "\n".join(node.contexts))
            node.status = self._infer_status(node)
            node.summary = self._summarize_node(node)

        self._build_edges()
        return self

    def to_dict(self) -> Dict[str, Any]:
        nodes = []
        for step in sorted(self.nodes):
            node = self.nodes[step]
            nodes.append(
                {
                    "step": node.step,
                    "roles": node.roles,
                    "actions": node.actions,
                    "contexts": node.contexts,
                    "summary": node.summary,
                    "status": node.status,
                    "is_failed": node.is_failed,
                    "raw_entry_count": len(node.raw_entries),
                }
            )

        edges = [
            {
                "source": edge.source,
                "target": edge.target,
                "type": edge.edge_type,
                "reason": edge.reason,
            }
            for edge in self.edges
        ]

        return {
            "role_mapping": self.role_map_record or self.role_mapping,
            "nodes": nodes,
            "edges": edges,
        }

    def to_networkx(self):
        if nx is None:
            raise ImportError("networkx 未安装，无法导出为图对象")

        graph = nx.DiGraph()
        for step in sorted(self.nodes):
            node = self.nodes[step]
            graph.add_node(
                step,
                step=node.step,
                roles=node.roles,
                actions=node.actions,
                contexts=node.contexts,
                summary=node.summary,
                status=node.status,
                is_failed=node.is_failed,
            )

        for edge in self.edges:
            graph.add_edge(edge.source, edge.target, type=edge.edge_type, reason=edge.reason)

        return graph

    def get_step_node(self, step: int) -> Optional[LogNode]:
        return self.nodes.get(step)

    def get_nodes_by_role(self, role: str) -> List[LogNode]:
        normalized = self._normalize_role(role)
        result = []
        for node in self.nodes.values():
            if normalized in node.roles or role in node.roles:
                result.append(node)
        return sorted(result, key=lambda item: item.step)

    def get_edges_by_type(self, edge_type: str) -> List[LogEdge]:
        return [edge for edge in self.edges if edge.edge_type == edge_type]

    def save_json(self, output_path: str | Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def _merge_role_mapping(self, entry: Dict[str, Any]) -> None:
        for key, value in entry.items():
            if isinstance(key, str) and isinstance(value, str):
                self.role_map_record[key] = value

    def _build_edges(self) -> None:
        sorted_steps = sorted(self.nodes)
        seen_edges: Set[Tuple[int, int, str]] = set()

        for index in range(len(sorted_steps) - 1):
            source = sorted_steps[index]
            target = sorted_steps[index + 1]
            self._add_edge(seen_edges, source, target, "time", "按 step 顺序连接")

        for step, node in self.nodes.items():
            dependency_steps = self._extract_dependency_steps(node)
            for source in sorted(dependency_steps):
                if source == step or source not in self.nodes:
                    continue
                self._add_edge(
                    seen_edges,
                    source,
                    step,
                    "dependency",
                    self._dependency_reason(node, source),
                )

    def _add_edge(
        self,
        seen_edges: Set[Tuple[int, int, str]],
        source: int,
        target: int,
        edge_type: str,
        reason: str,
    ) -> None:
        edge_key = (source, target, edge_type)
        if edge_key in seen_edges:
            return
        seen_edges.add(edge_key)
        self.edges.append(LogEdge(source=source, target=target, edge_type=edge_type, reason=reason))

    def _extract_dependency_steps(self, node: LogNode) -> Set[int]:
        combined = "\n".join([*node.actions, *node.contexts])
        step_ids: Set[int] = set()

        patterns = (
            r"parents?=\[([^\]]+)\]",
            r"parent[s]?[:：]\s*([0-9,，、\s]+)",
            r"上游节点[:：]\s*([0-9,，、\s]+)",
            r"依赖于步骤\[([^\]]+)\]",
            r"depends_on[:=]\s*\[([^\]]+)\]",
            r"from_step[:=]\s*(\d+)",
        )

        for pattern in patterns:
            for match in re.finditer(pattern, combined, flags=re.IGNORECASE):
                fragment = match.group(1) if match.groups() else match.group(0)
                for number in re.findall(r"\d+", fragment):
                    parsed = self._safe_int(number)
                    if parsed is not None:
                        step_ids.add(parsed)

        return step_ids

    def _dependency_reason(self, node: LogNode, source_step: int) -> str:
        joined = " | ".join(node.contexts)
        if str(source_step) in joined:
            return self._shorten(joined, 200)
        return f"step {source_step} -> step {node.step} 的日志中存在依赖线索"

    def _normalize_role(self, role: Any) -> str:
        if not isinstance(role, str):
            return ""
        role = role.strip()
        return self.role_mapping.get(role, role)

    def _normalize_action(self, action: Any, context: Any) -> str:
        if not isinstance(action, str):
            action = ""
        action = action.strip()
        context_text = self._clean_text(context)
        if action and self._has_failure_signal(action, context_text) and not action.endswith("_failed"):
            action = f"{action}_failed"
        if not action and self._has_failure_signal("", context_text):
            action = "failed"
        return action

    def _summarize_node(self, node: LogNode) -> str:
        if self.use_llm and self.llm_client is not None:
            summary = self._summarize_with_llm(node)
            if summary:
                return summary

        role_text = ", ".join(node.roles) if node.roles else "unknown-role"
        action_text = ", ".join(node.actions) if node.actions else "unknown-action"
        if node.contexts:
            return f"{role_text}: {action_text} | {self._shorten(node.contexts[0], 120)}"
        return f"{role_text}: {action_text}"

    def _summarize_with_llm(self, node: LogNode) -> str:
        prompt = (
            "你是日志图节点摘要器。请基于以下日志，输出一个简洁中文摘要，只输出摘要文本，不要 JSON。\n\n"
            f"step: {node.step}\n"
            f"roles: {json.dumps(node.roles, ensure_ascii=False)}\n"
            f"actions: {json.dumps(node.actions, ensure_ascii=False)}\n"
            f"contexts: {json.dumps(node.contexts, ensure_ascii=False)}\n"
        )
        response_text = self._call_llm(prompt)
        return self._clean_text(response_text)

    def _infer_status(self, node: LogNode) -> str:
        joined = "\n".join([*node.actions, *node.contexts])
        if self._has_failure_signal(joined, joined):
            return "failed"
        if self._has_success_signal(joined, joined):
            return "success"
        return "unknown"

    def _has_failure_signal(self, action: str, context: str) -> bool:
        text = f"{action}\n{context}"
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in FAILURE_PATTERNS)

    def _has_success_signal(self, action: str, context: str) -> bool:
        text = f"{action}\n{context}"
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in SUCCESS_PATTERNS)

    def _call_llm(self, prompt: str) -> str:
        client = self.llm_client
        if client is None:
            return ""

        if hasattr(client, "execute_prompt"):
            result = client.execute_prompt(prompt, parse_json=False)
            if isinstance(result, str):
                return result
            return getattr(result, "text", str(result))

        if hasattr(client, "generate_response"):
            result = client.generate_response(query=prompt)
            if isinstance(result, str):
                return result
            return getattr(result, "text", str(result))

        if hasattr(client, "chat"):
            result = client.chat([{ "role": "user", "content": prompt }])
            if isinstance(result, str):
                return result
            return getattr(result, "text", str(result))

        if hasattr(client, "complete"):
            result = client.complete(prompt)
            if isinstance(result, str):
                return result
            return getattr(result, "text", str(result))

        raise TypeError("不支持的 llm_client 接口，请提供 execute_prompt / generate_response / chat / complete 方法之一")

    def _safe_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _clean_text(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return re.sub(r"\x1b\[[0-9;]*[mK]", "", value).strip()

    def _deduplicate_preserve_order(self, values: Iterable[str]) -> List[str]:
        seen: Set[str] = set()
        result: List[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _shorten(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."


def load_log_entries(file_path: str | Path) -> List[Dict[str, Any]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"日志文件不存在: {path}")

    if path.suffix.lower() == ".jsonl":
        items: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                items.append(json.loads(line))
        return items

    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("logs"), list):
        return [item for item in data["logs"] if isinstance(item, dict)]

    raise ValueError("输入日志格式不支持，需为 JSON 数组、JSONL 或包含 logs 字段的 JSON")


def build_graph_from_file(
    file_path: str | Path,
    use_llm: bool = False,
    llm_client: Any = None,
) -> WorkflowLogGraph:
    return WorkflowLogGraph.from_file(file_path, use_llm=use_llm, llm_client=llm_client)


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 JSON 日志转换为步骤图")
    parser.add_argument("input", help="输入 JSON/JSONL 日志文件路径")
    parser.add_argument("--output", default="", help="输出图 JSON 文件路径")
    parser.add_argument("--use-llm", action="store_true", help="启用可选 LLM 摘要")
    return parser


def main() -> None:
    parser = _build_cli()
    args = parser.parse_args()

    graph = build_graph_from_file(args.input, use_llm=args.use_llm)
    if args.output:
        graph.save_json(args.output)
    else:
        print(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
