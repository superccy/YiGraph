from __future__ import annotations

import argparse
import copy
import json
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch.nn import functional as F

from .data import (
    CORRECT_ERROR_TASKS,
    TraceDataset,
    TraceTensor,
    build_dataset,
    load_correct_error_examples,
    load_raw_examples,
    validate_raw_examples,
)
from .features import TextEncoder
from .metrics import (
    average_metrics,
    binary_classification_metrics,
    rank_metrics,
    select_best_fbeta_threshold,
    select_best_f1_threshold,
)
from .model import RelationalRootCauseModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train R-GCN root-cause localization on multi-agent logs")
    parser.add_argument("--data-format", choices=("tracegraph", "correct_error"), default="tracegraph")
    parser.add_argument("--correct-error-path", type=Path, default=None)
    parser.add_argument("--correct-error-task", choices=CORRECT_ERROR_TASKS, default="all")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Dataset root containing data/ and answer/ directories",
    )
    parser.add_argument("--failure-dir", type=Path, default=None)
    parser.add_argument("--annotation-dir", type=Path, default=None)
    parser.add_argument("--success-dir", type=Path, default=None, help="Accepted for interface compatibility; not used in v1 supervised training")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--num-bases", type=int, default=4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--match-label-count-top-k",
        action="store_true",
        help="Output top N predictions per trace where N is the number of annotated positive steps",
    )
    parser.add_argument("--text-model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--no-hashing-fallback", action="store_true")
    parser.add_argument("--evaluation-mode", choices=("ranking", "classification"), default="ranking")
    parser.add_argument(
        "--threshold-strategy",
        choices=("oof_f1", "validation_f1", "validation_f0_5", "fixed"),
        default="validation_f1",
        help="oof_f1 selects a threshold from inner-fold out-of-fold predictions",
    )
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--oof-folds", type=int, default=3)
    parser.add_argument("--early-stopping-patience", type=int, default=5)
    parser.add_argument("--early-stopping-min-delta", type=float, default=0.0)
    parser.add_argument("--classification-threshold", type=float, default=0.5)
    parser.add_argument(
        "--positive-weight-scale",
        type=float,
        default=1.0,
        help="Scale BCE positive-class weight; values below 1 penalize false positives relatively more",
    )
    parser.add_argument("--model-type", choices=("rgcn",), default="rgcn")
    parser.add_argument(
        "--scorer-mode",
        choices=("candidate_only", "pairwise"),
        default="candidate_only",
        help="candidate_only scores each candidate embedding independently; pairwise also uses the error node and pair features",
    )
    parser.add_argument("--edge-mode", choices=("full", "time", "none"), default="full")
    parser.add_argument(
        "--candidate-scope",
        choices=("observed", "all"),
        default="observed",
        help="observed uses non-user steps up to the selected observation step; all uses every non-user step",
    )
    parser.add_argument(
        "--error-observed-strategy",
        choices=("auto", "discovered_at", "last_step"),
        default="auto",
        help="auto uses discovered_at when available, otherwise the final non-user step",
    )
    parser.add_argument("--device", default="cpu", help="Use cpu by default; pass cuda only with a compatible PyTorch/CUDA build")
    return parser.parse_args()


def main() -> None:
    run_start = time.perf_counter()
    args = parse_args()
    if args.data_format == "tracegraph":
        args.failure_dir, args.annotation_dir = resolve_data_directories(
            args.dataset_dir,
            args.failure_dir,
            args.annotation_dir,
        )
    set_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    data_start = time.perf_counter()
    if args.data_format == "correct_error":
        if args.correct_error_path is None:
            raise ValueError("--correct-error-path is required when --data-format correct_error")
        raw_examples = load_correct_error_examples(
            args.correct_error_path,
            task=args.correct_error_task,
            limit=args.limit,
            candidate_scope=args.candidate_scope,
            error_observed_strategy=args.error_observed_strategy,
        )
    else:
        raw_examples = load_raw_examples(
            args.failure_dir,
            args.annotation_dir,
            limit=args.limit,
            candidate_scope=args.candidate_scope,
            error_observed_strategy=args.error_observed_strategy,
        )
    if not raw_examples:
        raise ValueError("No traces loaded for the requested dataset/filter")
    validate_raw_examples(raw_examples)
    data_seconds = time.perf_counter() - data_start

    feature_start = time.perf_counter()
    text_encoder = TextEncoder(
        model_name=args.text_model,
        cache_dir=args.output_dir / "feature_cache",
        allow_hashing_fallback=not args.no_hashing_fallback,
    )
    dataset = build_dataset(raw_examples, text_encoder)
    feature_seconds = time.perf_counter() - feature_start

    folds = make_folds(dataset.examples, args.folds, args.seed)
    all_predictions: List[Dict] = []
    fold_metrics: List[Dict] = []
    all_classification_labels: List[int] = []
    all_classification_predictions: List[int] = []
    all_trace_classification_metrics: List[Dict[str, float]] = []
    if args.evaluation_mode == "classification" and not 0.0 < args.validation_ratio < 1.0:
        raise ValueError("--validation-ratio must be between 0 and 1")
    if not 0.0 <= args.classification_threshold <= 1.0:
        raise ValueError("--classification-threshold must be between 0 and 1")
    if args.positive_weight_scale <= 0.0:
        raise ValueError("--positive-weight-scale must be greater than 0")
    if args.num_layers < 1:
        raise ValueError("--num-layers must be at least 1")
    if args.num_bases < 1:
        raise ValueError("--num-bases must be at least 1")
    if args.oof_folds < 2:
        raise ValueError("--oof-folds must be at least 2")
    if args.early_stopping_patience < 1:
        raise ValueError("--early-stopping-patience must be at least 1")
    if args.early_stopping_min_delta < 0.0:
        raise ValueError("--early-stopping-min-delta must be non-negative")
    print(
        f"Loaded {len(dataset.examples)} traces in {data_seconds:.2f}s; "
        f"built features with backend={text_encoder.backend} in {feature_seconds:.2f}s",
        flush=True,
    )
    for fold_index, (outer_train_examples, test_examples) in enumerate(folds):
        fold_start = time.perf_counter()
        edge_mode = args.edge_mode
        training_details: Dict = {}
        if args.evaluation_mode == "classification" and args.threshold_strategy == "oof_f1":
            train_examples = list(outer_train_examples)
            validation_examples = []
        elif args.evaluation_mode == "classification":
            train_examples, validation_examples = split_train_validation(
                outer_train_examples,
                args.validation_ratio,
                args.seed + fold_index,
            )
        else:
            train_examples = list(outer_train_examples)
            validation_examples = []

        train_start = time.perf_counter()
        if args.evaluation_mode == "classification" and args.threshold_strategy == "oof_f1":
            model, threshold, validation_metrics, training_details = train_with_oof_threshold(
                outer_train_examples=outer_train_examples,
                dataset=dataset,
                args=args,
                edge_mode=edge_mode,
                outer_fold_index=fold_index,
            )
            last_train_loss = training_details["last_train_loss"]
        else:
            model = create_model(dataset, args)
            optimizer = create_optimizer(model, args)
            if args.evaluation_mode == "classification":
                training_details = train_with_early_stopping(
                    model=model,
                    optimizer=optimizer,
                    train_examples=train_examples,
                    validation_examples=validation_examples,
                    max_epochs=args.epochs,
                    patience=args.early_stopping_patience,
                    min_delta=args.early_stopping_min_delta,
                    device=args.device,
                    edge_mode=edge_mode,
                    positive_weight_scale=args.positive_weight_scale,
                    threshold_strategy=args.threshold_strategy,
                    fixed_threshold=args.classification_threshold,
                    seed=args.seed + fold_index,
                )
                threshold = training_details["threshold"]
                validation_metrics = training_details["validation_metrics"]
                last_train_loss = training_details["last_train_loss"]
                save_checkpoint(
                    args.output_dir / "checkpoints" / f"fold_{fold_index}_best.pt",
                    model,
                    {
                        "fold": fold_index,
                        "best_epoch": training_details["best_epoch"],
                        "threshold": threshold,
                        "threshold_strategy": args.threshold_strategy,
                    },
                )
            else:
                last_train_loss = train_fixed_epochs(
                    model=model,
                    optimizer=optimizer,
                    examples=train_examples,
                    epochs=args.epochs,
                    seed=args.seed + fold_index,
                    device=args.device,
                    edge_mode=edge_mode,
                    positive_weight_scale=args.positive_weight_scale,
                )
                threshold = None
                validation_metrics = {}
        train_seconds = time.perf_counter() - train_start

        eval_start = time.perf_counter()
        if args.evaluation_mode == "classification":
            predictions, metrics, test_labels, test_predictions, trace_metrics = evaluate_classification(
                model,
                test_examples,
                args.device,
                edge_mode,
                threshold,
            )
            all_classification_labels.extend(test_labels)
            all_classification_predictions.extend(test_predictions)
            all_trace_classification_metrics.extend(trace_metrics)
        else:
            threshold = None
            validation_metrics = {}
            predictions, metrics = evaluate_ranking(
                model,
                test_examples,
                args.device,
                args.top_k,
                edge_mode,
                args.match_label_count_top_k,
            )
        eval_seconds = time.perf_counter() - eval_start
        fold_seconds = time.perf_counter() - fold_start
        fold_metrics.append(
            {
                "fold": fold_index,
                "n_outer_train": len(outer_train_examples),
                "n_train": len(train_examples),
                "n_validation": len(validation_examples),
                "n_test": len(test_examples),
                "train_seconds": train_seconds,
                "eval_seconds": eval_seconds,
                "total_seconds": fold_seconds,
                "last_train_loss": last_train_loss,
                **training_details_for_output(training_details),
                **(
                    {
                        "classification_threshold": threshold,
                        "threshold_source": (
                            "oof"
                            if args.threshold_strategy == "oof_f1"
                            else "fixed"
                            if args.threshold_strategy == "fixed"
                            else "validation"
                        ),
                        "validation_precision": validation_metrics.get("precision", 0.0),
                        "validation_f1": validation_metrics.get("f1", 0.0),
                        "validation_f0_5": validation_metrics.get("f0_5", 0.0),
                        "validation_threshold_objective": validation_metrics.get(
                            "threshold_objective",
                            validation_metrics.get("f1", 0.0),
                        ),
                        "validation_recall": validation_metrics.get("recall", 0.0),
                        **(
                            {
                                "oof_precision": validation_metrics.get("precision", 0.0),
                                "oof_recall": validation_metrics.get("recall", 0.0),
                                "oof_f1": validation_metrics.get("f1", 0.0),
                            }
                            if args.threshold_strategy == "oof_f1"
                            else {}
                        ),
                    }
                    if args.evaluation_mode == "classification"
                    else {}
                ),
                **metrics,
            }
        )
        all_predictions.extend(predictions)
        threshold_text = f" threshold={threshold:.6f}" if threshold is not None else ""
        print(
            f"Fold {fold_index + 1}/{len(folds)} finished: "
            f"train={train_seconds:.2f}s eval={eval_seconds:.2f}s total={fold_seconds:.2f}s "
            f"last_loss={last_train_loss:.4f}{threshold_text}"
            f"{format_epoch_summary(training_details)}",
            flush=True,
        )

    total_seconds = time.perf_counter() - run_start
    if args.evaluation_mode == "classification":
        metrics_summary = binary_classification_metrics(
            all_classification_labels,
            all_classification_predictions,
        )
        macro_metrics = average_metrics(all_trace_classification_metrics)
        metrics_summary.update({f"macro_{key}": value for key, value in macro_metrics.items()})
    else:
        excluded_keys = {
            "train_seconds",
            "eval_seconds",
            "total_seconds",
            "last_train_loss",
        }
        metrics_summary = average_metrics(
            [
                {
                    key: value
                    for key, value in item.items()
                    if isinstance(value, float) and key not in excluded_keys
                }
                for item in fold_metrics
            ]
        )
    metrics_payload = {
        "n_traces": len(dataset.examples),
        "folds": args.folds,
        "data_format": args.data_format,
        "correct_error_path": str(args.correct_error_path) if args.correct_error_path is not None else None,
        "correct_error_task": args.correct_error_task if args.data_format == "correct_error" else None,
        "dataset_dir": str(args.dataset_dir) if args.dataset_dir is not None else None,
        "failure_dir": str(args.failure_dir) if args.failure_dir is not None else None,
        "annotation_dir": str(args.annotation_dir) if args.annotation_dir is not None else None,
        "text_model": args.text_model,
        "text_backend": text_encoder.backend,
        "model_type": args.model_type,
        "num_layers": args.num_layers,
        "num_bases": args.num_bases,
        "scorer_mode": args.scorer_mode,
        "edge_mode": args.edge_mode,
        "evaluation_mode": args.evaluation_mode,
        "candidate_scope": args.candidate_scope,
        "error_observed_strategy": args.error_observed_strategy,
        "positive_weight_scale": args.positive_weight_scale,
        **(
            {
                "threshold_strategy": args.threshold_strategy,
                "validation_ratio": args.validation_ratio,
                "oof_folds": args.oof_folds,
                "early_stopping_patience": args.early_stopping_patience,
                "early_stopping_min_delta": args.early_stopping_min_delta,
                "fixed_classification_threshold": args.classification_threshold,
            }
            if args.evaluation_mode == "classification"
            else {
                "prediction_top_k": "label_count" if args.match_label_count_top_k else args.top_k,
            }
        ),
        "runtime_seconds": {
            "data_loading": data_seconds,
            "feature_building": feature_seconds,
            "cross_validation": sum(item["total_seconds"] for item in fold_metrics),
            "total": total_seconds,
        },
        "metrics": metrics_summary,
    }
    write_outputs(args.output_dir, all_predictions, metrics_payload, fold_metrics)
    print(json.dumps(metrics_payload, ensure_ascii=False, indent=2))


def train_one_epoch(
    model: RelationalRootCauseModel,
    examples: Sequence[TraceTensor],
    optimizer: torch.optim.Optimizer,
    device: str,
    edge_mode: str,
    positive_weight_scale: float = 1.0,
) -> float:
    model.train()
    total_loss = 0.0
    used = 0
    for example in examples:
        labels = torch.tensor(example.labels, dtype=torch.float32, device=device)
        if labels.numel() == 0 or labels.sum().item() == 0:
            continue
        optimizer.zero_grad()
        logits = run_model(model, example, device, edge_mode)
        negatives = max(1.0, float((labels == 0).sum().item()))
        positives = max(1.0, float((labels == 1).sum().item()))
        pos_weight = torch.tensor(
            (negatives / positives) * positive_weight_scale,
            dtype=torch.float32,
            device=device,
        )
        loss = F.binary_cross_entropy_with_logits(logits, labels, pos_weight=pos_weight)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
        optimizer.step()
        total_loss += float(loss.item())
        used += 1
    return total_loss / max(1, used)


def create_model(dataset: TraceDataset, args: argparse.Namespace) -> RelationalRootCauseModel:
    model = RelationalRootCauseModel(
        dataset.input_dim,
        dataset.edge_dim,
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        scorer_mode=args.scorer_mode,
        num_layers=args.num_layers,
        num_bases=args.num_bases,
    )
    return model.to(args.device)


def create_optimizer(model: RelationalRootCauseModel, args: argparse.Namespace) -> torch.optim.Optimizer:
    return torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)


def train_fixed_epochs(
    model: RelationalRootCauseModel,
    optimizer: torch.optim.Optimizer,
    examples: Sequence[TraceTensor],
    epochs: int,
    seed: int,
    device: str,
    edge_mode: str,
    positive_weight_scale: float,
) -> float:
    last_train_loss = 0.0
    for epoch_index in range(epochs):
        shuffled = list(examples)
        random.Random(seed + epoch_index).shuffle(shuffled)
        last_train_loss = train_one_epoch(
            model,
            shuffled,
            optimizer,
            device,
            edge_mode,
            positive_weight_scale=positive_weight_scale,
        )
    return last_train_loss


def train_with_early_stopping(
    model: RelationalRootCauseModel,
    optimizer: torch.optim.Optimizer,
    train_examples: Sequence[TraceTensor],
    validation_examples: Sequence[TraceTensor],
    max_epochs: int,
    patience: int,
    min_delta: float,
    device: str,
    edge_mode: str,
    positive_weight_scale: float,
    threshold_strategy: str,
    fixed_threshold: float,
    seed: int,
) -> Dict:
    best_state = None
    best_objective = float("-inf")
    best_epoch = 1
    best_train_loss = 0.0
    best_threshold = fixed_threshold
    best_validation_metrics: Dict[str, float] = {}
    stale_epochs = 0
    epochs_trained = 0

    for epoch_index in range(max_epochs):
        shuffled = list(train_examples)
        random.Random(seed + epoch_index).shuffle(shuffled)
        train_loss = train_one_epoch(
            model,
            shuffled,
            optimizer,
            device,
            edge_mode,
            positive_weight_scale=positive_weight_scale,
        )
        validation_scores, validation_labels = collect_scores(
            model,
            validation_examples,
            device,
            edge_mode,
        )
        threshold, validation_metrics = select_threshold(
            validation_scores,
            validation_labels,
            threshold_strategy,
            fixed_threshold,
        )
        objective = validation_metrics.get("threshold_objective", validation_metrics.get("f1", 0.0))
        epochs_trained = epoch_index + 1
        if best_state is None or objective > best_objective + min_delta:
            best_state = copy.deepcopy(model.state_dict())
            best_objective = objective
            best_epoch = epochs_trained
            best_train_loss = train_loss
            best_threshold = threshold
            best_validation_metrics = validation_metrics
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return {
        "best_epoch": best_epoch,
        "epochs_trained": epochs_trained,
        "best_validation_objective": best_objective,
        "threshold": best_threshold,
        "validation_metrics": best_validation_metrics,
        "last_train_loss": best_train_loss,
    }


def train_with_oof_threshold(
    outer_train_examples: Sequence[TraceTensor],
    dataset: TraceDataset,
    args: argparse.Namespace,
    edge_mode: str,
    outer_fold_index: int,
) -> Tuple[RelationalRootCauseModel, float, Dict[str, float], Dict]:
    inner_fold_count = min(args.oof_folds, len(outer_train_examples))
    if inner_fold_count < 2:
        raise ValueError("OOF threshold selection requires at least two outer-training traces")

    inner_seed = args.seed + (outer_fold_index + 1) * 1000
    inner_folds = make_folds(outer_train_examples, inner_fold_count, inner_seed)
    oof_scores: List[float] = []
    oof_labels: List[int] = []
    inner_best_epochs: List[int] = []
    inner_epochs_trained: List[int] = []
    checkpoint_dir = args.output_dir / "checkpoints" / f"fold_{outer_fold_index}"

    for inner_fold_index, (inner_train, inner_validation) in enumerate(inner_folds):
        model_seed = inner_seed + inner_fold_index + 1
        set_seed(model_seed)
        inner_model = create_model(dataset, args)
        inner_optimizer = create_optimizer(inner_model, args)
        result = train_with_early_stopping(
            model=inner_model,
            optimizer=inner_optimizer,
            train_examples=inner_train,
            validation_examples=inner_validation,
            max_epochs=args.epochs,
            patience=args.early_stopping_patience,
            min_delta=args.early_stopping_min_delta,
            device=args.device,
            edge_mode=edge_mode,
            positive_weight_scale=args.positive_weight_scale,
            threshold_strategy="validation_f1",
            fixed_threshold=args.classification_threshold,
            seed=model_seed,
        )
        fold_scores, fold_labels = collect_scores(
            inner_model,
            inner_validation,
            args.device,
            edge_mode,
        )
        oof_scores.extend(fold_scores)
        oof_labels.extend(fold_labels)
        inner_best_epochs.append(result["best_epoch"])
        inner_epochs_trained.append(result["epochs_trained"])
        save_checkpoint(
            checkpoint_dir / f"inner_{inner_fold_index}_best.pt",
            inner_model,
            {
                "outer_fold": outer_fold_index,
                "inner_fold": inner_fold_index,
                "best_epoch": result["best_epoch"],
                "validation_f1": result["validation_metrics"].get("f1", 0.0),
            },
        )
        print(
            f"  Outer fold {outer_fold_index + 1}: inner {inner_fold_index + 1}/{inner_fold_count} "
            f"best_epoch={result['best_epoch']} validation_f1="
            f"{result['validation_metrics'].get('f1', 0.0):.4f}",
            flush=True,
        )

    threshold, oof_metrics = select_best_f1_threshold(oof_scores, oof_labels)
    selected_epoch = select_final_epoch(inner_best_epochs)

    final_seed = inner_seed + 100_000
    set_seed(final_seed)
    final_model = create_model(dataset, args)
    final_optimizer = create_optimizer(final_model, args)
    last_train_loss = train_fixed_epochs(
        model=final_model,
        optimizer=final_optimizer,
        examples=outer_train_examples,
        epochs=selected_epoch,
        seed=final_seed,
        device=args.device,
        edge_mode=edge_mode,
        positive_weight_scale=args.positive_weight_scale,
    )
    save_checkpoint(
        args.output_dir / "checkpoints" / f"fold_{outer_fold_index}_final.pt",
        final_model,
        {
            "fold": outer_fold_index,
            "selected_epoch": selected_epoch,
            "classification_threshold": threshold,
            "threshold_strategy": "oof_f1",
            "inner_best_epochs": inner_best_epochs,
        },
    )
    return final_model, threshold, oof_metrics, {
        "last_train_loss": last_train_loss,
        "oof_folds": inner_fold_count,
        "oof_candidates": len(oof_labels),
        "inner_best_epochs": inner_best_epochs,
        "inner_epochs_trained": inner_epochs_trained,
        "selected_epoch": selected_epoch,
        "epochs_trained": selected_epoch,
        "best_epoch": selected_epoch,
        "best_validation_objective": oof_metrics.get("f1", 0.0),
    }


def select_threshold(
    scores: Sequence[float],
    labels: Sequence[int],
    strategy: str,
    fixed_threshold: float,
) -> Tuple[float, Dict[str, float]]:
    if strategy == "validation_f1":
        return select_best_f1_threshold(scores, labels)
    if strategy == "validation_f0_5":
        return select_best_fbeta_threshold(scores, labels, beta=0.5)
    if strategy == "fixed":
        predictions = [1 if score >= fixed_threshold else 0 for score in scores]
        metrics = binary_classification_metrics(labels, predictions)
        metrics["threshold_objective"] = metrics["f1"]
        return fixed_threshold, metrics
    raise ValueError(f"Unsupported validation threshold strategy: {strategy}")


def select_final_epoch(best_epochs: Sequence[int]) -> int:
    if not best_epochs:
        raise ValueError("best_epochs must not be empty")
    return max(1, int(float(np.median(best_epochs)) + 0.5))


def save_checkpoint(path: Path, model: RelationalRootCauseModel, metadata: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "metadata": metadata,
        },
        str(path),
    )


def training_details_for_output(details: Dict) -> Dict:
    allowed_keys = {
        "best_epoch",
        "epochs_trained",
        "best_validation_objective",
        "oof_folds",
        "oof_candidates",
        "inner_best_epochs",
        "inner_epochs_trained",
        "selected_epoch",
    }
    return {key: value for key, value in details.items() if key in allowed_keys}


def format_epoch_summary(details: Dict) -> str:
    if not details:
        return ""
    if "selected_epoch" in details:
        return f" selected_epoch={details['selected_epoch']}"
    if "best_epoch" in details:
        return f" best_epoch={details['best_epoch']}/{details.get('epochs_trained', '?')}"
    return ""


def resolve_data_directories(
    dataset_dir: Optional[Path],
    failure_dir: Optional[Path],
    annotation_dir: Optional[Path],
) -> Tuple[Path, Path]:
    if dataset_dir is not None:
        failure_dir = failure_dir or dataset_dir / "data"
        annotation_dir = annotation_dir or dataset_dir / "answer"
    if failure_dir is None or annotation_dir is None:
        raise ValueError(
            "Provide --dataset-dir, or provide both --failure-dir and --annotation-dir"
        )
    if not failure_dir.is_dir():
        raise ValueError(f"Data directory does not exist: {failure_dir}")
    if not annotation_dir.is_dir():
        raise ValueError(f"Annotation directory does not exist: {annotation_dir}")
    return failure_dir, annotation_dir


def evaluate_ranking(
    model: RelationalRootCauseModel,
    examples: Sequence[TraceTensor],
    device: str,
    top_k: int,
    edge_mode: str,
    match_label_count_top_k: bool,
) -> Tuple[List[Dict], Dict[str, float]]:
    model.eval()
    predictions: List[Dict] = []
    metric_rows: List[Dict[str, float]] = []
    with torch.no_grad():
        for example in examples:
            logits = run_model(model, example, device, edge_mode)
            scores = torch.sigmoid(logits).detach().cpu().numpy()
            order = np.argsort(-scores)
            ranked_steps = [example.candidate_steps[int(index)] for index in order]
            metrics = rank_metrics(ranked_steps, example.positive_steps)
            metric_rows.append(metrics)

            metadata_by_step = {
                record["step"]: record
                for record in example.node_metadata
                if record["node_type"] == "step"
            }
            trace_predictions = []
            prediction_k = len(example.positive_steps) if match_label_count_top_k else top_k
            prediction_k = max(1, prediction_k)
            positive_set = set(example.positive_steps)
            for rank, candidate_index in enumerate(order[:prediction_k], start=1):
                step = example.candidate_steps[int(candidate_index)]
                node = metadata_by_step[step]
                trace_predictions.append(
                    {
                        "step": step,
                        "score": float(scores[int(candidate_index)]),
                        "rank": rank,
                        "agent": node.get("role", ""),
                        "action": node.get("action", ""),
                        "summary": node.get("summary", ""),
                        "content": node.get("content", ""),
                        "is_label": step in positive_set,
                    }
                )
            top1_step = ranked_steps[0] if ranked_steps else None
            top1_distance = min(abs(top1_step - step) for step in positive_set) if top1_step is not None and positive_set else None
            metadata = example.metadata or {}
            predictions.append(
                {
                    "trace_id": example.trace_id,
                    "trajectory_id": example.trace_id,
                    "dataset": metadata.get("dataset"),
                    "generator_model": metadata.get("generator_model"),
                    "error_observed_step": example.error_observed_step,
                    "positive_steps": example.positive_steps,
                    "mistake_step": example.positive_steps[0] if len(example.positive_steps) == 1 else None,
                    "mistake_agent": metadata.get("mistake_agent"),
                    "mistake_reason": metadata.get("mistake_reason"),
                    "top1_step": top1_step,
                    "top1_distance": top1_distance,
                    "acc@0": bool(metrics.get("acc@0", 0.0)),
                    "acc@1": bool(metrics.get("acc@1", 0.0)),
                    "acc@2": bool(metrics.get("acc@2", 0.0)),
                    "acc@3": bool(metrics.get("acc@3", 0.0)),
                    "predictions": trace_predictions,
                }
            )
    return predictions, average_metrics(metric_rows)


def collect_scores(
    model: RelationalRootCauseModel,
    examples: Sequence[TraceTensor],
    device: str,
    edge_mode: str,
) -> Tuple[List[float], List[int]]:
    model.eval()
    scores: List[float] = []
    labels: List[int] = []
    with torch.no_grad():
        for example in examples:
            logits = run_model(model, example, device, edge_mode)
            example_scores = torch.sigmoid(logits).detach().cpu().numpy()
            scores.extend(float(score) for score in example_scores)
            labels.extend(int(label) for label in example.labels)
    return scores, labels


def evaluate_classification(
    model: RelationalRootCauseModel,
    examples: Sequence[TraceTensor],
    device: str,
    edge_mode: str,
    threshold: float,
) -> Tuple[List[Dict], Dict[str, float], List[int], List[int], List[Dict[str, float]]]:
    model.eval()
    predictions: List[Dict] = []
    all_labels: List[int] = []
    all_predicted_labels: List[int] = []
    trace_metrics: List[Dict[str, float]] = []
    with torch.no_grad():
        for example in examples:
            logits = run_model(model, example, device, edge_mode)
            scores = torch.sigmoid(logits).detach().cpu().numpy()
            order = np.argsort(-scores)
            metadata_by_step = {
                record["step"]: record
                for record in example.node_metadata
                if record["node_type"] == "step"
            }

            example_labels = [int(label) for label in example.labels]
            example_predictions = [1 if float(score) >= threshold else 0 for score in scores]
            all_labels.extend(example_labels)
            all_predicted_labels.extend(example_predictions)
            trace_metric = binary_classification_metrics(example_labels, example_predictions)
            trace_metrics.append(
                {
                    key: value
                    for key, value in trace_metric.items()
                    if key in {"accuracy", "precision", "recall", "f1", "f0_5"}
                }
            )

            candidate_predictions = []
            for rank, candidate_index in enumerate(order, start=1):
                candidate_position = int(candidate_index)
                step = example.candidate_steps[candidate_position]
                node = metadata_by_step[step]
                candidate_predictions.append(
                    {
                        "step": step,
                        "score": float(scores[candidate_position]),
                        "predicted_label": example_predictions[candidate_position],
                        "true_label": example_labels[candidate_position],
                        "rank": rank,
                        "agent": node.get("role", ""),
                        "action": node.get("action", ""),
                        "summary": node.get("summary", ""),
                    }
                )
            predictions.append(
                {
                    "trace_id": example.trace_id,
                    "error_observed_step": example.error_observed_step,
                    "positive_steps": example.positive_steps,
                    "classification_threshold": threshold,
                    "predictions": candidate_predictions,
                }
            )

    metrics = binary_classification_metrics(all_labels, all_predicted_labels)
    macro_metrics = average_metrics(trace_metrics)
    metrics.update({f"macro_{key}": value for key, value in macro_metrics.items()})
    return predictions, metrics, all_labels, all_predicted_labels, trace_metrics


def run_model(model: RelationalRootCauseModel, example: TraceTensor, device: str, edge_mode: str) -> torch.Tensor:
    edges, edge_features, edge_times = select_edges(example, edge_mode)
    return model(
        node_features=torch.tensor(example.node_features, dtype=torch.float32, device=device),
        edges=torch.tensor(edges, dtype=torch.long, device=device),
        edge_features=torch.tensor(edge_features, dtype=torch.float32, device=device),
        edge_times=torch.tensor(edge_times, dtype=torch.float32, device=device),
        candidate_indices=torch.tensor(example.candidate_indices, dtype=torch.long, device=device),
        error_index=example.error_index,
        pair_features=torch.tensor(example.candidate_pair_features, dtype=torch.float32, device=device),
    )


def select_edges(example: TraceTensor, edge_mode: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if edge_mode == "full":
        return example.edges, example.edge_features, example.edge_times
    if edge_mode == "none" or example.edges.shape[0] == 0:
        return (
            np.zeros((0, 2), dtype=np.int64),
            np.zeros((0, example.edge_features.shape[1]), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
        )
    if edge_mode == "time":
        mask = example.edge_features[:, 0] == 1.0
        return example.edges[mask], example.edge_features[mask], example.edge_times[mask]
    raise ValueError(f"Unsupported edge mode: {edge_mode}")


def make_folds(examples: Sequence[TraceTensor], n_folds: int, seed: int) -> List[Tuple[List[TraceTensor], List[TraceTensor]]]:
    if n_folds < 2:
        raise ValueError("--folds must be at least 2")
    n_folds = min(n_folds, len(examples))
    shuffled = list(examples)
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    buckets = [shuffled[index::n_folds] for index in range(n_folds)]
    folds = []
    for index in range(n_folds):
        test = buckets[index]
        train = [example for bucket_index, bucket in enumerate(buckets) if bucket_index != index for example in bucket]
        folds.append((train, test))
    return folds


def split_train_validation(
    examples: Sequence[TraceTensor],
    validation_ratio: float,
    seed: int,
) -> Tuple[List[TraceTensor], List[TraceTensor]]:
    if len(examples) < 2:
        return list(examples), []
    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)
    validation_size = max(1, int(round(len(shuffled) * validation_ratio)))
    validation_size = min(validation_size, len(shuffled) - 1)
    validation = shuffled[:validation_size]
    train = shuffled[validation_size:]
    return train, validation


def write_outputs(output_dir: Path, predictions: Sequence[Dict], metrics: Dict, fold_metrics: Sequence[Dict]) -> None:
    predictions_path = output_dir / "predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as handle:
        for item in sorted(predictions, key=lambda row: int(row["trace_id"]) if str(row["trace_id"]).isdigit() else str(row["trace_id"])):
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    with (output_dir / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
    with (output_dir / "fold_metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(list(fold_metrics), handle, ensure_ascii=False, indent=2)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


if __name__ == "__main__":
    main()
