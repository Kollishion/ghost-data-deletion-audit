"""Policy evaluation for discovered, cutoff-bounded observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyDecision:
    observation: Any
    finding_operation: str | None
    finding_state: str | None
    remediation_operation: str | None
    remediation_state: str | None
    verification_operation: str
    verification_state: str
    violation: bool


DELETE_CATEGORIES = {
    "USER_PROFILE", "SECONDARY_IDENTIFIER", "SEARCH_INDEX_ENTRY", "CACHE_ENTRY",
    "SUPPORT_ATTACHMENT", "USER_EXPORT", "MARKETING_PROFILE",
}


def evaluate_observation(observation: Any) -> PolicyDecision:
    category = observation.category
    state = observation.state_hint.upper()

    def decision(find: str | None, find_state: str | None, remediate: str | None,
                 remediate_state: str | None, verify: str, verify_state: str,
                 violation: bool) -> PolicyDecision:
        return PolicyDecision(observation, find, find_state, remediate,
                              remediate_state, verify, verify_state, violation)

    if category in DELETE_CATEGORIES:
        if state == "ABSENT":
            return decision(None, None, None, None, "VERIFY_RECORD_ABSENT", "ABSENT", False)
        return decision("REPORT_REMAINING_RECORD", "PRESENT", "DELETE_RECORD", "ABSENT",
                        "VERIFY_RECORD_ABSENT", "ABSENT", True)

    if category in {"SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG"}:
        if state in {"REDACTED", "ANONYMIZED", "ABSENT"}:
            op, out = (("VERIFY_RECORD_ABSENT", "ABSENT") if state == "ABSENT"
                       else ("VERIFY_RECORD_REDACTED", "REDACTED"))
            return decision(None, None, None, None, op, out, False)
        return decision("REPORT_EXPOSED_PII", "PRESENT", "REDACT_RECORD", "REDACTED",
                        "VERIFY_RECORD_REDACTED", "REDACTED", True)

    if category in {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}:
        if state in {"ANONYMIZED", "ABSENT"}:
            op, out = (("VERIFY_RECORD_ABSENT", "ABSENT") if state == "ABSENT"
                       else ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"))
            return decision(None, None, None, None, op, out, False)
        return decision("REPORT_EXPOSED_PII", "PRESENT", "ANONYMIZE_RECORD", "ANONYMIZED",
                        "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED", True)

    if category == "ACCOUNT_TOMBSTONE":
        if state in {"REDACTED", "ABSENT"}:
            op, out = (("VERIFY_RECORD_ABSENT", "ABSENT") if state == "ABSENT"
                       else ("VERIFY_RECORD_REDACTED", "REDACTED"))
            return decision(None, None, None, None, op, out, False)
        return decision("REPORT_EXPOSED_PII", "PRESENT", "REDACT_RECORD", "REDACTED",
                        "VERIFY_RECORD_REDACTED", "REDACTED", True)

    if category == "DATA_FLOW":
        if state == "DISABLED":
            return decision(None, None, None, None, "VERIFY_DATA_FLOW_DISABLED", "DISABLED", False)
        return decision("REPORT_ACTIVE_DATA_FLOW", "ACTIVE", "DISABLE_DATA_FLOW", "DISABLED",
                        "VERIFY_DATA_FLOW_DISABLED", "DISABLED", True)

    if category == "BACKUP_ARCHIVE":
        if state in {"RESTORE_BLOCKED", "BLOCKED"}:
            return decision(None, None, None, None, "VERIFY_RESTORE_BLOCKED", "BLOCKED", False)
        return decision("REPORT_RESTORE_RISK", "ACTIVE", "BLOCK_RESTORE", "BLOCKED",
                        "VERIFY_RESTORE_BLOCKED", "BLOCKED", True)

    if category == "SECURITY_AUDIT_LOG":
        if state == "ABSENT":
            # The supplied retention period is not available on an absence
            # observation, so absence is a policy violation requiring review.
            return decision(None, None, None, None, "VERIFY_RECORD_PRESENT", "PRESENT", True)
        if state in {"RETENTION_EXPIRED", "EXPIRED"}:
            return decision("REPORT_REMAINING_RECORD", "PRESENT", "DELETE_RECORD", "ABSENT",
                            "VERIFY_RECORD_ABSENT", "ABSENT", True)
        return decision(None, None, None, None, "VERIFY_RECORD_PRESENT", "PRESENT", False)

    if category == "LEGAL_HOLD_RECORD":
        if state in {"HOLD_EXPIRED", "RELEASED", "EXPIRED"}:
            if state == "ABSENT":
                return decision(None, None, None, None, "VERIFY_RECORD_ABSENT", "ABSENT", False)
            return decision("REPORT_REMAINING_RECORD", "PRESENT", "DELETE_RECORD", "ABSENT",
                            "VERIFY_RECORD_ABSENT", "ABSENT", True)
        return decision(None, None, None, None, "VERIFY_RECORD_PRESENT", "PRESENT", False)

    # Unknown categories are not silently declared compliant. Keep the
    # observable record in the finding for a safe delete/remediation proposal.
    if state == "ABSENT":
        return decision(None, None, None, None, "VERIFY_RECORD_ABSENT", "ABSENT", False)
    return decision("REPORT_REMAINING_RECORD", "PRESENT", "DELETE_RECORD", "ABSENT",
                    "VERIFY_RECORD_ABSENT", "ABSENT", True)


def evaluate_all(observations: list[Any]) -> list[PolicyDecision]:
    return [evaluate_observation(item) for item in observations]
