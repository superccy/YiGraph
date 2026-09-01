# Plan-and-Execute and ReAct baselines

This directory contains the implementation of two comparable graph-analysis
baselines:

- `compiler`: an LLMCompiler-style Plan-and-Execute planner that emits an
  explicit dependency DAG, schedules ready tasks by dependency wave, and uses
  a join node for answering or replanning.
- `react`: a LangGraph ReAct planner that alternates reasoning and one action,
  observes the result, and then chooses the next action or finishes.

Only the planner control flow differs. Both baselines share:

- flat BM25 retrieval over `knowledge_base/algorithms.yaml`;
- the same NetworkX registry boundary and directed-graph adaptations;
- the same Python code generator and controlled executor;
- upstream-result adaptation, parameter binding, artifact passing, retries,
  and replanning feedback;
- token, cost, latency, data-load, Python, and graph-tool metrics.

The compiler planner rules are based on Appendix H of the LLMCompiler paper
(arXiv:2312.04511) and represented as validated JSON DAG tasks.

## Contents

```text
plan_execute_react_baselines/
├── graph_agent/       # planners and shared runtime
├── knowledge_base/    # flat algorithm documentation only
├── tests/             # synthetic, self-contained tests
├── requirements.txt
└── README.md
```

No datasets, credentials, caches, generated artifacts, logs, or experiment
outputs are included.

## Inputs

Provide these paths at runtime:

- `--question-file`: JSONL questions with `question_id`, `domain`, and `question` fields; defaults to `../questions_75.jsonl`;
- `--datasets-root`: an external directory containing `data/` and
  `dataset_schemas/`;
- `--knowledge-base`: optional override for the bundled flat documentation.

The dataset router maps the `finance`, `social`, and `protein` domains to
`AMLSim1M`, `Twitter_SignedGraphs`, and `ogbn_proteins`, respectively.

## Install and validate

```bash
python -m pip install -r requirements.txt

python -m graph_agent.run \
  --validate-only \
  --all \
  --datasets-root /path/to/external/datasets
```

Validation does not call a model or load the full graph.

## Run

Set credentials in the process environment. Do not store them in this
directory.

```bash
export BASELINE_MODEL='your-model-name'
export OPENAI_API_KEY='your-secret-at-runtime'
export OPENAI_BASE_URL='https://your-compatible-endpoint/v1'

python -m graph_agent.run \
  --baseline both \
  --question-id F01 \
  --datasets-root /path/to/external/datasets \
  --output-dir /path/outside/this/source-directory
```

Use `--baseline compiler` for Plan-and-Execute or `--baseline react` for
ReAct. Pricing arguments are optional; when absent, token counts are retained
and USD cost remains null.

## Test

```bash
pytest -q
```
