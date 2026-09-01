from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


def _signature(error_info: Dict[str, Any], operation: str = "") -> str:
    return "|".join(
        str(error_info.get(key) or "")
        for key in ("error_type", "stage", "location")
    ) + f"|{operation}"


class FailureKnowledgeBase:
    """Incrementally records normalized failure cases and their frequencies."""

    def __init__(self, records: Optional[Dict[str, Dict[str, Any]]] = None):
        self.records = records or {}

    def record(self, error_info: Dict[str, Any], *, operation: str = "") -> str:
        key = _signature(error_info, operation)
        record = self.records.setdefault(
            key,
            {
                "error_type": error_info.get("error_type", ""),
                "stage": error_info.get("stage", ""),
                "location": error_info.get("location", ""),
                "operation": operation,
                "count": 0,
                "last_error": "",
            },
        )
        record["count"] += 1
        record["last_error"] = str(error_info.get("error") or "")[:1000]
        return key


class RecoveryStrategyKnowledgeBase:
    """Tracks recovery strategy outcomes for each normalized failure case."""

    def __init__(self, records: Optional[Dict[str, Dict[str, Any]]] = None):
        self.records = records or {}

    def record(self, failure_key: str, strategy: str, *, success: Optional[bool] = None) -> None:
        strategies = self.records.setdefault(failure_key, {})
        record = strategies.setdefault(strategy, {"attempts": 0, "successes": 0, "failures": 0})
        if success is None:
            record["attempts"] += 1
        elif success is True:
            if record["attempts"] <= record["successes"] + record["failures"]:
                record["attempts"] += 1
            record["successes"] += 1
        elif success is False:
            if record["attempts"] <= record["successes"] + record["failures"]:
                record["attempts"] += 1
            record["failures"] += 1

    def best(self, failure_key: str) -> Optional[str]:
        strategies = self.records.get(failure_key) or {}
        if not strategies:
            return None
        return max(
            strategies,
            key=lambda name: (
                strategies[name]["successes"] / max(strategies[name]["attempts"], 1),
                strategies[name]["successes"],
                -strategies[name]["failures"],
            ),
        )


class RecoveryKnowledgeStore:
    """Owns the failure KB and strategy KB, with optional JSON persistence."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else None
        self.failures = FailureKnowledgeBase()
        self.strategies = RecoveryStrategyKnowledgeBase()
        if self.storage_path and self.storage_path.exists():
            self.load()

    def record_failure(self, error_info: Dict[str, Any], *, operation: str = "") -> str:
        key = self.failures.record(error_info, operation=operation)
        self._autosave()
        return key

    def record_strategy(self, failure_key: str, strategy: str, *, success: Optional[bool] = None) -> None:
        self.strategies.record(failure_key, strategy, success=success)
        self._autosave()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "failure_knowledge_base": deepcopy(self.failures.records),
            "recovery_strategy_knowledge_base": deepcopy(self.strategies.records),
        }

    def save(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.storage_path)

    def load(self) -> None:
        if not self.storage_path:
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self.failures = FailureKnowledgeBase(payload.get("failure_knowledge_base") or {})
        self.strategies = RecoveryStrategyKnowledgeBase(payload.get("recovery_strategy_knowledge_base") or {})

    def _autosave(self) -> None:
        if self.storage_path:
            self.save()
