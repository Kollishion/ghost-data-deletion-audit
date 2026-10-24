# Progress Handoff

## Status
- loaders: DONE
- identity: DONE
- discovery: IN PROGRESS (structured fields, cutoff-bounded activity graph, and system alias handling updated; subject-link and absence gaps remain)
- citation: DONE (sample rule measured; case_07 PDF and case_31 broad-snapshot selection mismatch remain)
- classifier: TODO (rules-only; not started)
- planner: TODO (not started per user instruction)
- serializer: TODO
- main.py: TODO (empty entry point)
- evaluate.py: TODO (evaluation entry point remains empty `code/evaluation/main.py`)
- full run: TODO
- PDF/image extraction: TODO (only manifest/filename review for case_07)
- reports: TODO
- packaging: TODO

## Latest metrics
- Identity resolution: 32/32 sample requests resolved to one stable `user_id` (2026-10-24 15:24 UTC).
- Sample status accuracy: NOT MEASURED (classifier not implemented).
- Discovery baseline: recall 81/111 = 73.0%; precision 81/86 = 94.2% (2026-10-24 15:24 UTC).
- Discovery step 1 structured extraction: recall 81/111 = 73.0%; precision 81/86 = 94.2% (2026-10-24 15:43 UTC).
- Discovery step 2 activity graph: recall 80/111 = 72.1%; precision 80/86 = 93.0% (2026-10-24 15:45 UTC).
- Discovery step 3 not-found audit: recall 80/111 = 72.1%; precision 80/86 = 93.0% (2026-10-24 15:46 UTC).
- Discovery step 4 extra-filter fix: recall 76/111 = 68.5%; precision 76/79 = 96.2% (2026-10-24 15:53 UTC).
- Discovery step 5 cutoff/citation review: recall 76/111 = 68.5%; precision 76/79 = 96.2% (2026-10-24 15:53 UTC).
- Citation rule: 73/75 = 97.3%; `case_07` and `case_31` mismatch (2026-10-24 15:47 UTC).

## Known failures
- Structured evidence has resource but its subject link was not extracted (13 pairs; `case_03`, `case_04`, `case_10`, `case_21`, `case_25`, `case_26`, `case_27`, `case_28`).
- Eligible activity names the resource but supplies no subject link or state evidence (12 pairs; `case_01` / `account_001`, `case_02` / `account_002`, `case_07` / `account_007`, `case_08` / `account_008`, `case_10` / `account_010`, `case_18` / `account_5521`, `case_20` / `account_5037`, `case_22` / `account_4990`, `case_29` / `account_7012`, `case_30` / `account_4163`, `case_31` / `account_4857`, `case_32` / `account_8858`).
- Evidence observation is only after cutoff (7 pairs; `case_09`, `case_23`, `case_24`, `case_29`, `case_30`). Earlier activity rows name account resources in `case_09` (`activity_3703`), `case_23` (`activity_3662`), `case_29` (`activity_3532`), and `case_30` (`activity_3465`); none carries a subject link. Audit-record resources have no earlier linking activity row: `audit_record_4902`, `audit_record_4128`, `audit_record_7095`, `audit_record_3954`, `audit_record_1707`.
- No occurrence in scanned participant evidence/activity (3 pairs; `case_04`, `case_18`, `case_20`). Checked non-image text for current/historical emails, phone, email hash, and stable user reference; `case_04` had no identifier hits, while `case_18`/`case_20` hits were user references/request emails in unrelated evidence, not links to the missing resources. No image filename/origin contained these identifiers or resource IDs, and no corresponding activity details were found.
- PDF-only discovery remains (1 pair; `case_07` / `support_001`; manifest identifies `evidence_58`, `delivery_correction_attachment.pdf`, origin `support_platform`, captured before cutoff).
- Remaining extra pairs (3): `case_07` / `object_19` is an explicit wrong-owner decoy (activity_4007 says user_07); `case_17` / `account_6523` is linked to the same user in evidence_67 but its March observation predates the August request; `case_17` / `tombstone_17` is an explicitly linked stable tombstone (activity_4011), a real retained resource omitted from the sample pair set.
- Citation mismatch: `case_31` / `account_4857` selected `evidence_54` because its filename/origin qualifies as an account snapshot. `evidence_51` was excluded as broad evidence because its filename/origin does not advertise the account system and it does not contain the resource string, despite `captured_at == audit_at`. The comparator cutoff uses `captured_at <= audit_at`; discovery also excludes observations after cutoff. Direct null-profile, 404, and `rows=0` observations are extracted; missing-row absence is not synthesized from a primary table with no row yet.

## Decisions made
- Keep `code/loaders.py` to avoid shadowing Python's stdlib `io`.
- Structured JSON/SQL records use known identity-link fields; log records parse key-value fields and correlate trace rows.
- Activity graph uses cutoff-eligible identity-bearing event details and linked resource IDs. Removed nearest-reported-time attribution because shared/unlinked worker events assigned resources across cases.
- Normalize `support_replica` to canonical `support_platform`.
- Preserve the report-only scope: classifier, planner, serializer, and main pipeline are untouched.

## How to run
- Main: `python code/main.py`
- Discovery comparator: `python code/compare_discovery.py`
- Citation comparator: `python code/evaluate_citations.py`
- Sample identity listing: `python code/inspect_samples.py`
- Evaluation entry point: `python code/evaluation/main.py`

## Next steps
1. Improve structured subject attribution for nullified profile/analytics rows and linked historical identifiers.
2. Add complete-primary-snapshot missing-row extraction and strengthen citation selection for `evidence_51`.
3. Inspect PDF/image evidence for `evidence_58`, rerun discovery/citation comparisons, then proceed to later pipeline stages only when authorized.


