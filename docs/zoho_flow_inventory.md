# Zoho Flow inventory — BI1-T110

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Last updated:** 2026-07-19

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
| `TeamInbox to CRM Payload Test` | **LIVE**, switched **OFF**, exercised via Test & Debug | Ingestion: webhook → normalize → dedup → CRM match → context → Zia → validate → persist |
| `Execute Approved AI Recommendation` | **PLANNED** | Approved-action execution; see `execute_approved_recommendation_flow.md` |

## Custom functions

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `normalize_teaminbox_payload` | `(map payload)` → map | LIVE / REPO | `scripts/normalize_teaminbox_payload.deluge` |
| `fetch_account_by_domain` | `(string domain)` → map | LIVE / REPO | `scripts/fetch_account_by_domain.deluge` |
| `fetch_open_deals_for_contact` | `(string contact_id)` → list | LIVE / REPO | `scripts/fetch_open_deals_for_contact.deluge` |
| `fetch_open_cases_for_contact` | `(string contact_id)` → list | LIVE / REPO | `scripts/fetch_open_cases_for_contact.deluge` |
| `fetch_open_tasks_for_contact` | `(string contact_id)` → list | LIVE / REPO | `scripts/fetch_open_tasks_for_contact.deluge` |
| `build_crm_context` | `(map match_input)` → map | LIVE / REPO | `scripts/build_crm_context.deluge` |
| `build_crm_snapshot` | `(map context, …)` → map | LIVE / REPO | `scripts/build_crm_snapshot.deluge` |
| `build_ai_analysis_request` | `(map message, map context, map snapshot)` → map | LIVE / REPO | `scripts/build_ai_analysis_request.deluge` |
| `validate_zia_analysis_response` | `(string raw_response, map trusted_request)` → map | LIVE / REPO | `scripts/validate_zia_analysis_response.deluge` |
| `check_ai_recommendation_exists` | `(string idempotency_key)` → map | **LIVE, NOT IN REPO** | — |
| `persist_ai_recommendation` | `(map validated_analysis)` → map | **DRAFT — cannot work as written** | `scripts/persist_ai_recommendation.deluge` |
| `execute_approved_recommendation` | `(string ai_recommendation_record_id)` → map | REPO, undeployed | `scripts/execute_approved_recommendation.deluge` |

### Two gaps in this table

1. **`check_ai_recommendation_exists` is deployed but has no repository source.** Its
   Deluge must be exported from Zoho Flow and committed. Until then the ingestion
   duplicate guard — verified working live — exists only inside Zoho. Note it is a
   read-then-write guard, not a datastore constraint: see the idempotency note below.
2. **`persist_ai_recommendation` is stale.** It writes ~20 fields that do not exist on
   the live module, uses `Target_Record_Id` where the live name is `Target_Record_ID`,
   and writes to a non-existent `Idempotency_Key` API name (the live API name is
   `Name`). The deployed persistence step therefore does **not** match this file.
   Reconcile against `live_module_inspection_2026-07-19.md`, or export the deployed
   version and replace this draft.

## The idempotency key: label vs API name

The CRM field **labelled** `Idempotency_Key` has the **API name** `Name`
(`6719186000003163039`, text/120). Every script, COQL query, and API payload must use
`Name`. It is **not unique**, so ingestion deduplication relies on the Flow-level
`check_ai_recommendation_exists` guard rather than a datastore constraint, and
concurrent ingestion of the same message is therefore **not datastore-enforced**.

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
| 9 | `Fetch Lead by Sender Email` | CRM action |
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
| 20 | `Persist AI Recommendation - [Match]` | Custom function (per route) |

`[Match]` is one of `Contact`, `Lead`, `Account` — blocks 13–20 are duplicated per
route.

### Routing

- Blocks 5–6 form the durable early duplicate guard. **Verified live:** `exists=true`
  stops processing; `exists=false` follows the Default path and continues.
- Match precedence is Contact email → Lead email → Account sender-domain → no match.
- The no-match branch has no defined behaviour yet (open decision).

### Variable mappings that have caused defects

Recorded because each was a real, diagnosed failure:

| Mapping | Correct value | Defect seen |
| --- | --- | --- |
| `Fetch Zia Analysis Result` input | the trigger block's **`executionId`** | A step ID was mapped instead, so the fetch never resolved |
| Route-specific `Query` | the matching route's variable | A copied block retained a null Query |
| `Validate Zia Analysis` inputs | the same route's request/response | Copied blocks pointed at another route's variables |

Route duplication is the root cause of all three. Verify every copied block's variable
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

The `Target_Module` picklist defines only `-None-`, `Contacts`, `Leads`, `Deals` — so
the persisted `Accounts` value is an out-of-list write. This is a metadata mismatch to
reconcile, not a blocked route. See finding 1 in `live_module_inspection_2026-07-19.md`.

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

1. Export `check_ai_recommendation_exists` from Zoho Flow and commit it.
2. Export the deployed persistence function and replace the stale
   `persist_ai_recommendation.deluge` draft.
3. Capture exact input/output schemas for each custom function; only signatures are
   recorded today.
4. Record deployment/version notes per function once the Flow structure is frozen.
