# Progress Handoff

## Status

- Loaders: DONE
- Identity resolution: DONE
- Discovery: IN PROGRESS; unchanged during this implementation task at the user's direction
- Request classifier: DONE; deterministic rules only, request text is the only input
- Policy evaluation: DONE for discovered resources and current rule categories
- Planner: DONE; phase / operation-rank / system / resource sort, no dependency edge needed by sample ordering
- Serializer: DONE
- Main full-dataset run: DONE; output.csv contains 518 ordered rows
- Sample evaluator: DONE; reports status, exact-step, field, sequence, and first mismatch per case
- Output validator: DONE

## Latest metrics (2026-10-24 16:42 UTC)

- Classifier fixtures: 48/48 passed across English, Portuguese, Spanish, French, Japanese, and Korean, including ambiguous cases.
- Classifier over 518 evaluation requests: 508 AUTHORIZED, 10 NOT_APPLICABLE, 0 UNCERTAIN. The ten explicit non-deletion requests are case_533 through case_542.
- Sample classifier contract: 0/32 NOT_APPLICABLE.
- Full output status counts: COMPLETE 93, INCOMPLETE 415, NOT_APPLICABLE 10.
- Output validation: PASS, 518 rows, sorted, exact case set, valid JSON and allowed phase/operation/state values.
- Sample status accuracy: 24/32 = 75.000%.
- Sample exact-step precision/recall/F1: 43.787% / 38.342% / 40.884% (74 exact steps; 169 predicted, 193 expected).
- Sample field accuracy: 922/1001 = 92.108% across 143 aligned steps; step number 80/143, evidence ID 127/143, remaining fields 143/143.
- Sample sequence accuracy: 5/32 = 15.625%.

## Known failures grouped by end-to-end effect

- Status accuracy: 8/32 sample statuses differ. Cases 01-04 and 26-28 are predicted INCOMPLETE instead of COMPLETE; case 12 is predicted COMPLETE instead of INCOMPLETE.
- Expected-step recall: 37 expected steps are missed because a resource is undiscovered or assigned to the wrong system/resource pair.
- Exact-step precision: 95 unsupported/extra predicted steps remain, mostly from over-broad resource linkage and observations that do not match the sample's in-scope set.
- Field/sequence scores: 53 expected steps have numbering/order differences, 16 have evidence-citation differences, and 13 have operation/phase differences. Step numbering differences include shifts caused by missing or extra earlier steps.
- The discovery handoff still records evidence attribution gaps, cutoff-limited observations, and activity-only resource claims. Discovery was not further investigated in this task.

## Next steps

1. Improve discovery coverage and precision without using adjacency as ownership; measure each change against the sample comparator.
2. Review the eight status mismatches and 95 extra steps after discovery changes, then rerun the sample evaluator.
3. Expand policy-specific evaluation for cache, marketing, email-delivery, attachment, legal-hold, and other categories absent from sample outputs.
4. Rerun python code/main.py, python code/validate_output.py, and python code/evaluation/evaluate.py after subsequent pipeline changes.

## Commands

- Full run: python code/main.py
- Output validation: python code/validate_output.py
- Sample evaluation: python code/evaluation/evaluate.py
- Classifier fixtures and request contract: python code/evaluation/evaluate_classifier.py
