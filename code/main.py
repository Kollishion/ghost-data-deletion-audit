"""Run the deletion audit over the evaluation requests and write output.csv."""

from __future__ import annotations

import logging
import os
import re

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


def _fallback_findings(observations: list[object]) -> list[dict[str, object]]:
    """Return any safely constructible findings when normal planning fails."""
    try:
        from .policy import evaluate_all
        from .planner import _step
        from .planner import OPERATION_RANK
    except ImportError:
        from policy import evaluate_all
        from planner import OPERATION_RANK, _step
    try:
        decisions = evaluate_all(observations)
    except Exception:
        return []
    findings = []
    for item in decisions:
        if item.finding_operation:
            obs = item.observation
            findings.append(_step("FINDING", obs.system_id, obs.resource_id,
                                  item.finding_operation, item.finding_state or "",
                                  getattr(obs, "evidence_id", "")))
    findings.sort(key=lambda step: (OPERATION_RANK[step["operation"]],
                                    step["system_id"], step["resource_id"]))
    for number, step in enumerate(findings, 1):
        step["step_no"] = number
    return findings


def run_requests(requests: list[dict[str, str]], *, graph_iterations: int = 0) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for case in requests:
        case_id = case.get("case_id", "<missing>")
        observations = []
        try:
            intent = classify_request(case.get("request_text", ""))
            if intent != AUTHORIZED:
                status, steps = "NOT_APPLICABLE", []
            else:
                observations = discover_case(case, graph_iterations=graph_iterations)
                status, steps = build_plan(observations)
            steps_json = serialize_case(status, steps)
        except Exception as exc:  # keep a single malformed case from aborting the run
            # Exception strings can contain user or evidence data; log a sanitized,
            # bounded message alongside the case identifier and exception type.
            message = re.sub(r"[\w.+-]+@[\w.-]+", "[redacted-email]", str(exc))
            message = re.sub(r"\b(?:\+?\d[\d ()-]{7,}\d)\b", "[redacted-phone]", message)[:240]
            message = re.sub(
                r"(?i)(api[_-]?key|access[_-]?token|secret|bearer)\s*[:=]\s*\S+",
                r"\1=[redacted]", message,
            )
            LOGGER.error("case_id=%s error=%s: %s", case_id, type(exc).__name__, message)
            try:
                steps = _fallback_findings(observations)
            except Exception:
                steps = []
            status = "INCOMPLETE"
            try:
                steps_json = serialize_case(status, steps)
            except Exception as fallback_exc:
                LOGGER.error("case_id=%s fallback_error=%s", case_id, type(fallback_exc).__name__)
                steps_json = "[]"
        output.append({
            "case_id": case_id,
            "deletion_status": status,
            "steps_json": steps_json,
        })
    return output


def main() -> None:
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(loaders.REPO_ROOT / "run.log", encoding="utf-8")],
        force=True,
    )
    rows = run_requests(loaders.read_requests(), graph_iterations=1)
    output_path = loaders.REPO_ROOT / "output.csv"
    temp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        write_output(rows, temp_path)
        # Publish only a complete CSV. Validation runs after this atomic replace;
        # a validation failure therefore leaves the complete output available.
        os.replace(temp_path, output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    from collections import Counter
    print(f"rows={len(rows)} status_counts={dict(sorted(Counter(r['deletion_status'] for r in rows).items()))}")
    try:
        from .validate_output import validate_report
    except ImportError:
        from validate_output import validate_report
    errors, warnings = validate_report(output_path)
    if warnings:
        case_ids = [warning.split(":", 1)[0] for warning in warnings]
        print(f"validation_warning=incomplete_without_finding count={len(warnings)} case_ids={case_ids}")
    if errors:
        for error in errors[:30]:
            print(f"validation_error: {error}")
        raise SystemExit(f"output validation failed ({len(errors)} errors)")
    print(f"validation=PASS rows={len(rows)} warnings={len(warnings)}")


if __name__ == "__main__":
    main()
