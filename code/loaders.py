"""Participant-facing dataset readers, with paths rooted at the repository."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "dataset"


def read_csv(name: str) -> list[dict[str, str]]:
    """Read a CSV below dataset/ as UTF-8 and return its rows as dictionaries."""
    path = DATASET_DIR / name
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_requests(*, samples: bool = False) -> list[dict[str, str]]:
    return read_csv("sample_deletion_requests.csv" if samples else "deletion_requests.csv")


def read_identities() -> list[dict[str, str]]:
    return read_csv("user_identities.csv")


def read_identity_audit() -> list[dict[str, str]]:
    return read_csv("user_audit_log.csv")


def read_activity() -> list[dict[str, str]]:
    return read_csv("system_activity.csv")


def read_deletion_rules() -> list[dict[str, str]]:
    return read_csv("deletion_rules.csv")


def read_evidence_manifest() -> list[dict[str, str]]:
    return read_csv("evidence_files.csv")


def evidence_path(relative_path: str) -> Path:
    """Resolve a manifest path relative to dataset/, without allowing escape."""
    path = (DATASET_DIR / relative_path).resolve()
    if not path.is_relative_to(DATASET_DIR.resolve()):
        raise ValueError(f"Evidence path escapes dataset/: {relative_path!r}")
    return path


def read_json(path: Path) -> Any:
    import json

    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)
