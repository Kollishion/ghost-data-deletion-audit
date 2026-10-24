"""Run the deletion audit over the evaluation requests and write output.csv."""

from __future__ import annotations

import logging

try:
    from . import loaders
    from .discovery import discover_case
    from .planner import build_plan
    from .request_classifier import AUTHORIZED, classify_request
    from .serializer import serialize_case, write_output
except ImportError:
    import loaders
    from discovery import discover_case
    from planner import build_plan
    from request_classifier import AUTHORIZED, classify_request
    from serializer import serialize_case, write_output


LOGGER = logging.getLogger("deletion_audit")


def run_requests(requests: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for case in requests:
        case_id = case.get("case_id", "<missing>")
        observations = []
        try:
            intent = classify_request(case.get("request_text", ""))
            if intent != AUTHORIZED:
                status, steps = "NOT_APPLICABLE", []
            else:
                observations = discover_case(case)
                status, steps = build_plan(observations)
            steps_json = serialize_case(status, steps)
        except Exception as exc:  # keep a single malformed case from aborting the run
            LOGGER.error("case_id=%s failed with %s", case_id, type(exc).__name__)
            status, steps = build_plan(observations)
            if status == "COMPLETE":
                status = "INCOMPLETE"
                steps = []
            steps_json = serialize_case(status, steps)
        output.append({
            "case_id": case_id,
            "deletion_status": status,
            "steps_json": steps_json,
        })
    return output


def main() -> None:
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    rows = run_requests(loaders.read_requests())
    write_output(rows, loaders.REPO_ROOT / "output.csv")
    from collections import Counter
    print(f"rows={len(rows)} status_counts={dict(sorted(Counter(r['deletion_status'] for r in rows).items()))}")


if __name__ == "__main__":
    main()
