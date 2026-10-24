# Exploration notes — Ghost Data Still Exists

Scope: read-only exploration of `problem_statement.md` and participant-facing files under `dataset/`. No solution code was written. Organizer-only directories were not consulted.

## 1. Problem statement read

The agent must audit 518 requests, decide whether the request authorizes deletion, resolve current and historical identifiers, reconstruct each resource's state as of `audit_at`, apply the supplied deletion rules, and emit ordered findings/remediation/verification steps. A workflow status or activity result is a claim, not proof. `COMPLETE` cases receive evidence-backed verification only; `INCOMPLETE` cases receive findings, ordered future remediation and future verification; a non-deletion request receives `NOT_APPLICABLE` and `[]`.

The project constraints for implementation are in the user's turn and should be followed later: Python entry point `python code/main.py`, fully offline/keyless, deterministic core logic, OCR/PDF extraction before optional local Ollama fallback, and no changes to `frontend/`, `backend/`, or `references/`.

## 2. CSV inventory and categorical values

There are nine CSV files in `dataset/`. Row counts below exclude the header. High-cardinality identifiers and free-text fields are reported as columns but are not repeated as category lists. Values nested inside `sample_output.csv.steps_json` are reported separately.

| CSV | Rows | Columns |
|---|---:|---|
| `deletion_requests.csv` | 518 | `case_id,email,requested_at,reported_status,reported_at,audit_at,request_text` |
| `deletion_rules.csv` | 15 | `rule_id,data_category,condition,required_action` |
| `evidence_files.csv` | 94 | `file_id,file_path,origin,captured_at` |
| `output.csv` | 0 | `case_id,deletion_status,steps_json` (header only; 36 bytes) |
| `sample_deletion_requests.csv` | 32 | `case_id,email,requested_at,reported_status,reported_at,audit_at,request_text` |
| `sample_output.csv` | 32 | `case_id,deletion_status,steps_json` |
| `system_activity.csv` | 4,011 | `activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details` |
| `user_audit_log.csv` | 306 | `audit_id,user_id,event_time,field_name,old_value,new_value` |
| `user_identities.csv` | 850 | `user_id,name,email,phone,email_hash,updated_at` |

### Distinct categorical values

- `deletion_requests.csv` and `sample_deletion_requests.csv` — `reported_status`: `COMPLETE`, `NOT_STARTED`, `PARTIALLY_COMPLETE`.
- `deletion_rules.csv` — `rule_id`: `rule_01`–`rule_15`; `data_category`: `ACCOUNT_TOMBSTONE`, `ANALYTICS_PROFILE`, `BACKUP_ARCHIVE`, `CACHE_ENTRY`, `EMAIL_DELIVERY_LOG`, `LEGAL_HOLD_RECORD`, `MARKETING_PROFILE`, `PRODUCT_TELEMETRY`, `SEARCH_INDEX_ENTRY`, `SECONDARY_IDENTIFIER`, `SECURITY_AUDIT_LOG`, `SUPPORT_ATTACHMENT`, `SUPPORT_MESSAGE`, `USER_EXPORT`, `USER_PROFILE`; `required_action`: `ANONYMIZE`, `DELETE`, `REDACT`, `RETAIN`.
- `deletion_rules.csv` — distinct `condition` values: `A supplied legal hold is active`; `Account is deleted and only a stable internal user_id is needed to preserve references to retained records`; `Always`; `Attachment belongs only to the deletion subject`; `Conversation contains shared customer, agent, or order context that must be retained`; `Log contains a user email address`; `Record is still attributable to a user`; `Record is within the supplied retention period`; `Restore access can be blocked`.
- `evidence_files.csv` — `origin` (30): `account_admin_portal`, `account_history_service`, `analytics_platform`, `backup_service`, `central_observability_export`, `customer_account_failover_replica_capture`, `customer_account_service`, `customer_data_failover_replica_capture`, `customer_data_inventory_capture`, `customer_data_read_replica_capture`, `customer_data_regional_replicas_capture`, `customer_data_reporting_replica_capture`, `customer_export_service`, `customer_search_primary_capture`, `downstream_delivery_service`, `export_service`, `identity_service`, `integration_admin`, `integration_management_service`, `legal_retention_service`, `marketing_platform`, `object_storage`, `records_assurance_snapshot_bundle`, `search_index_admin`, `search_index_service`, `security_audit_service`, `security_service`, `service_readback_logs`, `service_resource_export`, `support_platform`.
- `sample_output.csv` — `deletion_status`: `COMPLETE`, `INCOMPLETE`. No `NOT_APPLICABLE` row is in this public sample file.
- `sample_output.csv.steps_json` — `phase`: `FINDING`, `REMEDIATION`, `VERIFICATION`; `operation`: `ANONYMIZE_RECORD`, `BLOCK_RESTORE`, `DELETE_RECORD`, `DISABLE_DATA_FLOW`, `REDACT_RECORD`, `REPORT_ACTIVE_DATA_FLOW`, `REPORT_EXPOSED_PII`, `REPORT_REMAINING_RECORD`, `REPORT_RESTORE_RISK`, `VERIFY_DATA_FLOW_DISABLED`, `VERIFY_RECORD_ABSENT`, `VERIFY_RECORD_ANONYMIZED`, `VERIFY_RECORD_PRESENT`, `VERIFY_RECORD_REDACTED`, `VERIFY_RESTORE_BLOCKED`; `state`: `ABSENT`, `ACTIVE`, `ANONYMIZED`, `BLOCKED`, `DISABLED`, `PRESENT`, `REDACTED`; `system_id`: `account_service`, `analytics_platform`, `backup_service`, `export_service`, `identity_service`, `integration_service`, `search_service`, `security_service`, `support_platform`.
- `system_activity.csv` — `event_type` (17): `ANONYMIZE_RECORD`, `BLOCK_RESTORE`, `CHECK_DATA_FLOW`, `CHECK_RESTORE_ACCESS`, `CLASSIFY_REQUEST`, `CREATE_EXPORT`, `DELETE_RECORD`, `DISABLE_DATA_FLOW`, `INDEX_RECORD`, `LINK_RESOURCE_IDENTITY`, `REDACT_RECORD`, `REFRESH_CACHE`, `RESTORE_BACKUP`, `RETAIN_RECORD`, `SEND_EMAIL`, `SYNC_RECORD`, `UPDATE_RECORD`.
- `system_activity.csv` — `source_system` (11): `account_service`, `backup_service`, `data_catalog`, `deletion_worker`, `export_service`, `integration_service`, `notification_service`, `privacy_intake`, `profile_service`, `security_service`, `support_platform`.
- `system_activity.csv` — `target_system` (19): `account_failover_replica`, `account_replication_cluster`, `account_service`, `analytics_platform`, `archive_service`, `backup_service`, `cache_service`, `email_delivery_service`, `export_service`, `identity_service`, `integration_service`, `legal_service`, `marketing_platform`, `object_storage`, `object_store`, `privacy_case_management`, `search_service`, `security_service`, `support_platform`.
- `system_activity.csv` — `reported_result`: `FAILED`, `PARTIAL`, `SUCCESS`.
- `user_audit_log.csv` — `field_name`: `email` (107 rows), `email_hash` (107), `phone` (92).
- `user_identities.csv` — no low-cardinality categorical columns; its columns are identifiers, current identity attributes and timestamps.
- `output.csv` — no data rows, so no observed `deletion_status` values.

## 3. Deletion policy, printed in full

| rule_id | data_category | condition | required_action |
|---|---|---|---|
| rule_01 | USER_PROFILE | Always | DELETE |
| rule_02 | SECONDARY_IDENTIFIER | Always | DELETE |
| rule_03 | SEARCH_INDEX_ENTRY | Always | DELETE |
| rule_04 | CACHE_ENTRY | Always | DELETE |
| rule_05 | SUPPORT_MESSAGE | Conversation contains shared customer, agent, or order context that must be retained | REDACT |
| rule_06 | SUPPORT_ATTACHMENT | Attachment belongs only to the deletion subject | DELETE |
| rule_07 | ANALYTICS_PROFILE | Record is still attributable to a user | ANONYMIZE |
| rule_08 | PRODUCT_TELEMETRY | Record is still attributable to a user | ANONYMIZE |
| rule_09 | USER_EXPORT | Always | DELETE |
| rule_10 | MARKETING_PROFILE | Always | DELETE |
| rule_11 | EMAIL_DELIVERY_LOG | Log contains a user email address | REDACT |
| rule_12 | SECURITY_AUDIT_LOG | Record is within the supplied retention period | RETAIN |
| rule_13 | LEGAL_HOLD_RECORD | A supplied legal hold is active | RETAIN |
| rule_14 | BACKUP_ARCHIVE | Restore access can be blocked | RETAIN |
| rule_15 | ACCOUNT_TOMBSTONE | Account is deleted and only a stable internal user_id is needed to preserve references to retained records | REDACT |

Plain-language interpretation:

- **DELETE** means remove the whole record. It applies to user profiles, secondary identifiers, search index entries, cache entries, qualifying subject-only support attachments, exports and marketing profiles.
- **REDACT** means retain the record's non-identifying content but remove the prohibited direct identifiers. Shared support conversations stay because they contain context for other customers, agents or orders. Email delivery logs stay only without the user's email. A tombstone keeps its stable `user_id` reference but removes name, email, phone, email hash and other direct identifiers.
- **ANONYMIZE** means retain analytics or telemetry only after it is no longer attributable or linkable to the person. This is stronger than simply hiding an email field if some other identifier still links it back.
- **RETAIN** means preserve a record required by policy, such as an in-retention security audit, an active legal hold or a backup archive whose restore path can be blocked. Retention does not authorize retaining prohibited identifiers in a record; apply any separate redaction requirement too.
- **Tombstone** is a redacted account reference, not a live profile. Its stable internal reference may remain so retained records still join to it; direct identity fields must be cleared.
- **DELETE vs. REDACT vs. ANONYMIZE vs. RETAIN** therefore differ in whether the record is removed, kept with identifiers removed, kept irreversibly unlinked, or kept under a policy obligation. A blocked backup can be retained safely if evidence shows it cannot restore the subject's personal data.

## 4. Evidence inventory and representative content

There are 94 files under `dataset/evidence/`.

| Folder | SQL | JSON | LOG | TXT | PDF | PNG | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| `databases/` | 24 | 0 | 0 | 0 | 0 | 0 | 24 |
| `documents/` | 0 | 0 | 0 | 0 | 4 | 0 | 4 |
| `images/` | 0 | 0 | 0 | 0 | 0 | 11 | 11 |
| `logs/` | 0 | 0 | 26 | 0 | 0 | 0 | 26 |
| `records/` | 0 | 28 | 0 | 1 | 0 | 0 | 29 |
| **Total** | **24** | **28** | **26** | **1** | **4** | **11** | **94** |

Each example below is listed in the manifest. Paths are relative to `dataset/`.

| Type | Manifest row (`file_id`, `file_path`, `origin`, `captured_at`) | Contents summary |
|---|---|---|
| SQL | `evidence_54`, `evidence/databases/customer_accounts_failover_replica_20260902.sql`, `customer_account_failover_replica_capture`, `2026-09-02T23:00:00Z` | SQLite-compatible snapshot with primary and failover customer-profile tables. It directly shows Leila's `account_005` in the failover table while the primary table has no such row: replica drift, not a successful global deletion. |
| JSON | `evidence_13`, `evidence/records/connector_configurations_20260812.json`, `integration_management_service`, `2026-08-12T09:00:00Z` | Integration configuration export with `record_count: 39`; records include system/resource/type/result and a subject reference. The sample includes `USER_PROFILE` lookups returning `NOT_FOUND`; it is a global export with unrelated subjects too. |
| LOG | `evidence_16`, `evidence/logs/application_trace_ap_northeast_20260730.log`, `central_observability_export`, `2026-07-30T08:53:12Z` | Structured service traces across account, support, security, search and analytics services. It contains both misses and hits, resource IDs, direct-identifier scan results and unrelated user lookups; a log line must be linked to the correct subject. |
| Text record | `evidence_03`, `evidence/records/customer_account_handover_20261001.txt`, `customer_account_service`, `2026-10-01T12:00:00Z` | Shift handover snapshot listing accounts, analytics, backups, exports, integrations, search, security and support with states such as `NOT_FOUND`, `IDENTIFIABLE`, `ACTIVE`, `BLOCKED` and `FOUND`. It contains multiple subjects; it post-dates most audits. |
| PDF | `evidence_18`, `evidence/documents/account_history_report_20260718.pdf`, `account_history_service`, `2026-07-18T11:00:00Z` | Visually inspected first page: a customer statement with an internal user reference, email, invoice/order, item, billing and payment details. It demonstrates that ordinary business documents can contain identifiers; the record is for a different subject than the nearby examples, so its presence in the manifest does not attach it to a case. |
| Image | `evidence_04`, `evidence/images/account_admin_console_20260926.png`, `account_admin_portal`, `2026-09-26T11:00:00Z` | Admin-console screenshot with a customer profile, email and phone, account/user IDs, order history and support ticket reference. It is an ordinary support/business screen and must be matched by its identifiers and timestamp. |

## 5. Six sample cases: requests alongside reference outputs

**Public-sample limitation:** `sample_deletion_requests.csv` has 32 rows and `sample_output.csv` has 32 matching rows, but the latter contains only `COMPLETE` and `INCOMPLETE`. There are no public sample-output rows for `NOT_APPLICABLE`. The two non-deletion examples below are evaluation requests; their matching sample-output row is therefore explicitly absent. The `NOT_APPLICABLE,[]` form is required by the project contract.

### Case `case_28` — COMPLETE, similar-email decoy

Request row:

```csv
case_28,smartinez6461@gmail.com,2026-08-28T12:00:00Z,NOT_STARTED,2026-08-30T12:00:00Z,2026-09-15T12:00:00Z,"Can you verify that my account was deleted? A search result with a similar email belongs to someone else, so please do not treat that record as mine."
```

Matching `sample_output.csv` row:

```csv
case_28,COMPLETE,"[{""step_no"":1,""phase"":""VERIFICATION"",""system_id"":""account_service"",""resource_id"":""account_5482"",""operation"":""VERIFY_RECORD_ABSENT"",""state"":""ABSENT"",""evidence_id"":""evidence_92""},{""step_no"":2,""phase"":""VERIFICATION"",""system_id"":""security_service"",""resource_id"":""audit_record_9265"",""operation"":""VERIFY_RECORD_PRESENT"",""state"":""PRESENT"",""evidence_id"":""evidence_92""},{""step_no"":3,""phase"":""VERIFICATION"",""system_id"":""support_platform"",""resource_id"":""support_2351"",""operation"":""VERIFY_RECORD_REDACTED"",""state"":""REDACTED"",""evidence_id"":""evidence_92""},{""step_no"":4,""phase"":""VERIFICATION"",""system_id"":""analytics_platform"",""resource_id"":""analytics_6077"",""operation"":""VERIFY_RECORD_ANONYMIZED"",""state"":""ANONYMIZED"",""evidence_id"":""evidence_92""},{""step_no"":5,""phase"":""VERIFICATION"",""system_id"":""integration_service"",""resource_id"":""data_flow_2337"",""operation"":""VERIFY_DATA_FLOW_DISABLED"",""state"":""DISABLED"",""evidence_id"":""evidence_92""},{""step_no"":6,""phase"":""VERIFICATION"",""system_id"":""backup_service"",""resource_id"":""backup_838"",""operation"":""VERIFY_RESTORE_BLOCKED"",""state"":""BLOCKED"",""evidence_id"":""evidence_92""}]"
```

Reasoning:

1. The request asks for a deletion-state verification; it is not a new non-deletion request. The email matches current identity `user_28` (Sofía Martínez); no audit-log alias was found for this user.
2. `evidence_92` is `service_resource_export_20260915_114455.json`, captured at 11:44:55Z, before the 12:00Z cutoff. It shows `account_5482` with a null profile and HTTP 404; under `USER_PROFILE`/rule 01 this verifies absence.
3. The same point-in-time export links `audit_record_9265` to `user_28` and gives it a retention-until date, so rule 12 calls for retaining it. It shows `support_2351` with requester email/name/phone null, satisfying redaction for the retained shared support message under rule 05. `analytics_6077` has email/hash/phone null, so rule 07's anonymization requirement is met.
4. The export shows `data_flow_2337` disabled/stopped for `user_28`, and `backup_838` has `restore_allowed: false` while retaining the stable `user_28` reference. These support disabled-flow and blocked-restore checks; rule 14 allows a retained backup when restore access is blocked.
5. The six verification-only steps follow the verification operation order in the contract: absent, present, redacted, anonymized, flow disabled, restore blocked. They all cite the same eligible snapshot. Reported `NOT_STARTED` is not treated as state evidence.

### Case `case_31` — COMPLETE, correctly redacted tombstone

Request row:

```csv
case_31,a.eze08@gmail.com,2026-09-04T12:00:00Z,COMPLETE,2026-09-06T12:00:00Z,2026-09-15T12:00:00Z,"I no longer need this account. Please remove my name and contact details, but keeping an internal deleted-account reference is fine if other required records still depend on it."
```

Matching `sample_output.csv` row:

```csv
case_31,COMPLETE,"[{""step_no"":1,""phase"":""VERIFICATION"",""system_id"":""account_service"",""resource_id"":""account_4857"",""operation"":""VERIFY_RECORD_ABSENT"",""state"":""ABSENT"",""evidence_id"":""evidence_51""},{""step_no"":2,""phase"":""VERIFICATION"",""system_id"":""security_service"",""resource_id"":""audit_record_6909"",""operation"":""VERIFY_RECORD_PRESENT"",""state"":""PRESENT"",""evidence_id"":""evidence_51""},{""step_no"":3,""phase"":""VERIFICATION"",""system_id"":""identity_service"",""resource_id"":""tombstone_440"",""operation"":""VERIFY_RECORD_REDACTED"",""state"":""REDACTED"",""evidence_id"":""evidence_51""}]"
```

Reasoning:

1. `a.eze08@gmail.com` matches current `user_541` (Amara Eze); no historic identifier entries were found for this user.
2. `evidence_51` is `customer_data_snapshot_bundle_20260915.json`, captured exactly at `audit_at`. It shows live account `account_4857` absent, security audit `audit_record_6909` present and linked to `user_541`, and tombstone `tombstone_440` with `subject_reference: user_541`, `account_status: DELETED`, and `name`, `email`, `phone`, `email_hash` all null.
3. Apply rule 01 to the profile (delete); rule 12 to the in-retention security audit (retain); rule 15 to the tombstone (redact direct identifiers while keeping the stable user reference). This illustrates why deleting the tombstone would be wrong.
4. The three steps are all verification because state is already compliant. Their operation order is absent, present, redacted; each cites evidence captured no later than the audit cutoff.

### Case `case_05` — INCOMPLETE, failover replica still has profile

Request row:

```csv
case_05,leila.haddad@yahoo.com,2026-08-27T14:17:00Z,COMPLETE,2026-08-28T09:03:00Z,2026-09-08T13:40:00Z,"I deleted this account and received a confirmation, but the same email address is still recognized. Please remove any remaining copy of my profile."
```

Matching `sample_output.csv` row:

```csv
case_05,INCOMPLETE,"[{""evidence_id"":""evidence_54"",""operation"":""REPORT_REMAINING_RECORD"",""phase"":""FINDING"",""resource_id"":""account_005"",""state"":""PRESENT"",""step_no"":1,""system_id"":""account_service""},{""evidence_id"":"""",""operation"":""DELETE_RECORD"",""phase"":""REMEDIATION"",""resource_id"":""account_005"",""state"":""ABSENT"",""step_no"":2,""system_id"":""account_service""},{""evidence_id"":"""",""operation"":""VERIFY_RECORD_ABSENT"",""phase"":""VERIFICATION"",""resource_id"":""account_005"",""state"":""ABSENT"",""step_no"":3,""system_id"":""account_service""}]"
```

Reasoning:

1. The email matches current `user_05` (Leila Haddad); no historic identifier entries were found for this user.
2. `evidence_54` is the failover SQL snapshot from 2026-09-02 23:00Z, before the audit. Its failover table contains `account_005` for `user_05` and Leila's email; the primary table omits it. The disagreement means the global profile state is not absent. The `COMPLETE` workflow claim is contradicted by resource evidence.
3. The record is `USER_PROFILE`, so rule 01 requires deleting the whole copy. The finding comes first, then proposed deletion, then the future absence check. The two future steps correctly have empty evidence IDs.

### Case `case_19` — INCOMPLETE, shared support conversation must be redacted

Request row:

```csv
case_19,e.varga90@yahoo.com,2026-08-17T12:00:00Z,PARTIALLY_COMPLETE,2026-08-19T12:00:00Z,2026-09-15T12:00:00Z,"Please remove my profile and clean my personal details out of earlier support conversations. Some of those messages also relate to another customer, so the conversation itself may need to stay."
```

Matching `sample_output.csv` row:

```csv
case_19,INCOMPLETE,"[{""step_no"":1,""phase"":""FINDING"",""system_id"":""search_service"",""resource_id"":""search_6083"",""operation"":""REPORT_REMAINING_RECORD"",""state"":""PRESENT"",""evidence_id"":""evidence_01""},{""step_no"":2,""phase"":""FINDING"",""system_id"":""support_platform"",""resource_id"":""support_9553"",""operation"":""REPORT_EXPOSED_PII"",""state"":""PRESENT"",""evidence_id"":""evidence_01""},{""step_no"":3,""phase"":""REMEDIATION"",""system_id"":""search_service"",""resource_id"":""search_6083"",""operation"":""DELETE_RECORD"",""state"":""ABSENT"",""evidence_id"":""""},{""step_no"":4,""phase"":""REMEDIATION"",""system_id"":""support_platform"",""resource_id"":""support_9553"",""operation"":""REDACT_RECORD"",""state"":""REDACTED"",""evidence_id"":""""},{""step_no"":5,""phase"":""VERIFICATION"",""system_id"":""account_service"",""resource_id"":""account_9102"",""operation"":""VERIFY_RECORD_ABSENT"",""state"":""ABSENT"",""evidence_id"":""""},{""step_no"":6,""phase"":""VERIFICATION"",""system_id"":""search_service"",""resource_id"":""search_6083"",""operation"":""VERIFY_RECORD_ABSENT"",""state"":""ABSENT"",""evidence_id"":""""},{""step_no"":7,""phase"":""VERIFICATION"",""system_id"":""security_service"",""resource_id"":""audit_record_6793"",""operation"":""VERIFY_RECORD_PRESENT"",""state"":""PRESENT"",""evidence_id"":""""},{""step_no"":8,""phase"":""VERIFICATION"",""system_id"":""support_platform"",""resource_id"":""support_9553"",""operation"":""VERIFY_RECORD_REDACTED"",""state"":""REDACTED"",""evidence_id"":""""}]"
```

Reasoning:

1. The current address matches `user_19` (Elena Varga); no historical identity event was found for this user.
2. `evidence_01` (`service_events_ap_south_20260915.log`, captured 11:59:39Z, 21 seconds before cutoff) records a hit for `search_6083` with the case email and a direct-identifier scan on `support_9553` matching that email. The same log contains unrelated users; only those two resource IDs are linked to this case.
3. `search_6083` is a `SEARCH_INDEX_ENTRY`: rule 03 means delete it. `support_9553` is a shared `SUPPORT_MESSAGE`: rule 05 means keep the shared conversation but redact this user's direct identifiers. `account_9102` is a profile governed by rule 01 and `audit_record_6793` is a retained security record governed by rule 12.
4. Findings precede remediation. Findings are ordered as remaining record then exposed PII. Remediation deletes the search result and redacts the support message. Verification checks profile absence, search absence, audit retention and support redaction in the allowed operation order. The verification steps are future checks and therefore have empty evidence IDs.

### Case `case_536` — NOT_APPLICABLE, account recovery

Request row:

```csv
case_536,aditi.mehta@outlook.com,2026-09-04T12:00:00Z,NOT_STARTED,2026-09-05T12:00:00Z,2026-09-28T12:00:00Z,"I can't access my profile and need help resetting the login. Do not close the account."
```

There is **no matching row** in `sample_output.csv`; this is an evaluation request. The contract result is `case_536,NOT_APPLICABLE,[]`. The request authorizes login recovery and explicitly says not to close the account, so deletion auditing stops at intent classification. Identity and evidence investigation is not needed for an unauthorized deletion request.

### Case `case_537` — NOT_APPLICABLE, correction request

Request row:

```csv
case_537,l.alvarez94@yahoo.com,2026-09-02T12:00:00Z,NOT_STARTED,2026-09-04T12:00:00Z,2026-09-27T10:00:00Z,"My surname is misspelled on the account. Can you correct it without removing any of my records?"
```

There is **no matching row** in `sample_output.csv`; this is an evaluation request. The contract result is `case_537,NOT_APPLICABLE,[]`. It requests correction and explicitly preserves the data; a deletion status inferred from `reported_status` would be wrong.

## 6. Request text patterns and languages

The 518 evaluation rows contain 375 distinct full `request_text` strings. Most English deletion requests combine one of 12 opening phrasings with variable instructions about scope, historical identifiers, treatment, review and confirmation. Language counts:

| Language | Rows | Main deletion pattern |
|---|---:|---|
| English | 456 | 446 deletion requests and 10 distinct non-deletion requests |
| Portuguese | 14 | “Solicito a exclusão permanente da conta associada a este e-mail…” |
| Spanish | 12 | “Solicito la eliminación permanente de la cuenta asociada a este correo…” |
| French | 12 | “Je demande la suppression définitive du compte associé à cette adresse e-mail…” |
| Japanese | 12 | “このメールアドレスに関連するアカウントの完全な削除を依頼します…” |
| Korean | 12 | “이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다…” |

The English deletion opening patterns and row counts are:

| Opening | Rows |
|---|---:|
| “Please treat this message as a request for permanent account deletion.” | 52 |
| “I would like to submit a request to delete this account and its personal data.” | 49 |
| “I am requesting deletion of the account registered to this email address.” | 46 |
| “Please erase the account linked to this email address.” | 45 |
| “I am asking you to remove my account and the personal information linked to it.” | 39 |
| “I no longer use this account and would like it permanently deleted.” | 37 |
| “Please permanently delete the account associated with this email address.” | 37 |
| “Please process a permanent account-deletion request for this email address.” | 31 |
| “Please begin the deletion process for the account using this email address.” | 29 |
| “I would like the account associated with this address to be erased.” | 29 |
| “Please close my account and process the associated personal-data deletion.” | 29 |
| “I want to close this account and have its associated personal data deleted.” | 23 |

The 10 non-deletion intents occur once each, in `case_533`–`case_542`:

- `case_533`, `case_537`, `case_541`: correction/update (phone, surname, email).
- `case_534`, `case_538`: marketing opt-out while keeping account/service messages.
- `case_535`, `case_540`, `case_542`: export/access requests (account data or invoices), with explicit keep-account/no-delete wording.
- `case_536`: login recovery, explicitly “Do not close the account.”
- `case_539`: access to personal information, explicitly says it is not a request to erase it.

The non-deletion wording is intentionally mixed with terms such as “remove,” “change,” “copy,” and “delete.” Intent must be read from the full request, not keyword-matched in isolation.

## 7. Traps and evidence caveats found

- **Decoys / global records:** evidence is global, not case-indexed. `evidence_92` includes search results for unrelated people (for example `search_1993` is tied to Noah's address) alongside other subjects. The request for `case_28` explicitly warns that a similar-email result belongs to someone else. A later snapshot (`evidence_02`, captured 2026-09-17) contains `search_8168` for `smartinez6461.jr@gmail.com` with no customer reference; it is after `case_28`'s 2026-09-15 cutoff and must not affect that answer.
- **Evidence after `audit_at`:** manifest capture times range across months, while request audits run through 2026-10-01. For each case, filter evidence to `captured_at <= audit_at`; for example, `evidence_03` was captured 2026-10-01 and is too late for all earlier audits. `evidence_02` is too late for `case_28` despite containing a similar email string. Never let a later snapshot rewrite a past state.
- **Replica disagreement:** `evidence_54` has `account_005` for Leila in `customer_profiles_failover_replica`, absent from `customer_profiles_primary`. A primary-only query would falsely declare completion.
- **Active sync recreating data:** sample `case_15` finds `data_flow_9846` in `evidence_01`; its heartbeat says `enabled=true`, `scheduler_registered=true`, `last_run=success`. This is a live recreation path and must be disabled before downstream cleanup. Sample `case_29` similarly uses evidence `evidence_92` for flow `data_flow_3827`, alongside search, analytics and support copies.
- **Restore risk:** sample `case_17` finds `backup_3245` in `evidence_01`; the backup log says `restore_candidate_evaluated eligible=true deletion_block=false`. A prior `CHECK_RESTORE_ACCESS` event with a `SUCCESS` result is not proof that restore is blocked. Block the restore before relying on deleted source records.
- **Historical identifiers and hashes:** audit log fields include 107 email changes and 107 email-hash changes. In `case_10`, request email `nadia.ionescu@yahoo.com` resolves to current `user_10`, whose present email is `n.petrescu@yahoo.com`, through audit rows `audit_121`/`audit_122` and `audit_238`/`audit_239`. The chain also contains intermediate `nadia.petrescu@yahoo.com` and changed email hashes. Evidence must be searched using all known historical and current values, not only the current snapshot.
- **Claims contradicted by direct evidence:** in `case_10`, activity `activity_3596` reports successful deletion of `support_002` on 2026-09-02; `evidence_61` later records one row in the support replica for the historical email and `marker_found=false`. The activity result alone would miss the surviving copy. `evidence_61` is captured 2026-09-17 22:00:19Z, before that case's 2026-09-18 12:25Z audit.
- **Tombstone edge case:** sample `case_31` is compliant because stable `user_541` remains while direct identifiers are null. Sample `case_32` is incomplete because `tombstone_9178` still exposes PII; its correct action is redaction, not deletion of the stable reference.
- **Activity/evidence distinction:** `system_activity.csv` has 4,011 global events and result values `FAILED`, `PARTIAL`, `SUCCESS`, but these describe reported operations. Confirm actual state in evidence snapshots, logs and SQL; bind by user/resource/time and ignore unrelated rows.
- **Evidence type matters:** screenshots and documents are ordinary records, not explicit verdicts. SQL files may contain primary plus regional/reporting/failover copies. JSON/log exports mix relevant evidence with decoys. Use the manifest to locate a file, then inspect its contents and timestamp.

## Exploration exit

No implementation has been started. This file is the requested exploration artifact. Wait for the user to review it and authorize the next stage before writing anything under `code/`.
