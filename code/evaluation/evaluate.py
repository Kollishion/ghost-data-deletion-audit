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
STEP_FIELDS = tuple(field for field in FIELDS if field != "step_no")
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
    missing_by_case: dict[str, int] = {}
    extra_by_case: dict[str, int] = {}
    exact_steps_without_no = Counter()
    expected_without_no = Counter()
    renumbered_sequence_correct = 0
    extra_examples: dict[str, list[dict[str, Any]]] = {}
    extra_counts: Counter[str] = Counter()
    sample_case_rows = {row["case_id"]: row for row in loaders.read_requests(samples=True)}
    observed_by_case: dict[str, list[Any]] = {}
    link_totals: Counter[str] = Counter()
    link_expected: Counter[str] = Counter()
    extra_resource_details: dict[tuple[str, str, str, str], dict[str, Any]] = {}

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
            expected_without_no[(case_id, *(step.get(field) for field in STEP_FIELDS))] += 1
        for step in pred:
            pred_steps[(case_id, *(step.get(field) for field in FIELDS))] += 1
            exact_steps_without_no[(case_id, *(step.get(field) for field in STEP_FIELDS))] += 1
        if pred == exp:
            sequence_correct += 1
        if [tuple(s.get(k) for k in STEP_FIELDS) for s in pred] == [
                tuple(s.get(k) for k in STEP_FIELDS) for s in exp]:
            renumbered_sequence_correct += 1
        exp_n = Counter(tuple(step.get(k) for k in STEP_FIELDS) for step in exp)
        pred_n = Counter(tuple(step.get(k) for k in STEP_FIELDS) for step in pred)
        missing_steps = list((exp_n - pred_n).elements())
        extra_steps = list((pred_n - exp_n).elements())
        missing_by_case[case_id] = len(missing_steps)
        extra_by_case[case_id] = len(extra_steps)
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
        try:
            from discovery import discover_case
            from policy import evaluate_observation
            case = sample_case_rows[case_id]
            observations = discover_case(case)
        except Exception:
            observations = []
            case = sample_case_rows.get(case_id, {})
        observed_by_case[case_id] = observations
        obs_by_key = {(o.system_id, o.resource_id): o for o in observations}
        expected_resources = {(step.get("system_id"), step.get("resource_id")) for step in exp}
        for obs in observations:
            key = obs.link_type or obs.link_basis or "unlinked"
            link_totals[key] += 1
            if (obs.system_id, obs.resource_id) in expected_resources:
                link_expected[key] += 1
        if extra_steps:
            for extra in extra_steps:
                phase, system, resource, operation, state, evidence = extra
                obs = obs_by_key.get((system, resource))
                category = "sample omits grounded policy violation"
                if obs:
                    from datetime import datetime, timezone
                    try:
                        observed_time = datetime.fromisoformat(obs.observed_at.replace("Z", "+00:00"))
                        requested_time = datetime.fromisoformat(case["requested_at"].replace("Z", "+00:00"))
                        if observed_time.tzinfo is None:
                            observed_time = observed_time.replace(tzinfo=timezone.utc)
                        if requested_time.tzinfo is None:
                            requested_time = requested_time.replace(tzinfo=timezone.utc)
                        is_pre_request = observed_time < requested_time
                    except (ValueError, KeyError):
                        is_pre_request = False
                    if is_pre_request:
                        category = "pre-request observation"
                    elif not evaluate_observation(obs).violation:
                        category = ("activity-only unresolved resource omitted by sample"
                                    if obs.source_type == "activity_claim"
                                    else "already-compliant resource omitted by sample")
                if any(o.resource_id == resource and o.system_id != system
                       for o in observed_by_case.get(case_id, observations)):
                    category = "duplicate resource under different system_ids"
                extra_counts[category] += 1
                if obs:
                    extra_resource_details[(case_id, phase, system, resource + ":" + operation)] = {
                        "case_id": case_id, "phase": phase, "resource": resource, "operation": operation,
                        "link_type": obs.link_type or obs.link_basis,
                        "link_field": obs.link_field, "link_value": obs.link_value,
                        "matched_identifier": obs.matched_identifier,
                        "observation": {"timestamp": obs.observed_at, "state": obs.state_hint,
                                        "evidence_id": obs.evidence_id,
                                        "source_type": obs.source_type},
                    }
                if len(extra_examples.setdefault(category, [])) < 3:
                    extra_examples[category].append({
                        "case_id": case_id, "phase": phase, "operation": operation,
                        "system_id": system, "resource_id": resource,
                        "observation": ({"timestamp": obs.observed_at, "state": obs.state_hint,
                                         "evidence_id": obs.evidence_id,
                                         "link_basis": obs.link_basis,
                                         "source_type": obs.source_type} if obs else None),
                    })
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
    tp_no = sum((exact_steps_without_no & expected_without_no).values())
    pred_no = sum(exact_steps_without_no.values())
    exp_no = sum(expected_without_no.values())
    precision_no = tp_no / pred_no if pred_no else 1.0
    recall_no = tp_no / exp_no if exp_no else 1.0
    f1_no = (2 * precision_no * recall_no / (precision_no + recall_no)
             if precision_no + recall_no else 0.0)
    field_accuracy = field_correct / field_total if field_total else 1.0
    sequence_accuracy = sequence_correct / total if total else 1.0
    metrics = {
        "status_accuracy": status_correct / total if total else 1.0,
        "step_precision": precision, "step_recall": recall, "step_f1": f1,
        "step_precision_without_step_no": precision_no,
        "step_recall_without_step_no": recall_no, "step_f1_without_step_no": f1_no,
        "field_accuracy": field_accuracy, "field_correct": field_correct,
        "per_field_correct": dict(per_field_correct),
        "field_total": field_total, "aligned_steps": aligned_count,
        "sequence_accuracy": sequence_accuracy, "sequence_correct": sequence_correct,
        "sample_cases": total, "invalid_cases": invalid, "diagnostics": diagnostics,
        "failure_causes": dict(failure_causes),
        "missing_by_case": missing_by_case, "extra_by_case": extra_by_case,
        "renumbered_sequence_accuracy": renumbered_sequence_correct / total if total else 1.0,
        "extra_causes": dict(extra_counts), "extra_examples": extra_examples,
    }
    print(f"sample_status_accuracy={status_correct}/{total} ({metrics['status_accuracy']:.3%})")
    print(f"sample_step_level_precision={precision:.3%} recall={recall:.3%} f1={f1:.3%} "
          f"tp={tp} predicted={predicted_count} expected={expected_count}")
    print(f"sample_step_level_without_step_no_precision={precision_no:.3%} "
          f"recall={recall_no:.3%} f1={f1_no:.3%} tp={tp_no} "
          f"predicted={pred_no} expected={exp_no}")
    print("sample_per_case_missing_extra=" + json.dumps(
        {case: {"missing": missing_by_case[case], "extra": extra_by_case[case]}
         for case in case_exp if missing_by_case.get(case) or extra_by_case.get(case)},
        ensure_ascii=True))
    print(f"sample_renumbered_sequence_accuracy={renumbered_sequence_correct}/{total} "
          f"({(renumbered_sequence_correct / total if total else 1.0):.3%})")
    print("sample_extra_causes=" + json.dumps(dict(extra_counts), ensure_ascii=True))
    print("sample_extra_resources=" + json.dumps(
        list(extra_resource_details.values()), ensure_ascii=True))
    print("sample_link_type_precision=" + json.dumps([
        {"link_type": key, "expected_resources": link_expected[key],
         "observed_resources": link_totals[key],
         "precision": link_expected[key] / link_totals[key] if link_totals[key] else 1.0}
        for key in sorted(link_totals)], ensure_ascii=True))
    activity_times = {row.get("activity_id"): row.get("event_time", "")
                      for row in loaders.read_activity()}
    old_activity_expected = []
    sample_requests_by_id = sample_case_rows
    for cid, expected_row in case_exp.items():
        request_time = sample_requests_by_id[cid].get("requested_at", "")
        for step in json.loads(expected_row["steps_json"]):
            evidence = step.get("evidence_id", "")
            event_time = activity_times.get(evidence, "")
            if evidence.startswith("activity_") and event_time and request_time and event_time < request_time:
                old_activity_expected.append((cid, evidence, event_time))
    print(f"sample_expected_steps_from_pre_request_activity={len(old_activity_expected)}")
    from datetime import datetime, timezone
    manifest = loaders.read_evidence_manifest()
    visual_paths = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    visual_evidence = []
    for item in manifest:
        path = loaders.evidence_path(item["file_path"])
        if path.suffix.casefold() in visual_paths:
            captured = item.get("captured_at", "")
            try:
                parsed = datetime.fromisoformat(captured.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                parsed = None
            if parsed:
                visual_evidence.append((item, parsed))
    visual_cases = 0
    for request in loaders.read_requests():
        audit = datetime.fromisoformat(request["audit_at"].replace("Z", "+00:00"))
        if audit.tzinfo is None:
            audit = audit.replace(tzinfo=timezone.utc)
        if any(captured <= audit for _, captured in visual_evidence):
            visual_cases += 1
    print(f"full_evaluation_cases_with_eligible_pdf_or_image={visual_cases}/{len(loaders.read_requests())}")
    for cause, count in extra_counts.most_common():
        print(f"  extra_cause_examples={cause} count={count} " +
              json.dumps(extra_examples.get(cause, []), ensure_ascii=True))
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
