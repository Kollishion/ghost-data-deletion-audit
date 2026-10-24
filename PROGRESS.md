# Progress Handoff

## Status
- loaders: DONE
- identity: DONE
- discovery: IN PROGRESS (sample recall 73%; PDF/image and subject-link gaps remain)
- citation: DONE (candidate citation rules measured; 2/75 expected IDs unmatched)
- classifier: TODO (keep rules-only unless sample evaluation shows failure)
- planner: TODO
- serializer: TODO
- main.py: TODO (empty entry point)
- evaluate.py: TODO (evaluation entry point is currently empty `code/evaluation/main.py`)
- full run: TODO
- PDF/image extraction: TODO
- reports: TODO
- packaging: TODO

## Latest metrics
- Identity resolution: 32/32 sample requests resolved to one stable `user_id`; no unresolved or ambiguous cases (2026-10-24 15:24 UTC).
- Sample status accuracy: NOT MEASURED (classifier not implemented).
- Discovery: recall 81/111 = 73.0%; precision 81/86 = 94.2% (2026-10-24 15:24 UTC).
- Citation rule: best measured match 73/75 = 97.3%; same across tested rules (2026-10-24 15:24 UTC).

## Known failures
- Eligible text evidence contains resource but identity link was not extracted (12 resources; `case_03`, `case_04`, `case_21`, `case_25`, `case_26`, `case_27`, `case_28`).
- Activity names resource without subject link or text state (7 resources; `case_18`, `case_20`, `case_22`, `case_29`, `case_30`, `case_31`, `case_32`).
- Evidence only appears after `audit_at` (7 resources; `case_09`, `case_23`, `case_24`, `case_29`, `case_30`).
- Resource expected only in PDF evidence (1 resource; `case_07`, `support_001`, expected `evidence_58`).
- No occurrence found in scanned text/activity (3 resources; `case_04`, `case_18`, `case_20`).
- Discovery extras: 5 pairs across `case_07`, `case_17`, `case_18`, `case_20` (see comparator report).
- Citation mismatches: `case_07` / `support_001` expected `evidence_58` (PDF excluded); `case_31` / `account_4857` expected `evidence_51`, selected `evidence_54`.

## Decisions made
- Use `code/loaders.py` rather than `io.py` to avoid shadowing Python's stdlib `io`.
- Classifier remains rules-only unless demonstrated inadequate.
- Discovery scan so far excludes PDFs/images; resource discovery comparator reasons are heuristic explanations, not proof that a missed resource was impossible to find.

## How to run
- Main: `python code/main.py`
- Discovery comparator: `python code/compare_discovery.py`
- Citation comparator: `python code/evaluate_citations.py`
- Sample identity listing: `python code/inspect_samples.py`
- Evaluation entry point (currently empty): `python code/evaluation/main.py`

## Next steps
1. Extract PDF/image evidence and rerun identity-linked discovery; review all 30 misses and 5 extras.
2. Refine direct evidence/citation selection for PDF `evidence_58` and the `case_31` competing observations.
3. Implement classifier, planner, serializer, then main/evaluate entry points and produce sample/full-run reports.
