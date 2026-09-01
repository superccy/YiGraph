import unittest

from aag.engine.iterative_dag_builder import (
    IterativePlanningError,
    build_iterative_subquery_plan,
)


class IterativeDagBuilderTest(unittest.TestCase):
    def test_consumes_one_semantic_task_per_iteration(self):
        responses = [
            {
                "subquery": {
                    "query": "Find the most active account.",
                    "task_type_id": "Centrality",
                    "depends_on": [],
                },
                "remaining_query": "Find a shortest path from that account.",
                "done": False,
            },
            {
                "subquery": {
                    "query": "Find a shortest path from the most active account.",
                    "task_type_id": "Path",
                    "depends_on": ["q1"],
                },
                "remaining_query": "",
                "done": True,
            },
        ]

        def plan_next(_segment, _existing, _task_types):
            return responses.pop(0)

        plan = build_iterative_subquery_plan(
            "Find the most active account, then a shortest path from it.",
            [
                {"id": "Centrality", "task_type": "Centrality"},
                {"id": "Path", "task_type": "Path"},
            ],
            plan_next,
        )

        self.assertEqual(len(plan["subqueries"]), 2)
        self.assertEqual(plan["subqueries"][0]["task_type_id"], "Centrality")
        self.assertEqual(plan["subqueries"][1]["depends_on"], ["q1"])

    def test_rejects_forward_dependency(self):
        def plan_next(_segment, _existing, _task_types):
            return {
                "subquery": {
                    "query": "Invalid task",
                    "task_type_id": "Path",
                    "depends_on": ["q2"],
                },
                "remaining_query": "",
                "done": True,
            }

        with self.assertRaises(IterativePlanningError):
            build_iterative_subquery_plan(
                "Invalid dependency",
                [{"id": "Path", "task_type": "Path"}],
                plan_next,
            )


if __name__ == "__main__":
    unittest.main()
