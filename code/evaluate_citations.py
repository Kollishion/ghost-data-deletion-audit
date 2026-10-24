"""Evaluate sample evidence-ID selection rules against public expected IDs.

This module is evaluation-only; predictions must never import sample_output.csv.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

try:
    from . import loaders
    from .discovery import _dt, _snapshot_absence_observation
except ImportError:
    import loaders
    from discovery import _dt, _snapshot_absence_observation


DIRECT_EXTS = {".sql", ".json", ".log", ".txt"}
QUALITY = {".sql": 4, ".json": 4, ".log": 3, ".txt": 2}
SYSTEM_HINTS = {
    "account_service": ("customer_accounts", "customer_profiles", "account"),
    "analytics_platform": ("analytics",), "backup_service": ("backup",),
    "export_service": ("export",), "identity_service": ("identity", "tombstone"),
    "integration_service": ("connector", "integration", "data_flow"),
    "search_service": ("search",), "security_service": ("security", "audit"),
    "support_platform": ("support",), "cache_service": ("cache",),
    "email_delivery_service": ("email_delivery",), "marketing_platform": ("marketing",),
    "legal_service": ("legal",),
}


def _candidates(case: dict[str, str], system: str, resource: str):
    cutoff = _dt(case["audit_at"])
    rows = []
    for item in loaders.read_evidence_manifest():
        captured = _dt(item.get("captured_at", ""))
        if cutoff and captured and captured > cutoff:
            continue
        path = loaders.evidence_path(item["file_path"])
        if path.suffix.casefold() not in DIRECT_EXTS:
            continue
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        direct = resource in content
        # A complete system snapshot can prove absence after another source
        # associates the key; this is tested separately from direct evidence.
        name = (path.name + " " + item.get("origin", "")).casefold()
        scoped_absence = (not direct and path.suffix.casefold() == ".json" and
                          _snapshot_absence_observation(item, resource, system) is not None)
        broad = (not direct and (scoped_absence or
                 any(hint in name for hint in SYSTEM_HINTS.get(system, ()))))
        if not direct and not broad:
            continue
        observed = captured
        if direct:
            lines = [line for line in content.splitlines() if resource in line]
            stamps = []
            for line in lines:
                match = re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", line)
                if match:
                    stamp = _dt(match.group(0))
                    if stamp:
                        stamps.append(stamp)
            if stamps:
                observed = max(stamps)
                if cutoff and observed > cutoff:
                    continue
        origin = item.get("origin", "").casefold()
        if direct and path.suffix.casefold() == ".log":
            authority = 3 if "readback" in origin or "resource_lookup" in path.name else 1
        elif direct and path.suffix.casefold() == ".txt":
            authority = 3
        elif direct:
            authority = 5
        else:
            authority = 0
        rows.append({"file_id": item["file_id"], "captured": captured,
                     "observed": observed, "quality": QUALITY[path.suffix.casefold()],
                     "authority": authority, "direct": direct, "broad": broad})
    return rows


def _pick(candidates, tie: str, prefer_direct: bool):
    if not candidates:
        return ""
    direct = [c for c in candidates if c["direct"]]
    if direct:
        candidates = direct
    elif any(c["broad"] for c in candidates):
        candidates = [c for c in candidates if c["broad"]]
    if prefer_direct:
        authority = max(c["authority"] for c in candidates)
        candidates = [c for c in candidates if c["authority"] == authority]
    latest = max((c["observed"] or c["captured"]) for c in candidates)
    tied = [c for c in candidates if (c["observed"] or c["captured"]) == latest]
    reverse = tie == "largest"
    return sorted(tied, key=lambda c: c["file_id"], reverse=reverse)[0]["file_id"]


def main() -> None:
    requests = {r["case_id"]: r for r in loaders.read_requests(samples=True)}
    outputs = loaders.read_csv("sample_output.csv")
    manifest = {row["file_id"]: row for row in loaders.read_evidence_manifest()}
    rules = {
        "latest_direct_id_ascending_tie": ("smallest", False),
        "authoritative_direct_then_latest_ascending_tie": ("smallest", True),
        "authoritative_direct_then_latest_descending_tie": ("largest", True),
    }
    scores = Counter()
    denominators = Counter()
    per_case = defaultdict(lambda: {name: [0, 0] for name in rules})
    misses = defaultdict(list)
    total_evidence_steps = 0
    non_file_citations = Counter()
    findings = 0
    finding_file_ids = 0
    ineligible_expected = []
    excluded_formats = []

    for output in outputs:
        case_id = output["case_id"]
        case = requests[case_id]
        for step in json.loads(output["steps_json"]):
            expected = step["evidence_id"]
            if not expected:
                continue
            if step["phase"] == "FINDING":
                findings += 1
                finding_file_ids += expected.startswith("evidence_")
            total_evidence_steps += 1
            if not expected.startswith("evidence_"):
                non_file_citations[expected] += 1
            elif expected in manifest:
                meta = manifest[expected]
                captured = _dt(meta.get("captured_at", ""))
                cutoff = _dt(case["audit_at"])
                if captured and cutoff and captured > cutoff:
                    ineligible_expected.append((case_id, step["resource_id"], expected,
                                                meta["captured_at"], case["audit_at"]))
                ext = meta["file_path"].rsplit(".", 1)[-1].casefold()
                if f".{ext}" not in DIRECT_EXTS:
                    excluded_formats.append((case_id, step["resource_id"], expected, ext))
            candidates = _candidates(case, step["system_id"], step["resource_id"])
            for name, (tie, authority) in rules.items():
                chosen = _pick(candidates, tie, authority)
                per_case[case_id][name][1] += 1
                denominators[name] += 1
                if chosen == expected:
                    per_case[case_id][name][0] += 1
                    scores[name] += 1
                else:
                    misses[name].append((case_id, step["resource_id"], expected, chosen,
                                         len(candidates)))

    for case_id in sorted(requests):
        summary = " ".join(
            f"{name}={per_case[case_id][name][0]}/{per_case[case_id][name][1]}"
            for name in rules
        )
        print(f"{case_id}: {summary}")
    print(f"Evidence-bearing steps: {total_evidence_steps}; non-file expected IDs: {dict(non_file_citations)}")
    print(f"Finding citations: {finding_file_ids}/{findings} use evidence-file IDs; "
          f"activity_id/audit_id expected uses={dict(non_file_citations)}")
    print(f"Expected citations after audit_at: {ineligible_expected}")
    print(f"Expected citations in excluded formats: {excluded_formats}")
    for name in rules:
        denominator = denominators[name]
        print(f"{name}: {scores[name]}/{denominator} = "
              f"{scores[name] / denominator if denominator else 1.0:.3f}")
        for case_id, resource, expected, chosen, count in misses[name]:
            print(f"  miss {case_id} {resource}: expected={expected} chosen={chosen or '<none>'} candidates={count}")


if __name__ == "__main__":
    main()
