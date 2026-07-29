# Zoho Flow inventory — BI1-T110

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Last updated:** 2026-07-25

Source-controlled inventory of every Zoho Flow custom function, block label, route,
variable mapping, and sanitized test payload currently documented by this repository.
Its purpose is to stop the automation logic from being islanded inside Zoho Flow.

## Provenance legend

| Marker | Meaning |
| --- | --- |
| **LIVE** | Verified against Zoho with a real response |
| **REPO** | Source lives in this repository |
| **REPO-AHEAD** | Repository source is newer than the deployed function — **must be redeployed** |
| **DRAFT** | In the repository but not deployable as written |
| **DEAD** | Superseded; retained only until deleted |
| **PLANNED** | Documented only; nothing built |

**This document is the deploy gate.** Before deploying, check the `State` column: every
**REPO-AHEAD** row is a pending redeploy. Update this file in the same change that deploys.

## Flows

| Flow name | State | Purpose |
| --- | --- | --- |
| Single-path ingestion flow | **LIVE and ON** (cut over 2026-07-22) | The ingestion flow. Webhook → normalize → gate → dedup → match → context → association → snapshot → Zia poll → validate → persist. ~26 blocks. See `docs/single_path_refactor_spec.md` |
| `TeamInbox to CRM Payload Test` | **RETIRED; toggled OFF** (superseded 2026-07-22) | The former 4-branch ingestion flow (~80 blocks, Zia section duplicated per route). Kept OFF, not deleted, as a rollback path. Its per-route duplication was the root cause of every cross-route variable-contamination defect recorded below |
| `Execute Approved AI Recommendation` | **LIVE and ON** | Approval-side execution. Now runs three functions in order: `materialize_pending_lead` → `associate_email_to_crm_record` → `execute_approved_recommendation` (deferred-lead blocks added 2026-07-25). See `execute_approved_recommendation_flow.md` |
| `KB Website Form to AI Recommendation` | **LIVE and ON** (2026-07-23) | Form relay: `KB_Website_Form` submission → `build_form_intake_payload` builds a TeamInbox-shaped payload → Send Webhook POSTs it into the ingestion engine's webhook. Does no AI work itself; it feeds `TeamInbox to CRM Payload`. Verified one submission → exactly one recommendation (records `6719186000003399001`, `6719186000003401001`, `6719186000003358008`; 2026-07-23). |
| `Quote Intake` | **OUT OF SCOPE; toggled OFF 2026-07-23** | Not part of BI1-T110. Older flow: `KB_Website_Form` → allocate quote number via `kinetic-quote.replit.app/api/allocate-number` → append Zoho Sheet ledger row → create a `Proposal/Price Quote` Deal. Shares the form trigger with T110, so it was turned OFF to stop polluting T110 test data with quote Deals. Re-enable only when the QTS application is live. Deal `Account Name` mapping was corrected from `${trigger.SingleLine1}` (empty → "required field not found") to `${trigger.SingleLine}` on 2026-07-23. |

## Custom functions

Every signature below was read from the repository source on 2026-07-25, not from memory.
All sources are in `scripts/`; the `.deluge` extension is omitted from the Source column.

### On the live ingestion path

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `normalize_teaminbox_payload` | `(map payload)` → map | LIVE / REPO | `normalize_teaminbox_payload` |
| `check_ai_recommendation_exists` | `(string idempotency_key)` → map | LIVE / REPO | `check_ai_recommendation_exists` |
| `resolve_crm_match` | `(string from_email, string from_domain)` → map | LIVE / REPO | `resolve_crm_match` |
| `ensure_crm_match` | `(map normalized, map resolve_result)` → map | **REPO-AHEAD** | `ensure_crm_match` |
| `fetch_open_related` | `(map match)` → map | LIVE / REPO | `fetch_open_related` |
| `build_crm_context` | `(string from_email, string from_domain, string contact_id, string lead_id, string account_id, map pending_contact)` → map | LIVE / REPO | `build_crm_context` |
| `associate_email_to_crm_record` | `(map normalized_message, map crm_context)` → map | LIVE / REPO | `associate_email_to_crm_record` |
| `build_crm_snapshot` | `(string contact_id, string lead_id, string account_id, list open_deals, list open_cases, list open_tasks)` → map | LIVE / REPO | `build_crm_snapshot` |
| `build_ai_analysis_request` | `(map message, map context, map snapshot)` → map | LIVE / REPO | `build_ai_analysis_request` |
| `is_zia_analysis_complete` | `(string status_value, string response_value)` → map | LIVE / REPO | `is_zia_analysis_complete` |
| `build_zia_timeout_fallback` | `(map trusted_request)` → map | LIVE / REPO | `build_zia_timeout_fallback` |
| `validate_zia_analysis_response_tagged` | `(string raw_response, map trusted_request)` → map | **REPO-AHEAD** | `validate_zia_analysis_response_tagged` |
| `persist_recommendation` | `(map validated)` → map | LIVE / REPO | `persist_recommendation` |
| `notify_cliq_new_recommendation` | `(string recommendation_id)` → void | LIVE / REPO | `notify_cliq_new_recommendation` |

### On the live approval / execution path

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `materialize_pending_lead` | `(string ai_recommendation_record_id)` → map | LIVE / REPO | `materialize_pending_lead` |
| `associate_email_to_crm_record` | `(map normalized_message, map crm_context)` → map | LIVE / REPO | same function, second call site |
| `execute_approved_recommendation` | `(string ai_recommendation_record_id)` → map | LIVE / REPO | `execute_approved_recommendation` |

### Form intake

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `build_form_intake_payload` | `(string form_id, string submitter_email, string first_name, string last_name, string company, string phone, string area_of_interest, string comments, string submitted_at_ms, string intake_address)` → map | LIVE / REPO | `build_form_intake_payload` |
| `normalize_form_entry` | `(string form_id, string submitter_email, string first_name, string last_name, string company, string phone, string area_of_interest, string comments, string submitted_at)` → map | REPO only — not wired | `normalize_form_entry` |

`normalize_form_entry` is the intended replacement for the `build_form_intake_payload`
fake-email relay hop (`unified_intake_architecture.md` §2). The retirement is **not done**;
the form still goes through the relay.

### Superseded by the single-path flow — still deployed, no longer called

Retained live so the OFF 4-branch flow remains a rollback path. Do not edit.

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `fetch_lead_by_email` | `(string email)` → string Lead ID | LIVE / REPO | `fetch_lead_by_email` |
| `fetch_account_by_domain` | `(string domain)` → string Account ID | LIVE / REPO | `fetch_account_by_domain` |
| `fetch_open_deals_for_contact` | `(string contact_id)` → list | LIVE / REPO | `fetch_open_deals_for_contact` |
| `fetch_open_cases_for_contact` | `(string contact_id)` → list | LIVE / REPO | `fetch_open_cases_for_contact` |
| `fetch_open_tasks_for_contact` | `(string contact_id)` → list | LIVE / REPO | `fetch_open_tasks_for_contact` |
| `fetch_open_tasks_for_lead` | `(string lead_id)` → list | LIVE / REPO | `fetch_open_tasks_for_lead` |
| `validate_zia_analysis_response` | `(string raw_response, map trusted_request)` → map | LIVE / REPO | `validate_zia_analysis_response` |
| `validate_zia_analysis_response_no_match` | `(string raw_response, map trusted_request)` → map | LIVE / REPO | `validate_zia_analysis_response_no_match` |

### Built but not wired to any flow

| Function | Signature | State | Source |
| --- | --- | --- | --- |
| `advance_lead_on_first_outbound` | `(string lead_id)` → map | REPO only | `advance_lead_on_first_outbound` |
| `create_lead_for_unmatched` | `(map normalized)` → map | **DEAD** | `create_lead_for_unmatched` |

`advance_lead_on_first_outbound` backs the open outbound-response Lead-lifecycle item; no
trigger exists for it yet. `create_lead_for_unmatched` is dead — Model C replaced eager
lead creation with `materialize_pending_lead`, `ensure_crm_match` is read-only, and it has
zero references from `scripts/` or `tests/`. It also still contains a literal `\n`. Delete
it once the 4-branch rollback path is formally abandoned.

## Pending redeploys (the gate)

Two functions are **REPO-AHEAD** as of 2026-07-25 — the repository is newer than live:

| Function | What the redeploy delivers |
| --- | --- |
| `ensure_crm_match` | Stops collapsing misses to `"Unknown"`; drops the email-local fallback so it cannot pre-empt Zia extraction |
| `validate_zia_analysis_response_tagged` | Overlays Zia's `contact` object onto blank fields, then applies the email-domain fallback |

**Blocked on a live Zia agent change.** Agent `28302000000011001` must add a `contact`
object (`first_name` / `last_name` / `company`) to its response schema and instructions.
Until it does, the extraction code is a no-op that falls through to the domain fallback.
Full context and the exact schema text are in `STATUS.md`.

### Notes

1. The stale `persist_ai_recommendation.deluge` draft (wrote ~20 non-existent fields,
   wrong API names) was **retired and deleted** on 2026-07-22. The retired 4-branch flow
   persisted with route-specific Zoho CRM **Create or update module entry** actions; the
   live single-path flow persists with `persist_recommendation` (a V8
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
(returns the existing record id, `duplicate=true`). The field was added with
`zoho_crm_admin.py setup-ingestion-metadata --apply` and is **live and validated since
2026-07-23** — confirmed by CRM read on record `6719186000003380001`, carrying
`Ingestion_Key = teaminbox:901489292:1784900000000119001`.

Execution-stage safety does not depend on this field — it uses a conditional
`If-Unmodified-Since` claim keyed on `Modified_Time`.

## Ingestion Flow — live block order (single-path)

The 4-branch block table that stood here described the flow that was toggled OFF on
2026-07-22 and is recoverable from git history. The live order is:

| # | Block | Type |
| --- | --- | --- |
| 1 | `TeamInbox Inbound Webhook` | Trigger |
| 2 | `normalize_teaminbox_payload` | Custom function |
| 3 | `Processing Gate - Should Process?` | Decision — Default STOPs |
| 4 | `check_ai_recommendation_exists` | Custom function |
| 5 | `Recommendation Already Exists?` | Decision — true STOPs |
| 6 | `resolve_crm_match` | Custom function |
| 7 | `ensure_crm_match` | Custom function — read-only; emits `pending_lead` when unmatched |
| 8 | `fetch_open_related` | Custom function |
| 9 | `build_crm_context` | Custom function |
| 10 | `associate_email_to_crm_record` | Custom function — no-ops on a pending lead |
| 11 | `build_crm_snapshot` | Custom function |
| 12 | `build_ai_analysis_request` | Custom function |
| 13 | `Trigger Zia Analysis` | Zia Agent, async |
| 14 | `Wait for Zia Analysis` | Delay |
| 15 | `Fetch Zia Analysis Result` | Zia Agent fetch |
| 16 | `is_zia_analysis_complete` → `Zia Complete? 1` | Custom function + Decision |
| 17 | retry: Delay → fetch → `is_zia_analysis_complete` → `Zia Complete? 2` | Bounded second attempt |
| 18 | `build_zia_timeout_fallback` | Custom function — Default branch of `Zia Complete? 2` |
| 19 | `validate_zia_analysis_response_tagged` | Custom function — three call sites |
| 20 | `persist_recommendation` | Custom function — three terminal call sites |
| 21 | `notify_cliq_new_recommendation` | Custom function |

Blocks 19–20 appear three times — once per terminal branch (complete-on-first-fetch,
complete-on-retry, timeout). Decision branches never re-merge in Zoho Flow, so three
terminal persist points are structural, not duplication of the kind the 4-branch flow had:
each is a one-line function call, not a hand-mapped 13-field Create block.

The exact block *labels* and variable suffixes on the live canvas are not mirrored here —
only the order and the functions. Verify labels in the Flow UI before editing.

## Approval Flow — live block order

Runs on Blueprint approval of an `AI_Recommendations` record:

| # | Block | Purpose |
| --- | --- | --- |
| 1 | `materialize_pending_lead` | Creates the deferred Lead, owned by the approver. No-ops on an already-matched record |
| 2 | `associate_email_to_crm_record` | Attaches the source email to the Lead just created. Inputs are `${materializePendingLead_N.normalized_message}` and `${materializePendingLead_N.crm_context}`; on a matched or rerun record both maps come back empty and it no-ops |
| 3 | `execute_approved_recommendation` | Claims the recommendation and marks `Executed` — **does not** create a CRM Task (Bill 2026-07-28) |

Order matters — the Lead must exist before the email can attach to it. The executor only
finalizes bookkeeping after materialize + associate. **Known limitation:** the association
payload is emitted only on `status = "created"`, so if block 1 succeeds and block 2 fails,
a rerun returns `target_already_set` and will not retry the association. Attach the email
by hand.

### Routing

- Blocks 4–5 of ingestion form the durable early duplicate guard. **Verified live:**
  `exists=true` stops processing; `exists=false` follows the Default path and continues.
- Match precedence is Contact email → Lead email → Account sender-domain → deferred lead.
- The processing gate has four skip conditions: non-inbound event, finance inbox, internal
  sender, and `is_automated_sender` (no-reply / DMARC robots, added 2026-07-25).
- An unmatched sender no longer produces a bare `manual_review`. `ensure_crm_match` emits a
  `pending_lead`, the recommendation persists as `Pending Review`, and the Lead is created
  **only on approval** — a rejection creates no Lead and no Task.

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
3. ~~Mark the 4-branch flow retired and promote the single-path functions to LIVE.~~
   Done 2026-07-25.
4. Mirror the live block *labels* and variable suffixes for the single-path and approval
   flows. Only order and function names are recorded, so a copied-block variable defect of
   the kind tabled above would not be caught by reading this file.
5. Delete `create_lead_for_unmatched` once the 4-branch rollback path is abandoned, and
   retire `build_form_intake_payload` in favour of `normalize_form_entry`.
