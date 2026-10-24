"""Deterministic findings, remediation, and verification plan generation."""

from __future__ import annotations

from typing import Any

try:
    from .policy import evaluate_all
except ImportError:
    from policy import evaluate_all


PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
OPERATION_RANK = {
    "REPORT_REMAINING_RECORD": 0, "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2, "REPORT_RESTORE_RISK": 3,
    "DISABLE_DATA_FLOW": 0, "BLOCK_RESTORE": 1, "DELETE_RECORD": 2,
    "REDACT_RECORD": 3, "ANONYMIZE_RECORD": 4,
    "VERIFY_RECORD_ABSENT": 0, "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2, "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4, "VERIFY_RESTORE_BLOCKED": 5,
}


def _step(phase: str, system: str, resource: str, operation: str,
          state: str, evidence: str) -> dict[str, Any]:
    return {
        "step_no": 0,
        "phase": phase,
        "system_id": system,
        "resource_id": resource,
        "operation": operation,
        "state": state,
        "evidence_id": evidence,
    }


def build_plan(observations: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    decisions = evaluate_all(observations)
    # No evidence cannot establish that the required treatment is complete.
    incomplete = not decisions or any(item.violation for item in decisions)
    status = "INCOMPLETE" if incomplete else "COMPLETE"
    steps: list[dict[str, Any]] = []

    if incomplete:
        for item in decisions:
            obs = item.observation
            if item.finding_operation:
                steps.append(_step("FINDING", obs.system_id, obs.resource_id,
                                   item.finding_operation, item.finding_state or "",
                                   obs.evidence_id))
        for item in decisions:
            obs = item.observation
            if item.remediation_operation:
                steps.append(_step("REMEDIATION", obs.system_id, obs.resource_id,
                                   item.remediation_operation, item.remediation_state or "", ""))
        for item in decisions:
            obs = item.observation
            steps.append(_step("VERIFICATION", obs.system_id, obs.resource_id,
                               item.verification_operation, item.verification_state, ""))
    else:
        for item in decisions:
            obs = item.observation
            steps.append(_step("VERIFICATION", obs.system_id, obs.resource_id,
                               item.verification_operation, item.verification_state,
                               obs.evidence_id))

    steps.sort(key=lambda step: (
        PHASE_ORDER[step["phase"]],
        OPERATION_RANK[step["operation"]],
        step["system_id"],
        step["resource_id"],
    ))
    for number, step in enumerate(steps, 1):
        step["step_no"] = number
    return status, steps
