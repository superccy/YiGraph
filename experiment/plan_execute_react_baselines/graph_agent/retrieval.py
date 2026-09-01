from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|[\u4e00-\u9fff]")

QUERY_EXPANSIONS = {
    "直接": "degree_centrality neighbors adjacency direct connections",
    "功能模块": "louvain_communities greedy_modularity_communities label_propagation_communities community module partition",
    "功能分区": "louvain_communities greedy_modularity_communities community module partition",
    "模块划分": "louvain_communities greedy_modularity_communities label_propagation_communities community module partition",
    "互动": "degree_centrality in_degree_centrality out_degree_centrality interactions",
    "注意": "in_degree_centrality pagerank incoming attention",
    "影响力": "pagerank eigenvector_centrality degree_centrality influence",
    "核心": "pagerank degree_centrality eigenvector_centrality core_number centrality",
    "权威": "hits pagerank authority",
    "号召": "hits out_degree_centrality hub",
    "中介": "betweenness_centrality articulation_points bridges intermediary",
    "中转": "betweenness_centrality intermediary shortest_path",
    "必经": "betweenness_centrality articulation_points shortest_path",
    "冻结": "articulation_points node_connectivity betweenness_centrality cut",
    "切断": "minimum_node_cut articulation_points bridges cut",
    "阻断": "betweenness_centrality articulation_points descendants diffusion",
    "路径": "shortest_path bfs_tree dfs_tree simple_paths path",
    "传播": "bfs_tree descendants shortest_path diffusion reachability",
    "扩散": "descendants bfs_tree reachability diffusion",
    "循环": "simple_cycles cycle_basis strongly_connected_components cycle",
    "回流": "simple_cycles strongly_connected_components cycle circulation",
    "圈层": "louvain_communities greedy_modularity_communities label_propagation_communities community",
    "社区": "louvain_communities greedy_modularity_communities community modularity",
    "团伙": "louvain_communities strongly_connected_components community group",
    "阵营": "louvain_communities community signed graph partition",
    "话题": "subgraph louvain_communities hits topic",
}

QUERY_ALGORITHM_HINTS = {
    "直接": ["degree_centrality", "in_degree_centrality", "out_degree_centrality"],
    "功能模块": ["louvain_communities", "greedy_modularity_communities", "label_propagation_communities"],
    "功能分区": ["louvain_communities", "greedy_modularity_communities"],
    "模块划分": ["louvain_communities", "greedy_modularity_communities", "label_propagation_communities"],
    "影响力": ["pagerank", "degree_centrality", "eigenvector_centrality"],
    "核心": ["pagerank", "degree_centrality", "betweenness_centrality"],
    "权威": ["hits", "pagerank"],
    "号召": ["hits", "out_degree_centrality"],
    "中介": ["betweenness_centrality", "articulation_points"],
    "中转": ["betweenness_centrality", "shortest_path"],
    "必经": ["betweenness_centrality", "articulation_points", "shortest_path"],
    "冻结": ["articulation_points", "minimum_node_cut", "betweenness_centrality"],
    "阻断": ["betweenness_centrality", "articulation_points", "descendants"],
    "路径": ["shortest_path", "dfs_tree", "bfs_tree"],
    "传播": ["bfs_tree", "descendants", "betweenness_centrality"],
    "循环": ["strongly_connected_components", "simple_cycles", "find_cycle"],
    "回流": ["strongly_connected_components", "simple_cycles", "find_cycle"],
    "洗钱": ["simple_cycles", "strongly_connected_components", "pagerank"],
    "圈层": ["louvain_communities", "greedy_modularity_communities", "label_propagation_communities"],
    "社区": ["louvain_communities", "greedy_modularity_communities"],
    "团伙": ["louvain_communities", "strongly_connected_components", "betweenness_centrality"],
    "阵营": ["louvain_communities", "greedy_modularity_communities", "hits"],
    "话题": ["louvain_communities", "hits", "pagerank"],
}


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def expand_query(text: str) -> str:
    additions = [expansion for phrase, expansion in QUERY_EXPANSIONS.items() if phrase in text]
    return text + (" " + " ".join(additions) if additions else "")


@dataclass(frozen=True)
class AlgorithmDocument:
    algorithm_id: str
    text: str
    metadata: Dict[str, Any]


class FlatDocumentationRetriever:
    """BM25 over one flat document per algorithm; no graph/RAG hierarchy is used."""

    def __init__(self, knowledge_base_dir: Path) -> None:
        algorithms_path = knowledge_base_dir / "algorithms.yaml"
        task_types_path = knowledge_base_dir / "task_types.yaml"
        if not algorithms_path.is_file():
            raise FileNotFoundError(f"Algorithm documentation not found: {algorithms_path}")
        algorithms = yaml.safe_load(algorithms_path.read_text(encoding="utf-8")) or []
        if not isinstance(algorithms, list):
            raise ValueError("algorithms.yaml must contain a top-level list")
        task_types = self._load_task_types(task_types_path)
        self.documents = [self._to_document(item, task_types) for item in algorithms]
        self._term_frequencies = [Counter(tokenize(doc.text)) for doc in self.documents]
        self._doc_lengths = [sum(freq.values()) for freq in self._term_frequencies]
        self._avg_doc_length = sum(self._doc_lengths) / max(1, len(self._doc_lengths))
        document_frequency: Dict[str, int] = defaultdict(int)
        for freq in self._term_frequencies:
            for term in freq:
                document_frequency[term] += 1
        count = len(self.documents)
        self._idf = {
            term: math.log(1.0 + (count - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }
        self._by_id = {doc.algorithm_id: doc for doc in self.documents}

    @staticmethod
    def _load_task_types(path: Path) -> Dict[str, Dict[str, Any]]:
        if not path.is_file():
            return {}
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if isinstance(payload, dict):
            payload = payload.get("task_types", payload.get("tasks", []))
        if not isinstance(payload, list):
            return {}
        return {str(item.get("id")): item for item in payload if isinstance(item, dict) and item.get("id")}

    @staticmethod
    def _to_document(item: Dict[str, Any], task_types: Dict[str, Dict[str, Any]]) -> AlgorithmDocument:
        algorithm_id = str(item["id"])
        task_id = str(item.get("task_type_id") or "")
        deployment = item.get("Deployment_method") or {}
        metadata = {
            "id": algorithm_id,
            "task_type_id": task_id,
            "task_type": task_types.get(task_id, {}),
            "input_schema": deployment.get("input_schema", {}),
            "output_schema": deployment.get("output_schema", {}),
            "graph_type": deployment.get("graph_type", {}),
            "support_engine": deployment.get("support_engine"),
        }
        searchable = {
            "id": algorithm_id,
            "task_type": task_types.get(task_id, {}),
            "application_scenario": item.get("Application_scenario"),
            "principles": item.get("Principles"),
            "solvable_questions": item.get("solvable_questions", []),
            "input_schema": metadata["input_schema"],
            "output_schema": metadata["output_schema"],
        }
        text = yaml.safe_dump(searchable, allow_unicode=True, sort_keys=False)
        return AlgorithmDocument(algorithm_id=algorithm_id, text=text, metadata=metadata)

    @property
    def algorithm_ids(self) -> Sequence[str]:
        return tuple(self._by_id)

    def get(self, algorithm_id: str) -> AlgorithmDocument | None:
        return self._by_id.get(algorithm_id)

    def retrieve(self, query: str, top_k: int = 12) -> List[AlgorithmDocument]:
        query_terms = tokenize(expand_query(query))
        if not query_terms:
            return self.documents[:top_k]
        k1, b = 1.5, 0.75
        scores: List[tuple[float, int]] = []
        for index, (freq, length) in enumerate(zip(self._term_frequencies, self._doc_lengths)):
            score = 0.0
            for term in query_terms:
                tf = freq.get(term, 0)
                if not tf:
                    continue
                denominator = tf + k1 * (1 - b + b * length / max(1.0, self._avg_doc_length))
                score += self._idf.get(term, 0.0) * tf * (k1 + 1) / denominator
            if score > 0:
                scores.append((score, index))
        scores.sort(key=lambda pair: (-pair[0], self.documents[pair[1]].algorithm_id))
        forced_ids: List[str] = []
        for phrase, algorithm_ids in QUERY_ALGORITHM_HINTS.items():
            if phrase in query:
                forced_ids.extend(algorithm_ids)
        selected: List[AlgorithmDocument] = []
        for algorithm_id in forced_ids:
            document = self._by_id.get(algorithm_id)
            if document and all(item.algorithm_id != algorithm_id for item in selected):
                selected.append(document)
        for _, index in scores:
            document = self.documents[index]
            if all(item.algorithm_id != document.algorithm_id for item in selected):
                selected.append(document)
            if len(selected) >= top_k:
                break
        if len(selected) < top_k:
            selected_ids = {item.algorithm_id for item in selected}
            selected.extend(
                item for item in self.documents if item.algorithm_id not in selected_ids
            )
        return selected[:top_k]

    @staticmethod
    def render(documents: Iterable[AlgorithmDocument]) -> str:
        return "\n---\n".join(doc.text for doc in documents)
