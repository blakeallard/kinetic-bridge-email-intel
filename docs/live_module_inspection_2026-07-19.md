# AI_Recommendations — live CRM inspection evidence

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Recorded:** 2026-07-19
**Purpose:** replace assumed field names with verified ones before implementing the
approved-action executor.

## How these reads were authenticated

Two different credential paths exist in this project, and earlier drafts of this
document conflated them:

| Path | Credentials | Status |
| --- | --- | --- |
| The `zoho` MCP server available to the agent session | Held by the MCP server under a pre-existing OAuth grant; never exposed to the agent or to this repository | **Available** — used for every read below |
| `scripts/zoho_crm_admin.py` | Reads `ZOHO_CRM_CLIENT_ID` / `ZOHO_CRM_CLIENT_SECRET` / `ZOHO_CRM_REFRESH_TOKEN` from the environment | **Unavailable** — all three are unset in this working environment |

So both statements are true and not in conflict: the reads below were authenticated
**through the MCP server**, while the standalone Python utility has **no credentials**
and has never been executed against Zoho. Nothing in this repository holds, prints, or
persists any credential value.

**Method:** read-only calls via the MCP server — `settings/modules`, `settings/fields`,
and single-record reads. No write was performed.

Everything below is **verified live Zoho behaviour**.

## Module

| Property | Value |
| --- | --- |
| API name | `AI_Recommendations` |
| Module ID | `6719186000003163020` |
| Internal name | `CustomModule1` |
| Generated type | `custom` |
| API supported | `true` |
| Blueprint supported | `true` |
| Display field | `Name` |
| Layout | `Standard` — `6719186000003163019` |
| Profiles | Administrator `6719186000000026011`, Standard `6719186000000026014` |

## Custom fields

| API name | Type | Length | Unique | Field ID |
| --- | --- | --- | --- | --- |
| `Name` (UI label **`Idempotency_Key`**) | text | 120 | no | `6719186000003163039` |
| `Message_ID` | text | 255 | no | `6719186000003163611` |
| `Status` | picklist | 120 | no | `6719186000003163668` |
| `Recommendation_Type` | text | 255 | no | `6719186000003163627` |
| `Target_Module` | picklist | 120 | no | `6719186000003163656` |
| `Target_Record_ID` | text | 255 | no | `6719186000003163619` |
| `Validation_Status` | picklist | 120 | no | `6719186000003163644` |
| `Requires_Approval` | boolean | 5 | no | `6719186000003163635` |
| `Created_By_AI` | boolean | 5 | no | `6719186000003163587` |
| `Raw_Zia_Response` | textarea | 2000 | no | `6719186000003163603` |
| `Validated_Analysis_JSON` | textarea | 2000 | no | `6719186000003163595` |
| `Reviewed_By` | userlookup | 50 | no | `6719186000003163790` |
| `Reviewed_At` | datetime | 120 | no | `6719186000003163782` |
| `Review_Notes` | textarea | 2000 | no | `6719186000003163807` |
| `Approved_Action_JSON` | textarea | 32000 | no | `6719186000003163799` |
| `Execution_Status` | picklist | 120 | no | `6719186000003163959` |
| `Execution_Key` | text | 255 | **yes** (case-insensitive) | `6719186000003163918` |
| `Executed_Task_ID` | text | 255 | no | `6719186000003163910` |
| `Execution_Started_At` | datetime | 120 | no | `6719186000003163934` |
| `Executed_At` | datetime | 120 | no | `6719186000003163926` |
| `Execution_Error` | textarea | 32000 | no | `6719186000003163950` |
| `Execution_Attempts` | integer | 9 | no | `6719186000003163942` |

`Name` is the only `system_mandatory` field. `Execution_Key` is the only unique field
in the module.

## Picklist values

| Field | Values |
| --- | --- |
| `Status` | `Pending Review`, `Approved`, `Rejected`, `Executed` |
| `Validation_Status` | `valid`, `invalid`, `fallback` |
| `Target_Module` | `Contacts`, `Leads`, **`Deals`** |
| `Execution_Status` | `Not Started`, `In Progress`, `Executed`, `Failed`, `Blocked` |

## Verified approved record `6719186000003183001`

| Field | Live value |
| --- | --- |
| `Name` | `teaminbox:901489292:1784333133430111003` |
| `Message_ID` | `1784333133430111003` |
| `Status` | `Approved` |
| `Requires_Approval` | `true` |
| `Created_By_AI` | `true` |
| `Validation_Status` | `valid` |
| `Recommendation_Type` | `create_crm_task` |
| `Target_Module` | `Contacts` |
| `Target_Record_ID` | `6719186000002999004` |
| `Reviewed_By` | `Blake Allard` (`6719186000002395001`) |
| `Reviewed_At` | `2026-07-19T18:00:00-07:00` |
| `Execution_Status` | `null` |
| `Execution_Key` | `null` |
| `Executed_Task_ID` | `null` |
| `Execution_Attempts` | `null` |
| `Validated_Analysis_JSON` | `null` |
| `Raw_Zia_Response` | populated (full Zia JSON) |

This record is a valid executor input: it satisfies every policy precondition and is
in an unclaimed execution state.

## Findings that contradict prior documentation

These are corrections, not opinions — each is backed by the API responses above.

### 1. `Target_Module` is a metadata/configuration mismatch — the Account route DOES persist

An earlier draft of this document claimed the Account route "cannot persist". **That
claim was wrong and is retracted.** Direct record read proves otherwise:

| Field | Value on record `6719186000003181001` |
| --- | --- |
| `Target_Module` | **`Accounts`** |
| `Target_Record_ID` | `6719186000002999003` |
| `Status` | `Pending Review` |
| `Validation_Status` | `valid` |
| `Recommendation_Type` | `create_crm_task` |

The Account route persisted `Accounts` successfully. The mismatch is between the
**stored data** and the **field metadata**:

The complete `Target_Module` picklist metadata — every entry, including `type` —
contains no `Accounts` option:

| `actual_value` | `display_value` | `id` | `type` |
| --- | --- | --- | --- |
| `-None-` | `-None-` | `6719186000003163659` | `used` |
| `Contacts` | `Contacts` | `6719186000003163655` | `used` |
| `Leads` | `Leads` | `6719186000003163657` | `used` |
| `Deals` | `Deals` | `6719186000003163658` | `used` |

There are no inactive or unused entries; `global_picklist` is `null` and
`pick_list_values_sorted_lexically` is `false`. So `Accounts` is stored as an
**out-of-list picklist value** — Zoho accepted the API write because the field does
not restrict values to the defined option set.

**Correct characterisation: a metadata/configuration mismatch, not a blocked route.**

Consequences of leaving it unreconciled:

- List-view filters, reports, and Kanban grouping on `Target_Module` will not offer
  or match `Accounts`.
- If an administrator ever enables "restrict to defined values" on this field, every
  future Account-route write breaks, and existing records may fail validation on edit.
- The UI may render the value as blank or invalid on the record detail page.

Remedy: add `Accounts` to the `Target_Module` picklist so metadata matches the data
already stored. `Deals` is a defined option that ingestion never produces — the
validator clamps the target to the matched CRM module — and the executor blocks it
regardless. Removing `Deals` is optional tidying.

The executor's supported values remain `Contacts`, `Leads`, `Accounts`; `Deals` stays
blocked.

### 2. The idempotency key field: UI label vs API name

An earlier draft said "there is no `Idempotency_Key` field". **That was imprecise and
is corrected here.** The field exists; its UI label and API name differ:

| Property | Value |
| --- | --- |
| CRM field **label** (what you see in the UI) | `Idempotency_Key` |
| CRM field **API name** (what code must use) | `Name` |
| Field ID | `6719186000003163039` |
| Type / length | text, 120 |
| Unique constraint | **no** |
| System mandatory | yes (it is the module's display field) |

It holds `teaminbox:<portal>:<message_id>` — for example
`teaminbox:901489292:1784333133430111003`.

Precise statement of the situation:

- The field is labelled `Idempotency_Key` and is used as the idempotency key.
- Its API name is `Name`. **Any Deluge, COQL, or API payload must say `Name`.**
- It is **not unique**, so the datastore does not enforce deduplication.
- Ingestion duplicate checking **does exist**, in Zoho Flow, via
  `check_ai_recommendation_exists` + the `Recommendation Already Exists?` decision.
  That guard is verified working.
- Because the guard is a read-then-write in Flow rather than a datastore constraint,
  **concurrent ingestion is not datastore-enforced**: two simultaneous deliveries of
  the same message can both pass the existence check and both create a record.

This does not affect execution-stage safety, which uses a conditional
(`If-Unmodified-Since`) claim — see the flow document.

Remedy (ingestion, outside this stage): add a unique constraint to `Name`, or add a
separate unique field and write the key to both.

### 3. `Validated_Analysis_JSON` is empty on verified records

Only `Raw_Zia_Response` is populated. The executor treats the raw response as
untrusted and never reads it, so Task content is built from the trusted scalar fields
only (`Message_ID`, `Target_*`, `Recommendation_Type`, `Review_Notes`, `Reviewed_*`).
Rationale, intent, and confidence are **not** available to the Task because they are
not persisted in structured fields.

### 4. `docs/ai_recommendations_module_spec.md` describes a module that does not exist

The spec predates the build and names ~20 fields absent from the live module
(`Idempotency_Key`, `Confidence_Band`, `Rationale`, `Intent_*`, `Opportunity_Signals`,
`Lifecycle_*`, `Conflicts`, `Schema_Version`, `Source`, `Human_Approval_Required`,
`Closed_Won_Change_Requested`, `Quote_Generation_Requested`,
`Contains_Insufficient_Context`, `Approver`, `Decision_*`), and uses
`Target_Record_Id` where the live name is `Target_Record_ID`.

Consequence: **`scripts/persist_ai_recommendation.deluge` cannot work as written.**
It writes fields that do not exist and reads a `Status` value (`Manual Review`) that
is not on the picklist. It is a stale draft, not deployed code.

### 5. `Execution_Attempts` has no API-enforced 0–3 range

The field metadata exposes no range constraint. The 0–3 limit is enforced by the
executor's policy gate (and, if configured, a CRM validation rule — not visible via
the fields API).

## Not verified

- **Blueprint transitions.** Transitions are exposed per record, not per module; the
  metadata API confirms only that the module supports Blueprints. Whether an
  API-invocable `Approved → Executed` transition exists is **unproven**, so the
  executor does not touch `Status`. Use `zoho_crm_admin.py inspect-blueprint` with a
  record id to settle this.
- **Task linkage for Leads and Accounts.** See the dedicated section below. Unresolved
  and unverified.

## Task linkage — conflicting evidence, unresolved

The BI1-T110 brief states the expected model is: *Contacts and Leads use `Who_Id`;
Accounts use `What_Id` with `$se_module = Accounts`.*

Two independent sources contradict the Leads half of that:

| Source | What it says |
| --- | --- |
| Live `Tasks` field metadata | `Who_Id` is a lookup whose `module.api_name` is **`Contacts`** — it is not polymorphic. `What_Id` has `module.api_name: "se_module"`, i.e. it is the polymorphic slot resolved by `$se_module`. |
| [Zoho Kaizen #36 — Tasks API](https://help.zoho.com/portal/en/community/topic/kaizen-36-tasks-api) | Lead example uses `"What_Id": {...}` with `"$se_module": "Leads"` and **no** `Who_Id`. Contact example uses `"Who_Id"` with `"$se_module": "Contacts"`. Account example sets `What_Id` to the account with `"$se_module": "Accounts"`. |

The Zoho v8 *Insert Records* reference is silent on Tasks specifically; it documents
`$se_module` for Events and lists its permitted modules as "Accounts, Deals, Products,
Quotes, Sales_Orders, Purchase_Orders, Invoices, Campaigns, Vendors, and Cases" —
excluding both Leads and Contacts, which contradicts Kaizen #36 in turn.

**The executor currently implements the metadata-and-Kaizen mapping:**

| Target module | Link field | `$se_module` |
| --- | --- | --- |
| `Contacts` | `Who_Id` | `Contacts` |
| `Leads` | `What_Id` | `Leads` |
| `Accounts` | `What_Id` | `Accounts` |

This is a single table (`TASK_LINK_FIELD` in `scripts/execution_policy.py`, mirrored in
the Deluge); switching Leads to `Who_Id` is a one-line change if the live test proves
the brief right.

**No part of this mapping is verified.** The org contains only three Tasks, all linked
to a Contact plus an Account, so there is no live Lead-linked Task to learn from.
Acceptance tests 5 and 6 must settle it before any route is trusted. Do not treat the
table above as confirmed.

## Concurrency primitive

`Modified_Time` is returned on record reads (for example
`2026-07-19T18:43:17-07:00` on record `6719186000003183001`), which is what the
executor's conditional `If-Unmodified-Since` claim depends on. Whether Zoho's
`If-Unmodified-Since` header enforces the precondition at sub-second granularity is
**not verified** — see the risks section of the flow document.
