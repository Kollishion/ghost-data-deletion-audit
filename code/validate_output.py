"""Validate the generated submission CSV against the output contract."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

try:
    from . import loaders
    from .serializer import HEADER, STEP_FIELDS
except ImportError:
    import loaders
    from serializer import HEADER, STEP_FIELDS


ALLOWED = {
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
}
PHASE_RANK = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != HEADER:
            return [f"header mismatch: {reader.fieldnames!r}"]
        rows = list(reader)
    expected_ids = sorted(row["case_id"] for row in loaders.read_requests())
    actual_ids = [row["case_id"] for row in rows]
    if len(rows) != len(expected_ids):
        errors.append(f"row count {len(rows)} != {len(expected_ids)}")
    if actual_ids != sorted(actual_ids):
        errors.append("rows are not sorted by case_id")
    if len(actual_ids) != len(set(actual_ids)):
        errors.append("duplicate case_id values")
    if actual_ids != expected_ids:
        missing = sorted(set(expected_ids) - set(actual_ids))
        extra = sorted(set(actual_ids) - set(expected_ids))
        errors.append(f"case_id set mismatch missing={missing[:5]} extra={extra[:5]}")

    for row in rows:
        case_id = row["case_id"]
        status = row["deletion_status"]
        if status not in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}:
            errors.append(f"{case_id}: invalid status {status!r}")
        try:
            steps = json.loads(row["steps_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            errors.append(f"{case_id}: invalid steps_json ({type(exc).__name__})")
            continue
        if not isinstance(steps, list):
            errors.append(f"{case_id}: steps_json is not an array")
            continue
        if status == "NOT_APPLICABLE" and steps:
            errors.append(f"{case_id}: NOT_APPLICABLE must have []")
        phase_ranks = []
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict) or set(step) != set(STEP_FIELDS):
                errors.append(f"{case_id}: step {index} has invalid fields")
                continue
            if step["step_no"] != index:
                errors.append(f"{case_id}: step_no is not consecutive at {index}")
            pair = (step["phase"], step["operation"], step["state"])
            if pair not in ALLOWED:
                errors.append(f"{case_id}: disallowed phase/operation/state {pair!r}")
            phase_ranks.append(PHASE_RANK.get(step["phase"], -1))
            if status == "COMPLETE" and step["phase"] != "VERIFICATION":
                errors.append(f"{case_id}: COMPLETE contains a non-verification step")
            if status == "INCOMPLETE" and step["phase"] in {"REMEDIATION", "VERIFICATION"} \
                    and step["evidence_id"]:
                errors.append(f"{case_id}: future step contains evidence_id")
        if phase_ranks != sorted(phase_ranks):
            errors.append(f"{case_id}: phases are out of order")
    return errors


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else loaders.REPO_ROOT / "output.csv"
    errors = validate(path)
    if errors:
        print(f"validation=FAIL errors={len(errors)}")
        for error in errors[:30]:
            print(f"  {error}")
        raise SystemExit(1)
    print(f"validation=PASS rows={sum(1 for _ in csv.DictReader(path.open(encoding='utf-8-sig', newline='')))}")


if __name__ == "__main__":
    main()
