"""Compare discovered resource pairs with the public sample answer pairs."""

from __future__ import annotations

import json
from datetime import datetime

try:
    from . import loaders
    from .discovery import discover_samples
except ImportError:
    import loaders
    from discovery import discover_samples


def main() -> None:
    expected_rows = {r["case_id"]: r for r in loaders.read_csv("sample_output.csv")}
    requests = {r["case_id"]: r for r in loaders.read_requests(samples=True)}
    manifest = loaders.read_evidence_manifest()
    activity = loaders.read_activity()
    actual = discover_samples()
    total_tp = total_fp = total_fn = 0
    for case_id in sorted(expected_rows):
        expected_steps = json.loads(expected_rows[case_id]["steps_json"])
        expected = {(s["system_id"], s["resource_id"]) for s in expected_steps}
        predicted = {(o.system_id, o.resource_id) for o in actual.get(case_id, [])}
        tp = len(expected & predicted)
        fp, fn = len(predicted - expected), len(expected - predicted)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        recall = tp / len(expected) if expected else 1.0
        precision = tp / len(predicted) if predicted else (1.0 if not expected else 0.0)
        misses = sorted(expected - predicted)
        extras = sorted(predicted - expected)
        print(f"{case_id}: recall={recall:.3f} precision={precision:.3f} "
              f"expected={len(expected)} discovered={len(predicted)} "
              f"misses={misses} extras={extras}")
        cutoff = datetime.fromisoformat(requests[case_id]["audit_at"].replace("Z", "+00:00"))
        for system, resource in misses:
            eligible_hits, later_hits = [], []
            for item in manifest:
                path = loaders.evidence_path(item["file_path"])
                if path.suffix.casefold() in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8-sig", errors="replace")
                except OSError:
                    continue
                if resource not in text:
                    continue
                captured = datetime.fromisoformat(item["captured_at"].replace("Z", "+00:00"))
                (eligible_hits if captured <= cutoff else later_hits).append(item["file_id"])
            claims = [r for r in activity if r["resource_id"] == resource and
                      r["target_system"] == system and
                      datetime.fromisoformat(r["event_time"].replace("Z", "+00:00")) <= cutoff]
            if eligible_hits:
                reason = f"resource occurs in eligible non-PDF/image evidence {eligible_hits}, but no row/trace-local subject link was extracted"
            elif claims:
                suffix = (f"; direct evidence is only post-cutoff {later_hits}" if later_hits else
                          "; no text-format state/identity record")
                reason = f"time-eligible activity claim(s) {','.join(r['activity_id'] for r in claims)} name this resource without a subject link{suffix}"
            elif later_hits:
                reason = f"resource occurs only in post-cutoff non-PDF/image evidence {later_hits}"
            else:
                reason = "no resource occurrence in scanned non-PDF/image evidence or eligible activity"
            print(f"  MISS REASON {resource}: {reason}")
    micro_recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 1.0
    micro_precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 1.0
    print(f"MICRO: recall={micro_recall:.3f} precision={micro_precision:.3f} "
          f"tp={total_tp} fp={total_fp} fn={total_fn}")


if __name__ == "__main__":
    main()
