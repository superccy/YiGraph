import unittest

from aag.utils.llm_payload import without_original_result


class LlmPayloadTest(unittest.TestCase):
    def test_removes_original_result_recursively_without_mutating_source(self):
        source = {
            "original_result": {"large": "raw"},
            "summary": "kept",
            "nested": [
                {"Original_Result": [1, 2, 3], "value": 7},
                ("item", {"original_result": "raw", "count": 2}),
            ],
        }

        filtered = without_original_result(source)

        self.assertNotIn("original_result", filtered)
        self.assertEqual(filtered["summary"], "kept")
        self.assertEqual(filtered["nested"][0], {"value": 7})
        self.assertEqual(filtered["nested"][1][1], {"count": 2})
        self.assertIn("original_result", source)


if __name__ == "__main__":
    unittest.main()
