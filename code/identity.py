"""Resolve request emails and collect the subject's as-of identifiers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

try:  # Support both ``python code/inspect_samples.py`` and package imports.
    from . import loaders
except ImportError:  # pragma: no cover - exercised by the standalone script
    import loaders


IDENTIFIER_FIELDS = {"email", "phone", "email_hash"}


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def _indexes(identities: Iterable[dict[str, str]], audit: Iterable[dict[str, str]]):
    by_email: dict[str, set[str]] = {}
    for row in identities:
        if row.get("email"):
            by_email.setdefault(normalize_email(row["email"]), set()).add(row["user_id"])
    for row in audit:
        if row.get("field_name", "").casefold() == "email":
            for value in (row.get("old_value", ""), row.get("new_value", "")):
                if value.strip():
                    by_email.setdefault(normalize_email(value), set()).add(row["user_id"])
    return by_email


def resolve_identity(
    email: str,
    audit_at: str,
    *,
    identities: list[dict[str, str]] | None = None,
    audit: list[dict[str, str]] | None = None,
) -> tuple[str, set[str]]:
    """Return (stable user_id, identifiers valid/current or historical by cutoff).

    The identifier set includes known current snapshot values only when their
    snapshot predates the cutoff, plus values in identity transitions no later
    than the cutoff. All three direct-identifier fields are represented.
    """
    identities = loaders.read_identities() if identities is None else identities
    audit = loaders.read_identity_audit() if audit is None else audit
    by_email = _indexes(identities, audit)
    candidates = by_email.get(normalize_email(email), set())
    if len(candidates) != 1:
        reason = "unmatched" if not candidates else "ambiguous"
        raise ValueError(f"Request email is {reason}: {email!r}")
    user_id = next(iter(candidates))
    cutoff = _time(audit_at)
    identifiers: set[str] = {email.strip()}

    for row in identities:
        if row["user_id"] != user_id or _time(row["updated_at"]) > cutoff:
            continue
        for field in IDENTIFIER_FIELDS:
            value = row.get(field, "").strip()
            if value:
                identifiers.add(value)

    # If the snapshot is newer than the cutoff, the earliest transition after
    # the cutoff supplies the value that remained in force at audit_at.
    future_first: dict[str, tuple[datetime, str]] = {}
    for row in audit:
        if row["user_id"] != user_id:
            continue
        field = row.get("field_name", "").casefold()
        event_time = _time(row["event_time"])
        old_value = row.get("old_value", "").strip()
        if field not in IDENTIFIER_FIELDS or event_time <= cutoff or not old_value:
            continue
        if field not in future_first or event_time < future_first[field][0]:
            future_first[field] = (event_time, old_value)
    identifiers.update(value for _, value in future_first.values())

    for row in audit:
        if row["user_id"] != user_id or _time(row["event_time"]) > cutoff:
            continue
        if row.get("field_name", "").casefold() not in IDENTIFIER_FIELDS:
            continue
        for key in ("old_value", "new_value"):
            value = row.get(key, "").strip()
            if value:
                identifiers.add(value)

    return user_id, identifiers
