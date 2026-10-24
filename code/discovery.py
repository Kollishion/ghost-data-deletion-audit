"""Discover subject-linked resources from participant evidence and activity."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
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


def _snapshot_resource_absent(path: Path, system_id: str, resource_id: str) -> bool:
    """Return true when a scoped JSON record array explicitly omits the key.

    In particular, an empty ``records`` array is an explicit empty snapshot,
    rather than a missing/unparsed observation. This predicate is intentionally
    scoped by the snapshot's source system and only applies to a JSON record set.
    """
    try:
        root = loaders.read_json(path)
    except (ValueError, OSError):
        return False
    for obj in _objects(root):
        store = str(obj.get("data_store", obj.get("system_id", "")))
        records = obj.get("records")
        if store == system_id and isinstance(records, list):
            if not records:
                return True
    return False


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
    source_type: str = "evidence"
    link_basis: str = ""
    link_field: str = ""
    link_value: str = ""
    matched_identifier: str = ""
    link_type: str = ""


def _snapshot_absence_observation(
    item: dict[str, str], resource_id: str, system_id: str
) -> Observation | None:
    """Parse an explicit empty scoped snapshot as an ABSENT observation."""
    captured = item.get("captured_at", "")
    path = loaders.evidence_path(item["file_path"])
    if not _snapshot_resource_absent(path, system_id, resource_id):
        return None
    _, category = _identify(resource_id, {})
    observed = _dt(captured)
    return Observation(system_id, resource_id, item["file_id"],
                       observed.isoformat() if observed else "", "ABSENT", category)


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
        # Plain-text handover rows carry an explicit category in their own
        # pipe-delimited fields; preserve that classification over the ID prefix.
        line = str(obj.get("line", ""))
        columns = [part.strip() for part in line.split("|")]
        if len(columns) >= 5:
            explicit_category = columns[3].upper()
            if explicit_category in set(CATEGORY_BY_PREFIX.values()):
                category = explicit_category
        # A contact lookup carrying an explicit opt-in field is a marketing
        # contact record by its own event/consent fields. The marketing rule
        # requires deletion; it is not an analytics profile merely because
        # the service storing it is the analytics platform.
        event_name = str(obj.get("event", obj.get("event_name", ""))).casefold()
        if ("contact_lookup" in event_name and
                any(key in obj for key in ("email_opt_in", "marketing_opt_in", "subscription_status"))):
            category = "MARKETING_PROFILE"
        if (str(obj.get("source", "")).casefold() == "legacy_contact_index" and
                bool(obj.get("lookup_key"))):
            category = "SEARCH_INDEX_ENTRY"
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
    value = obj.get("resource_id")
    if isinstance(value, str) and RESOURCE_RE.fullmatch(value):
        result.add(value)
    for key in ("resource_ids", "linked_resource_ids"):
        value = obj.get(key, [])
        if isinstance(value, list):
            result.update(v for v in value if isinstance(v, str) and RESOURCE_RE.fullmatch(v))
    return sorted(result)


def _referenced_resources(obj: Any) -> set[str]:
    """Extract resource references separately from the record's own resource."""
    refs: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key).casefold())
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and (
                "resource" in key or key in {
                    "reference_id", "source_reference_id", "target_reference_id",
                    "archive_key", "backup_key", "replica_pair", "snapshot_key",
                }):
            refs.update(RESOURCE_RE.findall(value))

    visit(obj)
    return refs - set(_direct_resources(obj))


RESOURCE_JOIN_FIELDS = {
    "correlation_key", "correlation_id", "trace_id", "request_id",
    "reference_id", "source_reference_id", "target_reference_id",
    "email_hash", "profile_hash", "record_hash", "archive_key", "backup_key",
}


def _resource_join_values(obj: Any) -> set[tuple[str, str]]:
    values: set[tuple[str, str]] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).casefold()
                if normalized in RESOURCE_JOIN_FIELDS and isinstance(child, (str, int)):
                    candidate = str(child).strip().casefold()
                    if candidate and candidate not in {"null", "none"}:
                        values.add((normalized, candidate))
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(obj)
    return values


def _sql_system(table_name: str) -> str:
    name = table_name.casefold()
    for fragment, system in (
        ("customer_profiles", "account_service"), ("search", "search_service"),
        ("analytics", "analytics_platform"), ("support", "support_platform"),
        ("export", "export_service"), ("connector", "integration_service"),
        ("backup", "backup_service"), ("audit", "security_service"),
    ):
        if fragment in name:
            return system
    return ""


OWNER_LINK_FIELDS = {
    "user_id", "subject_reference", "customer_reference", "linked_user_id",
    "linked_subject_reference", "owner_user_id", "requester_user_id",
    "customer_user_id", "account_user_id",
}


def _explicit_subject_refs(obj: Any) -> set[str]:
    """Extract stable subject references only from recognized link fields."""
    refs: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).casefold() in OWNER_LINK_FIELDS:
                    values = child if isinstance(child, list) else [child]
                    for item in values:
                        if isinstance(item, str) and re.fullmatch(r"user_\d+", item.strip(), re.I):
                            refs.add(item.strip().casefold())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(obj)
    return refs


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


def _subject_link_details(obj: Any, user_id: str, identifiers: set[str]) -> tuple[str, str, str, str]:
    """Return the concrete field/value/identifier that grounded the user link."""
    link_names = {"subject_reference", "user_id", "customer_reference", "owner_email",
                  "requester_email", "customer_email", "email", "email_hash", "phone",
                  "owner_phone", "requester_phone", "customer_phone", "linked_user_id",
                  "linked_subject_reference"}
    needles = {user_id.casefold(): user_id}
    needles.update({value.strip().casefold(): value.strip() for value in identifiers if value.strip()})

    def leaves(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                yield from leaves(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from leaves(child, f"{path}[{index}]")
        elif value is not None:
            yield path, str(value)

    fields = list(leaves(obj))
    # Explicit link fields have the strongest provenance and require equality.
    for path, value in fields:
        key = path.rsplit(".", 1)[-1].split("[", 1)[0].casefold()
        candidate = value.strip().casefold()
        if key in link_names and candidate in needles:
            matched = needles[candidate]
            return path, value, matched, f"structured:{key}"
    # Keep legacy content matching, but expose the exact leaf that matched.
    for path, value in fields:
        folded = value.casefold()
        for normalized, original in needles.items():
            pattern = re.escape(normalized)
            if normalized.startswith("user_"):
                pattern = r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])"
            elif "@" not in normalized and not re.fullmatch(r"[0-9a-f]{64}", normalized):
                pattern = r"(?<!\w)" + pattern + r"(?!\w)"
            if re.search(pattern, folded, re.I):
                key = path.rsplit(".", 1)[-1].split("[", 1)[0].casefold()
                link_type = f"identifier:{key}" if key in link_names | {"correlation_key"} else "content_match"
                return path, value, original, link_type
    return "", "", "", ""


def _state_hint(
    category: str, obj: Any, cutoff: datetime | None,
    identifiers: set[str] | None = None, user_id: str = "",
) -> str:
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
        nonempty_direct = any(str(obj.get(k) or "").strip().casefold() not in {"", "null", "none"}
                              for k in direct_fields)
        subject_refs = {"user_id", "subject_reference", "customer_reference",
                        "linked_user_id", "linked_subject_reference"}
        has_stable_link = any(
            str(obj.get(k) or "").strip().casefold() == user_id.casefold()
            for k in subject_refs
        )
        correlation = str(obj.get("correlation_key", "")).strip().casefold()
        is_subject_correlation = bool(correlation and identifiers and
                                      correlation in {v.strip().casefold() for v in identifiers})
        if nonempty_direct or (category != "ACCOUNT_TOMBSTONE" and
                               (has_stable_link or is_subject_correlation)):
            return "EXPOSED_PII"
        # A row count or successful lookup establishes presence, not
        # anonymization. Only structured records with identifier columns can
        # prove the fields were removed.
        if any(key in obj for key in ("rows", "row_count", "record_count")):
            return "PRESENT"
        return "ANONYMIZED" if category != "ACCOUNT_TOMBSTONE" else "REDACTED"
    if category in {"SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "EMAIL_DELIVERY_LOG"}:
        pii_fields = {"email", "phone", "email_hash", "requester_email", "requester_phone",
                      "requester_name", "owner_email", "customer_email", "full_name"}
        if any(str(obj.get(k) or "").strip().casefold() not in {"", "null", "none"}
               for k in pii_fields):
            return "EXPOSED_PII"
        free_text = " ".join(str(obj.get(k) or "") for k in
                             ("message_text", "message_excerpt", "body", "attachment_text"))
        for identifier in identifiers or ():
            needle = identifier.strip().casefold()
            if needle and needle in free_text.casefold():
                return "EXPOSED_PII"
        if any(key in obj for key in pii_fields):
            return "REDACTED"
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
                obj = {**dict(zip(columns, row)), "_table_name": table}
                if isinstance(obj.get("record_json"), str):
                    try:
                        obj.update(json.loads(obj["record_json"]))
                    except json.JSONDecodeError:
                        pass
                yield obj
    finally:
        db.close()


@lru_cache(maxsize=1)
def _manifest() -> tuple[dict[str, str], ...]:
    return tuple(loaders.read_evidence_manifest())


@lru_cache(maxsize=256)
def _parse_evidence_objects(relative_path: str) -> tuple[dict[str, Any], ...]:
    path = loaders.evidence_path(relative_path)
    suffix = path.suffix.casefold()
    if suffix == ".sql":
        rows = list(_sql_objects(path))
        systems: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            system = _sql_system(str(row.get("_table_name", "")))
            resource_id = str(row.get("resource_id", ""))
            if system and RESOURCE_RE.fullmatch(resource_id):
                systems[system].add(resource_id)
        sql_text = path.read_text(encoding="utf-8-sig")
        metadata = {"_sql_snapshot": (
            "point-in-time database snapshot" in sql_text.casefold()
            or "snapshot_scope" in sql_text.casefold()),
            "_sql_systems": {key: sorted(value) for key, value in systems.items()}}
        return tuple([*rows, metadata])
    if suffix == ".json":
        try:
            return tuple(_objects(loaders.read_json(path)))
        except (ValueError, OSError):
            return ()
    if suffix not in {".log", ".txt"}:
        return ()
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ()
    parsed_lines: list[dict[str, Any]] = []
    traces: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        if not line.strip():
            continue
        time_match = re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", line)
        row = _log_fields(line)
        row.update({"line": line, "resource_ids": RESOURCE_RE.findall(line),
                    "observed_at": time_match.group(0) if time_match else ""})
        parsed_lines.append(row)
        trace_match = re.search(
            r'(?:trace_id|traceId|requestId|correlation_id)[=:" ]+([A-Za-z0-9-]+)',
            line, re.I)
        if trace_match:
            traces.setdefault(trace_match.group(1), []).append(row)
    for trace_id, rows in traces.items():
        ids = sorted({rid for row in rows for rid in row["resource_ids"]})
        if ids:
            fields: dict[str, Any] = {}
            for row in rows:
                fields.update({key: value for key, value in row.items() if key != "line"})
            parsed_lines.append({**fields, "trace_id": trace_id,
                                 "lines": [row["line"] for row in rows],
                                 "resource_ids": ids,
                                 "observed_at": max((row["observed_at"] for row in rows), default="")})
    return tuple(parsed_lines)


def discover_case(case: dict[str, str], *, graph_iterations: int = 0) -> list[Observation]:
    user_id, identifiers = resolve_identity(case["email"], case["audit_at"])
    cutoff = _dt(case["audit_at"])
    requested_at = _dt(case.get("requested_at", ""))
    found: dict[tuple[str, str], Observation] = {}
    explicit_owners: dict[str, set[str]] = {}
    resource_graph: dict[str, set[str]] = defaultdict(set)
    evidence_candidates: dict[str, list[tuple[str, datetime | None, str, str, Any, tuple[str, str, str, str]]]] = defaultdict(list)
    join_rows: list[tuple[set[str], set[tuple[str, str]]]] = []
    sql_snapshots: list[tuple[str, datetime | None, dict[str, set[str]]]] = []

    def add(resource_id: str, evidence_id: str, observed: datetime | None,
            state_hint: str = "PRESENT", system: str = "", obj: Any = None,
            link_basis: str = "", source_type: str = "evidence",
            link_details: tuple[str, str, str, str] = ("", "", "", "")) -> None:
        if cutoff and observed and observed > cutoff:
            return
        actual_system, category = _identify(resource_id, obj, system)
        key = (actual_system, resource_id)
        stamp = observed.isoformat() if observed else ""
        candidate = Observation(actual_system, resource_id, evidence_id,
                                 stamp, state_hint, category, source_type, link_basis,
                                 *link_details)
        old = found.get(key)
        state_priority = {
            "PRESENT": 0, "ACTIVE": 0, "RESTORE_ALLOWED": 0,
            "EXPOSED_PII": 1, "ABSENT": 2, "REDACTED": 2,
            "ANONYMIZED": 2, "DISABLED": 2, "RESTORE_BLOCKED": 2,
            "RETAINED": 2, "RETENTION_EXPIRED": 2, "HOLD_EXPIRED": 2,
        }
        candidate_key = (source_type == "evidence", stamp,
                         state_priority.get(state_hint, 1))
        old_key = ((old.source_type == "evidence"), old.observed_at,
                   state_priority.get(old.state_hint, 1)) if old else None
        if old is None or candidate_key > old_key:
            found[key] = candidate

    for item in _manifest():
        captured = _dt(item.get("captured_at", ""))
        if cutoff and captured and captured > cutoff:
            continue
        path = loaders.evidence_path(item["file_path"])
        suffix = path.suffix.casefold()
        if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
            continue
        objects = _parse_evidence_objects(item["file_path"])
        for metadata in (obj for obj in objects if obj.get("_sql_snapshot")):
            sql_snapshots.append((item["file_id"], captured,
                                  {key: set(value) for key, value in
                                   metadata.get("_sql_systems", {}).items()}))

        for obj in objects:
            ids = _direct_resources(obj)
            if not ids:
                continue
            refs = _referenced_resources(obj)
            row_resources = set(ids) | refs
            owners = _explicit_subject_refs(obj)
            for resource_id in row_resources:
                explicit_owners.setdefault(resource_id, set()).update(owners)
            for resource_id in row_resources:
                resource_graph[resource_id].update(row_resources - {resource_id})
            join_rows.append((row_resources, _resource_join_values(obj)))
            link_details = _subject_link_details(obj, user_id, identifiers)
            observed = _observation_time(obj) or captured
            # The origin/target/system on the record overrides prefix defaults.
            source_system = next((str(obj[k]) for k in ("system", "target_system", "service")
                                  if isinstance(obj, dict) and obj.get(k)), "")
            for resource_id in ids:
                category = _identify(resource_id, obj, source_system)[1]
                hint = _state_hint(category, obj, cutoff, identifiers, user_id)
                evidence_candidates[resource_id].append(
                    (item["file_id"], observed, hint, source_system, obj, link_details))
            if not (link_details[0] or _is_subject_match(obj, user_id, identifiers)):
                continue
            structured_link = link_details[3].startswith("structured:")
            link_basis = ("structured subject field" if structured_link
                          else "current/historical identifier match")
            for resource_id in sorted(set(ids)):
                category = _identify(resource_id, obj, source_system)[1]
                hint = _state_hint(category, obj, cutoff, identifiers, user_id)
                add(resource_id, item["file_id"], observed, hint, source_system, obj,
                    link_basis, "evidence", link_details)

    # Join exact record keys (trace/correlation/reference/hash/archive) across
    # rows, and retain explicit resource-reference edges as separate links.
    join_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for resources, values in join_rows:
        for value in values:
            join_index[value].update(resources)
    for resources in join_index.values():
        if len(resources) < 2:
            continue
        for resource_id in resources:
            resource_graph[resource_id].update(resources - {resource_id})

    activity_rows = loaders.read_activity()
    # Build a cutoff-bounded resource graph. Identity-bearing catalog events
    # seed the subject's resources; event details can then connect related keys.
    graph: dict[str, set[str]] = {}
    event_by_resource: dict[str, list[tuple[dict[str, str], datetime | None]]] = {}
    for event in activity_rows:
        event_time = _dt(event.get("event_time", ""))
        if cutoff and event_time and event_time > cutoff:
            continue
        if requested_at and event_time and event_time < requested_at:
            continue
        rid = event.get("resource_id", "")
        refs = set(RESOURCE_RE.findall(event.get("details", "")))
        if rid and RESOURCE_RE.fullmatch(rid):
            refs.add(rid)
        detail = event.get("details", "")
        owner_refs = {
            value.casefold() for value in re.findall(
                r"\b(?:user_id|subject_reference|customer_reference|owner_user_id|"
                r"requester_user_id|linked_user_id)\s*[:=]\s*(user_\d+)\b",
                detail, re.I,
            )
        }
        if event.get("event_type", "").upper() == "LINK_RESOURCE_IDENTITY":
            owner_refs.update(value.casefold() for value in re.findall(r"\buser_\d+\b", detail, re.I))
        for resource_id in refs:
            explicit_owners.setdefault(resource_id, set()).update(owner_refs)
        for key in refs:
            graph.setdefault(key, set()).update(refs - {key})
            event_by_resource.setdefault(key, []).append((event, event_time))

    seeds: set[str] = set()
    for event in activity_rows:
        event_time = _dt(event.get("event_time", ""))
        if cutoff and event_time and event_time > cutoff:
            continue
        if requested_at and event_time and event_time < requested_at:
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
                "PRESENT", system, None,
                "identity-bearing activity link" if resource_id in seeds else
                "explicit resource reference from linked activity",
                "activity_claim")

    for resource_id, neighbors in graph.items():
        resource_graph[resource_id].update(neighbors)
    reachable = {resource for _, resource in found}
    reachable.update(linked_resources)
    frontier = set(reachable)
    for iteration in range(max(0, graph_iterations)):
        next_frontier: set[str] = set()
        parent_for: dict[str, str] = {}
        for source in sorted(frontier):
            for target in resource_graph.get(source, set()) - reachable:
                next_frontier.add(target)
                parent_for.setdefault(target, source)
        next_frontier = {
            target for target in next_frontier
            if not any(owner != user_id.casefold()
                       for owner in explicit_owners.get(target, set()))
        }
        for target in sorted(next_frontier):
            candidates = evidence_candidates.get(target, ())
            if candidates:
                for evidence_id, observed, hint, system, obj, _ in candidates:
                    add(target, evidence_id, observed, hint, system, obj,
                        f"resource graph iteration {iteration + 1}", "evidence",
                        ("resource_reference", parent_for.get(target, ""), target,
                         "resource_graph"))
            else:
                default_system, _ = _identify(target, {})
                for evidence_id, captured, systems in sql_snapshots:
                    if default_system in systems and target not in systems[default_system]:
                        add(target, evidence_id, captured, "ABSENT", default_system, None,
                            f"resource graph iteration {iteration + 1} via scoped SQL absence",
                            "evidence", ("snapshot_scope", parent_for.get(target, default_system), target,
                                         "resource_graph"))
        reachable.update(next_frontier)
        frontier = next_frontier

    # A scoped, explicitly empty structured snapshot is a direct absence
    # observation for resources already linked to this subject. The activity
    # link supplies identity; the snapshot supplies state.
    for existing in list(found.values()):
        if existing.link_basis not in {
                "structured subject field", "current/historical identifier match",
                "identity-bearing activity link"}:
            continue
        for item in _manifest():
            captured = _dt(item.get("captured_at", ""))
            if cutoff and captured and captured > cutoff:
                continue
            path = loaders.evidence_path(item["file_path"])
            if path.suffix.casefold() != ".json":
                continue
            absent = _snapshot_absence_observation(item, existing.resource_id,
                                                   existing.system_id)
            if absent:
                add(existing.resource_id, item["file_id"], _dt(absent.observed_at),
                    "ABSENT", existing.system_id, None, existing.link_basis, "evidence")

    # A resource with explicit ownership evidence for a different stable user
    # is a decoy for this subject, even if its identifier appears nearby.
    found = {
        key: observation
        for key, observation in found.items()
        if not any(owner != user_id.casefold()
                   for owner in explicit_owners.get(observation.resource_id, set()))
    }

    # Preserve the best eligible observation for each unique system/resource pair.
    return sorted(found.values(), key=lambda o: (o.system_id, o.resource_id))


def discover_samples() -> dict[str, list[Observation]]:
    return {case["case_id"]: discover_case(case) for case in loaders.read_requests(samples=True)}
