import unittest

from aag.engine.dependency_types import (
    RuntimeDependencyValueType,
    can_use_as_graph,
    classify_runtime_dependency_value,
)


class DependencyTypesTest(unittest.TestCase):
    def test_classifies_graph_node_edge_and_scalar_values(self):
        self.assertEqual(
            classify_runtime_dependency_value(
                {"nodes": ["a", "b"], "edges": [["a", "b"]]},
                field_key="subgraph",
            ),
            RuntimeDependencyValueType.GRAPH,
        )
        self.assertEqual(
            classify_runtime_dependency_value(["a", "b"], field_key="community_nodes"),
            RuntimeDependencyValueType.NODE_SET,
        )
        self.assertEqual(
            classify_runtime_dependency_value([["a", "b"]], field_key="edges"),
            RuntimeDependencyValueType.EDGE_SET,
        )
        scalar_type = classify_runtime_dependency_value(0.75, field_key="threshold")
        self.assertEqual(scalar_type, RuntimeDependencyValueType.SCALAR)
        self.assertFalse(can_use_as_graph(scalar_type))


if __name__ == "__main__":
    unittest.main()
