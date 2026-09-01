#!/usr/bin/env python3
"""Collect per-configuration summaries into JSON, CSV, and a console table."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


FIELDS = (
    "model",
    "planner",
    "knowledge",
    "flat_mode",
    "total",
    "accuracy_count",
    "accuracy",
    "algorithm_accuracy_count",
    "algorithm_accuracy",
    "token",
    "errors",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()

    paths = sorted(args.run_root.glob("*/*/summary.json"))
    rows: List[Dict[str, Any]] = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    (args.run_root / "all_summaries.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.run_root / "all_summaries.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print("model\tplanner\tknowledge\taccuracy\talgorithm_accuracy\ttoken\terrors")
    for row in rows:
        knowledge = row["knowledge"]
        if row.get("flat_mode"):
            knowledge += f"-{row['flat_mode']}"
        accuracy = row.get("accuracy_count") or "-"
        print(
            f"{row['model']}\t{row['planner']}\t{knowledge}\t{accuracy}\t"
            f"{row['algorithm_accuracy_count']}\t{row['token']}\t{row['errors']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
