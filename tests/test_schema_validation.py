import unittest

from aag.utils.schema_validation import (
    SchemaValidationError,
    assert_valid_output,
    assert_valid_parameters,
)


class SchemaValidationTest(unittest.TestCase):
    def test_input_spec_checks_required_type_constraint_and_unknown_fields(self):
        schema = {
            "parameters": {
                "G": {"type": "graph", "required": True},
                "k": {"type": "integer", "required": True, "minimum": 1},
                "normalized": {"type": "boolean", "default": True},
            }
        }
        assert_valid_parameters({"k": 3, "normalized": False}, schema)

        with self.assertRaises(SchemaValidationError):
            assert_valid_parameters({"k": 0}, schema)
        with self.assertRaises(SchemaValidationError):
            assert_valid_parameters({"k": 3, "unexpected": 1}, schema)

    def test_output_spec_checks_nested_fields(self):
        schema = {
            "type": "dict",
            "fields": {
                "scores": {"type": "dictionary", "required": True},
                "count": {"type": "integer", "required": True, "minimum": 0},
            },
            "additionalProperties": False,
        }
        assert_valid_output({"scores": {"a": 0.5}, "count": 1}, schema)
        with self.assertRaises(SchemaValidationError):
            assert_valid_output({"scores": [], "count": 1}, schema)
        with self.assertRaises(SchemaValidationError):
            assert_valid_output({"scores": {}, "count": 0, "extra": True}, schema)


if __name__ == "__main__":
    unittest.main()
