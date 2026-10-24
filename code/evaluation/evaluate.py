"""Score a prediction CSV against the 32 public sample outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

import loaders
from main import run_requests
from serializer import HEADER, write_output

FIELDS = ("step_no", "phase", "system_id", "resource_id",
          "operation", "state", "evidence_id")
ALIGNMENT_FIELDS = ("phase", "operation", "system_id", "resource_id")


def _read_predictions(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _lcs_pairs(expected: list[dict[str, Any]], predicted: list[dict[str, Any]]):
    rows, cols = len(expected), len(predicted)
    dp = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(cols - 1, -1, -1):
            if tuple(expected[i][k] for k in ALIGNMENT_FIELDS) == tuple(
                    predicted[j][k] for k in ALIGNMENT_FIELDS):
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    pairs = []
    i = j = 0
    while i < rows and j < cols:
        if tuple(expected[i][k] for k in ALIGNMENT_FIELDS) == tuple(
                predicted[j][k] for k in ALIGNMENT_FIELDS):
            pairs.append((i, j))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def evaluate(prediction_path: Path) -> dict[str, Any]:
    predicted_rows = _read_predictions(prediction_path)
    expected_rows = loaders.read_csv("sample_output.csv")
    case_pred = {row["case_id"]: row for row in predicted_rows}
    case_exp = {row["case_id"]: row for row in expected_rows}
    status_correct = sum(case_pred.get(key, {}).get("deletion_status") ==
                         expected["deletion_status"] for key, expected in case_exp.items())
    total = len(case_exp)
    pred_steps: Counter[tuple[Any, ...]] = Counter()
    exp_steps: Counter[tuple[Any, ...]] = Counter()
    field_correct = aligned_count = 0
    field_total = 0
    per_field_correct: Counter[str] = Counter()
    sequence_correct = 0
    diagnostics: list[str] = []
    invalid = 0
    failure_causes: Counter[str] = Counter()

    for case_id, exp_row in case_exp.items():
        pred_row = case_pred.get(case_id)
        try:
            exp = json.loads(exp_row["steps_json"])
            pred = json.loads(pred_row["steps_json"]) if pred_row else []
            if not isinstance(exp, list) or not isinstance(pred, list):
                raise ValueError("steps_json must be an array")
        except (ValueError, TypeError, KeyError) as exc:
            invalid += 1
            diagnostics.append(f"{case_id}: invalid or missing steps_json ({type(exc).__name__})")
            exp, pred = [], []
        for step in exp:
            exp_steps[(case_id, *(step.get(field) for field in FIELDS))] += 1
        for step in pred:
            pred_steps[(case_id, *(step.get(field) for field in FIELDS))] += 1
        if pred == exp:
            sequence_correct += 1
        pairs = _lcs_pairs(exp, pred)
        aligned_count += len(pairs)
        field_total += len(pairs) * len(FIELDS)
        for i, j in pairs:
            for field in FIELDS:
                if exp[i].get(field) == pred[j].get(field):
                    field_correct += 1
                    per_field_correct[field] += 1
        pred_by_resource: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
        for step in pred:
            pred_by_resource.setdefault((step.get("system_id"), step.get("resource_id")), []).append(step)
        for expected_step in exp:
            candidates = pred_by_resource.get(
                (expected_step.get("system_id"), expected_step.get("resource_id")), [])
            if not candidates:
                failure_causes["discovery or system/resource attribution misses"] += 1
                continue
            if any(all(expected_step.get(field) == candidate.get(field) for field in FIELDS)
                   for candidate in candidates):
                continue
            same_key = [candidate for candidate in candidates
                        if all(expected_step.get(field) == candidate.get(field)
                               for field in ALIGNMENT_FIELDS)]
            if same_key and any(expected_step.get("state") != candidate.get("state")
                                for candidate in same_key):
                failure_causes["policy state mismatch"] += 1
            elif same_key and any(expected_step.get("evidence_id") != candidate.get("evidence_id")
                                  for candidate in same_key):
                failure_causes["evidence citation mismatch"] += 1
            elif same_key and any(expected_step.get("step_no") != candidate.get("step_no")
                                  for candidate in same_key):
                failure_causes["step numbering or order mismatch"] += 1
            elif same_key:
                failure_causes["other field mismatch"] += 1
            else:
                failure_causes["policy operation or phase mismatch"] += 1
        if pred != exp or (pred_row and pred_row.get("deletion_status") != exp_row["deletion_status"]):
            mismatch = None
            for i in range(max(len(exp), len(pred))):
                if i >= len(exp):
                    mismatch = f"extra predicted step {pred[i]}"
                    break
                if i >= len(pred):
                    mismatch = f"missing expected step {exp[i]}"
                    break
                diff = [field for field in FIELDS if exp[i].get(field) != pred[i].get(field)]
                if diff:
                    mismatch = f"step {i + 1} fields {diff}"
                    break
            if mismatch is None and pred_row is None:
                mismatch = "missing prediction row"
            diagnostics.append(
                f"{case_id}: status {pred_row.get('deletion_status') if pred_row else '<missing>'}"
                f" vs {exp_row['deletion_status']}; first mismatch: {mismatch or 'none'}"
            )

    tp = sum((pred_steps & exp_steps).values())
    predicted_count = sum(pred_steps.values())
    expected_count = sum(exp_steps.values())
    failure_causes["extra or unsupported predicted steps"] = sum((pred_steps - exp_steps).values())
    precision = tp / predicted_count if predicted_count else 1.0
    recall = tp / expected_count if expected_count else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    field_accuracy = field_correct / field_total if field_total else 1.0
    sequence_accuracy = sequence_correct / total if total else 1.0
    metrics = {
        "status_accuracy": status_correct / total if total else 1.0,
        "step_precision": precision, "step_recall": recall, "step_f1": f1,
        "field_accuracy": field_accuracy, "field_correct": field_correct,
        "per_field_correct": dict(per_field_correct),
        "field_total": field_total, "aligned_steps": aligned_count,
        "sequence_accuracy": sequence_accuracy, "sequence_correct": sequence_correct,
        "sample_cases": total, "invalid_cases": invalid, "diagnostics": diagnostics,
        "failure_causes": dict(failure_causes),
    }
    print(f"sample_status_accuracy={status_correct}/{total} ({metrics['status_accuracy']:.3%})")
    print(f"sample_step_level_precision={precision:.3%} recall={recall:.3%} f1={f1:.3%} "
          f"tp={tp} predicted={predicted_count} expected={expected_count}")
    print(f"sample_field_level_accuracy={field_correct}/{field_total} ({field_accuracy:.3%}); "
          f"aligned_steps={aligned_count}/{expected_count}")
    for field in FIELDS:
        print(f"  field_{field}={per_field_correct[field]}/{aligned_count}")
    print(f"sample_sequence_accuracy={sequence_correct}/{total} ({sequence_accuracy:.3%})")
    ranked_causes = failure_causes.most_common(5)
    print("sample_top_failure_causes=" + json.dumps(
        [{"cause": cause, "expected_steps_affected": count}
         for cause, count in ranked_causes], ensure_ascii=True))
    print(f"sample_invalid_cases={invalid} sample_first_mismatches={len(diagnostics)}")
    for item in diagnostics:
        print(f"  {item}")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path)
    args = parser.parse_args()
    if args.predictions:
        evaluate(args.predictions)
        return
    sample_rows = run_requests(loaders.read_requests(samples=True))
    with tempfile.TemporaryDirectory(prefix="ghost-data-sample-") as directory:
        path = Path(directory) / "sample_predictions.csv"
        write_output(sample_rows, path)
        evaluate(path)


if __name__ == "__main__":
    main()
