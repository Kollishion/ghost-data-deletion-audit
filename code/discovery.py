"""Discover subject-linked resources from participant evidence and activity."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from . import loaders
    from .identity import resolve_identity
except ImportError:  # direct script/module execution from code/
    import loaders
    from identity import resolve_identity


RESOURCE_RE = re.compile(
    r"\b(?:account|analytics|audit_record|backup|data_flow|email_delivery|export|"
    r"legal_hold|marketing|object|search|secondary|support|telemetry|"
    r"tombstone|cache)_\d+\b"
)
SYSTEM_BY_PREFIX = {
    "account_": "account_service", "analytics_": "analytics_platform",
    "audit_record_": "security_service", "backup_": "backup_service",
    "data_flow_": "integration_service", "email_delivery_": "email_delivery_service",
    "export_": "export_service", "legal_hold_": "legal_service",
    "marketing_": "marketing_platform", "object_": "object_storage",
    "search_": "search_service", "secondary_": "account_service",
    "support_": "support_platform", "telemetry_": "analytics_platform",
    "tombstone_": "identity_service", "cache_": "cache_service",
}


def _dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _flatten(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _flatten(child)
    elif isinstance(value, list):
        for child in value:
            yield from _flatten(child)
    elif value is not None:
        yield str(value)


def _objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _log_fields(line: str) -> dict[str, Any]:
    """Parse key=value and key: value tokens from one structured log record."""
    row: dict[str, Any] = {}
    for match in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|\S+)', line):
        value = match.group(2).strip('"')
        row[match.group(1).casefold()] = value
    return row


def _is_subject_match(obj: Any, user_id: str, identifiers: set[str]) -> bool:
    values = [v.strip().casefold() for v in _flatten(obj) if v.strip()]
    needles = {user_id.casefold(), *(v.strip().casefold() for v in identifiers)}
    for value in values:
        for needle in needles:
            # Boundary-aware substring search handles serialized log lines while
            # preventing user_1 from matching user_10. Punctuation is allowed
            # around phones and email addresses in evidence text.
            pattern = re.escape(needle)
            if needle.startswith("user_"):
                pattern = r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])"
            elif "@" not in needle and not re.fullmatch(r"[0-9a-f]{64}", needle):
                pattern = r"(?<!\w)" + pattern + r"(?!\w)"
            if re.search(pattern, value, re.I):
                return True
    return False


def _observation_time(obj: Any) -> datetime | None:
    if not isinstance(obj, dict):
        return None
    for key in ("observed_at", "captured_at", "recorded_at", "updated_at",
                "event_time", "indexed_at", "created_at", "exported_at"):
        value = obj.get(key)
        if isinstance(value, str) and (parsed := _dt(value)):
            return parsed
    return None


@dataclass(frozen=True)
class Observation:
    system_id: str
    resource_id: str
    evidence_id: str
    observed_at: str
    state_hint: str
    category: str


CATEGORY_BY_PREFIX = {
    "account_": "USER_PROFILE", "analytics_": "ANALYTICS_PROFILE",
    "audit_record_": "SECURITY_AUDIT_LOG", "backup_": "BACKUP_ARCHIVE",
    "data_flow_": "DATA_FLOW", "email_delivery_": "EMAIL_DELIVERY_LOG",
    "export_": "USER_EXPORT", "legal_hold_": "LEGAL_HOLD_RECORD",
    "marketing_": "MARKETING_PROFILE", "object_": "SUPPORT_ATTACHMENT",
    "search_": "SEARCH_INDEX_ENTRY", "secondary_": "SECONDARY_IDENTIFIER",
    "support_": "SUPPORT_MESSAGE", "telemetry_": "PRODUCT_TELEMETRY",
    "tombstone_": "ACCOUNT_TOMBSTONE", "cache_": "CACHE_ENTRY",
}


def _identify(resource_id: str, obj: Any, default_system: str = "") -> tuple[str, str]:
    prefix = next((p for p in SYSTEM_BY_PREFIX if resource_id.startswith(p)), "")
    category = CATEGORY_BY_PREFIX.get(prefix, "UNKNOWN")
    system = default_system or SYSTEM_BY_PREFIX.get(prefix, "unknown")
    # In SQL inventory tables, origin_system is the actual system of the resource.
    if isinstance(obj, dict) and isinstance(obj.get("origin_system"), str):
        system = obj["origin_system"]
    system = {"support_replica": "support_platform"}.get(system, system)
    if isinstance(obj, dict):
        collection = str(obj.get("collection_name", obj.get("collection", ""))).casefold()
        record_type = str(obj.get("record_type", "")).casefold()
        event = str(obj.get("event", obj.get("event_name", ""))).casefold()
        if "ticket_attachment" in collection or "support_attachment" in record_type or "attachment" in event:
            category = "SUPPORT_ATTACHMENT"
        elif "secondary_identifier" in collection or "secondary_identifier" in record_type:
            category = "SECONDARY_IDENTIFIER"
        elif "telemetry" in collection or "product_telemetry" in record_type:
            category = "PRODUCT_TELEMETRY"
    return system, category


def _direct_resources(obj: Any) -> list[str]:
    """Read resource keys from the current record's resource/link fields."""
    result: set[str] = set()
    if not isinstance(obj, dict):
        return []
    for key in ("resource_id", "linked_resource_id", "source_resource_id",
                "target_resource_id", "parent_resource_id", "related_resource_id"):
        value = obj.get(key)
        if isinstance(value, str) and RESOURCE_RE.fullmatch(value):
            result.add(value)
    for key in ("resource_ids", "linked_resource_ids"):
        value = obj.get(key, [])
        if isinstance(value, list):
            result.update(v for v in value if isinstance(v, str) and RESOURCE_RE.fullmatch(v))
    return sorted(result)


def _structured_subject_match(obj: Any, user_id: str, identifiers: set[str]) -> bool:
    """Match identity through known record-link fields, not unrelated payload text."""
    link_names = {"subject_reference", "user_id", "customer_reference", "owner_email",
                  "requester_email", "customer_email", "email", "email_hash", "phone",
                  "owner_phone", "requester_phone", "customer_phone", "linked_user_id",
                  "linked_subject_reference"}
    needles = {user_id.casefold(), *(v.strip().casefold() for v in identifiers)}

    def visit(value: Any, key: str = "") -> bool:
        if isinstance(value, dict):
            return any(visit(child, str(child_key).casefold())
                       for child_key, child in value.items())
        if isinstance(value, list):
            return any(visit(child, key) for child in value)
        if key not in link_names or value is None:
            return False
        candidate = str(value).strip().casefold()
        return bool(candidate and candidate not in {"null", "none"} and candidate in needles)

    return visit(obj)


def _state_hint(category: str, obj: Any, cutoff: datetime | None) -> str:
    """Extract an observed state clue from one resource record/line."""
    raw = " ".join(_flatten(obj))
    if re.search(r"\b(NOT_FOUND|NOT FOUND|ABSENT|rows\s*[=:]\s*0|http_status\s*[=:]\s*404|status_code\s*[=:]\s*404)\b", raw, re.I):
        return "ABSENT"
    if not isinstance(obj, dict):
        return "PRESENT"
    if str(obj.get("status_code", "")) == "404" or str(obj.get("http_status", "")) == "404":
        return "ABSENT"
    if any(key in obj and obj.get(key) is None for key in ("profile", "record", "row")):
        return "ABSENT"
    if category == "DATA_FLOW":
        enabled = obj.get("enabled")
        if str(enabled).casefold() in {"true", "1", "yes"}:
            return "ACTIVE"
        if str(enabled).casefold() in {"false", "0", "no"}:
            return "DISABLED"
    if category == "BACKUP_ARCHIVE":
        restore = obj.get("restore_allowed")
        if str(restore).casefold() in {"true", "1", "yes"}:
            return "RESTORE_ALLOWED"
        if str(restore).casefold() in {"false", "0", "no"}:
            return "RESTORE_BLOCKED"
    if category in {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY", "ACCOUNT_TOMBSTONE"}:
        direct_fields = {"email", "phone", "email_hash", "full_name", "name",
                         "display_name", "owner_email", "customer_email", "requester_email"}
        if any(str(obj.get(k) or "").strip().casefold() not in {"", "null", "none"}
               for k in direct_fields):
            return "EXPOSED_PII"
        return "ANONYMIZED" if category != "ACCOUNT_TOMBSTONE" else "REDACTED"
    if category in {"SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "EMAIL_DELIVERY_LOG"}:
        pii_fields = {"email", "phone", "email_hash", "requester_email", "requester_phone",
                      "owner_email", "customer_email", "message_text", "message_excerpt"}
        if any(str(obj.get(k) or "").strip().casefold() not in {"", "null", "none"}
               for k in pii_fields):
            return "EXPOSED_PII"
    if category == "SECURITY_AUDIT_LOG":
        until = _dt(str(obj.get("retention_until", "")))
        return "RETAINED" if not until or not cutoff or until >= cutoff else "RETENTION_EXPIRED"
    if category == "LEGAL_HOLD_RECORD":
        until = _dt(str(obj.get("retained_until", "")))
        return "RETAINED" if not until or not cutoff or until >= cutoff else "HOLD_EXPIRED"
    status = str(obj.get("account_status", "")).casefold()
    if category == "USER_PROFILE" and status in {"deleted", "not_found", "absent"}:
        return "ABSENT"
    return "PRESENT"


def _sql_objects(path: Path) -> Iterable[dict[str, Any]]:
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(path.read_text(encoding="utf-8-sig"))
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            if table == "snapshot_scope":
                continue
            cur = db.execute(f'SELECT * FROM "{table}"')
            columns = [d[0] for d in cur.description]
            for row in cur:
                obj = dict(zip(columns, row))
                if isinstance(obj.get("record_json"), str):
                    try:
                        obj.update(json.loads(obj["record_json"]))
                    except json.JSONDecodeError:
                        pass
                yield obj
    finally:
        db.close()


def _manifest() -> list[dict[str, str]]:
    return loaders.read_evidence_manifest()


def discover_case(case: dict[str, str]) -> list[Observation]:
    user_id, identifiers = resolve_identity(case["email"], case["audit_at"])
    cutoff = _dt(case["audit_at"])
    found: dict[tuple[str, str], Observation] = {}

    def add(resource_id: str, evidence_id: str, observed: datetime | None,
            state_hint: str = "PRESENT", system: str = "", obj: Any = None) -> None:
        if cutoff and observed and observed > cutoff:
            return
        actual_system, category = _identify(resource_id, obj, system)
        key = (actual_system, resource_id)
        stamp = observed.isoformat() if observed else ""
        old = found.get(key)
        if old is None or stamp > old.observed_at:
            found[key] = Observation(actual_system, resource_id, evidence_id,
                                     stamp, state_hint, category)

    for item in _manifest():
        captured = _dt(item.get("captured_at", ""))
        if cutoff and captured and captured > cutoff:
            continue
        path = loaders.evidence_path(item["file_path"])
        suffix = path.suffix.casefold()
        if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
            continue
        if suffix == ".sql":
            objects = _sql_objects(path)
        elif suffix == ".json":
            try:
                root = loaders.read_json(path)
            except (ValueError, OSError):
                continue
            objects = _objects(root)
        elif suffix in {".log", ".txt"}:
            try:
                lines = path.read_text(encoding="utf-8-sig").splitlines()
            except OSError:
                continue
            parsed_lines = []
            traces: dict[str, list[dict[str, Any]]] = {}
            for line in lines:
                if not line.strip():
                    continue
                time_match = re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", line)
                row = _log_fields(line)
                row.update({"line": line, "resource_ids": RESOURCE_RE.findall(line),
                            "observed_at": time_match.group(0) if time_match else ""})
                parsed_lines.append(row)
                trace_match = re.search(r'(?:trace_id|traceId|requestId|correlation_id)[=:" ]+([A-Za-z0-9-]+)', line, re.I)
                if trace_match:
                    traces.setdefault(trace_match.group(1), []).append(row)
            # Correlated log records form one observation when the identifier
            # lookup and resource read are separate lines in the same trace.
            for trace_id, rows in traces.items():
                ids = sorted({rid for row in rows for rid in row["resource_ids"]})
                if ids:
                    fields = {}
                    for row in rows:
                        fields.update({k: v for k, v in row.items() if k != "line"})
                    parsed_lines.append({**fields, "trace_id": trace_id, "lines": [r["line"] for r in rows],
                                         "resource_ids": ids,
                                         "observed_at": max((r["observed_at"] for r in rows), default="")})
            objects = parsed_lines
        else:
            continue

        for obj in objects:
            if not _direct_resources(obj):
                continue
            if not (_structured_subject_match(obj, user_id, identifiers) or
                    _is_subject_match(obj, user_id, identifiers)):
                continue
            observed = _observation_time(obj) or captured
            ids = _direct_resources(obj)
            # The origin/target/system on the record overrides prefix defaults.
            source_system = next((str(obj[k]) for k in ("system", "target_system", "service")
                                  if isinstance(obj, dict) and obj.get(k)), "")
            category = _identify(ids[0], obj, source_system)[1]
            hint = _state_hint(category, obj, cutoff)
            for resource_id in sorted(set(ids)):
                add(resource_id, item["file_id"], observed, hint, source_system, obj)

    activity_rows = loaders.read_activity()
    # Build a cutoff-bounded resource graph. Identity-bearing catalog events
    # seed the subject's resources; event details can then connect related keys.
    graph: dict[str, set[str]] = {}
    event_by_resource: dict[str, list[tuple[dict[str, str], datetime | None]]] = {}
    for event in activity_rows:
        event_time = _dt(event.get("event_time", ""))
        if cutoff and event_time and event_time > cutoff:
            continue
        rid = event.get("resource_id", "")
        refs = set(RESOURCE_RE.findall(event.get("details", "")))
        if rid and RESOURCE_RE.fullmatch(rid):
            refs.add(rid)
        for key in refs:
            graph.setdefault(key, set()).update(refs - {key})
            event_by_resource.setdefault(key, []).append((event, event_time))

    seeds: set[str] = set()
    for event in activity_rows:
        event_time = _dt(event.get("event_time", ""))
        if cutoff and event_time and event_time > cutoff:
            continue
        details = event.get("details", "")
        if not _is_subject_match({"details": details}, user_id, identifiers):
            continue
        seeds.update(RESOURCE_RE.findall(details))
        rid = event.get("resource_id", "")
        if rid and RESOURCE_RE.fullmatch(rid):
            seeds.add(rid)
    linked_resources = set(seeds)
    frontier = list(seeds)
    while frontier:
        current = frontier.pop()
        for neighbor in graph.get(current, ()):
            if neighbor not in linked_resources:
                linked_resources.add(neighbor)
                frontier.append(neighbor)
    for resource_id in sorted(linked_resources):
        for event, event_time in event_by_resource.get(resource_id, ()):
            system = event.get("target_system", "")
            add(resource_id, event.get("activity_id", ""), event_time,
                "PRESENT", system)

    # Preserve the best eligible observation for each unique system/resource pair.
    return sorted(found.values(), key=lambda o: (o.system_id, o.resource_id))


def discover_samples() -> dict[str, list[Observation]]:
    return {case["case_id"]: discover_case(case) for case in loaders.read_requests(samples=True)}
