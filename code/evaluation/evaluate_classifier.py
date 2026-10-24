"""Run independent classifier fixtures and participant-request contract checks."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

import loaders
from request_classifier import AUTHORIZED, NOT_APPLICABLE, UNCERTAIN, classify_request


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    fixtures_path = Path(__file__).with_name("classifier_fixtures.json")
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    fixture_failures = [
        (item["language"], item["text"], item["expected"],
         classify_request(item["text"]))
        for item in fixtures
        if classify_request(item["text"]) != item["expected"]
    ]

    requests = loaders.read_requests()
    results = [(row["case_id"], classify_request(row["request_text"])) for row in requests]
    status_counts = Counter(label for _, label in results)
    sample_results = [classify_request(row["request_text"])
                      for row in loaders.read_requests(samples=True)]
    uncertain = [case_id for case_id, label in results if label == UNCERTAIN]
    not_applicable = [case_id for case_id, label in results if label == NOT_APPLICABLE]

    print(f"fixtures={len(fixtures)} fixture_failures={len(fixture_failures)}")
    for language, text, expected, actual in fixture_failures:
        safe_text = text.encode("ascii", "backslashreplace").decode("ascii")
        print(f"fixture_mismatch language={language} expected={expected} actual={actual} text={safe_text}")
    print(f"evaluation_requests={len(requests)} status_counts={dict(sorted(status_counts.items()))}")
    print(f"sample_requests=32 sample_not_applicable={sample_results.count(NOT_APPLICABLE)}")
    print(f"full_not_applicable_exactly_ten={status_counts[NOT_APPLICABLE] == 10}")
    print(f"not_applicable_case_ids={not_applicable}")
    print(f"borderline_uncertain_count={len(uncertain)} borderline_case_ids={uncertain[:25]}")
    if fixture_failures or NOT_APPLICABLE in sample_results or status_counts[NOT_APPLICABLE] != 10:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
