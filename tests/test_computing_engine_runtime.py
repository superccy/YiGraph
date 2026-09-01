import unittest
from types import SimpleNamespace

from aag.expert_search_engine.database.datatype import EdgeData, GraphData, VertexData

try:
    from aag.computing_engine.computing_engine import ComputingEngine
    COMPUTING_ENGINE_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    ComputingEngine = None
    COMPUTING_ENGINE_IMPORT_ERROR = exc


@unittest.skipIf(ComputingEngine is None, f"optional runtime dependency unavailable: {COMPUTING_ENGINE_IMPORT_ERROR}")
class ComputingEngineRuntimeTest(unittest.TestCase):
    def test_resolves_direct_runtime_tool_without_static_mapping(self):
        engine = ComputingEngine()
        engine.clients = {
            "networkx": SimpleNamespace(
                available_tools={"run_antichains": {"name": "run_antichains"}}
            )
        }
        engine.engine_supported_algorithms = {}
        engine.algorithm_tool_mapping = {}

        self.assertTrue(engine.has_executable_algorithm("antichains"))
        self.assertEqual(engine._resolve_engine("antichains"), "networkx")
        self.assertEqual(engine._resolve_tool_name("antichains", "networkx"), "run_antichains")

    def test_executes_generated_algorithm_with_specs(self):
        engine = ComputingEngine()
        engine.graph_properties = {"directed": False, "multigraph": False}
        graph = GraphData(
            vertices=[VertexData("a"), VertexData("b")],
            edges=[EdgeData("a", "b")],
        )
        result = engine.execute_generated_algorithm(
            algorithm_name="degree",
            code=(
                "def run_algorithm(G, **parameters):\n"
                "    return dict(G.degree())\n"
            ),
            parameters={},
            global_graph=graph,
            input_schema={"parameters": {"G": {"type": "graph", "required": True}}},
            output_schema={"type": "dictionary"},
        )
        self.assertTrue(result["success"], result.get("error"))
        self.assertEqual(result["result"], {"a": 1, "b": 1})
        self.assertEqual(result["execution_mode"], "online_code_generation")


if __name__ == "__main__":
    unittest.main()
