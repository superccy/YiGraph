import unittest

from baselines import (
    build_trace_graph,
    failed_node_localization,
    hierarchical_backtracking,
    rule_based_dependency_tracking,
)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.trace = [
            {"step": 1, "role": "Planner", "action": "plan", "context": "ok"},
            {
                "step": 2,
                "role": "Dependency Resolver",
                "action": "dependency_analysis_failed",
                "context": "Missing required field result",
            },
            {"step": 3, "role": "Executor", "action": "execute", "context": "ok"},
            {
                "step": 4,
                "role": "Executor",
                "action": "execute_failed",
                "context": "Execution failed after retries; parents=[2, 3]",
            },
        ]
        self.graph = build_trace_graph(self.trace)
        self.candidates = {1, 2, 3, 4}

    def test_failed_nodes(self):
        self.assertEqual(
            failed_node_localization(self.graph, self.candidates), {2, 4}
        )

    def test_rule_based(self):
        selected, evidence = rule_based_dependency_tracking(
            self.graph, self.candidates
        )
        self.assertIn(2, selected)
        self.assertIn("missing_field_or_parameter", evidence[2])

    def test_hierarchical_adds_only_first_matching_layer(self):
        selected, evidence = hierarchical_backtracking(self.graph, self.candidates)
        self.assertEqual(selected, {2, 3, 4})
        self.assertEqual(evidence["selected_upstream_layer"], [2, 3])


if __name__ == "__main__":
    unittest.main()

