"""Output schema and deterministic CSV/JSON serialization."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


HEADER = ["case_id", "deletion_status", "steps_json"]
STEP_FIELDS = ["step_no", "phase", "system_id", "resource_id",
               "operation", "state", "evidence_id"]


def serialize_case(status: str, steps: list[dict[str, Any]]) -> str:
    if status == "NOT_APPLICABLE":
        if steps:
            raise ValueError("NOT_APPLICABLE rows must have no steps")
        return "[]"
    if status not in {"COMPLETE", "INCOMPLETE"}:
        raise ValueError(f"Invalid deletion status: {status}")
    for number, step in enumerate(steps, 1):
        if list(step) != STEP_FIELDS:
            step = {key: step[key] for key in STEP_FIELDS}
            steps[number - 1] = step
        if step["step_no"] != number:
            raise ValueError("Step numbers must be consecutive")
    return json.dumps(steps, ensure_ascii=False, separators=(",", ":"))


def write_output(rows: Iterable[dict[str, str]], path: Path) -> None:
    ordered = sorted(rows, key=lambda row: row["case_id"])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ordered)
