from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskSpec:
    id: int
    description: str
    dependencies: List[int] = field(default_factory=list)
    algorithm_hint: Optional[str] = None
    expected_output: str = "JSON-serializable analysis result"

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "TaskSpec":
        return cls(
            id=int(value["id"]),
            description=str(value["description"]).strip(),
            dependencies=[int(item) for item in value.get("dependencies", [])],
            algorithm_hint=(str(value["algorithm_hint"]).strip() if value.get("algorithm_hint") else None),
            expected_output=str(value.get("expected_output") or "JSON-serializable analysis result"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskOutcome:
    task: TaskSpec
    success: bool
    result: Any = None
    error: Optional[str] = None
    code: Optional[str] = None
    attempts: int = 0
    duration_seconds: float = 0.0
    artifact_dir: Optional[str] = None

    def to_dict(self, include_result: bool = True) -> Dict[str, Any]:
        payload = asdict(self)
        if not include_result:
            payload.pop("result", None)
        return payload

