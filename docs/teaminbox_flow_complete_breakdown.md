# TeamInbox email-intelligence Flow: complete technical breakdown

**Task:** BI1-T110  
**Validated:** 2026-07-21  
**Flow:** `TeamInbox to CRM Payload Test` (operator confirmed ON; controlled changes
validated with Test & Debug)

## Plain-language overview

An inbound TeamInbox email enters Zoho Flow. The Flow converts the webhook into one
predictable message shape, rejects messages that should not be processed, prevents a
previously stored message from being processed again, and looks for the sender in CRM.
It searches in a strict order: Contact first, Lead second, then Account by email domain.
The matched CRM context and safe email content are sent to Zia for analysis. Zia may
recommend an action, but it cannot perform one. A validator replaces all identity and
safety values with trusted Flow values. Finally, the Flow creates an
`AI_Recommendations` record in `Pending Review`. A human must approve it before a
separate execution Flow may create a CRM Task.

```text
TeamInbox email
  -> normalize and gate
  -> duplicate check
  -> Contact? / Lead? / Account domain?
  -> CRM context and snapshot
  -> controlled Zia request
  -> asynchronous Zia result
  -> trusted validation
  -> Pending Review recommendation
  -> human approval
  -> separate allow-listed executor (not deployed yet)
```

## Exact processing sequence

### 1. TeamInbox webhook

**Why:** starts the Flow when TeamInbox sends a `NEW_INBOUND_MESSAGE` event.

**Receives:** nested `from`, `to`, `cc`, `bcc`, `date`, `event`, and `content` maps,
plus `messageId`, `portalId`, `subject`, and `summary`.

**Connects to:** `normalize_teaminbox_payload`, passing the entire webhook payload as
a map—not an individual field.

### 2. Normalize the message

**Function:** `normalize_teaminbox_payload`

**Why:** downstream blocks should not depend directly on TeamInbox's nested payload.

**Important outputs:** `from_email`, `from_domain`, `message_id`,
`idempotency_key`, `body_html`, `event_name`, and `should_process`.

The key is deterministic:

```text
teaminbox:<portal_id>:<message_id>
```

### 3. Processing gate

`shouldProcess` is assigned from the normalized `should_process` boolean. Processing
continues only when the event is inbound and the recipient is not an AP/AR finance
mailbox. A false result stops the route safely.

### 4. Early duplicate guard

`check_ai_recommendation_exists` searches `AI_Recommendations` using the normalized
idempotency key. `exists=true` stops. `exists=false` continues.

This protects ordinary replay, as proven with `REGRESSION-LEAD-013`. It is not an
atomic datastore constraint: two simultaneous deliveries can still both pass before
either creates its record.

### 5. Contact lookup (highest precedence)

The native CRM Fetch Contact action receives normalized `from_email`. If it returns an
ID, `contactId` is populated and `Contact Found?` takes its True branch. Lead and
Account lookup do not run.

### 6. Lead lookup (second precedence)

This runs only when Contact lookup returns no ID.

The native Zoho Flow Fetch Lead action was proven defective on 2026-07-21: its saved
Email field—including a literal email—became `Email: ""` in the runtime input. It was
replaced by `fetch_lead_by_email`, which performs an exact CRM Lead email search and
returns the trusted Lead ID. The successful test returned `6719186000003163012`.

`leadId` receives the function result. `Lead Found?` routes True when it is nonblank.

### 7. Account-domain fallback (third precedence)

This runs only when neither Contact nor Lead matched. `fetch_account_by_domain` uses
the normalized sender domain and the CRM Account `Email_Domain` field. A match
populates `accountId`; `Account Found?` then takes its True branch.

### 8. Build trusted CRM context

`build_crm_context` receives sender identity plus the three possible IDs. It applies
the same precedence again and emits `match_status`, `match_type`, `matched_module`,
`matched_record_id`, and `match_method`. This object—not Zia—is the authority for the
eventual target module and record ID.

### 9. Build CRM snapshot

Route-specific enrichment is collected before `build_crm_snapshot`:

- Contact: open Deals, Cases, Tasks, Contact lifecycle, and linked Account.
- Lead: open Tasks and Lead status when CRM supplies one.
- Account: Account name/lifecycle and available open-record lists.

Empty related-record results are normalized to empty lists. A blank Lead Status is
allowed and does not prevent processing.

### 10. Build the controlled AI request

`build_ai_analysis_request` requires three maps:

```text
normalized_message = entire normalize function output
crm_context = same route's context output
crm_snapshot = same route's snapshot output
```

Mapping only `body_html` is invalid because `normalized_message` is a map. The builder
strips HTML into `body_text`, carries trusted CRM context, and adds the fixed policy:

```json
{
  "read_only": true,
  "human_approval_required": true,
  "closed_won_auto_execution_allowed": false,
  "qts_quote_generation_allowed": false
}
```

### 11. Trigger and fetch Zia asynchronously

The request is serialized as the Zia Query. Trigger returns `executionId`; after the
current one-minute delay, Fetch Zia Result must use that exact execution ID. A step ID
is not interchangeable with an execution ID.

### 12. Validate untrusted Zia output

`validate_zia_analysis_response` receives:

```text
raw_response = same route's Fetch Zia Result.response
trusted_request = entire same route build_ai_analysis_request output
```

The validator parses Zia JSON but restores trusted `message_id`, `idempotency_key`,
target module, and target record ID. It forces human approval and safe defaults. This
was visibly exercised when Zia returned quoted IDs such as
`'6719186000003163012'`; persistence still received the correct unquoted trusted ID.

### 13. Persist the recommendation

Each matched route has its own final CRM Create or Update Module Entry block. All must
map from that route's current validator output—not a copied or obsolete variable.

Required live mappings:

| CRM UI field | Value |
| --- | --- |
| `Idempotency_Key` (API name `Name`) | validated `idempotency_key` |
| `Message_ID` | validated `message_id` |
| `Target_Module` | validated recommendation target module |
| `Target_Record_ID` | validated recommendation target ID |
| `Recommendation_Type` | validated recommendation action |
| `Status` | constant `Pending Review` |
| `Requires_Approval` | validated safety value (forced true) |
| `Created_By_AI` | constant true |
| `Validation_Status` | constant `valid` |
| `Validated_Analysis_JSON` | entire validated result |
| `Raw_Zia_Response` | raw route-specific Zia response |
| `Review_Notes` | validated recommendation review notes |
| `Execution_Status` | `Not Started` |

Review/audit and execution-result fields remain blank during ingestion. Persistence
does not create a Task or perform the recommendation.

For the no-match route, the dedicated validator forces `manual_review`, clears both
target fields, marks context insufficient with `crm_record_not_found`, and persists
`Validation_Status=fallback`. This remains human-reviewable but cannot satisfy the
approved-action executor policy.

### 14. Human approval and separate execution

The CRM Blueprint controls `Pending Review -> Approved` and `Pending Review ->
Rejected`. The planned executor accepts only an approved, valid, AI-created,
approval-required `create_crm_task` recommendation targeting Contacts, Leads, or
Accounts. It never reads the raw Zia response and never sends email, changes a Deal to
Closed Won, or generates a quote. The executor exists in the repository but is not
deployed.

## Verified route evidence

| Route | Message | Trusted target | Persisted recommendation |
| --- | --- | --- | --- |
| Lead | `RECOVERY-LEAD-013` | Leads `6719186000003163012` | `6719186000003247001` |
| Contact | `REGRESSION-CONTACT-016` | Contacts `6719186000002999004` | `6719186000003249001` |
| Account | `REGRESSION-ACCOUNT-018` | Accounts `6719186000002999003` | `6719186000003250001` |
| No match | `REGRESSION-NOMATCH-020` | blank | `6719186000003254001` (`manual_review` / `fallback`) |

Lead and no-match replays found their existing recommendations and stopped at the
duplicate decision.

## Known limitations and required production work

1. The Flow is ON, but production behavior has not been fully characterized; at least
   one natural TeamInbox execution occurred before the 2026-07-21 corrections.
2. `Accounts` is still missing from the `Target_Module` picklist metadata even though
   API writes accept and store it.
3. Ingestion duplicate checking is read-then-write, not atomically unique.
4. The fixed Zia delay should become bounded polling with a safe timeout path.
5. The approved-action executor is implemented locally but not deployed or live-tested.
6. Live custom-function source and repository source must be reconciled after every
   Flow edit; the repository copy was reconciled to the live `Lead_Status` field on
   2026-07-21.

## Technical summary

The ingestion Flow now reliably converts TeamInbox webhook data into a normalized
contract, applies an early replay guard, resolves CRM identity with deterministic
Contact-before-Lead-before-Account precedence, builds trusted CRM context, invokes Zia
as a read-only asynchronous analyst, validates all AI output against trusted IDs and
safety rules, and persists a human-reviewable recommendation. Contact, Lead, Account,
no-match, and ordinary duplicate replay paths are proven in Test & Debug. The original blocker
was isolated to Zoho Flow's native Fetch Lead action dropping its Email input at
runtime; a direct CRM search custom function is the validated replacement. Production
production readiness still depends on the documented schema, concurrency, timeout,
and executor-deployment work.
