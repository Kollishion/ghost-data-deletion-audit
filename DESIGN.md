# Ghost Data Still Exists — Design

This document specifies the implementation plan for the deletion-audit agent. It is design only; the modules below are proposed and no implementation changes are included here. Predictions use participant-facing files under `dataset/` only.

## 1. Module layout

| Module | Responsibility |
|---|---|
| `code/main.py` | CLI entry point. Load one request at a time, run classification, identity resolution, evidence reconstruction, policy evaluation, plan generation, and deterministic output serialization. Write the final `output.csv` at the repository root. |
| `code/loaders.py` | Read the request, identity, audit, activity, policy, evidence-manifest, and evidence files using paths relative to the repo root. Validate required columns, timestamps, file references, and output rows. |
| `code/request_classifier.py` | Decide whether `request_text` authorizes deletion. Apply deterministic multilingual intent rules first and call Ollama only when the rules are inconclusive. This module receives only request text. |
| `code/identity.py` | Resolve a request email to a stable `user_id`, then build the set of current and historical email, email-hash, and phone identifiers valid at the case's `audit_at`. |
| `code/evidence.py` | Dispatch evidence parsing by format (SQL, JSON/CSV, text/log, PDF, image); extract resource observations and identifier matches; deduplicate repeated mentions; apply the capture-time cutoff. |
| `code/activity.py` | Filter and interpret `system_activity.csv` by event time. Use activity as a lead or corroborating claim, never as sole proof of resulting resource state. |
| `code/policy.py` | Match a resource to `deletion_rules.csv`, evaluate its condition at `audit_at`, and determine required state, violation, finding operation, remediation operation, and verification operation. |
| `code/planner.py` | Collect all in-scope resources, construct dependency constraints, sort findings/remediations/verifications deterministically, and assign consecutive step numbers. |
| `code/serializer.py` | Enforce the exact step schema and status values, encode `steps_json`, and write sorted CSV rows with the required header. |
| `code/evaluation/evaluate.py` | Compare a generated sample prediction file to `dataset/sample_output.csv`; report status, exact-step, field, and full-sequence scores plus malformed/missing/extra cases. |

## 2. Policy rules and resulting operations

The operation/state pairs below are limited to the allowed-operations table in `AGENTS.md`. A compliant record contributes verification coverage but no finding or remediation. A finding cites the best participant-visible evidence ID. Proposed remediation and future verification steps in an `INCOMPLETE` case have an empty `evidence_id`.

| Rule | Detection of a violation at `audit_at` | Finding | Remediation | Verification |
|---|---|---|---|---|
| 01 `USER_PROFILE` — `DELETE` | A linked account/profile record is present in an eligible snapshot or readback. | `REPORT_REMAINING_RECORD` / `PRESENT` | `DELETE_RECORD` / `ABSENT` | `VERIFY_RECORD_ABSENT` / `ABSENT` |
| 02 `SECONDARY_IDENTIFIER` — `DELETE` | A linked secondary identifier record remains in a source or replica. | `REPORT_REMAINING_RECORD` / `PRESENT` | `DELETE_RECORD` / `ABSENT` | `VERIFY_RECORD_ABSENT` / `ABSENT` |
| 03 `SEARCH_INDEX_ENTRY` — `DELETE` | A linked search document remains searchable or is present in an index snapshot. | `REPORT_REMAINING_RECORD` / `PRESENT` | `DELETE_RECORD` / `ABSENT` | `VERIFY_RECORD_ABSENT` / `ABSENT` |
| 04 `CACHE_ENTRY` — `DELETE` | A linked cache key/value is present in a current cache snapshot or readback. | `REPORT_REMAINING_RECORD` / `PRESENT` | `DELETE_RECORD` / `ABSENT` | `VERIFY_RECORD_ABSENT` / `ABSENT` |
| 05 `SUPPORT_MESSAGE` — `REDACT` when shared customer/agent/order context must remain | The shared conversation is present and still exposes the subject's identifiers. Its presence alone is not a violation once those identifiers are redacted. | `REPORT_EXPOSED_PII` / `PRESENT` | `REDACT_RECORD` / `REDACTED` | `VERIFY_RECORD_REDACTED` / `REDACTED` |
| 06 `SUPPORT_ATTACHMENT` — `DELETE` when it belongs only to the subject | Attachment ownership/content ties it solely to the subject and the attachment remains. | `REPORT_REMAINING_RECORD` / `PRESENT` | `DELETE_RECORD` / `ABSENT` | `VERIFY_RECORD_ABSENT` / `ABSENT` |
| 07 `ANALYTICS_PROFILE` — `ANONYMIZE` while attributable | The analytics row is linkable through email, hash, phone, stable user reference, or another direct identifier. | `REPORT_EXPOSED_PII` / `PRESENT` | `ANONYMIZE_RECORD` / `ANONYMIZED` | `VERIFY_RECORD_ANONYMIZED` / `ANONYMIZED` |
| 08 `PRODUCT_TELEMETRY` — `ANONYMIZE` while attributable | Telemetry remains linkable to the subject; aggregate or irreversibly de-linked telemetry is compliant. | `REPORT_EXPOSED_PII` / `PRESENT` | `ANONYMIZE_RECORD` / `ANONYMIZED` | `VERIFY_RECORD_ANONYMIZED` / `ANONYMIZED` |
| 09 `USER_EXPORT` — `DELETE` | An export file, manifest entry, or downloadable object linked to the subject remains. | `REPORT_REMAINING_RECORD` / `PRESENT` | `DELETE_RECORD` / `ABSENT` | `VERIFY_RECORD_ABSENT` / `ABSENT` |
| 10 `MARKETING_PROFILE` — `DELETE` | A linked marketing profile remains in the marketing system. | `REPORT_REMAINING_RECORD` / `PRESENT` | `DELETE_RECORD` / `ABSENT` | `VERIFY_RECORD_ABSENT` / `ABSENT` |
| 11 `EMAIL_DELIVERY_LOG` — `REDACT` when it contains a user email | A required delivery log remains but its email field is still exposed. The log itself can remain after redaction. | `REPORT_EXPOSED_PII` / `PRESENT` | `REDACT_RECORD` / `REDACTED` | `VERIFY_RECORD_REDACTED` / `REDACTED` |
| 12 `SECURITY_AUDIT_LOG` — `RETAIN` while inside the supplied retention period | Evaluate the record's retention start/expiry or retention interval against `audit_at`. If the retention obligation is active, presence is compliant and absence is a retention violation. If it has expired by `audit_at`, it is no longer required to be retained and a still-present subject-linked record is treated as a deletion violation. | For an expired, still-present record: `REPORT_REMAINING_RECORD` / `PRESENT`. A missing in-period record is reported as a policy violation; no allowed operation fabricates/restores it, so the case cannot be considered complete. | For an expired, still-present record: `DELETE_RECORD` / `ABSENT`. No destructive action while retention is active. | In-period required record: `VERIFY_RECORD_PRESENT` / `PRESENT`. Expired record: `VERIFY_RECORD_ABSENT` / `ABSENT`. |
| 13 `LEGAL_HOLD_RECORD` — `RETAIN` while a supplied hold is active | Resolve hold status and effective/release dates as of `audit_at`. An active hold makes continued presence compliant; a released/expired hold removes the retention exception. | For a released hold with remaining subject data: `REPORT_REMAINING_RECORD` / `PRESENT`. Active hold is not a finding. | After release, `DELETE_RECORD` / `ABSENT` if the hold record itself is no longer required. Never delete while the hold is active. | Active hold: `VERIFY_RECORD_PRESENT` / `PRESENT`. Released hold after deletion: `VERIFY_RECORD_ABSENT` / `ABSENT`. |
| 14 `BACKUP_ARCHIVE` — `RETAIN` when restore access can be blocked | A retained archive is compliant only if evidence establishes that restore is blocked. An archive with restore access still allowed is a recreation risk. | `REPORT_RESTORE_RISK` / `ACTIVE` | `BLOCK_RESTORE` / `BLOCKED` | `VERIFY_RESTORE_BLOCKED` / `BLOCKED` |
| 15 `ACCOUNT_TOMBSTONE` — `REDACT` when only stable `user_id` is needed | A tombstone is allowed to retain the stable internal reference, but the name, email, phone, email hash, and any other direct identifiers required by policy must be absent. | If prohibited identifiers remain: `REPORT_EXPOSED_PII` / `PRESENT` | `REDACT_RECORD` / `REDACTED` | `VERIFY_RECORD_REDACTED` / `REDACTED` |

An active sync/import/integration process is represented by the supporting `DATA_FLOW` resource type, not one of the 15 deletion categories. If it can copy or recreate a subject's data, report `REPORT_ACTIVE_DATA_FLOW` / `ACTIVE`, remediate with `DISABLE_DATA_FLOW` / `DISABLED`, then verify with `VERIFY_DATA_FLOW_DISABLED` / `DISABLED`.

### Sample-derived category/system/prefix mapping

`system_id` is taken from the evidence's system/target-system field and normalized to the values below. Prefixes are those observed in resources and participant evidence. Categories marked “not in samples” have no output resource example in the 32 sample outputs; the listed mappings are used only when participant evidence supports them.

| Category or process | `target_system` → output `system_id` | `resource_id` prefix | In sample outputs? |
|---|---|---|---|
| `USER_PROFILE` | `account_service` → `account_service` | `account_` | Yes |
| `SECONDARY_IDENTIFIER` | No participant-evidence resource mapping found | — | No |
| `SEARCH_INDEX_ENTRY` | `search_service` → `search_service` | `search_` | Yes |
| `CACHE_ENTRY` | No participant-evidence resource mapping found | — | No |
| `SUPPORT_MESSAGE` | `support_platform` → `support_platform` | `support_` | Yes |
| `SUPPORT_ATTACHMENT` | `support_platform` → `support_platform` | `support_` | No |
| `ANALYTICS_PROFILE` | `analytics_platform` → `analytics_platform` | `analytics_` | Yes |
| `PRODUCT_TELEMETRY` | No participant-evidence resource mapping found | — | No |
| `USER_EXPORT` | `export_service` → `export_service` | `export_` | Yes |
| `MARKETING_PROFILE` | No participant-evidence resource mapping found | — | No |
| `EMAIL_DELIVERY_LOG` | No participant-evidence resource mapping found | — | No |
| `SECURITY_AUDIT_LOG` | `security_service` → `security_service` | `audit_record_` | Yes |
| `LEGAL_HOLD_RECORD` | `legal_service` → `legal_service` | `legal_hold_` | No |
| `BACKUP_ARCHIVE` | `backup_service` → `backup_service` | `backup_` | Yes |
| `ACCOUNT_TOMBSTONE` | `identity_service` → `identity_service` | `tombstone_` | Yes |
| Supporting `DATA_FLOW` | `integration_service` → `integration_service` | `data_flow_` | Yes |

The “not in samples” set for rule categories is `SECONDARY_IDENTIFIER`, `CACHE_ENTRY`, `SUPPORT_ATTACHMENT`, `PRODUCT_TELEMETRY`, `MARKETING_PROFILE`, `EMAIL_DELIVERY_LOG`, and `LEGAL_HOLD_RECORD`. The sample output covers the other eight rule categories. These seven must still be handled from the policy and evidence when encountered in the full dataset.

## 3. Step ordering and dependency algorithm

The planner first creates one finding per distinct policy violation or active recreation risk, one remediation per required change, and verification coverage for every relevant in-scope resource. Duplicate mentions of the same `(system_id, resource_id)` are merged before planning; multiple distinct violations on one resource remain distinguishable only when they require distinct allowed operations.

The allowed operation rank within each phase is:

1. `FINDING`: `REPORT_REMAINING_RECORD`, `REPORT_EXPOSED_PII`, `REPORT_ACTIVE_DATA_FLOW`, `REPORT_RESTORE_RISK`.
2. `REMEDIATION`: `DISABLE_DATA_FLOW`, `BLOCK_RESTORE`, `DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`.
3. `VERIFICATION`: `VERIFY_RECORD_ABSENT`, `VERIFY_RECORD_PRESENT`, `VERIFY_RECORD_REDACTED`, `VERIFY_RECORD_ANONYMIZED`, `VERIFY_DATA_FLOW_DISABLED`, `VERIFY_RESTORE_BLOCKED`.

For each phase, the planner sorts by **operation rank, then `system_id`, then `resource_id`** (ordinal string order). It then assigns `step_no` consecutively across the concatenated phases: all FINDING steps, then REMEDIATION, then VERIFICATION. If there are dependency edges, a stable topological sort is applied within that phase: among currently eligible steps, select the lowest `(operation rank, system_id, resource_id)`. The edge is a hard prerequisite; the stated sort breaks ties among steps that are safe to run. This makes the result deterministic while preserving required dependencies.

Remediation dependency edges are:

- Disable every implicated active data flow and block every implicated unsafe restore before changing any record that flow/restore could recreate.
- For a copy chain, remediate downstream copies before their source records. Add an edge from each dependent downstream record operation to its upstream source operation; use evidence/activity lineage to construct the chain rather than assuming a source from resource names.
- Independent records follow the operation/system/resource ordering above.

The sample arrays were checked against the phase → operation → system → resource key: **none conflict** with that sort. In particular, sampled active data flows are disabled before the sampled dependent records are processed. No sampled dependency requires reversing the operation/system/resource sort for downstream-before-source ordering. The topological tie-breaking rule is still required for cases where the complete dataset exposes such a dependency.

## 4. Verification scope and evidence IDs

Samples establish that verification is for the **complete set of relevant resources**, not just resources that generated findings or remediation steps.

- In `COMPLETE`, emit only evidence-backed `VERIFICATION` steps. Cover every policy-relevant record or process located for the subject, including absent user profiles, policy-required retained records, compliant redacted/anonymized records, and blocked restore/data-flow controls. Thus `case_19`-style coverage may include the absent account and retained audit record even though neither had a finding.
- In `INCOMPLETE`, emit findings for all supported violations/risks; remediation for every violation/risk; then future verification for the complete relevant resource set. This includes compliant resources that must remain, such as a security audit record, and relevant absent source accounts, as illustrated by `case_19` (`account_9102`, `audit_record_6793`). It is not restricted to the finding list.
- For each `COMPLETE` verification, select the most recent direct, authoritative participant evidence for that resource whose capture/observation time is at or before `audit_at`. Choose independently per resource, so one case may cite different evidence files for different resources. A later-in-time but ineligible file is never selected. If equally recent eligible sources conflict, prefer a direct system snapshot/readback over an activity claim; retain a deterministic `file_id` tie-break after source quality.
- Every finding cites the participant-visible `file_id`, `activity_id`, or `audit_id` supporting it. `INCOMPLETE` remediation and post-remediation verification steps always serialize `evidence_id` as `""`, because those are proposed future actions/checks, not observed facts.

## 5. Time filtering

All datetimes are normalized to UTC. For each case, `audit_at` is the as-of boundary and must be applied before matching, state reconstruction, policy evaluation, evidence selection, or activity interpretation.

- Evidence manifest: include a file only when its `captured_at <= audit_at`. A file captured later is excluded in full, even if its contents describe an earlier event. For an eligible file, an individual row/observation with its own timestamp later than `audit_at` is also excluded.
- SQL snapshots: both the file capture time and the row/snapshot timestamp must be no later than the cutoff. Compare relevant primary, regional, reporting, and failover copies only among eligible snapshots.
- JSON, CSV, logs, and text: apply the manifest capture filter and then filter each record's `observed_at`, `recorded_at`, event timestamp, or equivalent timestamp to `<= audit_at`. Do not use a later export's state as a proxy for the earlier state.
- PDFs and images: the file's manifest `captured_at` must be eligible; when the artifact exposes a record/event time, that time must also be `<= audit_at`. Extracted dates are evidence content, not a reason to admit a file captured after the cutoff.
- `system_activity.csv`: retain only rows with `event_time <= audit_at`. The event is a lead/claim; it does not override direct evidence of state.
- `user_audit_log.csv`: use only identity changes with `event_time <= audit_at` when constructing the identifier chain. Later identity changes do not add identifiers to the as-of set.
- `user_identities.csv`: use a snapshot row only if its `updated_at <= audit_at`. If the current snapshot was updated after the cutoff, reconstruct the as-of identity from audit-log transitions up to the cutoff (including the old value at the first later transition when it supplies the value that existed immediately before that transition). Never apply a post-cutoff value to the case.
- The request email and request text are part of the request itself; they do not make any post-cutoff identity/evidence state eligible.

## 6. Identity resolution and evidence searches

Resolve the request email against the identity snapshot and the historical audit log to identify the stable `user_id`. Normalize emails case-insensitively and trim surrounding whitespace; normalize phones to a comparison form while retaining original display forms. Hashes are compared as exact normalized values, not recomputed unless the supplied hash algorithm is documented.

For a matched `user_id`, sort its email, `email_hash`, and phone audit events by `event_time`. Each change links `old_value` to `new_value`; walk both directions from values known at the as-of point to collect the connected chain, constrained to events at or before `audit_at`. Include the request email if it matches a historical or current value. Include the snapshot's email/hash/phone only when the snapshot is as-of eligible; otherwise derive the cutoff state and all prior values from the audit chain. Do not join users solely by a common name, and do not treat a shared email or phone as conclusive if conflicting identity evidence exists.

Search rules by evidence type:

- **SQL/database snapshots:** exact match `user_id`/stable subject reference, all historical/current email values, email hashes, and phone values in their corresponding columns; inspect related replica tables and resource IDs.
- **Structured JSON and CSV exports/manifests:** match `subject_reference`, `owner_email`, `customer_email`, `email`, `email_hash`, `phone`, stable user reference, and resource IDs when present. A null direct identifier does not establish absence if a stable reference or linked resource establishes the relationship.
- **Logs and plain text:** search exact email variants, exact email hashes, normalized and source-form phone strings, stable user IDs, and already-linked resource IDs. Treat a textual hit as a candidate and corroborate it with context/system/resource/time to reject decoys.
- **PDFs and screenshots:** extract visible text (PDF text extraction or OCR) and search the same email/hash/phone/user/resource identifiers. Verify relevant fields and surrounding context; a name by itself is not a reliable link.
- **Resource/lineage references:** follow a verified resource ID, stable user reference, or system-to-system flow even if direct identifiers have already been removed. This is necessary to find tombstones, replicas, copies, and recreation paths.

## 7. NOT_APPLICABLE request classifier

The classifier input is **only `request_text`**. It must not read or branch on `case_id`, row ordering, request email, reported status, audit evidence, or sample answers.

1. Apply high-precision deterministic multilingual rules first. Recognize explicit requests to delete/erase/close/remove the account or personal data, while honoring negation and distinguishing access, correction, export, marketing opt-out, status-check-only, and other non-deletion requests. Clear deletion intent returns `AUTHORIZED`; clear non-deletion intent returns `NOT_APPLICABLE`.
2. If deterministic rules are inconclusive, send only the request text to the configured local Ollama model with a constrained prompt requiring exactly `AUTHORIZED`, `NOT_APPLICABLE`, or `UNCERTAIN` plus a short reason. Use deterministic settings and validate the returned label/schema. Re-prompt once for malformed output; do not include sample cases or expected outputs in the prompt.
3. Resolve `UNCERTAIN` conservatively with a second deterministic rule pass; if the text still does not actually authorize deletion, classify it `NOT_APPLICABLE`. The output is `NOT_APPLICABLE` with `steps_json=[]`.
4. Test the classifier independently using participant-authored synthetic fixtures covering explicit deletion, negated deletion, access/correction/export/marketing requests, ambiguous requests, and multiple languages. Freeze those fixtures before comparing any result to public examples. Do not use `sample_output.csv` as training, prompt examples, or a source of classifier rules. As a final contract check, confirm that none of the 32 public sample requests is classified `NOT_APPLICABLE`; this is a check only and must not feed labels back into the classifier.

## 8. Sample findings that resolve the open questions

- **Verification breadth:** both statuses verify all relevant resources. `INCOMPLETE` includes future checks for found violations plus already-compliant/must-remain resources. `COMPLETE` includes only currently evidenced checks. `case_19` specifically includes its account and retained security audit resource without findings.
- **Category/system/prefix coverage:** see the mapping table in §2. Seven rule categories do not appear in the sample outputs; their absence is not a license to skip them in the 518-case run.
- **Ordering versus dependencies:** no conflict occurs in the 32 samples. Dependency edges remain hard constraints, and lexical/operation ordering is applied among currently eligible steps.
- **Rule 12 retention:** evaluate the supplied retention interval/expiry at each case's `audit_at`, not at today's date or file-generation date. A record still inside retention must be present and is verified with `VERIFY_RECORD_PRESENT`; after expiry it is no longer retention-exempt and a still-present record is a delete violation. No sample has an expired security-audit retention period: every sample security audit record is included as a required retained record.
- **Rule 13 legal hold:** evaluate active/release status at `audit_at`; preserve and verify an active hold record, and remove the retention exception once it is released. No sample output contains a `LEGAL_HOLD_RECORD` verification/resource.
- **Evidence selection:** choose the latest eligible direct evidence for each resource independently, with capture/observation cutoff applied. The samples use different files for distinct resources when needed (for example, `case_04` cites `evidence_54` and `evidence_56`).
- **Repeated mention:** in `evidence_92`, `backup_838` appears once as the `resource_id` and once inside its `archive_key` (`.../backup_838.tar.zst`) on the same backup object. It is one resource and must produce at most one finding/remediation/verification set for that object; deduplicate by `(system_id, resource_id)` while retaining all mention locations as provenance.
- **Classifier:** it reads only `request_text`; it has no case-range shortcuts. None of the 32 samples is `NOT_APPLICABLE`.

## 9. Evaluation plan for `code/evaluation/evaluate.py`

Run the evaluator against a generated prediction CSV and `dataset/sample_output.csv` only. It parses quoted CSV and JSON arrays, validates exact headers, one row per sample case, status enum, consecutive step numbering, allowed fields/operations/states, and phase ordering before scoring. The evaluator is not imported by the prediction/classification path.

- **Status accuracy:** exact `deletion_status` matches divided by 32 sample cases.
- **Step-level accuracy:** compare normalized complete step objects (all seven fields) per case; report micro precision/recall/F1 over the expected and predicted step collections, with case ID included in the comparison key so duplicate step content in different cases cannot match across cases.
- **Field-level accuracy:** align each case's predicted and expected ordered steps using longest-common-subsequence alignment on `(phase, operation, system_id, resource_id)`; report correct matches for `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, and `evidence_id`, each over aligned steps × 7 fields. Also report alignment coverage so missing/extra steps are visible.
- **Sequence accuracy:** percentage of cases whose parsed arrays match exactly in order and all fields after ignoring object-key order and JSON whitespace, as required by the contract.
- **Diagnostics:** report invalid rows/JSON, missing/extra cases, status mismatches, first differing step/field, and aggregate scores. Keep the evaluator read-only with respect to the prediction and expected files.

The public sample set is a contract/evaluation set, not a source for classifier labels or prediction-time shortcuts. Any classifier tuning fixtures are kept separate and created independently.

## Appendix A. Participant evidence inventory (non-image formats)

Inventory scope: every `dataset/evidence/` file with a `.sql`, `.json`, `.log`, or `.txt` extension was inspected. PDFs and images were deliberately excluded from parsing and this inventory. The manifest has 24 SQL snapshots, 28 JSON documents, 26 logs, and one text handover.

### A.1 SQL snapshot schemas

All SQL files are SQLite-compatible scripts. The inventory files create a scope table plus normalized profile, search, analytics, support, export, connector, backup, and security-audit tables. Replica files instead store generic `resource_id`, `origin_system`, `collection_name`, `record_json`, and `updated_at` rows. SQL insertion order follows the table declaration but parsers must use declared columns.

| Table | Columns |
|---|---|
| `snapshot_scope` | `origin_system`, `captured_at` |
| `customer_profiles` | `resource_id`, `customer_reference`, `full_name`, `email`, `phone`, `email_hash`, `account_status`, `updated_at` |
| `customer_profiles_primary`, `customer_profiles_failover_replica` | `resource_id`, `user_id`, `full_name`, `email`, `phone`, `account_status`, `updated_at` |
| `customer_search_documents` | `resource_id`, `customer_reference`, `display_name`, `email`, `phone`, `email_hash`, `index_name`, `updated_at` |
| `search_documents_primary` | `resource_id`, `display_name`, `email`, `source_resource_id`, `indexed_at` |
| `customer_analytics_profiles` | `resource_id`, `customer_reference`, `email`, `phone`, `email_hash`, `audience_cohort`, `updated_at` |
| `support_records` | `resource_id`, `customer_reference`, `requester_name`, `requester_email`, `requester_phone`, `message_excerpt`, `updated_at` |
| `customer_exports` | `resource_id`, `customer_reference`, `owner_email`, `owner_phone`, `object_key`, `updated_at` |
| `connector_subscriptions` | `resource_id`, `customer_reference`, `customer_email`, `connector_name`, `enabled`, `last_delivery_status`, `updated_at` |
| `backup_restore_entries` | `resource_id`, `customer_reference`, `customer_email`, `archive_key`, `restore_allowed`, `updated_at` |
| `security_audit_records` | `resource_id`, `subject_reference`, `event_code`, `retention_until`, `updated_at` |
| `customer_data_primary`, `customer_data_read_replica`, `customer_data_reporting_replica`, `customer_data_replica_ap_south`, `customer_data_replica_eu_west`, `customer_data_failover_replica` | `resource_id`, `origin_system`, `collection_name`, `record_json`, `updated_at` |

`record_json` is a JSON object whose field names vary by collection; parse it and retain the outer origin/collection/snapshot timestamp. Inventory snapshots include primary plus one or more reporting, read, regional, or failover copies, so absence/presence must be evaluated per replica and snapshot time.

### A.2 JSON shapes and keys

Three envelope shapes recur: a record manifest (`origin`, `system`, `record_type`, `record_count`, `recorded_at`/`exported_at`, `subject_reference`, `resource_id`, `result`, `records`); a snapshot bundle (`captured_at`, `snapshots` and/or `records` plus resource objects); and a service export with system-named collections such as `account_service`, `analytics_platform`, `backup_service`, `export_service`, `integration_service`, `search_service`, `security_service`, and `support_platform`.

Across nested records, identity/link fields include `user_id`, `subject_reference`, `customer_reference`, `subject_selector`, `owner_email`, `customer_email`, `requester_email`, `email`, `phone`, and `email_hash`. Resource/state/policy fields include `resource_id`, `source_resource_id`, `record_type`, `collection`, `account_status`, `enabled`, `last_delivery_status`, `restore_allowed`, `retention_until`, `retained_until`, `retention_reason`, `event_code`, `archive_key`, `object_key`, `file_name`, `storage_class`, `download_available`, and `indexed_at`/`updated_at`/`observed_at`. Business context fields include `ticket_id`, `order_reference`, `message_text`/`message_excerpt`, and aggregate metric keys (`sessions_30d`, `orders_completed_90d`, `products_viewed_30d`, `revenue_90d_usd`, `audience_cohort`). The exact nested shape is collection-specific; recurse dictionaries and arrays instead of assuming one record schema.

### A.3 Log line shapes

The 26 logs use several line encodings: timestamp + `[LEVEL] [service] [trace] event: key="value"`; timestamp + `level=... service=... trace_id=... event=... key=value`; timestamp + `requestId=... level=... function=... message="..."` with a second quoted key/value payload; timestamp + JSON object after the timestamp; syslog timestamp/header followed by service, trace, level, event, and key/value fields; and readback lines with `service=... event=... resource_id=...` fields. A single operation may span `*_started` and `*_completed` lines. Join lines only by explicit trace/request/correlation IDs. Common semantic events include profile/index/analytics reads, PII scans, connector reads, restore checks, export starts, attachment/message scans, and security-audit reads. `rows`, `result`, `http_status`, `direct_identifiers`, and `enabled` are state clues, while log messages still need source/time interpretation.

### A.4 Plain-text handover layout

`customer_account_handover_20261001.txt` has a title line, `Snapshot: <ISO-8601 UTC>` header, a free-text section heading, then one record per line in the fixed pipe-delimited layout:

`- <timestamp> | <system_id> | <resource_id> | <data_category> | <state/result> | <subject identifier or note>`

The final field may be an email or a phrase such as `no direct identifier`; it is not a fixed identity column. Apply both the file capture cutoff and each row timestamp.

## Appendix B. Full-scan resource prefix map

Prefixes below were scanned across all non-PDF/image evidence files and every `system_activity.csv` `resource_id`. Activity can assign multiple target systems to a prefix because it includes both resource updates and cross-system events. Prefer the record's own `origin_system`/service/system field; use the activity target as a corroborating mapping. Unlisted prefixes found in free text are ordinary field names or event labels, not resource IDs.

| Resource prefix | Target/output system | Data category / role | Notes |
|---|---|---|---|
| `account_` | `account_service` | `USER_PROFILE` | Activity also names replication/privacy control targets. |
| `analytics_` | `analytics_platform` | `ANALYTICS_PROFILE` | `PRODUCT_TELEMETRY` has no distinct telemetry resource ID in the scan; inspect analytics collections for telemetry records. |
| `audit_record_` | `security_service` | `SECURITY_AUDIT_LOG` | Activity also archives records to `archive_service`. |
| `backup_` | `backup_service` | `BACKUP_ARCHIVE` | Search-service activity can reference a backup during restore/search checks. |
| `cache_` | `cache_service` | `CACHE_ENTRY` | Present in activity; no cache snapshot file was found. |
| `data_flow_` | `integration_service` | Supporting `DATA_FLOW` | Search activity also consumes/indexes flows. |
| `email_delivery_` | `email_delivery_service` | `EMAIL_DELIVERY_LOG` | Present in activity (`SEND_EMAIL`); no distinct email-log snapshot was found. |
| `export_` | `export_service` | `USER_EXPORT` | Activity may target `object_store`; use the resource's export-service identity. |
| `legal_hold_` | `legal_service` | `LEGAL_HOLD_RECORD` | Found in activity and structured SQL/JSON collections. |
| `marketing_` | `marketing_platform` | `MARKETING_PROFILE` | Explicit `LINK_RESOURCE_IDENTITY` association exists. |
| `object_` | `object_storage` | Attachment object | Attachment catalog identity is expressed in activity; check ownership/content evidence before treating as subject-only support attachment. |
| `search_` | `search_service` | `SEARCH_INDEX_ENTRY` | |
| `support_` | `support_platform` | `SUPPORT_MESSAGE` or `SUPPORT_ATTACHMENT` | `collection_name`/`record_type` distinguishes messages from ticket attachments. |
| `tombstone_` | `identity_service` | `ACCOUNT_TOMBSTONE` | Stable user reference is allowed; direct identifiers are not. |
| `secondary_` | No concrete resource ID observed | `SECONDARY_IDENTIFIER` | No prefix instance appeared in this scan; do not infer a record without direct evidence. |
| `telemetry_` | No concrete resource ID observed | `PRODUCT_TELEMETRY` | Activity/logs mention telemetry flushing but did not expose a telemetry resource ID. Inspect analytics collection metadata for category evidence. |

The seven categories absent from the sample outputs are `SECONDARY_IDENTIFIER`, `CACHE_ENTRY`, `SUPPORT_ATTACHMENT`, `PRODUCT_TELEMETRY`, `MARKETING_PROFILE`, `EMAIL_DELIVERY_LOG`, and `LEGAL_HOLD_RECORD`. Of these, `cache_`, `support_` attachments, `marketing_`, email-delivery activity, and `legal_hold_` are present in the complete evidence/activity scan even though absent from sample-output steps. The scan found no explicit resource prefix for secondary identifiers or product telemetry; those remain policy categories, not invented prefixes.

### B.1 `LINK_RESOURCE_IDENTITY` semantics

The 12 events are explicit catalog associations, not operation results. They name `target_system`, `resource_id`, and in `details` the linked email plus stable `user_id`; an attachment example states exclusive ownership and names an object/file. Parse the identifier tuple from `details`, match the stable ID or an as-of email identifier, and map the resource ID to `target_system`. Enforce `event_time <= audit_at`. Treat the link as identity/lineage evidence only; use a direct eligible state observation to decide present/absent/redacted/anonymized. Do not use `reported_result=SUCCESS` as that state.
