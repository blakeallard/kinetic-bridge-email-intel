# Single-path refactor spec — TeamInbox → CRM Flow (BI1-T110)

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Last updated:** 2026-07-22

**Status: BUILT and validated end-to-end (2026-07-22).** The single-path flow was
assembled in Zoho Flow and exercised via Postman webhooks against every case: Contact /
Lead / Account / No-Match matching, internal-sender / finance-inbox / non-inbound gate
skips, dedup, email association, Zia completion + validate (valid path), timeout
fallback, and a `valid` persist. One record then flowed through Blueprint approval and
the executor to create a real CRM Task — proving full parity with the live 4-branch
flow, ingestion through execution.

The live 4-branch flow duplicates the Zia section across four routes (Contact, Lead,
Account, No-Match). This flow collapses it to **one linear path** by moving matching into
a function and putting the CRM persistence field-map inside a function. It reduces ~80
blocks to ~26 and eliminates the per-route Create-block duplication that caused every
cross-route variable contamination bug.

The four functions live in `scripts/single_path/`. This is a from-scratch restructure of
the front half of the flow, not an in-place tweak — it is a proven drop-in candidate,
not yet swapped in for the live flow.

## New / changed custom functions

### 1. `resolve_crm_match(string from_email, string from_domain)` → map  (NEW)
Replaces the nested `Fetch Contact` / `Contact Found?` / `fetch_lead_by_email` /
`Lead Found?` / `fetch_account_by_domain` / `Account Found?` decision tree (9 blocks → 1).
Runs Contact-by-email → Lead-by-email → Account-by-domain precedence internally. Returns:

```
{ match_status: "matched" | "no_match",
  match_type:   "contact" | "lead" | "account" | "none",
  matched_module: "Contacts" | "Leads" | "Accounts" | "",
  matched_record_id: "",
  contact_id: "", lead_id: "", account_id: "" }   // only the matched one populated
```

### 2. `fetch_open_related(map match)` → map  (NEW)
Collapses the four `fetch_open_*` blocks into one. Reads `match.contact_id` /
`match.lead_id`; returns `{ open_deals, open_cases, open_tasks }` (empty lists for blank ids).

### 3. `persist_recommendation(map validated)` → map  (NEW)
The single place the `AI_Recommendations` Create field-map lives. Writes via a **V8
`invokeurl` create** (`POST /crm/v8/AI_Recommendations`, connection
`zoho_crm_to_zoho_flow`) — the `zoho.crm.createRecord` task signature does not accept a
connection string cleanly, so raw `invokeurl` is used, matching
`associate_email_to_crm_record`. Two field constraints handled here:
`Validated_Analysis_JSON` is capped at **2000 chars** (a CRM field limit) with
`raw_zia_response` stripped out of it, and `Raw_Zia_Response` stores the raw text
separately (also capped at 2000). Returns `persisted`, `record_id`, `api_code`,
`api_message`, and `api_details` (the last exposes the rejected field on `INVALID_DATA`).
Ingestion idempotency is datastore-enforced: the key is also written to the unique
`Ingestion_Key` field, and a `DUPLICATE_DATA` create response is treated as "already
recorded" — `persisted=false`, `duplicate=true`, `record_id` set to the existing record
from `details.duplicate_record.id`. `persisted` is `true` only on a fresh `SUCCESS`
create.
Every terminal branch calls this one function instead of a hand-mapped Create block.

### 4. `validate_zia_analysis_response_tagged` → map  (NEW — a clone, not an in-place edit)

A copy of `validate_zia_analysis_response` that also emits `validation_status` =
`"valid"` if `match_status == "matched"` else `"fallback"`, and carries
`raw_zia_response` in the output. It is a **separate** function so the live 4-branch
flow's shared `validate_zia_analysis_response` is never modified. One validator serves
matched AND no-match (it already forces `manual_review` when unmatched), so the
single-path flow needs neither `_no_match` nor `_contact` clones.

Reused unchanged: `normalize_teaminbox_payload`, `check_ai_recommendation_exists`,
`build_crm_context`, `associate_email_to_crm_record`, `build_crm_snapshot`,
`build_ai_analysis_request`, `is_zia_analysis_complete`, `build_zia_timeout_fallback`.

## Block-by-block (every block, every field)

```
1  TeamInbox Inbound Webhook   (trigger)                          -> webhookTrigger
2  normalize_teaminbox_payload payload = ${webhookTrigger.payload} -> normalized
3  Decision Processing Gate    condition1: ${normalized.should_process} is true
       Default -> STOP ; condition1 v
4  check_ai_recommendation_exists  idempotency_key = ${normalized.idempotency_key} -> dupCheck
5  Decision Already Exists?    condition1: ${dupCheck.exists} is true
       condition1 -> STOP ; Default v
6  resolve_crm_match           from_email = ${normalized.from_email}
                               from_domain = ${normalized.from_domain}        -> match
7  fetch_open_related          match = ${match}                               -> related
8  build_crm_context           from_email  = ${normalized.from_email}
                               from_domain = ${normalized.from_domain}
                               contact_id  = ${match.contact_id}
                               lead_id     = ${match.lead_id}
                               account_id  = ${match.account_id}              -> context
9  associate_email_to_crm_record  normalized_message = ${normalized}
                                  crm_context        = ${context}             -> assoc
10 build_crm_snapshot          contact_id = ${match.contact_id}
                               lead_id    = ${match.lead_id}
                               account_id = ${match.account_id}
                               open_deals = ${related.open_deals}
                               open_cases = ${related.open_cases}
                               open_tasks = ${related.open_tasks}             -> snapshot
11 build_ai_analysis_request   normalized_message = ${normalized}
                               crm_context        = ${context}
                               crm_snapshot       = ${snapshot}               -> request
12 Trigger Zia Analysis        Query = ${request}                            -> ziaTrigger
13 Wait for Zia Analysis       (Delay ~60s)
14 Fetch Zia Result            Execution ID = ${ziaTrigger.executionId}      -> ziaFetch1
15 is_zia_analysis_complete    status_value = ${ziaFetch1.status}
                               response_value = ${ziaFetch1.response}        -> check1
16 Decision Zia Complete 1?    condition1: ${check1.complete} is true
     condition1 (True):
17     validate_zia_analysis_response  raw_response = ${check1.response}
                                       trusted_request = ${request}          -> validated
18     persist_recommendation          validated = ${validated}
     Default:
19     Wait for Zia Retry 1     (Delay ~60s)
20     Fetch Zia Result         Execution ID = ${ziaTrigger.executionId}     -> ziaFetch2
21     is_zia_analysis_complete status_value = ${ziaFetch2.status}
                                response_value = ${ziaFetch2.response}        -> check2
22     Decision Zia Complete 2? condition1: ${check2.complete} is true
         condition1 (True):
23         validate_zia_analysis_response raw_response = ${check2.response}
                                          trusted_request = ${request}        -> validated2
24         persist_recommendation         validated = ${validated2}
         Default (timeout):
25         build_zia_timeout_fallback     trusted_request = ${request}        -> timeout
26         persist_recommendation         validated = ${timeout}
```

## Persist field-map (inside `persist_recommendation`, written once)

| AI_Recommendations field (API name) | Source |
| --- | --- |
| `Name` (display title) | `"AI Recommendation: "` + title-cased action + `" - "` + title-cased `intent.category` |
| `Ingestion_Key` (unique) | `validated.idempotency_key` |
| `Message_ID` | `validated.message_id` |
| `Target_Module` | `validated.recommendation.target_module` |
| `Target_Record_ID` | `validated.recommendation.target_record_id` |
| `Recommendation_Type` | `validated.recommendation.action` (raw slug, unchanged) |
| `Requires_Approval` | `validated.safety.human_approval_required` |
| `AI_Category` | title-cased `validated.intent.category` |
| `AI_Summary` | `validated.intent.summary` |
| `AI_Rationale` | `validated.recommendation.rationale` |
| `Safety_Summary` (multi-select) | list derived from `validated.safety` flags + `conflicts` |
| `Validated_Analysis_JSON` | `validated` (whole map) |
| `Raw_Zia_Response` | `validated.raw_zia_response` |
| `Review_Notes` | `"Recommended Action: <action>" + LF + "Reason: " + review_notes` |
| `Status` | constant `Pending Review` |
| `Created_By_AI` | constant `true` |
| `Validation_Status` | `validated.validation_status` (`valid`/`fallback`) |
| `Execution_Status` | constant `Not Started` |

`Safety_Summary` value derivation (all five values must exist on the live picklist):

| Value | Emitted when |
| --- | --- |
| `Human Approval Required` | `safety.human_approval_required` is true (validator always sets it) |
| `Closed Won Change Requested` | `safety.closed_won_change_requested` is true |
| `Quote Generation Requested` | `safety.quote_generation_requested` is true |
| `Insufficient Context` | `safety.contains_insufficient_context` is true |
| `Conflict Detected` | `safety.conflicts` is non-empty |

**`Name` is no longer the idempotency key.** Idempotency is carried solely by the unique
`Ingestion_Key`. The Flow-level fast-path guard `check_ai_recommendation_exists` was
repointed to search `(Ingestion_Key:equals:<key>)` so it keeps matching replays before
Zia runs.

## Wins

- ~26 blocks vs ~80; one Zia polling section vs four.
- The Create field-map exists exactly once, in tested Deluge — the source of every
  contamination bug in the current build.
- One validator; no `_no_match` / `_contact` clones.
- Adding a fifth match type later touches only `resolve_crm_match` — zero flow-graph edits.

## Honest limit

Blocks 12-26 (trigger / wait / fetch / decision x2 + three `persist_recommendation` calls)
cannot shrink further: Zoho Flow can't do bounded waits inside Deluge, and decision
branches never re-merge, so three terminal persist points remain. But they are three
one-line function calls, not three 13-field Create blocks. That is the whole difference
between this and the current duplicated design.
