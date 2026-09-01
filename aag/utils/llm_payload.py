"""Helpers for reducing execution payloads before they are sent to an LLM."""

from __future__ import annotations

from typing import Any


def without_original_result(value: Any) -> Any:
    """Recursively copy a payload while removing every ``original_result`` key."""
    if isinstance(value, dict):
        return {
            key: without_original_result(item)
            for key, item in value.items()
            if str(key).strip().lower() != "original_result"
        }
    if isinstance(value, list):
        return [without_original_result(item) for item in value]
    if isinstance(value, tuple):
        return tuple(without_original_result(item) for item in value)
    return value
