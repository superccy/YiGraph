from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


SYSTEM_INJECTED_PARAMETERS = {
    "G",
    "graph",
    "global_graph",
    "dataset_config",
    "backend_kwargs",
    "__post_processing_code__",
}


class SchemaValidationError(ValueError):
    """Raised when runtime data violates an InputSpec or OutputSpec."""

    def __init__(self, errors: Sequence[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _type_tokens(type_spec: Any) -> set[str]:
    if isinstance(type_spec, (list, tuple, set)):
        tokens: set[str] = set()
        for item in type_spec:
            tokens.update(_type_tokens(item))
        return tokens
    normalized = re.sub(r"[^a-z0-9_]+", " ", str(type_spec or "any").lower())
    return {token for token in normalized.split() if token}


def _allows_none(spec: Mapping[str, Any], tokens: set[str]) -> bool:
    return bool(
        spec.get("nullable")
        or "none" in tokens
        or "null" in tokens
        or spec.get("default", object()) is None
    )


def _matches_type(value: Any, type_spec: Any) -> bool:
    tokens = _type_tokens(type_spec)
    raw_type = str(type_spec or "any").lower()
    if not tokens or tokens & {"any", "object", "unknown"}:
        return True
    if value is None:
        return "none" in tokens or "null" in tokens or "optional" in tokens

    if tokens & {"bool", "boolean"} and isinstance(value, bool):
        return True
    if tokens & {"int", "integer"} and isinstance(value, int) and not isinstance(value, bool):
        return True
    if tokens & {"float", "number", "numeric", "double", "real", "scalar"}:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            return True
    if "node" in tokens and isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return True
    if tokens & {"str", "string", "key", "path", "label"} and isinstance(value, str):
        return True
    if tokens & {"dict", "dictionary", "mapping", "map"} and isinstance(value, Mapping):
        return True
    if tokens & {"list", "array", "sequence", "container", "set", "tuple", "generator", "iterator", "iterable", "pair", "edges"}:
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
            return True
    if "graph" in tokens:
        if hasattr(value, "nodes") and hasattr(value, "edges"):
            return True
        if isinstance(value, Mapping) and ({"nodes", "edges"} <= set(value) or {"vertices", "edges"} <= set(value)):
            return True
    if tokens & {"callable", "function"} and callable(value):
        return True
    if tokens & {"class", "type", "dtype"} and (isinstance(value, type) or isinstance(value, str)):
        return True
    if tokens & {"numpy", "ndarray", "scipy", "sparse"} and hasattr(value, "shape"):
        return True
    if isinstance(value, str) and ("'" in raw_type or '"' in raw_type):
        return True

    recognized = {
        "bool", "boolean", "int", "integer", "float", "number", "numeric", "double",
        "real", "scalar", "str", "string", "key", "node", "path", "label", "dict",
        "dictionary", "mapping", "map", "list", "array", "sequence", "container", "set",
        "tuple", "generator", "iterator", "iterable", "pair", "edges", "graph", "callable",
        "function", "class", "type", "dtype", "numpy", "ndarray", "scipy", "sparse",
    }
    # Legacy schemas contain prose types. Enforce every type we can parse and
    # leave truly unknown prose to explicit enum/range/shape constraints.
    return not bool(tokens & recognized)


def _validate_constraints(value: Any, spec: Mapping[str, Any], path: str) -> List[str]:
    errors: List[str] = []
    choices = spec.get("enum") or spec.get("choices")
    if choices is not None and value not in choices:
        errors.append(f"{path} must be one of {list(choices)!r}, got {value!r}")

    minimum = spec.get("minimum", spec.get("min"))
    maximum = spec.get("maximum", spec.get("max"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if minimum is not None and value < minimum:
            errors.append(f"{path} must be >= {minimum}, got {value}")
        if maximum is not None and value > maximum:
            errors.append(f"{path} must be <= {maximum}, got {value}")

    min_length = spec.get("minLength", spec.get("min_items"))
    max_length = spec.get("maxLength", spec.get("max_items"))
    if hasattr(value, "__len__"):
        if min_length is not None and len(value) < min_length:
            errors.append(f"{path} length must be >= {min_length}, got {len(value)}")
        if max_length is not None and len(value) > max_length:
            errors.append(f"{path} length must be <= {max_length}, got {len(value)}")

    pattern = spec.get("pattern")
    if pattern and isinstance(value, str) and re.search(pattern, value) is None:
        errors.append(f"{path} does not match pattern {pattern!r}")
    return errors


def validate_value(value: Any, spec: Optional[Mapping[str, Any]], path: str = "value") -> List[str]:
    if not spec:
        return []
    type_spec = spec.get("type", "any")
    tokens = _type_tokens(type_spec)
    if value is None:
        if _allows_none(spec, tokens):
            return []
        return [f"{path} must not be null"]
    if not _matches_type(value, type_spec):
        return [f"{path} expected type {type_spec!r}, got {type(value).__name__}"]

    errors = _validate_constraints(value, spec, path)
    fields = spec.get("fields") or spec.get("properties")
    if fields and isinstance(value, Mapping):
        required = set(spec.get("required") or [])
        required.update(name for name, child in fields.items() if child.get("required") is True)
        for name in required:
            if name not in value:
                errors.append(f"{path} missing required field {name!r}")
        for name, child in fields.items():
            if name in value:
                errors.extend(validate_value(value[name], child, f"{path}.{name}"))
        if spec.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(fields))
            if unknown:
                errors.append(f"{path} has unknown fields: {unknown}")
    return errors


def validate_parameters(
    parameters: Optional[Mapping[str, Any]],
    schema: Optional[Mapping[str, Any]],
    *,
    system_injected: Optional[set[str]] = None,
    reject_unknown: bool = True,
) -> List[str]:
    if not schema:
        return []
    if not isinstance(parameters, Mapping):
        return [f"parameters must be a mapping, got {type(parameters).__name__}"]

    specs: Dict[str, Any] = dict(schema.get("parameters") or schema.get("properties") or {})
    injected = SYSTEM_INJECTED_PARAMETERS | set(system_injected or set())
    required = set(schema.get("required") or [])
    required.update(name for name, spec in specs.items() if spec.get("required") is True)
    required.difference_update(injected)

    errors: List[str] = []
    for name in sorted(required):
        if name not in parameters:
            errors.append(f"parameters missing required field {name!r}")
    for name, value in parameters.items():
        if name in injected:
            continue
        spec = specs.get(name)
        if spec is None:
            if reject_unknown:
                errors.append(f"parameters has unknown field {name!r}")
            continue
        errors.extend(validate_value(value, spec, f"parameters.{name}"))
    return errors


def assert_valid_parameters(
    parameters: Optional[Mapping[str, Any]],
    schema: Optional[Mapping[str, Any]],
    *,
    system_injected: Optional[set[str]] = None,
    reject_unknown: bool = True,
) -> None:
    errors = validate_parameters(
        parameters,
        schema,
        system_injected=system_injected,
        reject_unknown=reject_unknown,
    )
    if errors:
        raise SchemaValidationError(errors)


def assert_valid_output(value: Any, schema: Optional[Mapping[str, Any]]) -> None:
    errors = validate_value(value, schema, "output")
    if errors:
        raise SchemaValidationError(errors)
