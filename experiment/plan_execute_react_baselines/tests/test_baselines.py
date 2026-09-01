from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest
import yaml

from graph_agent.code_executor import (
    TaskExecutionService,
    UnsafeGeneratedCode,
    validate_generated_code,
)
from graph_agent.config import (
    DatasetConfig,
    ModelConfig,
    RunConfig,
    dataset_for_domain,
)
from graph_agent.datasets import GraphWorkspace
from graph_agent.metrics import MetricsCollector
from graph_agent.retrieval import FlatDocumentationRetriever, expand_query
from graph_agent.run import load_questions
from graph_agent.workflows import (
    SharedServices,
    _validate_compiler_plan,
    build_compiler_graph,
    build_react_graph,
)


class ScriptedLLM:
    def __init__(self, responses: Dict[str, List[Dict[str, Any]]]) -> None:
        self.responses = responses

    def json(self, purpose: str, system: str, user: str) -> Dict[str, Any]:
        assert system
        assert user
        return self.responses[purpose].pop(0)


def make_fixture(tmp_path: Path) -> tuple[RunConfig, GraphWorkspace, FlatDocumentationRetriever, MetricsCollector]:
    data_dir = tmp_path / "data" / "Tiny" / "graph"
    schema_dir = tmp_path / "dataset_schemas" / "Tiny"
    kb_dir = tmp_path / "knowledge_base"
    data_dir.mkdir(parents=True)
    schema_dir.mkdir(parents=True)
    kb_dir.mkdir(parents=True)
    pd.DataFrame({"node_id": [1, 2, 3], "name": ["a", "b", "c"]}).to_csv(
        data_dir / "nodes.csv", index=False
    )
    pd.DataFrame({"source": [1, 2, 1], "target": [2, 3, 3], "amount": [2.0, 3.0, 4.0]}).to_csv(
        data_dir / "edges.csv", index=False
    )
    schema = {
        "datasets": [
            {
                "name": "Tiny",
                "schema": {
                    "graph": {"directed": True, "multigraph": True, "weighted": False},
                    "vertex": [{"id_field": "node_id", "path": "../../data/Tiny/graph/nodes.csv"}],
                    "edge": [
                        {
                            "source_field": "source",
                            "target_field": "target",
                            "path": "../../data/Tiny/graph/edges.csv",
                        }
                    ],
                },
            }
        ]
    }
    (schema_dir / "graph_schemas.yaml").write_text(
        yaml.safe_dump(schema, sort_keys=False), encoding="utf-8"
    )
    algorithms = [
        {
            "id": "degree_centrality",
            "task_type_id": "Centrality",
            "Deployment_method": {
                "support_engine": "networkx",
                "input_schema": {"parameters": {"G": {"type": "graph"}}},
                "output_schema": {"type": "dictionary"},
                "graph_type": {"directed": "both"},
            },
            "Application_scenario": "Find the most connected user in a social graph.",
            "solvable_questions": ["Which user has the most direct connections?"],
        }
    ]
    (kb_dir / "algorithms.yaml").write_text(
        yaml.safe_dump(algorithms, sort_keys=False), encoding="utf-8"
    )
    (kb_dir / "task_types.yaml").write_text("[]\n", encoding="utf-8")
    model = ModelConfig(model="fake", api_key="fake")
    config = RunConfig(model=model, output_dir=tmp_path / "runs", knowledge_base_dir=kb_dir)
    metrics = MetricsCollector(model)
    workspace = GraphWorkspace(
        DatasetConfig("Tiny", data_dir.parent, schema_dir / "graph_schemas.yaml"), metrics, chunksize=2
    )
    return config, workspace, FlatDocumentationRetriever(kb_dir), metrics


def services_with(tmp_path: Path, llm: ScriptedLLM) -> SharedServices:
    config, workspace, retriever, metrics = make_fixture(tmp_path)
    executor = TaskExecutionService(config, llm, metrics, workspace, retriever)  # type: ignore[arg-type]
    return SharedServices(config, llm, metrics, workspace, retriever, executor)  # type: ignore[arg-type]


def test_code_validator_blocks_import_and_open() -> None:
    with pytest.raises(UnsafeGeneratedCode):
        validate_generated_code("import os\nresult = 1")
    with pytest.raises(UnsafeGeneratedCode):
        validate_generated_code("result = open('/tmp/x').read()")
    validate_generated_code("result = sorted([3, 1, 2])")


def test_compiler_plan_validation() -> None:
    tasks = _validate_compiler_plan(
        [
            {"id": 1, "description": "a", "dependencies": []},
            {"id": 2, "description": "b", "dependencies": [1]},
        ]
    )
    assert [task.id for task in tasks] == [1, 2]
    with pytest.raises(ValueError):
        _validate_compiler_plan([{"id": 1, "description": "bad", "dependencies": [1]}])
    replanned = _validate_compiler_plan(
        [{"id": 3, "description": "reuse prior result", "dependencies": [1]}],
        external_dependency_ids={1, 2},
        minimum_task_id=3,
    )
    assert replanned[0].dependencies == [1]


def test_flat_retrieval_expands_chinese_graph_concepts(tmp_path: Path) -> None:
    _, _, retriever, _ = make_fixture(tmp_path)
    # The tiny fixture has only degree_centrality, which should be forced by “直接”.
    assert retriever.retrieve("统计直接交易账户", top_k=1)[0].algorithm_id == "degree_centrality"
    assert "louvain_communities" in expand_query("识别蛋白质功能模块")


def test_question_dataset_routing(tmp_path: Path) -> None:
    assert dataset_for_domain("finance", tmp_path).name == "AMLSim1M"
    assert dataset_for_domain("social", tmp_path).name == "Twitter_SignedGraphs"
    assert dataset_for_domain("protein", tmp_path).name == "ogbn_proteins"
    assert dataset_for_domain("Protein", tmp_path).schema_path == (
        tmp_path / "dataset_schemas" / "ogbn_proteins" / "graph_schemas.yaml"
    )
    with pytest.raises(ValueError):
        dataset_for_domain("unknown", tmp_path)


def test_load_questions_jsonl_uses_string_ids_and_domains(tmp_path: Path) -> None:
    question_file = tmp_path / "questions_75.jsonl"
    rows = [
        {"question_id": "F01", "domain": "finance", "question": "Finance question"},
        {"question_id": "S25", "domain": "social", "question": "Social question"},
        {"question_id": "P25", "domain": "protein", "question": "Protein question"},
    ]
    question_file.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    questions = load_questions(question_file)

    assert list(questions) == ["F01", "S25", "P25"]
    assert questions["S25"] == {
        "question_id": "S25",
        "domain": "social",
        "question": "Social question",
    }


def test_workspace_materializes_identical_graph_once_across_threads(tmp_path: Path) -> None:
    _, workspace, _, metrics = make_fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        graphs = list(pool.map(lambda _: workspace.graph(simple=True), range(2)))
    assert graphs[0] is graphs[1]
    graph_loads = [
        event for event in metrics.snapshot()["events"]
        if event["kind"] == "data_load" and event["name"] == "networkx_graph"
    ]
    assert len(graph_loads) == 1


def test_compiler_and_react_share_executor(tmp_path: Path) -> None:
    code = (
        "G = workspace.graph(simple=True)\n"
        "scores = graph_tool('degree_centrality', graph=G)\n"
        "result = {'top': sorted(scores.items(), key=lambda item: item[1], reverse=True)[0]}"
    )
    compiler_llm = ScriptedLLM(
        {
            "compiler_planning": [
                {
                    "tasks": [
                        {
                            "id": 1,
                            "description": "Find highest degree node",
                            "dependencies": [],
                            "algorithm_hint": "degree_centrality",
                        }
                    ]
                }
            ],
            "code_generation": [{"code": code}],
            "compiler_join": [{"decision": "finish", "answer": "Node 1 is central."}],
        }
    )
    compiler_state = build_compiler_graph(services_with(tmp_path / "compiler", compiler_llm)).invoke(
        {"question": "Who is central?"}
    )
    assert compiler_state["final_answer"] == "Node 1 is central."
    assert compiler_state["outcomes"][0].success

    react_llm = ScriptedLLM(
        {
            "react_reasoning": [
                {
                    "thought": "Measure direct connectivity.",
                    "action": "execute",
                    "task": {
                        "id": 1,
                        "description": "Find highest degree node",
                        "dependencies": [],
                        "algorithm_hint": "degree_centrality",
                    },
                },
                {"thought": "Observation is sufficient.", "action": "finish", "answer": "Node 1 is central."},
            ],
            "code_generation": [{"code": code}],
        }
    )
    react_state = build_react_graph(services_with(tmp_path / "react", react_llm)).invoke(
        {"question": "Who is central?"}
    )
    assert react_state["final_answer"] == "Node 1 is central."
    assert react_state["outcomes"][0].success


def test_compiler_replanning_can_depend_on_prior_round(tmp_path: Path) -> None:
    llm = ScriptedLLM(
        {
            "compiler_planning": [
                {"tasks": [{"id": 1, "description": "produce seed", "dependencies": []}]},
                {"tasks": [{"id": 2, "description": "adapt seed", "dependencies": [1]}]},
            ],
            "code_generation": [
                {"code": "result = {'seed': 7}"},
                {"code": "result = {'adapted': inputs[1]['seed'] + 1}"},
            ],
            "compiler_join": [
                {"decision": "replan", "feedback": "adapt the seed"},
                {"decision": "finish", "answer": "Adapted value is 8."},
            ],
        }
    )
    state = build_compiler_graph(services_with(tmp_path, llm)).invoke(
        {"question": "Produce and adapt a value."}
    )
    assert state["final_answer"] == "Adapted value is 8."
    assert [outcome.task.id for outcome in state["outcomes"]] == [1, 2]
    assert state["outcomes"][1].result == {"adapted": 8}
