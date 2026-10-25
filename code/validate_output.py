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
OPERATION_RANK = {
    "REPORT_REMAINING_RECORD": 0, "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2, "REPORT_RESTORE_RISK": 3,
    "DISABLE_DATA_FLOW": 0, "BLOCK_RESTORE": 1, "DELETE_RECORD": 2,
    "REDACT_RECORD": 3, "ANONYMIZE_RECORD": 4,
    "VERIFY_RECORD_ABSENT": 0, "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2, "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4, "VERIFY_RESTORE_BLOCKED": 5,
}


def _evidence_times() -> dict[str, str]:
    times = {row["file_id"]: row["captured_at"] for row in loaders.read_evidence_manifest()}
    times.update({row["activity_id"]: row["event_time"] for row in loaders.read_activity()})
    times.update({row["audit_id"]: row["event_time"] for row in loaders.read_identity_audit()})
    return times


def validate_report(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != HEADER:
            return [f"header mismatch: {reader.fieldnames!r}"], warnings
        rows = list(reader)
    requests = {row["case_id"]: row for row in loaders.read_requests()}
    expected_ids = sorted(requests)
    if len(expected_ids) != 518:
        errors.append(f"deletion_requests.csv has {len(expected_ids)} cases, expected 518")
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

    evidence_times = _evidence_times()

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
        if status == "COMPLETE" and any(
            isinstance(step, dict) and step.get("phase") != "VERIFICATION" for step in steps
        ):
            errors.append(f"{case_id}: COMPLETE must contain only verification steps")
        if status == "INCOMPLETE" and not any(
            isinstance(step, dict) and step.get("phase") == "FINDING" for step in steps
        ):
            warnings.append(f"{case_id}: INCOMPLETE has no FINDING step")
        phase_ranks = []
        sort_keys = []
        duplicate_keys = set()
        request = requests.get(case_id)
        audit_at = request.get("audit_at", "") if request else ""
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict) or set(step) != set(STEP_FIELDS):
                errors.append(f"{case_id}: step {index} has invalid fields")
                continue
            if (not isinstance(step["step_no"], int) or isinstance(step["step_no"], bool)
                    or any(not isinstance(step[field], str) for field in STEP_FIELDS[1:])):
                errors.append(f"{case_id}: step {index} has invalid field types")
                continue
            if step["step_no"] != index:
                errors.append(f"{case_id}: step_no is not consecutive at {index}")
            pair = (step["phase"], step["operation"], step["state"])
            if pair not in ALLOWED:
                errors.append(f"{case_id}: disallowed phase/operation/state {pair!r}")
            phase_ranks.append(PHASE_RANK.get(step["phase"], -1))
            sort_keys.append((PHASE_RANK.get(step["phase"], -1),
                              OPERATION_RANK.get(step["operation"], -1),
                              step["system_id"], step["resource_id"]))
            duplicate_key = (step["phase"], step["operation"], step["system_id"], step["resource_id"])
            if duplicate_key in duplicate_keys:
                errors.append(f"{case_id}: duplicate step key {duplicate_key!r}")
            duplicate_keys.add(duplicate_key)
            if status == "COMPLETE" and step["phase"] != "VERIFICATION":
                errors.append(f"{case_id}: COMPLETE contains a non-verification step")
            if status == "COMPLETE" and not step["evidence_id"]:
                errors.append(f"{case_id}: COMPLETE verification has empty evidence_id")
            if step["phase"] == "FINDING" and not step["evidence_id"]:
                errors.append(f"{case_id}: finding has empty evidence_id")
            if status == "INCOMPLETE" and step["phase"] in {"REMEDIATION", "VERIFICATION"} \
                    and step["evidence_id"]:
                errors.append(f"{case_id}: future step contains evidence_id")
            evidence_id = step["evidence_id"]
            if evidence_id:
                if evidence_id not in evidence_times:
                    errors.append(f"{case_id}: unknown evidence_id {evidence_id!r}")
                elif evidence_times[evidence_id] > audit_at:
                    errors.append(f"{case_id}: evidence {evidence_id} is after audit_at")
        if phase_ranks != sorted(phase_ranks):
            errors.append(f"{case_id}: phases are out of order")
        if sort_keys != sorted(sort_keys):
            errors.append(f"{case_id}: steps are not sorted by phase, operation rank, system, resource")
    return errors, warnings


def validate(path: Path) -> list[str]:
    """Return hard validation errors; warning-only results remain successful."""
    errors, _ = validate_report(path)
    return errors


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else loaders.REPO_ROOT / "output.csv"
    errors, warnings = validate_report(path)
    if warnings:
        case_ids = [warning.split(":", 1)[0] for warning in warnings]
        print(f"validation_warning=incomplete_without_finding count={len(warnings)} case_ids={case_ids}")
    if errors:
        print(f"validation=FAIL errors={len(errors)}")
        for error in errors[:30]:
            print(f"  {error}")
        raise SystemExit(1)
    print(f"validation=PASS rows={sum(1 for _ in csv.DictReader(path.open(encoding='utf-8-sig', newline='')))} warnings={len(warnings)}")


if __name__ == "__main__":
    main()
