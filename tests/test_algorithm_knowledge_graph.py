import unittest

from aag.expert_search_engine.algorithm_knowledge_graph import (
    AlgorithmKnowledgeGraph,
    complexity_rank,
)


def _algorithm(algorithm_id, description, complexity, directed="both", weighted=False):
    return {
        "id": algorithm_id,
        "Application_scenario": description,
        "Principles": {
            "description": description,
            "time_complexity": complexity,
        },
        "solvable_questions": [description],
        "Deployment_method": {
            "support_engine": "networkx",
            "graph_type": {
                "directed": directed,
                "multigraph": False,
                "weighted": weighted,
                "heterogeneous": False,
            },
        },
    }


class AlgorithmKnowledgeGraphTest(unittest.TestCase):
    def setUp(self):
        algorithms = {
            "shortest_path": _algorithm(
                "shortest_path", "find an unweighted shortest path", "O(V + E)"
            ),
            "dijkstra_path": _algorithm(
                "dijkstra_path", "find a weighted shortest path", "O((V + E) log V)", weighted=True
            ),
            "all_simple_paths": _algorithm(
                "all_simple_paths", "enumerate simple paths", "Exponential"
            ),
            "directed_path": _algorithm(
                "directed_path", "find a path in a directed graph", "O(V + E)", directed=True
            ),
        }
        tasks = {
            "Path": {
                "id": "Path",
                "algorithm": list(algorithms),
            }
        }
        self.knowledge_graph = AlgorithmKnowledgeGraph(tasks, algorithms, max_neighbors=3)

    def test_dfs_starts_from_semantic_seed(self):
        candidates = self.knowledge_graph.dfs_candidates(
            "Path", "dijkstra_path", "find the shortest path"
        )
        self.assertEqual(candidates[0]["id"], "dijkstra_path")
        self.assertIn("shortest_path", {candidate["id"] for candidate in candidates})
        self.assertNotIn("all_simple_paths", {candidate["id"] for candidate in candidates})

    def test_graph_constraints_filter_directed_only_algorithm(self):
        candidates = [
            self.knowledge_graph.algorithm_index["shortest_path"],
            self.knowledge_graph.algorithm_index["directed_path"],
        ]
        feasible, rejected = self.knowledge_graph.filter_by_graph_constraints(
            candidates,
            {
                "graph_properties": {
                    "directed": False,
                    "multigraph": False,
                    "weighted": False,
                    "heterogeneous": False,
                }
            },
        )
        self.assertEqual([candidate["id"] for candidate in feasible], ["shortest_path"])
        self.assertEqual(rejected["directed_path"], ["directed"])

    def test_lowest_complexity_wins(self):
        selected = self.knowledge_graph.select_lowest_complexity(
            [
                self.knowledge_graph.algorithm_index["dijkstra_path"],
                self.knowledge_graph.algorithm_index["shortest_path"],
                self.knowledge_graph.algorithm_index["all_simple_paths"],
            ],
            {"graph_properties": {"weighted": False}},
        )
        self.assertEqual(selected["id"], "shortest_path")
        self.assertLess(complexity_rank("O(V + E)"), complexity_rank("O(V * E)"))


if __name__ == "__main__":
    unittest.main()
