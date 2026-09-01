import tempfile
import unittest
from pathlib import Path

from aag.error_recovery.knowledge_base import RecoveryKnowledgeStore


class RecoveryKnowledgeStoreTest(unittest.TestCase):
    def test_incremental_failure_and_strategy_knowledge_persist(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = Path(temporary_directory) / "recovery.json"
            store = RecoveryKnowledgeStore(str(storage))
            error = {
                "error_type": "GRAPH_EXEC_FAIL",
                "stage": "graph_execute",
                "location": "step_2",
                "error": "bad parameter",
            }
            key = store.record_failure(error, operation="pagerank")
            store.record_strategy(key, "retry_with_error_feedback", success=None)
            store.record_strategy(key, "retry_with_error_feedback", success=True)

            restored = RecoveryKnowledgeStore(str(storage)).snapshot()
            self.assertEqual(restored["failure_knowledge_base"][key]["count"], 1)
            strategy = restored["recovery_strategy_knowledge_base"][key]["retry_with_error_feedback"]
            self.assertEqual(strategy["attempts"], 1)
            self.assertEqual(strategy["successes"], 1)


if __name__ == "__main__":
    unittest.main()
