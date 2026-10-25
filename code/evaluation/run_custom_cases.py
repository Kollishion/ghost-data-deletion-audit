"""Run the independent fictional cases in evaluation/custom_cases."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "code"
FIXTURE_ROOT = ROOT / "evaluation" / "custom_cases"
sys.path.insert(0, str(CODE))

import discovery  # noqa: E402
import loaders  # noqa: E402
from main import run_requests  # noqa: E402
from request_classifier import NOT_APPLICABLE, classify_request  # noqa: E402


def _step(phase: str, system: str, resource: str, operation: str,
          state: str, evidence: str = "") -> dict[str, Any]:
    return {
        "step_no": 0,
        "phase": phase,
        "system_id": system,
        "resource_id": resource,
        "operation": operation,
        "state": state,
        "evidence_id": evidence,
    }


def _number(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for number, step in enumerate(steps, 1):
        step["step_no"] = number
    return steps


EXPECTED: dict[str, tuple[str, list[dict[str, Any]]]] = {
    "custom_A": ("INCOMPLETE", _number([
        _step("FINDING", "account_service", "account_7101",
              "REPORT_REMAINING_RECORD", "PRESENT", "custom_evidence_A"),
        _step("REMEDIATION", "account_service", "account_7101", "DELETE_RECORD", "ABSENT"),
        _step("VERIFICATION", "account_service", "account_7101", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ])),
    "custom_B": ("INCOMPLETE", _number([
        _step("FINDING", "search_service", "search_7155",
              "REPORT_REMAINING_RECORD", "PRESENT", "custom_evidence_B"),
        _step("FINDING", "integration_service", "data_flow_8820",
              "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", "custom_evidence_B"),
        _step("REMEDIATION", "integration_service", "data_flow_8820", "DISABLE_DATA_FLOW", "DISABLED"),
        _step("REMEDIATION", "search_service", "search_7155", "DELETE_RECORD", "ABSENT"),
        _step("VERIFICATION", "search_service", "search_7155", "VERIFY_RECORD_ABSENT", "ABSENT"),
        _step("VERIFICATION", "integration_service", "data_flow_8820",
              "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ])),
    "custom_C": ("INCOMPLETE", _number([
        _step("FINDING", "support_platform", "support_5530",
              "REPORT_EXPOSED_PII", "PRESENT", "custom_evidence_C"),
        _step("REMEDIATION", "support_platform", "support_5530", "REDACT_RECORD", "REDACTED"),
        _step("VERIFICATION", "security_service", "audit_record_6002", "VERIFY_RECORD_PRESENT", "PRESENT"),
        _step("VERIFICATION", "support_platform", "support_5530", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ])),
    # No subject-linked evidence is expected. The conservative unknown-state
    # status is INCOMPLETE; the key assertion is that the decoy never appears.
    "custom_D": ("INCOMPLETE", []),
    "custom_E": ("INCOMPLETE", _number([
        _step("FINDING", "backup_service", "backup_9034",
              "REPORT_RESTORE_RISK", "ACTIVE", "custom_evidence_E"),
        _step("REMEDIATION", "backup_service", "backup_9034", "BLOCK_RESTORE", "BLOCKED"),
        _step("VERIFICATION", "backup_service", "backup_9034", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
    ])),
    "custom_F_i": ("INCOMPLETE", []),
    "custom_F_ii": ("INCOMPLETE", _number([
        _step("FINDING", "account_service", "account_7103",
              "REPORT_REMAINING_RECORD", "PRESENT", "custom_evidence_F_ii"),
        _step("REMEDIATION", "account_service", "account_7103", "DELETE_RECORD", "ABSENT"),
        _step("VERIFICATION", "account_service", "account_7103", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ])),
    "custom_G": ("NOT_APPLICABLE", []),
}


def main() -> int:
    old_dataset_dir = loaders.DATASET_DIR
    try:
        loaders.DATASET_DIR = FIXTURE_ROOT
        discovery._manifest.cache_clear()
        discovery._parse_evidence_objects.cache_clear()
        with (FIXTURE_ROOT / "deletion_requests.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as stream:
            requests = list(csv.DictReader(stream))
        rows = run_requests(requests, graph_iterations=1)
        actual_by_id = {
            row["case_id"]: (row["deletion_status"], json.loads(row["steps_json"]))
            for row in rows
        }
        all_pass = True
        for case_id, (expected_status, expected_steps) in EXPECTED.items():
            actual_status, actual_steps = actual_by_id.get(case_id, ("<missing>", []))
            passed = actual_status == expected_status and actual_steps == expected_steps
            if case_id == "custom_D":
                passed = passed and all(
                    step.get("resource_id") != "search_7156" for step in actual_steps
                )
            all_pass &= passed
            print(
                f"{case_id} | expected_status={expected_status} actual_status={actual_status} "
                f"| expected_steps={json.dumps(expected_steps, separators=(',', ':'))} "
                f"actual_steps={json.dumps(actual_steps, separators=(',', ':'))} "
                f"| {'PASS' if passed else 'FAIL'}"
            )
            if not passed:
                if case_id == "custom_D" and any(
                    step.get("resource_id") == "search_7156" for step in actual_steps
                ):
                    print("  failure: the index entry for user_9905 was attributed to user_9904")
                else:
                    print("  failure: actual status or ordered steps differ from the independent expectation")

        marketing = next(row for row in requests if row["case_id"] == "custom_G")
        if classify_request(marketing["request_text"]) != NOT_APPLICABLE:
            print("custom_G failure: marketing-only request was not classified NOT_APPLICABLE")
            all_pass = False
        return 0 if all_pass else 1
    finally:
        loaders.DATASET_DIR = old_dataset_dir
        discovery._manifest.cache_clear()
        discovery._parse_evidence_objects.cache_clear()


if __name__ == "__main__":
    raise SystemExit(main())
