# Zoho Flow inventory — BI1-T110

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Last updated:** 2026-07-21

Source-controlled inventory of every Zoho Flow custom function, block label, route,
variable mapping, and sanitized test payload currently documented by this repository.
Its purpose is to stop the automation logic from being islanded inside Zoho Flow.

## Provenance legend

| Marker | Meaning |
| --- | --- |
| **LIVE** | Verified against Zoho with a real response |
| **REPO** | Source lives in this repository |
| **DRAFT** | In the repository but not deployable as written |
| **PLANNED** | Documented only; nothing built |

## Flows

| Flow name | State | Purpose |
| --- | --- | --- |
| `TeamInbox to CRM Payload Test` | **LIVE and ON**; all four routes carry completion-check + bounded retry + safe-timeout (2026-07-22) | Ingestion (4-branch): webhook → normalize → dedup → CRM match → context → Zia poll → validate → persist |
| Single-path ingestion flow | **BUILT and validated end-to-end (2026-07-22)** | Consolidated one-path equivalent of the 4-branch flow; see `docs/single_path_refactor_spec.md` |
| `Execute Approved AI Recommendation` | **LIVE and ON** | Approved-action execution; verified creating a CRM Task from an abstracted-flow record on 2026-07-22. See `execute_approved_recommendation_flow.md` |

## Custom functions

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `normalize_teaminbox_payload` | `(map payload)` → map | LIVE / REPO | `scripts/normalize_teaminbox_payload.deluge` |
| `fetch_lead_by_email` | `(string email)` → string Lead ID | LIVE / REPO | `scripts/fetch_lead_by_email.deluge` |
| `fetch_account_by_domain` | `(string domain)` → string Account ID | LIVE / REPO | `scripts/fetch_account_by_domain.deluge` |
| `fetch_open_deals_for_contact` | `(string contact_id)` → list | LIVE / REPO | `scripts/fetch_open_deals_for_contact.deluge` |
| `fetch_open_cases_for_contact` | `(string contact_id)` → list | LIVE / REPO | `scripts/fetch_open_cases_for_contact.deluge` |
| `fetch_open_tasks_for_contact` | `(string contact_id)` → list | LIVE / REPO | `scripts/fetch_open_tasks_for_contact.deluge` |
| `fetch_open_tasks_for_lead` | `(string lead_id)` → list | LIVE / REPO | `scripts/fetch_open_tasks_for_lead.deluge` |
| `build_crm_context` | `(string from_email, string from_domain, string contact_id, string lead_id, string account_id)` → map | LIVE / REPO | `scripts/build_crm_context.deluge` |
| `build_crm_snapshot` | `(string contact_id, string lead_id, string account_id, list open_deals, list open_cases, list open_tasks)` → map | LIVE / REPO | `scripts/build_crm_snapshot.deluge` |
| `build_ai_analysis_request` | `(map message, map context, map snapshot)` → map | LIVE / REPO | `scripts/build_ai_analysis_request.deluge` |
| `validate_zia_analysis_response` | `(string raw_response, map trusted_request)` → map | LIVE / REPO | `scripts/validate_zia_analysis_response.deluge` |
| `validate_zia_analysis_response_no_match` | `(string raw_response, map trusted_request)` → map | LIVE / REPO | `scripts/validate_zia_analysis_response_no_match.deluge` |
| `check_ai_recommendation_exists` | `(string idempotency_key)` → map | LIVE / REPO | `scripts/check_ai_recommendation_exists.deluge` |
| `is_zia_analysis_complete` | `(string status_value, string response_value)` → map | LIVE / REPO | `scripts/is_zia_analysis_complete.deluge` |
| `build_zia_timeout_fallback` | `(map trusted_request)` → map | LIVE / REPO | `scripts/build_zia_timeout_fallback.deluge` |
| `execute_approved_recommendation` | `(string ai_recommendation_record_id)` → map | LIVE / REPO | `scripts/execute_approved_recommendation.deluge` |

### Single-path refactor functions (`scripts/single_path/`)

These back the consolidated one-path flow proven end-to-end on 2026-07-22. See
`docs/single_path_refactor_spec.md`.

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `resolve_crm_match` | `(string from_email, string from_domain)` → map | REPO, single-path | `scripts/single_path/resolve_crm_match.deluge` |
| `fetch_open_related` | `(map match)` → map | REPO, single-path | `scripts/single_path/fetch_open_related.deluge` |
| `validate_zia_analysis_response_tagged` | `(string raw_response, map trusted_request)` → map | REPO, single-path | `scripts/single_path/validate_zia_analysis_response_tagged.deluge` |
| `persist_recommendation` | `(map validated)` → map | REPO, single-path | `scripts/single_path/persist_recommendation.deluge` |

### Notes

1. The stale `persist_ai_recommendation.deluge` draft (wrote ~20 non-existent fields,
   wrong API names) was **retired and deleted** on 2026-07-22. The live 4-branch flow
   persists with route-specific Zoho CRM **Create or update module entry** actions; the
   single-path flow persists with `single_path/persist_recommendation` (a V8
   `invokeurl` create — `Validated_Analysis_JSON` is capped at 2000 chars and
   `Raw_Zia_Response` is stored separately, not embedded).

## The idempotency key: label vs API name

The CRM field **labelled** `Idempotency_Key` has the **API name** `Name`
(`6719186000003163039`, text/120). Every script, COQL query, and API payload must use
`Name`. `Name` itself is **not unique**; the Flow-level `check_ai_recommendation_exists`
guard is only a cost-saving fast path (it short-circuits before Zia when a duplicate is
already indexed), not the correctness mechanism.

Datastore-enforced deduplication is provided by a separate **unique** field
`Ingestion_Key` (text/255, unique case-insensitive), which `persist_recommendation`
writes with the same `teaminbox:<portal>:<message_id>` key. A concurrent duplicate
create is rejected with `DUPLICATE_DATA`, which persist treats as "already recorded"
(returns the existing record id, `duplicate=true`). Add the field with
`zoho_crm_admin.py setup-ingestion-metadata --apply`. (Code landed 2026-07-23; effective
once the operator adds the field and deploys the updated function.)

Execution-stage safety does not depend on this field — it uses a conditional
`If-Unmodified-Since` claim keyed on `Modified_Time`.

## Ingestion Flow — block labels in order

| # | Block label | Type |
| --- | --- | --- |
| 1 | `TeamInbox Inbound Webhook` | Trigger |
| 2 | `normalize_teaminbox_payload` | Custom function |
| 3 | `Set Variable - shouldProcess` | Variable |
| 4 | `Processing Gate - Should Process?` | Decision |
| 5 | `check_ai_recommendation_exists` | Custom function |
| 6 | `Recommendation Already Exists?` | Decision |
| 7 | `Fetch Contact by Sender Email` | CRM action |
| 8 | `Contact Found?` | Decision |
| 9 | `fetch_lead_by_email` | Custom function |
| 10 | `Lead Found?` | Decision |
| 11 | `Fetch Account by Sender Domain` | Custom function |
| 12 | `Account Found?` | Decision |
| 13 | `Build CRM Context - [Match]` | Custom function (per route) |
| 14 | `Build CRM Snapshot - [Match]` | Custom function (per route) |
| 15 | `Build AI Analysis Request - [Match]` | Custom function (per route) |
| 16 | `Trigger Zia Analysis - [Match]` | Zia Agent, async |
| 17 | `Wait for Zia Analysis - [Match]` | Delay |
| 18 | `Fetch Zia Analysis Result - [Match]` | Zia Agent fetch |
| 19 | `Validate Zia Analysis - [Match]` | Custom function (per route) |
| 20 | `Create or update module entry` | Zoho CRM action (per route) |

`[Match]` is one of `Contact`, `Lead`, `Account`, or `No Match` — blocks 13–20 are
duplicated per route. The no-match route uses its dedicated validator function because
Zoho duplicated the shared function's parameter metadata when a new action was added.

### Routing

- Blocks 5–6 form the durable early duplicate guard. **Verified live:** `exists=true`
  stops processing; `exists=false` follows the Default path and continues.
- Match precedence is Contact email → Lead email → Account sender-domain → no match.
- No match produces `manual_review`, blank trusted target fields,
  `Validation_Status=fallback`, and a `Pending Review` recommendation. It cannot pass
  the approved-action executor's allow-list.

### Variable mappings that have caused defects

Recorded because each was a real, diagnosed failure:

| Mapping | Correct value | Defect seen |
| --- | --- | --- |
| `Fetch Zia Analysis Result` input | the trigger block's **`executionId`** | A step ID was mapped instead, so the fetch never resolved |
| Route-specific `Query` | the matching route's variable | A copied block retained a null Query |
| `Validate Zia Analysis` inputs | the same route's request/response | Copied blocks pointed at another route's variables |
| `fetch_lead_by_email.email` | normalized `from_email` | Native connector discarded even a literal Email at runtime; retired and replaced by the custom function |
| `build_ai_analysis_request.normalized_message` | entire normalized-message map | Lead copy mapped only `body_html`, causing a map/string type error |
| Route persistence scalars | current route validator output | Contact/Lead copies retained obsolete validator variable names |

Route duplication is the root cause of these mapping defects. Verify every copied block's variable
names and route label.

## Zia Agent

| Property | Value |
| --- | --- |
| Name | `Kinetic Bridge Email Intelligence Agent` |
| Agent ID | `28302000000011001` |
| Active version | 3 (`28302000000011050`) |
| Model | Zoho-hosted Qwen Text 14b |
| Connectors / knowledge base | none |
| Posture | Read-only analyst; treats email and CRM content as untrusted; one JSON object out; human approval preserved |

## Sanitized test payloads and verified outputs

| Route | Test identity | Verified result |
| --- | --- | --- |
| Contact | `blake@kinetic-bridge.com` | Contacts `6719186000002999004` |
| Lead | `bi1-t110-lead-only@example.com` | Leads `6719186000003163012` |
| Account-domain | `account-fallback-test@kinetic-bridge.com` | Accounts `6719186000002999003` |
| No match | `no-match@bi1-t110-no-match.invalid` | `match_status: no_match`, `match_type: none` |
| Non-inbound event | malformed / incorrectly wrapped test data | `should_process: false` |

Verified Contact snapshot: lifecycle `Quoted`; Account `TEST CO`; open Deal
`Blake Test 1` (`6719186000003070020`), stage `Negotiation/Review`, amount `3172.41`,
closing `2026-07-31`; no open Cases or Tasks.

Verified validated-analysis results: Contact / Lead / Account routes each returned
`create_crm_task` against their trusted target ID with human approval required and an
empty conflicts list. Final Account validation: message ID `1784333133430110834`,
target `Accounts` / `6719186000002999003`.

### Persistence and approval records

| Record | Idempotency key (label `Idempotency_Key`, API name `Name`) | Outcome |
| --- | --- | --- |
| `6719186000003181001` | `teaminbox:901489292:1784333133430111002` | Pending Review; `Target_Module` = **`Accounts`**, `Target_Record_ID` = `6719186000002999003` — proves the Account route persists |
| `6719186000003183001` | `teaminbox:901489292:1784333133430111003` | Approved; reviewer audit fields populated; no CRM action taken |
| `6719186000003185001` | `teaminbox:901489292:1784333133430111004` | Rejected; reviewer audit fields populated; no CRM action taken |
| `6719186000003254001` | `teaminbox:901489292:REGRESSION-NOMATCH-020` | Pending Review; `manual_review`; fallback validation; blank target; duplicate replay stopped early |

Current CRM field-editor UI inspection on 2026-07-21 confirms the `Target_Module`
picklist defines `Contacts`, `Leads`, `Deals`, and `Accounts`. The 2026-07-19 API
metadata result that omitted `Accounts` is retained as historical evidence but is
superseded as current-state evidence. No picklist change is required.

## CRM Blueprint

| Property | Value |
| --- | --- |
| Name | `AI Recommendation Review` |
| State | Published and active (**LIVE**) |
| Transitions | `Pending Review → Approved` via `Approve Recommendation`; `Pending Review → Rejected` via `Reject Recommendation` |
| Approval restrictions | `Requires_Approval` selected, `Created_By_AI` selected, `Validation_Status = valid`, `Recommendation_Type = create_crm_task` |
| Both transitions require | `Reviewed_By`, `Reviewed_At`, `Review_Notes` |
| Not verified | Whether any transition is API-invocable — see requirement 17 |

## Fixed execution policy

Asserted by `build_ai_analysis_request` and re-asserted by the executor:

- `read_only: true`
- `human_approval_required: true`
- `closed_won_auto_execution_allowed: false`
- `qts_quote_generation_allowed: false`

## Excluded from this repository, by policy

Webhook URLs, connection secrets, OAuth tokens, and debug endpoints are never
recorded here. Credentials for the inspection utility come from environment variables
only — see `execute_approved_recommendation_flow.md`.

## Outstanding inventory work

1. Capture exact input/output schemas for each custom function; only signatures are
   recorded today.
2. Record deployment/version notes per function once the Flow structure is frozen.
3. If the single-path flow is adopted as live, mark the 4-branch flow retired here and
   promote `scripts/single_path/` functions from "single-path" to "LIVE".
