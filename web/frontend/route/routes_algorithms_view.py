"""Read-only presentation of the paper's existing algorithm metadata."""
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, request

bp = Blueprint("algorithms_view", __name__, url_prefix="/api")
KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "aag" / "knowledge_base"


@lru_cache(maxsize=4)
def _read_yaml(path, modified):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream) or []


def _load(name):
    path = KNOWLEDGE_DIR / name
    return _read_yaml(path, path.stat().st_mtime_ns)


def _algorithms():
    result = []
    for item in _load("algorithms.yaml"):
        deployment = item.get("Deployment_method") or {}
        principles = item.get("Principles") or {}
        if not isinstance(principles, dict):
            principles = {"description": str(principles)}
        parameters = (deployment.get("input_schema") or {}).get("parameters") or {}
        output = deployment.get("output_schema") or {}
        description = str(principles.get("description") or "")
        uses = item.get("Application_scenario") or ""
        result.append({
            "id": str(item["id"]), "name": str(item["id"]),
            "displayName": str(item.get("name") or item["id"]),
            "category": str(item.get("task_type_id") or "Uncategorized"),
            "summary": description, "description": description,
            "complexity": str(principles.get("time_complexity") or "—"),
            "inputs": [f"{name}: {value.get('description', value.get('type', ''))}" if isinstance(value, dict) else str(name)
                       for name, value in parameters.items()],
            "outputs": [str(output.get("description") or output.get("type") or "—")],
            "useCases": uses if isinstance(uses, list) else ([str(uses)] if uses else []),
            "chartPreference": "table", "tags": [str(deployment.get("support_engine") or "")],
        })
    return result


@bp.get("/algorithms")
def algorithms():
    try:
        query = request.args.get("search", "").casefold()
        category = request.args.get("category", "")
        data = [a for a in _algorithms()
                if (not category or a["category"] == category)
                and (not query or query in (a["name"] + " " + a["description"]).casefold())]
        return jsonify(success=True, data=data, total=len(data), readOnly=True)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return jsonify(success=False, error=str(exc)), 500


@bp.get("/algorithms/categories")
def categories():
    try:
        counts = Counter(a["category"] for a in _algorithms())
        labels = {str(t["id"]): str(t.get("task_type") or t["id"]) for t in _load("task_types.yaml")}
        data = [{"id": key, "label": labels.get(key, key), "count": count} for key, count in counts.items()]
        return jsonify(success=True, data=data, readOnly=True)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return jsonify(success=False, error=str(exc)), 500


@bp.get("/algorithms/<algorithm_id>")
def algorithm(algorithm_id):
    try:
        found = next((a for a in _algorithms() if a["id"] == algorithm_id), None)
        if found is None:
            return jsonify(success=False, error="Algorithm not found"), 404
        return jsonify(success=True, data=found, readOnly=True)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return jsonify(success=False, error=str(exc)), 500
