# AI_Recommendations CRM Module — Design Spec

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Status:** Proposed. Not yet created in CRM.
**Blocker:** Creating a custom CRM module is a schema change = **Tier 3 (Bill-only)** approval.
As of 2026-07-19 the CRM contains **no custom modules** — verified by listing all 52
org modules; nothing named `AI_Recommendations` (or similar) exists.

This module is the persistence + human-approval gate between the read-only Zia analysis
and any approved action execution. Every validated Zia result becomes one record here in
`Pending Review` status; a human approves/rejects; a separate execution Flow acts only on
approved, allow-listed recommendations.

## Why a unique key matters

Durable idempotency (remaining-work item #2) must be enforced by the datastore, not by
Deluge alone. `Idempotency_Key` is therefore a **unique** field. A replayed TeamInbox
message produces the same `idempotency_key` (`teaminbox:<portal>:<message_id>`), so the
create call fails with a duplicate error instead of writing a second recommendation. The
persistence function catches that error and treats it as "already recorded."

## Field schema

Field names map directly to the `validate_zia_analysis_response` output map.

| Field label | API name (expected) | Type | Notes |
| --- | --- | --- | --- |
| Recommendation Name | `Name` | Text | Default record name, e.g. `Rec <message_id>` |
| Idempotency Key | `Idempotency_Key` | Text (**unique**) | `teaminbox:<portal>:<message_id>`; dedup key |
| Message ID | `Message_Id` | Text | Original TeamInbox message id |
| Status | `Status` | Picklist | `Pending Review` / `Approved` / `Rejected` / `Executed` / `Execution Failed` / `Manual Review` |
| Recommended Action | `Recommended_Action` | Picklist | `create_crm_task` / `update_lifecycle` / `manual_review` / … (allow-list) |
| Confidence Band | `Confidence_Band` | Picklist | `low` / `medium` / `high` |
| Rationale | `Rationale` | Multiline | From `recommendation.rationale` |
| Review Notes | `Review_Notes` | Multiline | From `recommendation.review_notes` |
| Target Module | `Target_Module` | Text | Trusted; clamped to matched CRM context |
| Target Record ID | `Target_Record_Id` | Text | Trusted; clamped to matched record |
| Intent Category | `Intent_Category` | Text | From `intent.category` |
| Intent Summary | `Intent_Summary` | Multiline | From `intent.summary` |
| Opportunity Signals | `Opportunity_Signals` | Multiline | JSON-serialized list |
| Lifecycle Observed Stage | `Lifecycle_Observed_Stage` | Text | |
| Lifecycle Recommended Stage | `Lifecycle_Recommended_Stage` | Text | Nullable |
| Lifecycle Change Recommended | `Lifecycle_Change_Recommended` | Boolean | |
| Human Approval Required | `Human_Approval_Required` | Boolean | Always `true` |
| Closed Won Change Requested | `Closed_Won_Change_Requested` | Boolean | Policy flag |
| Quote Generation Requested | `Quote_Generation_Requested` | Boolean | Policy flag |
| Contains Insufficient Context | `Contains_Insufficient_Context` | Boolean | |
| Conflicts | `Conflicts` | Multiline | JSON-serialized list |
| Schema Version | `Schema_Version` | Text | e.g. `1.0` |
| Source | `Source` | Text | `zoho_teaminbox` |
| Raw Analysis | `Raw_Analysis` | Multiline (large) | Raw Zia response, pre-validation |
| Validated Analysis | `Validated_Analysis` | Multiline (large) | Full validated JSON |
| Approver | `Approver` | User lookup | Set on approve/reject |
| Decision Timestamp | `Decision_Timestamp` | DateTime | Set on approve/reject |
| Decision Notes | `Decision_Notes` | Multiline | Human note on the decision |

## Safety invariants (enforced regardless of AI output)

- `Human_Approval_Required` is written `true` on every record.
- No record is ever created in `Approved` or `Executed` status by the ingestion Flow;
  the ingestion Flow only ever writes `Pending Review` (or `Manual Review`).
- `Target_Module` / `Target_Record_Id` are taken from the trusted CRM context, never from
  the model's free-text output.
- Closed Won changes and QTS quote generation are recorded as flags but are **never**
  executed automatically — the downstream execution Flow's allow-list excludes them.

## Open decisions

1. **No-match branch:** should a no-match message create a `Manual Review` record here, or
   be dropped? (Remaining-work item #6.) Spec assumes it *can* create a `Manual Review`
   record with empty target fields if we decide it should.
2. **Field storage limits:** `Raw_Analysis` / `Validated_Analysis` may exceed a standard
   multiline field's size; confirm the large-text limit or store a WorkDrive/Notes ref.
3. **Unique-field behavior:** confirm Zoho returns a catchable duplicate error on unique
   violation for the create call (assumed by `persist_ai_recommendation`).
