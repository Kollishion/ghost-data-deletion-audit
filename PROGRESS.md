# Progress Handoff

## Status

- Loaders and identity resolution: DONE
- Discovery: IN PROGRESS; now chooses the latest eligible direct state, handles equal-time explicit absence, adds absence observations from scoped empty snapshots for already linked resources, and removes resources explicitly owned by another user.
- Request classifier: DONE; deterministic rules only, request text is the only classifier input
- Policy: DONE; activity claims remain unresolved and cannot create findings
- Planner and serializer: DONE
- Main full-dataset run: DONE; output.csv has 518 sorted rows
- Sample evaluator and output validator: DONE

## Metrics

- Classifier fixtures: 48/48 passed across English, Portuguese, Spanish, French, Japanese, and Korean.
- Classifier over 518 requests: 508 AUTHORIZED, 10 NOT_APPLICABLE, 0 UNCERTAIN; the ten NOT_APPLICABLE requests are case_533 through case_542.
- Public sample classifier check: 0/32 NOT_APPLICABLE.
- Sample status accuracy: 29/32 = 90.625% (baseline 24/32 = 75.000%).
- Sample sequence accuracy: 5/32 = 15.625%; unchanged after fixes 1–3.
- Final sample exact-step precision/recall/F1: 47.742% / 38.342% / 42.529%.
- Final aligned field accuracy: 920/987 = 93.212%.
- Full output validation: PASS, 518 rows; COMPLETE 141, INCOMPLETE 367, NOT_APPLICABLE 10.
- Updated sample scoring: status accuracy 29/32 (90.625%); with step_no precision/recall/F1 50.323% / 40.415% / 44.828%; ignoring step_no (multiset) 92.903% / 74.611% / 82.759%; renumbered sequence accuracy 6/32 (18.750%).
- Updated aligned field accuracy: 942/1008 (93.452%). The new multiset scorer reports 8 extra steps from grounded policy violations omitted by the sample set, 2 pre-request activity-claim verification steps, and 1 already-compliant absence verification omitted by the sample. No surviving extras link explicitly to another owner; no duplicate resource appears under multiple system IDs.
- Case 12 classification now uses the record's own `contact_lookup_completed` event and `email_opt_in=true` fields to classify it as a marketing contact record (rule_10, DELETE), not by its `analytics_` resource prefix. This changes the predicted action to REPORT_REMAINING_RECORD / DELETE_RECORD and raises sample exact-step F1 from 42.529% to 44.828%.

## Remaining mismatches grouped by effect

- Status (3 cases): cases 01, 02, and 04 remain INCOMPLETE instead of COMPLETE. No participant evidence links their account resource IDs to the request subjects; the available DELETE_RECORD activity rows are unlinked claims. The empty account snapshot therefore cannot be attached to those per-user resources without an unsupported inference.
- Sequence / discovery (37 expected steps affected): account and analytics resources remain undiscovered in cases 01–04 and 26–28, leaving missing verification steps. In case 03, account_7566 is now correctly ABSENT from the 404/rows=0 completion observation, but analytics_9406 is still undiscovered.
- Case 12: analytics_9914 is attributable through a correlation key matching the user's email hash. Its own `contact_lookup_completed` and `email_opt_in=true` fields establish a marketing contact record, so rule_10 requires DELETE; this now matches the sample's REPORT_REMAINING_RECORD / DELETE_RECORD.
- Remaining sample extra-step causes under the six-field multiset score: 8 evidence-backed violations in sample cases that the expected set omits; 2 verification-only resources named by identity-bearing activity before requested_at; 1 compliant ABSENT observation with a verification step omitted by the expected set. Those observations do not justify suppressing a policy violation or treating old activity claims as current state. No ownership or cross-system duplicate cause was found.
- Aggregate sample sequence failure causes: 81 extra/unsupported predicted steps, 67 step numbering/order mismatches, 37 discovery/system-resource attribution misses, and 15 policy operation/phase mismatches. Explicit other-user ownership elimination did not change the sample score.

## Next steps

1. Improve subject-to-resource linkage for cases with only unlinked activity claims, without using case/resource numbering or reported status.
2. Recover the remaining sample account and analytics resource links, then rerun sample scoring.
3. Resolve the case_12 expected-action conflict against the participant-facing deletion rule and sample contract.
4. Rerun python code/main.py, python code/validate_output.py, and python code/evaluation/evaluate.py after future pipeline changes.

## Commands

- Full run: python code/main.py
- Output validation: python code/validate_output.py
- Sample evaluation: python code/evaluation/evaluate.py
- Classifier checks: python code/evaluation/evaluate_classifier.py
