# Progress Handoff

## Status

- Request classifier: DONE; deterministic rules use request text only.
- Identity resolution: DONE for current and historical identifier values.
- Discovery: PARTIAL; state observations are cutoff-bounded, evidence links retain field-level provenance, pre-request activity is excluded, linked resource references are separated from the source record's state, and one-hop evidence graph expansion is enabled.
- Policy mapping: DONE for the participant-facing deletion rules; explicit evidence record categories override resource ID prefixes.
- Planner, serializer, evaluator, and validator: DONE. The main entry point catches per-case errors, atomically writes the complete output, and validates it after publication.
- Full run: 518 rows; INCOMPLETE-without-FINDING is a warning and does not fail an otherwise valid run.

## Current metrics

- Classifier fixtures: 48/48 passed across English, Portuguese, Spanish, French, Japanese, and Korean.
- Classifier over 518 requests: 508 AUTHORIZED, 10 NOT_APPLICABLE, 0 UNCERTAIN. Public samples: 0/32 NOT_APPLICABLE.
- Baseline before this audit: status accuracy 29/32 (90.625%); with step_no P/R/F1 50.980% / 40.415% / 45.087%; without step_no (multiset) 94.118% / 74.611% / 83.237%; renumbered sequence 6/32 (18.750%).
- Current sample: status accuracy 29/32 (90.625%); with step_no P/R/F1 58.278% / 45.596% / 51.163%; without step_no P/R/F1 99.338% / 77.720% / 87.209%; renumbered sequence 8/32 (25.000%); aligned field accuracy 988/1050 (94.095%).
- Iterative graph resource score (expected resource set: 111):

| Graph iterations | Precision | Recall | Matched / predicted |
|---:|---:|---:|---:|
| 0 | 98.684% | 67.568% | 75 / 76 |
| 1 | 98.701% | 68.468% | 76 / 77 |
| 2 | 98.701% | 68.468% | 76 / 77 |

  Status accuracy stayed 29/32 at every iteration and precision stayed above 90%; production uses one iteration.
- Full output: 518 rows; COMPLETE 141, INCOMPLETE 367, NOT_APPLICABLE 10; validation PASS with 16 warnings and zero hard errors. Plain string case_id sort: first `case_100`–`case_104`; last `case_95`–`case_99`.
- Activity-backed absence experiment: no rule added. Before/after sample status accuracy 29/32 (90.625%); without-step_no precision 99.338%, recall 77.720%; no predictions/correct cases changed. Full status counts remain COMPLETE 141, INCOMPLETE 367, NOT_APPLICABLE 10; all 16 no-finding warnings remain.

Expected-step evidence audit: zero sample VERIFY_* steps cite `activity_` or `audit_` evidence IDs. The four expected verification steps in cases 01, 02, and 04 cite direct evidence files evidence_54/evidence_56. Related activity is not a consistent user-linked pattern: account_001 has DELETE_RECORD/SUCCESS, account_002 has DELETE_RECORD/PARTIAL, account_004 has no corresponding activity row, and analytics_901 has ANONYMIZE_RECORD/SUCCESS. None has a LINK_RESOURCE_IDENTITY event tying that resource to the case user. Therefore no activity-derived absence is grounded; partial/failed activity is not treated as absence.

## Guardrail results (2026-10-25)

- Validator coverage: exact header and request IDs/count/order, status and JSON schema, required seven fields and types, allowed phase/operation/state triples, sorting and duplicate keys, consecutive numbering, phase-specific evidence rules, evidence ID existence/cutoff, and status consistency.
- Current validator result: PASS with 16 warnings and zero hard errors. The warnings identify `case_33`, `case_35`, `case_39`, `case_416`, `case_417`, `case_45`, `case_46`, `case_50`, `case_517`, `case_519`, `case_52`, `case_521`, `case_53`, `case_55`, `case_61`, and `case_63`, which are INCOMPLETE without findings. Warning-only output exits zero; every other validator condition remains a hard error.
- Per-case fallback: implemented with sanitized `case_id`/error logging to root `run.log`; no cases required fallback in the latest run.
- Determinism: the previous two-run hash comparison passed (`f9df457a4827c4115e5f9fb8b9f4dfbf56f5f5ef58749f040bf5f1b042982cea`). The previous run's nonzero exit codes reflected the now-downgraded warnings and are superseded; determinism was not rerun for this validator-only change.
- Offline scan: source has no localhost:11434, urllib, HTTP client, Ollama client, or network calls. `requests` matches are local request-list variable names.
- Submission hygiene: PASS; curated code.zip set has 23 files, excludes dataset/env/cache/output-backup artifacts, and includes `README.md`; no API-key/token pattern found.

## INCOMPLETE cases without findings

Eligible evidence mentions use exact identifier matching and `captured_at <= audit_at`; activity counts use events between `requested_at` and `audit_at`. Visual counts are eligible PDF/image entries in the manifest only: the manifest has no subject attribution, and none of these identifiers appears in visual paths/origin fields. Reported workflow status is listed for context, never used as proof.

- `case_33`: reported COMPLETE; user_18; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 8, user link unavailable; discovered export_1842 only as an activity claim, which supplies no state.
- `case_35`: reported NOT_STARTED; user_13; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 10, user link unavailable; discovered search_428 only as an activity claim, which supplies no state.
- `case_39`: reported COMPLETE; user_14; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 9, user link unavailable; discovered data_flow_1121 only as an activity claim, which supplies no state.
- `case_416`: reported COMPLETE; user_414; evidence mentions 1 log; activity 0; eligible visual files 2, user link unavailable; the log mentions the identifier on a line without a resource_id.
- `case_417`: reported NOT_STARTED; user_415; evidence mentions 1 log; activity 0; eligible visual files 2, user link unavailable; the log mentions the identifier on a search-query line without a resource_id.
- `case_45`: reported COMPLETE; user_03; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 12, user link unavailable; discovered audit_record_003 only as an activity claim, which supplies no state.
- `case_46`: reported COMPLETE; user_17; evidence mentions 1 log; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 2, user link unavailable; account_6523 is explicitly ABSENT (compliant), while tombstone_17 is only an activity claim, so no violation is grounded.
- `case_50`: reported NOT_STARTED; user_20; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 7, user link unavailable; discovered analytics_7438 only as an activity claim, which supplies no state.
- `case_517`: reported PARTIALLY_COMPLETE; user_515; evidence mentions 1 log; activity 0; eligible visual files 0; the identifier is on an operations-stream line without a resource_id.
- `case_519`: reported PARTIALLY_COMPLETE; user_517; evidence mentions 1 log; activity 0; eligible visual files 0; the identifier is on an audit-query line without a resource_id.
- `case_52`: reported COMPLETE; user_18; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 6, user link unavailable; discovered export_1260 only as an activity claim, which supplies no state.
- `case_521`: reported COMPLETE; user_519; evidence mentions 1 log; activity 0; eligible visual files 0; the identifier is on an audit-query line without a resource_id.
- `case_53`: reported COMPLETE; user_22; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 4, user link unavailable; discovered support_1034 only as an activity claim, which supplies no state.
- `case_55`: reported NOT_STARTED; user_16; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 3, user link unavailable; discovered backup_9287 only as an activity claim, which supplies no state.
- `case_61`: reported PARTIALLY_COMPLETE; user_07; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 1, user link unavailable; discovered object_19 only as an activity claim, which supplies no state.
- `case_63`: reported NOT_STARTED; user_09; evidence mentions none; activity 1 LINK_RESOURCE_IDENTITY; eligible visual files 14, user link unavailable; discovered marketing_001 only as an activity claim, which supplies no state.

Grouped causes: 10 activity-only resource nominations (cases 33, 35, 39, 45, 50, 52, 53, 55, 61, 63); 5 identity mentions in log lines without a same-line resource_id (cases 416, 417, 517, 519, 521); 1 compliant ABSENT observation plus activity-only tombstone (case 46). No finding is inferred from reported_status or an unlinked visual manifest entry.

## Independent custom regression cases (2026-10-25)

- Added `evaluation/custom_cases/` with fictional CSV, JSON, and SQL fixtures for failover replica drift, active sync plus search-index residue, support redaction with a retained audit record, a similar-email decoy, restore risk, cutoff-after and exact-cutoff observations, and a marketing-only opt-out.
- Added `code/evaluation/run_custom_cases.py`; its expected status and steps are declared in code independently of the pipeline output. It swaps the loader's dataset root only for the duration of the run and clears evidence caches before and after.
- Result: 8/8 custom cases PASS. No pipeline behavior changes were needed. Exact-boundary evidence is included; post-cutoff evidence is ignored; the decoy is not attributed to the requesting user; retained audit data is verified without deletion; marketing-only request returns NOT_APPLICABLE with no steps.

## Policy category audit

| Category | Policy output for a violating/present record | Sample coverage |
|---|---|---|
| USER_PROFILE | REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | Yes |
| SECONDARY_IDENTIFIER | REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | No |
| SEARCH_INDEX_ENTRY | REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | Yes |
| CACHE_ENTRY | REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | No |
| SUPPORT_MESSAGE | REPORT_EXPOSED_PII / REDACT_RECORD / VERIFY_RECORD_REDACTED; already redacted records get verification only | Yes |
| SUPPORT_ATTACHMENT | REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT when evidence links the attachment only to the subject | Yes (case_13) |
| ANALYTICS_PROFILE | REPORT_EXPOSED_PII / ANONYMIZE_RECORD / VERIFY_RECORD_ANONYMIZED; anonymized records get verification only | Yes |
| PRODUCT_TELEMETRY | REPORT_EXPOSED_PII / ANONYMIZE_RECORD / VERIFY_RECORD_ANONYMIZED; anonymized records get verification only | No |
| USER_EXPORT | REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | Yes |
| MARKETING_PROFILE | REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | Yes (case_12) |
| EMAIL_DELIVERY_LOG | REPORT_EXPOSED_PII / REDACT_RECORD / VERIFY_RECORD_REDACTED; redacted records get verification only | No |
| SECURITY_AUDIT_LOG | RETAINED: VERIFY_RECORD_PRESENT; expired: REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | Yes |
| LEGAL_HOLD_RECORD | Active: VERIFY_RECORD_PRESENT; released/expired: REPORT_REMAINING_RECORD / DELETE_RECORD / VERIFY_RECORD_ABSENT | No |
| BACKUP_ARCHIVE | Unblocked restore: REPORT_RESTORE_RISK / BLOCK_RESTORE / VERIFY_RESTORE_BLOCKED; blocked: verification only | Yes |
| ACCOUNT_TOMBSTONE | REPORT_EXPOSED_PII / REDACT_RECORD / VERIFY_RECORD_REDACTED; compliant tombstones get verification only | Yes |

DATA_FLOW is an operational category outside deletion_rules.csv: active flows emit REPORT_ACTIVE_DATA_FLOW / DISABLE_DATA_FLOW / VERIFY_DATA_FLOW_DISABLED; disabled flows get verification only.

The case_13 row in evidence_03 explicitly says SUPPORT_ATTACHMENT, is linked to the request subject, and is present. Category now comes from that record field rather than the support_ prefix, so rule_06 deletes it. The case_10 trace identifies source=legacy_contact_index and an email lookup_key; it is classified as SEARCH_INDEX_ENTRY and deleted rather than treated as a shared support conversation. Case_12's contact lookup with explicit email_opt_in=true remains MARKETING_PROFILE under rule_10.

## Observation audit for the eight previously extra steps

The old eight extra steps were two case_06 account steps, three case_10 support steps, and three case_13 support steps. Their expected steps and eligible evidence show why:

- case_06 audit_at 2026-09-10T09:15:00Z: expected account_006 step is VERIFY_RECORD_ABSENT. evidence_57 at 2026-09-09T22:12:00Z says the separate resource search_001 has source_resource_id=account_006; that does not establish account_006 as PRESENT. evidence_54's 2026-09-02T23:00:00Z account primary and failover snapshot tables both omit account_006, yielding the eligible ABSENT observation. activity_3545 at 2026-08-30T17:08:20Z reports deletion success, but is only a claim. The graph now links account_006 and uses the snapshot absence; the false account finding/remediation are gone.
- case_10 audit_at 2026-09-18T12:25:00Z: expected support_002 steps are REPORT_REMAINING_RECORD (evidence_61), DELETE_RECORD, and VERIFY_RECORD_ABSENT. activity_3596 at 2026-09-02T10:09:01Z reports success. Later eligible evidence_61 records rows=1 at 2026-09-17T22:00:05Z and marker_found=false at 2026-09-17T22:00:06Z, with last_write=2026-09-07T10:01:00Z. No eligible primary/replica snapshot conflicts with it. The later observation supports PRESENT and the expected delete plan.
- case_13 audit_at 2026-10-01T12:00:00Z: expected support_4218 steps are REPORT_REMAINING_RECORD (evidence_03), DELETE_RECORD, and VERIFY_RECORD_ABSENT. evidence_03 is captured exactly at audit_at and says SUPPORT_ATTACHMENT | FOUND | noor-khalil@proton.me. Earlier activity_3752 at 2026-09-09T12:39:20Z reports failure; it does not conflict with the later direct observation. No other eligible observation or replica snapshot for support_4218 was found.

The policy/category fixes and resource/state separation remove all eight prior extra steps; the remaining single predicted-only step is case_17's VERIFY_RECORD_ABSENT for account_6523, supported by evidence_51 but omitted by the sample.

## Remaining mismatches grouped by end-to-end effect

- Status (3 cases): cases 01, 02, and 04 remain INCOMPLETE instead of COMPLETE. Their expected account IDs are not grounded to those request subjects in eligible evidence or linked records; activity rows only name the account resources and cannot establish identity/state.
- Discovery recall (37 expected steps affected): one-hop graph adds account_006 but does not find the remaining sample resources without an eligible identity/reference path. Missing links include the anonymized analytics rows in cases 03, 04, and 26–28, as well as account records with no subject reference. Case_07's support attachment is in a PDF not currently extracted. The graph did not join by case/resource numbering or row order.
- Remaining policy/coverage mismatches (6 expected steps affected): principally sample verification resources not surfaced through eligible direct evidence; case_10 still lacks expected account_010 verification.
- Extra steps: one compliant account_6523 absence verification in case_17 is omitted by the sample.

## Next steps

1. Add PDF/image extraction and link content through identifiers before broadening graph joins.
2. Investigate the remaining missing resources only where participant-facing evidence provides a grounded path.
3. Re-run sample evaluation, full generation, and validation after future pipeline changes.

## Commands

- Full run: python code/main.py
- Output validation: python code/validate_output.py
- Sample evaluation: python code/evaluation/evaluate.py --graph-iterations 1
- Graph comparison: run the evaluator with --graph-iterations 0, 1, and 2.
- Classifier checks: python code/evaluation/evaluate_classifier.py
