import ast
import builtins
import importlib
import inspect
import yaml
import logging
import json
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Dict, Any, Optional
from aag.utils.path_utils import DEFAULT_CONFIG_SERVER_PATH

from aag.computing_engine.mcp_client import GraphMCPClient
from aag.computing_engine.code_executor import DynamicCodeExecutor
from aag.expert_search_engine.database.datatype import GraphData
from aag.computing_engine.graph_query.nl_query_engine import NaturalLanguageQueryEngine, LLMInterface
from aag.computing_engine.graph_query.graph_query import Neo4jGraphClient, Neo4jConfig
from aag.utils.schema_validation import (
    SchemaValidationError,
    assert_valid_output,
    assert_valid_parameters,
)


logger = logging.getLogger(__name__)


class ComputingEngine:
    """
    Unified computing scheduler layer.
    - Manages multiple engines (NetworkX / PyG / Nebula).
    - Exposes a single execution interface to the scheduler.
    - Wraps MCP client communication.
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_SERVER_PATH):
        self.config_path = Path(config_path)
        self.clients: Dict[str, GraphMCPClient] = {}
        self.engine_supported_algorithms = {}   # algorithm_type -> engine_name
        self.algorithm_tool_mapping = {}        # algorithm_name -> tool_name
        self.parameter_modules = {}
        self._initialized = False
        self.code_executor = DynamicCodeExecutor(timeout=120, auto_install=True)
        self.nl_query_engine: Optional[NaturalLanguageQueryEngine] = None
        self.neo4j_config: Optional[Dict[str, Any]] = None
        self.reasoner = None  # set in initialize_graph_query_engine
        self.graph_properties: Dict[str, Any] = {}

    async def initialize(self):
        """Load config and connect to all MCP servers."""
        config = self._load_config()
        self.engine_supported_algorithms = config.get("engine_supported_algorithms", {})
        self._parse_algorithm_tool_mapping(config.get("engine_supported_algorithms", {}))
        
        for engine_name, server in config.get("servers", {}).items():
            client = GraphMCPClient(
                server_command=server.get("command", "python"),
                server_args=server.get("args", [])
            )
            ok = await client.connect()
            if ok:
                self.clients[engine_name] = client
                logger.info(f"✅ Engine '{engine_name}' connected")
            else:
                logger.warning(f"⚠️ Engine '{engine_name}' failed to connect")

            try:
                module_path = f"aag.computing_engine.{engine_name}_server.parameter_utils"
                module = importlib.import_module(module_path)
                self.parameter_modules[engine_name] = module
                logger.info(f"🧩 Loaded parameter module: {module_path}")
            except ImportError as e:
                logger.warning(f"⚠️ No parameter_utils.py found for engine '{engine_name}' ({e})")
        self._initialized = True
        logger.info(f"✅ Loaded {len(self.clients)} computing engines")
        # logger.info(f"🧠 Annotation modules loaded: {list(self.parameter_modules.keys())}")


    def _load_config(self) -> dict:
        """Load engine definitions from config file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _parse_algorithm_tool_mapping(self, engine_algorithms: dict):
        """
        engine_supported_algorithms:
          networkx:
            bfs:
              - tool: bfs_edges
        """
        
        for engine_name, algorithms in engine_algorithms.items():
            engine_mapping = {}
            
            for algo_name, tool_configs in algorithms.items():
                if isinstance(tool_configs, list) and len(tool_configs) > 0:
                    tool_config = tool_configs[0]
                    tool_base_name = tool_config.get("tool")
                    if tool_base_name and isinstance(tool_base_name, str):
                        engine_mapping[algo_name] = f"run_{tool_base_name}"
                    else:
                        logger.warning(f"⚠️ Invalid tool name for algorithm '{algo_name}' in engine '{engine_name}': {tool_base_name}")
            
            self.algorithm_tool_mapping[engine_name] = engine_mapping
        
        logger.info(f"✅ Parsed {sum(len(m) for m in self.algorithm_tool_mapping.values())} algorithm-tool mappings")
        logger.debug(f"Algorithm-tool mapping: {self.algorithm_tool_mapping}")

    def _resolve_engine(self, algo_name: str) -> str:
        """Resolve which engine owns the given algorithm."""
        algo_name = algo_name.lower()
        for engine, algorithms in self.engine_supported_algorithms.items():
            if isinstance(algorithms, dict):
                if algo_name in algorithms:
                    return engine
        direct_tool_name = f"run_{algo_name}"
        for engine, client in self.clients.items():
            if direct_tool_name in client.available_tools:
                return engine
        logger.warning(f"⚠️ Algorithm '{algo_name}' not found in config; fallback to 'networkx'")
        return "networkx"

    def _resolve_tool_name(self, algo_name: str, engine_name: str) -> str:
        """
        Resolve the actual tool name from algorithm and engine.

        Args:
            algo_name: Algorithm name (e.g. "bfs").
            engine_name: Engine name (e.g. "networkx").

        Returns:
            Tool name (e.g. "run_bfs_edges").

        Raises:
            ValueError: If tool name cannot be resolved.
        """
        algo_name = algo_name.lower()
        engine_mapping = self.algorithm_tool_mapping.get(engine_name, {})
        candidates = []
        if algo_name in engine_mapping:
            candidates.append(engine_mapping[algo_name])
        candidates.extend((f"run_{algo_name}", algo_name))

        client = self.clients.get(engine_name)
        if client:
            for candidate in dict.fromkeys(candidates):
                if candidate in client.available_tools:
                    return candidate
        elif candidates:
            return candidates[0]
        
        logger.error(f"❌ Cannot resolve tool name for algorithm '{algo_name}' in engine '{engine_name}'")
        raise ValueError(f"Algorithm '{algo_name}' has no tool mapping in engine '{engine_name}'. "
                         f"Please check config_servers.yaml")

    def has_executable_algorithm(self, algo_name: str) -> bool:
        """Return whether a connected engine exposes an executable tool."""
        normalized = algo_name.lower()
        configured_engines = [
            engine
            for engine, algorithms in self.engine_supported_algorithms.items()
            if isinstance(algorithms, dict) and normalized in algorithms
        ]
        engines = configured_engines + [
            engine for engine in self.clients if engine not in configured_engines
        ]
        for engine in engines:
            client = self.clients.get(engine)
            if not client:
                continue
            mapped = self.algorithm_tool_mapping.get(engine, {}).get(normalized)
            candidates = [mapped, f"run_{normalized}", normalized]
            if any(candidate and candidate in client.available_tools for candidate in candidates):
                return True
        return False

    async def run_algorithm(self, algo_name: str, parameters: Dict[str, Any], post_processing_code: Optional[str] = None, global_graph: Optional[GraphData] = None) -> Dict[str, Any]:
        """Run the specified algorithm."""
        try:
            engine_name = self._resolve_engine(algo_name)
            if engine_name not in self.clients:
                return {"success": False, "error": f"Engine '{engine_name}' not connected"}

            client = self.clients[engine_name]
            tool_name = self._resolve_tool_name(algo_name, engine_name)

            if algo_name.lower() == "initialize_graph":
                self._remember_graph_properties(parameters or {})
            
            prepared_params = parameters or {}
            if self._should_normalize(engine_name, tool_name):
                prepared_params = self._normalize_parameters(engine_name, tool_name, prepared_params)
            
            logger.info(f"🚀 Running '{algo_name}' (tool: {tool_name}) on engine [{engine_name}]")
            result = await client.call_tool(tool_name, prepared_params, post_processing_code, global_graph)
            return result

        except Exception as e:
            logger.error(f"❌ Algorithm '{algo_name}' failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_algorithm_description(self, algo_name: str) -> tuple[str, Optional[dict]]:
        """Get tool description (input/output schema) for the given algorithm."""
        engine = self._resolve_engine(algo_name)
        client = self.clients.get(engine)
        if not client:
            return f"⚠️ Engine '{engine}' not connected.\n", None

        try:
            tool_name = self._resolve_tool_name(algo_name, engine)
        except ValueError as exc:
            return f"⚠️ {exc}\n", None
        tool_info = client.available_tools.get(tool_name)
        if not tool_info:
            return f"⚠️ Tool '{tool_name}' not found in engine '{engine}'.\n", None

        input_schema = tool_info.get("input_schema", {})
        output_schema = tool_info.get("output_schema", {})
        annotated_input = self._annotate_schema(input_schema, engine)
        doc = (
            f"### `{tool_name}` (Engine: {engine})\n"
            f"**Description:** {tool_info.get('description', 'No description')}\n\n"
            f"**Input Parameters** *(with system-injected annotations)*:\n"
            f"```json\n{json.dumps(annotated_input, indent=2, ensure_ascii=False)}\n```\n\n"
            f"**Output Structure** *(data received by your `process(data)` in the `result` field)*:\n"
            f"```json\n{json.dumps(output_schema, indent=2, ensure_ascii=False)}\n```\n"
            f"{'-'*50}\n"
        )

        tool_metadata = {
            "name": tool_name,
            "engine": engine,
            "description": tool_info.get("description", "No description"),
            "input_params": annotated_input,
            "output_params": output_schema,
        }
        logger.debug(f"🧩 Generated description for '{tool_name}':\n{doc}")
        return doc, tool_metadata

    def _remember_graph_properties(self, parameters: Dict[str, Any]) -> None:
        dataset_config = parameters.get("dataset_config") or {}
        schema = dataset_config.get("schema") or {}
        graph = schema.get("graph") or dataset_config.get("graph") or {}
        if isinstance(graph, Mapping):
            self.graph_properties = {
                "directed": bool(graph.get("directed", False)),
                "multigraph": bool(graph.get("multigraph", graph.get("multiedge", False))),
            }

    @staticmethod
    def _strip_code_fence(code: str) -> str:
        match = re.match(r"^\s*```(?:python)?\s*(.*?)\s*```\s*$", code or "", re.DOTALL)
        return match.group(1) if match else (code or "")

    @staticmethod
    def _validate_generated_code(code: str) -> None:
        allowed_imports = {
            "networkx", "numpy", "scipy", "math", "statistics", "collections",
            "itertools", "functools", "heapq", "random", "operator",
        }
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [(node.module or "").split(".")[0]]
            else:
                continue
            disallowed = [name for name in modules if name not in allowed_imports]
            if disallowed:
                raise ValueError(f"Generated algorithm imports are not allowed: {disallowed}")

    @staticmethod
    def _generated_code_builtins() -> Dict[str, Any]:
        allowed_imports = {
            "networkx", "numpy", "scipy", "math", "statistics", "collections",
            "itertools", "functools", "heapq", "random", "operator",
        }

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level != 0 or name.split(".")[0] not in allowed_imports:
                raise ImportError(f"Import is not allowed in generated algorithm code: {name}")
            return __import__(name, globals, locals, fromlist, level)

        safe_names = {
            "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
            "frozenset", "int", "isinstance", "issubclass", "iter", "len", "list",
            "map", "max", "min", "next", "pow", "range", "repr", "reversed", "round",
            "set", "slice", "sorted", "str", "sum", "tuple", "type", "zip",
            "Exception", "RuntimeError", "ValueError", "KeyError", "TypeError",
        }
        builtins_map = {name: getattr(builtins, name) for name in safe_names}
        builtins_map["__import__"] = guarded_import
        return builtins_map

    def _graph_data_to_networkx(self, graph_data: GraphData):
        import networkx as nx

        directed = bool(self.graph_properties.get("directed", True))
        multigraph = bool(self.graph_properties.get("multigraph", False))
        if directed and multigraph:
            graph = nx.MultiDiGraph()
        elif directed:
            graph = nx.DiGraph()
        elif multigraph:
            graph = nx.MultiGraph()
        else:
            graph = nx.Graph()
        for vertex in graph_data.vertices:
            graph.add_node(vertex.vid, **dict(vertex.properties or {}))
        for edge in graph_data.edges:
            attributes = dict(edge.properties or {})
            if edge.rank is not None:
                attributes.setdefault("rank", edge.rank)
            graph.add_edge(edge.src, edge.dst, **attributes)
        return graph

    @classmethod
    def _normalize_generated_result(cls, value: Any) -> Any:
        try:
            import networkx as nx
            if isinstance(value, nx.Graph):
                return {
                    "type": "graph",
                    "graph_type": type(value).__name__,
                    "nodes": [dict({"id": node}, **attrs) for node, attrs in value.nodes(data=True)],
                    "edges": [dict({"src": src, "dst": dst}, **attrs) for src, dst, attrs in value.edges(data=True)],
                }
        except ImportError:
            pass
        if isinstance(value, Iterator):
            value = list(value)
        if isinstance(value, Mapping):
            return {
                key if isinstance(key, (str, int, float, bool)) or key is None else str(key): cls._normalize_generated_result(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [cls._normalize_generated_result(item) for item in value]
        if hasattr(value, "item") and callable(value.item):
            try:
                return value.item()
            except (ValueError, TypeError):
                pass
        return value

    def execute_generated_algorithm(
        self,
        *,
        algorithm_name: str,
        code: str,
        parameters: Dict[str, Any],
        global_graph: GraphData,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        post_processing_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute an online-generated graph algorithm using a fixed function contract."""
        try:
            if global_graph is None:
                raise ValueError("Global graph is required for generated algorithm execution")
            assert_valid_parameters(parameters, input_schema, reject_unknown=True)
            clean_code = self._strip_code_fence(code)
            self._validate_generated_code(clean_code)
            namespace = {"__builtins__": self._generated_code_builtins()}
            exec(clean_code, namespace)
            operation = namespace.get("run_algorithm")
            if not callable(operation):
                raise ValueError("Generated code must define run_algorithm(G, **parameters)")
            signature = inspect.signature(operation)
            if not signature.parameters:
                raise ValueError("run_algorithm must accept a graph argument")

            graph = self._graph_data_to_networkx(global_graph)
            call_parameters = {
                key: value for key, value in (parameters or {}).items()
                if key not in {"G", "graph", "global_graph", "dataset_config", "backend_kwargs"}
            }
            raw_result = operation(graph, **call_parameters)
            assert_valid_output(raw_result, output_schema)
            result = raw_result
            if post_processing_code:
                result = self.code_executor.execute(
                    post_processing_code,
                    raw_result,
                    global_graph=global_graph,
                )
            result = self._normalize_generated_result(result)
            return {
                "algorithm": algorithm_name,
                "success": True,
                "result": result,
                "error": None,
                "summary": "Online-generated algorithm code executed successfully.",
                "execution_mode": "online_code_generation",
            }
        except Exception as exc:
            logger.error("❌ Generated algorithm '%s' failed: %s", algorithm_name, exc)
            return {
                "algorithm": algorithm_name,
                "success": False,
                "result": None,
                "error": str(exc),
                "summary": "Online-generated algorithm code execution failed.",
                "execution_mode": "online_code_generation",
            }

    def _annotate_schema(self, input_schema: Dict, engine_name: str) -> Dict:
        """
        Dispatch to each engine's schema annotation; engines define annotate_schema() in their server module.
        """
        module = self.parameter_modules.get(engine_name)
        if not module:
            logger.debug(f"⚠️ No annotation module for engine '{engine_name}'")
            return input_schema

        annotate_func = getattr(module, "annotate_schema", None)

        if callable(annotate_func):
            try:
                return annotate_func(input_schema)
            except Exception as e:
                logger.error(f"❌ Error running annotate_schema() for '{engine_name}': {e}")
        return input_schema
    

    def _should_normalize(self, engine_name: str, tool_name: str) -> bool:
        module = self.parameter_modules.get(engine_name)
        if not module:
            return False
        guard = getattr(module, "should_normalize", None)
        if callable(guard):
            return guard(tool_name)
        return hasattr(module, "normalize_parameters")

    def _normalize_parameters(self, engine_name: str, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        module = self.parameter_modules.get(engine_name)
        if not module:
            return parameters
        normalize_fn = getattr(module, "normalize_parameters", None)
        if not callable(normalize_fn):
            return parameters

        client = self.clients.get(engine_name)
        tool_info = client.available_tools.get(tool_name) if client else None
        try:
            return normalize_fn(tool_name, dict(parameters or {}), tool_info, logger=logger)
        except Exception as exc:
            logger.warning("⚠️ Parameter normalization failed (%s): %s", tool_name, exc)
            return parameters

    def execute_code(self, code: str, data: Any, global_graph: Optional[GraphData] = None, fallback_to_direct_exec: bool = True, is_numeric_analysis: bool = False) -> Any:
        """
        Execute dynamically generated code (numeric analysis, post-processing, etc.).

        Args:
            code: Python code string to execute.
            data: Data passed to the code (dict or other).
            fallback_to_direct_exec: If code is not a process() function, run it directly.
            is_numeric_analysis: If True, unpack as **data; else pass data as-is.

        Returns:
            Execution result.

        Raises:
            RuntimeError: If execution fails.
        """
        try:
            value = self.code_executor.execute(code, data, global_graph=global_graph, is_numeric_analysis=is_numeric_analysis)
            return {
                "algorithm": "numeric_analysis_code",
                "success": True,
                "result": value,
                "error": None,
                "summary": "Numeric analysis code executed successfully.",
        }
        except (ValueError, AttributeError) as e:
            if not fallback_to_direct_exec:
                return {"success": False, "result": None, "error": str(e), "summary": "Numeric analysis code execution failed."}
            try:
                if isinstance(data, dict):
                    namespace = {**data, "__builtins__": __builtins__}
                else:
                    namespace = {"data": data, "__builtins__": __builtins__}
                exec(code, namespace)
                return {
                        "algorithm": "numeric_analysis_code",
                        "success": True,
                        "result": namespace.get("result", data),
                        "error": None,
                        "summary": "Numeric analysis code executed successfully via direct exec fallback.",
                }
            except Exception as fallback_error:
                return {"success": False, "result": None, "error": str(fallback_error), "summary": "Numeric analysis code execution failed."}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e), "summary": "Numeric analysis code execution failed."}

    def initialize_graph_query_engine(self, neo4j_config: Dict[str, Any], reasoner):
        """
        Initialize the graph query engine.

        Args:
            neo4j_config: Neo4j config dict (enabled, uri, user, password).
            reasoner: Reasoner instance for LLM calls.
        """
        try:
            self.neo4j_config = neo4j_config
            self.reasoner = reasoner
            logger.info(f"📝 Initializing graph query engine; config: {neo4j_config}")

            if not neo4j_config.get("enabled", False):
                logger.info("ℹ NaturalLanguageQueryEngine disabled in config")
                self.nl_query_engine = None
                return

            logger.info("📝 Neo4j enabled; creating connection...")
            config = Neo4jConfig(
                uri=neo4j_config.get("uri", "bolt://localhost:7687"),
                user=neo4j_config.get("user", "neo4j"),
                password=neo4j_config.get("password", "")
            )
            logger.info(f"📝 Creating Neo4jGraphClient, uri={config.uri}")
            db_client = Neo4jGraphClient(config)
            logger.info("📝 Creating NaturalLanguageQueryEngine")
            # Wrap reasoner in LLMInterface
            llm_interface = LLMInterface(reasoner)
            self.nl_query_engine = NaturalLanguageQueryEngine(db_client, llm_interface)
            self.nl_query_engine.initialize()
            logger.info("✓ NaturalLanguageQueryEngine initialized in ComputingEngine")
        except Exception as e:
            logger.error(f"✗ NaturalLanguageQueryEngine initialization failed: {e}", exc_info=True)
            self.nl_query_engine = None

    def execute_graph_query(self, query: str) -> Dict[str, Any]:
        """
        Execute a graph query.

        Args:
            query: User query.

        Returns:
            Result dict with success, results, count, query_type, etc.
        """
        if not self.nl_query_engine:
            return {
                "success": False,
                "error": "Graph query engine not initialized; check Neo4j config."
            }
        try:
            result = self.nl_query_engine.ask(query)
            return result
        except Exception as e:
            logger.error(f"Graph query execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Graph query execution failed: {str(e)}"
            }

    async def shutdown(self):
        """Disconnect all engines."""
        # MCP stdio contexts are nested while clients are initialized, so they
        # must be closed in LIFO order to preserve AnyIO cancel-scope nesting.
        for name, client in reversed(list(self.clients.items())):
            await client.disconnect()
        logger.info("👋 All computing engines disconnected")
