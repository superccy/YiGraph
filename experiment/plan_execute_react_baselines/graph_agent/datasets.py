from __future__ import annotations

import gzip
import json
import pickle
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

import networkx as nx
import pandas as pd
import yaml

from .config import DatasetConfig
from .metrics import MetricsCollector


class GraphWorkspace:
    """Lazy, reusable access to one dataset and its NetworkX materializations."""

    def __init__(
        self,
        config: DatasetConfig,
        metrics: MetricsCollector,
        chunksize: int = 250_000,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.config = config
        self.metrics = metrics
        self.chunksize = chunksize
        self.cache_dir = cache_dir
        self.schema = self._load_schema(config.schema_path)
        self.dataset_schema = self.schema["datasets"][0]
        self.vertex_config = self.dataset_schema["schema"]["vertex"][0]
        self.edge_config = self.dataset_schema["schema"]["edge"][0]
        self.graph_config = self.dataset_schema["schema"]["graph"]
        self.vertex_path = self._data_path(self.vertex_config["path"])
        self.edge_path = self._data_path(self.edge_config["path"])
        self.vertex_columns = list(pd.read_csv(self.vertex_path, nrows=0).columns)
        self.edge_columns = list(pd.read_csv(self.edge_path, nrows=0).columns)
        self._graphs: Dict[str, nx.Graph] = {}
        self._node_frame: Optional[pd.DataFrame] = None
        self._lock = threading.RLock()

    @staticmethod
    def _load_schema(path: Path) -> Dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"Dataset schema not found: {path}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not payload.get("datasets"):
            raise ValueError(f"Invalid graph schema: {path}")
        return payload

    def _data_path(self, schema_path: str) -> Path:
        candidate = self.config.data_dir / "graph" / Path(schema_path).name
        if candidate.is_file():
            return candidate
        relative = (self.config.schema_path.parent / schema_path).resolve()
        if relative.is_file():
            return relative
        raise FileNotFoundError(f"Dataset file not found: {candidate} (schema: {schema_path})")

    def describe(self) -> Dict[str, Any]:
        store = self.dataset_schema.get("schema", {}).get("graph_store_info", {})
        return {
            "dataset_name": self.config.name,
            "schema_path": str(self.config.schema_path),
            "vertex_path": str(self.vertex_path),
            "edge_path": str(self.edge_path),
            "graph": self.graph_config,
            "graph_store_info": self.dataset_schema.get("schema", {}).get("graph_store_info", store),
            "vertex": self.vertex_config,
            "edge": self.edge_config,
            "vertex_csv_columns": self.vertex_columns,
            "edge_csv_columns": self.edge_columns,
            "notes": [
                "CSV columns are authoritative even when attribute_fields in the schema is empty.",
                "Use only needed edge_attributes when materializing a large NetworkX graph.",
            ],
        }

    def node_frame(self, columns: Optional[Sequence[str]] = None, copy: bool = False) -> pd.DataFrame:
        with self._lock:
            if self._node_frame is None:
                started = time.perf_counter()
                self._node_frame = pd.read_csv(self.vertex_path)
                self.metrics.add_event("data_load", "vertex_csv", time.perf_counter() - started, rows=len(self._node_frame))
            frame = self._node_frame
        if columns is not None:
            frame = frame[list(columns)]
        return frame.copy() if copy else frame

    def edge_frame(
        self,
        columns: Optional[Sequence[str]] = None,
        nrows: Optional[int] = None,
    ) -> pd.DataFrame:
        started = time.perf_counter()
        frame = pd.read_csv(self.edge_path, usecols=list(columns) if columns else None, nrows=nrows)
        self.metrics.add_event("data_load", "edge_csv", time.perf_counter() - started, rows=len(frame))
        return frame

    def iter_edges(
        self,
        columns: Optional[Sequence[str]] = None,
        chunksize: Optional[int] = None,
    ) -> Iterator[pd.DataFrame]:
        usecols = list(columns) if columns else None
        for chunk in pd.read_csv(self.edge_path, usecols=usecols, chunksize=chunksize or self.chunksize):
            yield chunk

    def graph(
        self,
        *,
        simple: bool = False,
        edge_attributes: Optional[Sequence[str]] = None,
        node_attributes: Optional[Sequence[str]] = None,
    ) -> nx.Graph:
        source = self.edge_config["source_field"]
        target = self.edge_config["target_field"]
        node_id = self.vertex_config["id_field"]
        edge_attributes = tuple(name for name in (edge_attributes or ()) if name not in {source, target})
        node_attributes = tuple(name for name in (node_attributes or ()) if name != node_id)
        cache_key = json.dumps([simple, edge_attributes, node_attributes])
        # Single-flight graph construction: compiler tasks in the same ready
        # wave share one workspace and must not materialize identical 18M-edge
        # graphs concurrently.
        with self._lock:
            if cache_key in self._graphs:
                return self._graphs[cache_key]
            disk_path = self._cache_path(cache_key)
            if disk_path and disk_path.is_file():
                started = time.perf_counter()
                with gzip.open(disk_path, "rb") as handle:
                    graph = pickle.load(handle)
                self._graphs[cache_key] = graph
                self.metrics.add_event("data_load", "networkx_cache", time.perf_counter() - started, path=str(disk_path))
                return graph
            started = time.perf_counter()
            graph = self._new_graph(simple=simple)
            self._add_nodes(graph, node_attributes)
            columns = [source, target, *edge_attributes]
            for chunk in self.iter_edges(columns=columns):
                if edge_attributes:
                    records = (
                        (row[0], row[1], {name: row[index + 2] for index, name in enumerate(edge_attributes)})
                        for row in chunk.itertuples(index=False, name=None)
                    )
                    graph.add_edges_from(records)
                else:
                    graph.add_edges_from(chunk.itertuples(index=False, name=None))
            duration = time.perf_counter() - started
            self.metrics.add_event(
                "data_load",
                "networkx_graph",
                duration,
                nodes=graph.number_of_nodes(),
                edges=graph.number_of_edges(),
                simple=simple,
                edge_attributes=list(edge_attributes),
            )
            self._graphs[cache_key] = graph
            disk_path = self._cache_path(cache_key)
            if disk_path:
                disk_path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(disk_path, "wb", compresslevel=1) as handle:
                    pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)
            return graph

    def _new_graph(self, simple: bool) -> nx.Graph:
        directed = bool(self.graph_config.get("directed", True))
        multigraph = bool(self.graph_config.get("multigraph", False)) and not simple
        if directed and multigraph:
            return nx.MultiDiGraph()
        if directed:
            return nx.DiGraph()
        if multigraph:
            return nx.MultiGraph()
        return nx.Graph()

    def _add_nodes(self, graph: nx.Graph, node_attributes: Sequence[str]) -> None:
        node_id = self.vertex_config["id_field"]
        if node_attributes:
            columns = [node_id, *[name for name in node_attributes if name != node_id]]
            frame = self.node_frame(columns=columns)
            graph.add_nodes_from(
                (row[0], {name: row[index + 1] for index, name in enumerate(node_attributes)})
                for row in frame.itertuples(index=False, name=None)
            )
        else:
            frame = pd.read_csv(self.vertex_path, usecols=[node_id])
            graph.add_nodes_from(frame[node_id].tolist())

    def _cache_path(self, cache_key: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        import hashlib

        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{self.config.name}-{digest}.nx.pkl.gz"
