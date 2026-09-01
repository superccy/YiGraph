from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence, Tuple


def rank_metrics(ranked_steps: Sequence[int], positive_steps: Iterable[int], ks: Sequence[int] = (1, 3, 5)) -> Dict[str, float]:
    positives = set(positive_steps)
    if not positives:
        empty = {f"recall@{k}": 0.0 for k in ks}
        empty.update({f"hit@{k}": 0.0 for k in ks})
        empty.update({"mrr": 0.0, "map": 0.0, "ndcg@5": 0.0, "acc@0": 0.0, "acc@1": 0.0, "acc@2": 0.0, "acc@3": 0.0})
        return empty

    result: Dict[str, float] = {}
    for k in ks:
        top_k = set(ranked_steps[:k])
        result[f"recall@{k}"] = len(top_k & positives) / len(positives)
        result[f"hit@{k}"] = 1.0 if top_k & positives else 0.0
    label_count = len(positives)
    result["recall@label_count"] = len(set(ranked_steps[:label_count]) & positives) / label_count
    if ranked_steps:
        top_step = int(ranked_steps[0])
        nearest_distance = min(abs(top_step - int(step)) for step in positives)
        for k in range(4):
            result[f"acc@{k}"] = 1.0 if nearest_distance <= k else 0.0
    else:
        for k in range(4):
            result[f"acc@{k}"] = 0.0

    reciprocal_rank = 0.0
    precisions: List[float] = []
    hits = 0
    dcg = 0.0
    for rank, step in enumerate(ranked_steps, start=1):
        if step not in positives:
            continue
        hits += 1
        if reciprocal_rank == 0.0:
            reciprocal_rank = 1.0 / rank
        precisions.append(hits / rank)
        if rank <= 5:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(len(positives), 5)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    result["mrr"] = reciprocal_rank
    result["map"] = sum(precisions) / len(positives) if precisions else 0.0
    result["ndcg@5"] = dcg / ideal_dcg if ideal_dcg > 0 else 0.0
    return result


def average_metrics(items: Sequence[Dict[str, float]]) -> Dict[str, float]:
    if not items:
        return {}
    keys = sorted(items[0])
    return {key: sum(item.get(key, 0.0) for item in items) / len(items) for key in keys}


def binary_classification_metrics(y_true: Sequence[int], y_pred: Sequence[int]) -> Dict[str, float]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")

    tp = sum(1 for truth, pred in zip(y_true, y_pred) if truth == 1 and pred == 1)
    fp = sum(1 for truth, pred in zip(y_true, y_pred) if truth == 0 and pred == 1)
    tn = sum(1 for truth, pred in zip(y_true, y_pred) if truth == 0 and pred == 0)
    fn = sum(1 for truth, pred in zip(y_true, y_pred) if truth == 1 and pred == 0)
    total = tp + fp + tn + fn

    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    f0_5 = fbeta_score(precision, recall, beta=0.5)

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f0_5": f0_5,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def fbeta_score(precision: float, recall: float, beta: float) -> float:
    if beta <= 0:
        raise ValueError("beta must be greater than 0")
    beta_squared = beta * beta
    denominator = beta_squared * precision + recall
    if denominator == 0:
        return 0.0
    return (1.0 + beta_squared) * precision * recall / denominator


def select_best_f1_threshold(scores: Sequence[float], labels: Sequence[int]) -> Tuple[float, Dict[str, float]]:
    return select_best_fbeta_threshold(scores, labels, beta=1.0)


def select_best_fbeta_threshold(
    scores: Sequence[float],
    labels: Sequence[int],
    beta: float,
) -> Tuple[float, Dict[str, float]]:
    if len(scores) != len(labels):
        raise ValueError("scores and labels must have the same length")
    if beta <= 0:
        raise ValueError("beta must be greater than 0")
    if not scores:
        return 0.5, binary_classification_metrics([], [])

    best_threshold = 0.5
    best_metrics: Dict[str, float] = {}
    best_key = None
    for threshold in sorted(set(float(score) for score in scores)):
        predictions = [1 if score >= threshold else 0 for score in scores]
        metrics = binary_classification_metrics(labels, predictions)
        objective = fbeta_score(metrics["precision"], metrics["recall"], beta)
        if beta < 1.0:
            first_tie_break = metrics["precision"]
            second_tie_break = metrics["recall"]
        else:
            first_tie_break = metrics["recall"]
            second_tie_break = metrics["precision"]
        key = (
            objective,
            first_tie_break,
            second_tie_break,
            -abs(threshold - 0.5),
            -threshold,
        )
        if best_key is None or key > best_key:
            best_key = key
            best_threshold = threshold
            best_metrics = dict(metrics)
            best_metrics["threshold_objective"] = objective

    return best_threshold, best_metrics
