# Simple Failure-Recovery Baselines

This directory contains three deterministic, non-learning methods for offline
failure root-cause localization:

1. **Failed-Node Localization** selects every node with an explicit failure
   signal in its action or execution text.
2. **Rule-based Dependency Tracking** selects nodes with explicit evidence of
   missing fields or parameters, type/structure errors, graph/schema
   incompatibility, or dependency-resolution failure. Reporter-only nodes are
   excluded. It falls back to Failed-Node Localization when no rule matches.
3. **Hierarchical Backtracking** retains all failed-node candidates. The latest
   failed node is the current layer (L1). It searches upstream breadth-first and
   adds exactly the first layer that contains another explicit failure signal;
   traversed intermediate layers are not selected.

The implementation does not call an LLM, use a trained model, access a network,
or contain credentials. Ground-truth labels are only read by `evaluate.py` when
computing final node-level micro-averaged precision, recall, and F1.

## Input format

`--dataset` must contain `data/<trace_id>.json`. Each trace is a JSON list with
entries containing `step`, `role`, `action`, and `context`.

`--evaluation-manifest` is an external JSONL file. Each row contains:

```json
{"trace_id":"1","truth":[2,4],"candidate_steps":[1,2,3,4,5]}
```

The manifest and dataset are intentionally not included in this directory.

## Run

```bash
python3 evaluate.py \
  --dataset /path/to/dataset \
  --evaluation-manifest /path/to/evaluation_manifest.jsonl \
  --output /path/to/output
```

## Test

```bash
python3 -m unittest -v test_baselines.py
```

Only the Python standard library is required.
