# TeamInbox → CRM Flow — verified variable map (BI1-T110)

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Last updated:** 2026-07-22

Authoritative, block-by-block map of the live `TeamInbox to CRM Payload Test` Flow.
Every value below was confirmed against the Zoho Flow UI unless marked otherwise.

## Legend

| Mark | Meaning |
| --- | --- |
| ✅ | Value confirmed by direct UI inspection |
| ~ | Inferred from a reference elsewhere; not directly opened |
| ⬜ | Not built yet |

## Verification status

| Route | Status |
| --- | --- |
| Contact | ✅ 100% verified by direct UI inspection (2026-07-22) — Zia section + context chain |
| Lead | ✅ 100% verified by direct UI inspection (2026-07-22) — Zia section + context chain |
| Account | ✅ 100% verified by direct UI inspection (2026-07-22) — Zia section + context chain |
| No Match | ✅ 100% verified by direct UI inspection (2026-07-22) — Zia section + context chain; validator `validate_zia_analysis_response_no_match`; all Creates `Validation_Status = fallback` |

**Cleanup done (2026-07-22):** the orphan Lead helper `isZiaAnalysisComplete_64` and the
stray No-Match Create `createOrUpdateModuleEntry_78` were both deleted. No orphan blocks remain.

Residual note (Contact + Lead): each route's two decision **condition bindings** read
`Complete is true` from the shared `IS_ZIA_ANALYSIS_COMPLETE` picker label. Visually
correct; not yet proven per-helper by a live Test & Debug run.

---

## Shared trunk (before routing)

| # | Block label | Type |
| --- | --- | --- |
| 1 | `TeamInbox Inbound Webhook` | Trigger |
| 2 | `normalize_teaminbox_payload` | Custom function |
| 3 | `Set Variable - shouldProcess` | Variable |
| 4 | `Processing Gate - Should Process?` | Decision → True continues |
| 5 | `check_ai_recommendation_exists` | Custom function |
| 6 | `Recommendation Already Exists?` | Decision → Default continues |
| 7 | `Fetch Contact by Sender Email` | CRM |
| 8 | `Set Variable - contactId` | Variable |
| 9 | `Contact Found?` | Decision → True = **Contact route**; False continues |
| 10 | `fetch_lead_by_email` | Custom function |
| 11 | `Set Variable - leadId` | Variable |
| 12 | `Lead Found?` | Decision → True = **Lead route**; False continues |
| 13 | `fetch_account_by_domain` | Custom function |
| 14 | `Set Variable - accountId` | Variable |
| 15 | `Account Found?` | Decision → True = **Account route**; False = **No-Match route** |

---

## CONTACT route ✅

Base variables:

| Role | Variable Name |
| --- | --- |
| AI request | `buildAiAnalysisRequest_33` ✅ |
| Trigger agent execution | `ziaTriggerContact` ~ (executionId source) |
| First fetch | `ziaResultContact` ✅ |
| Retry fetch | `ziaResultContactRetry1` ✅ |

Zia section:

| Block (Variable Name) | Function / Type | Inputs | Output/consts |
| --- | --- | --- | --- |
| `isZiaAnalysisComplete_63` | is_zia_analysis_complete | status_value `${ziaResultContact.status}` · response_value `${ziaResultContact.response}` | — |
| Decision 1 | Decision | `${isZiaAnalysisComplete_63.complete}` is `true` ~ | — |
| **↳ condition1 (True)** | | | |
| `validateZiaAnalysisResponseContact_51` | validate_zia_analysis_response_contact | raw_response `${isZiaAnalysisComplete_63.response}` · trusted_request `${buildAiAnalysisRequest_33}` | — |
| `createContactRecommendation_52` | CRM Create/update | reads `validateZiaAnalysisResponseContact_51` · Raw_Zia_Response `${ziaResultContact.response}` | Validation_Status `valid` |
| **↳ Default** | | | |
| `Wait for Zia Retry 1` | Delay | — | — |
| `ziaResultContactRetry1` | Fetch trigger execution | Execution ID `${ziaTriggerContact.executionId}` ~ | — |
| `isZiaAnalysisComplete_65` | is_zia_analysis_complete | status_value `${ziaResultContactRetry1.status}` · response_value `${ziaResultContactRetry1.response}` | — |
| Decision 2 | Decision | `${isZiaAnalysisComplete_65.complete}` is `true` ~ | — |
| **↳↳ Complete (True)** | | | |
| `validateZiaAnalysisResponseContactRetry1` | validate_zia_analysis_response_contact | raw_response `${ziaResultContactRetry1.response}` [opt → `${isZiaAnalysisComplete_65.response}`] · trusted_request `${buildAiAnalysisRequest_33}` | — |
| `createOrUpdateModuleEntry_61` | CRM Create/update | reads `validateZiaAnalysisResponseContactRetry1` · Raw_Zia_Response `${ziaResultContactRetry1.response}` | Validation_Status `valid` |
| **↳↳ Default (timeout)** | | | |
| `buildZiaTimeoutFallback_64` | build_zia_timeout_fallback | trusted_request `${buildAiAnalysisRequest_33}` | — |
| `createOrUpdateModuleEntry_63` | CRM Create/update | reads `buildZiaTimeoutFallback_64` · Raw_Zia_Response `${ziaResultContactRetry1.response}` | Validation_Status `fallback` |

---

## LEAD route ✅

Base variables:

| Role | Variable Name |
| --- | --- |
| AI request | `buildAiAnalysisRequest_38` ✅ |
| Trigger agent execution | `triggerAgentExecution_29` ✅ (Query `${buildAiAnalysisRequest_38}`) |
| First fetch | `ziaResultLead` ✅ |
| Retry fetch | `fetchTriggerExecution_71` ✅ |

Zia section:

| Block (Variable Name) | Function / Type | Inputs | Output/consts |
| --- | --- | --- | --- |
| `isZiaAnalysisComplete_66` | is_zia_analysis_complete | status_value `${ziaResultLead.status}` · response_value `${ziaResultLead.response}` | — |
| Decision 1 | Decision | `${isZiaAnalysisComplete_66.complete}` is `true` | — |
| **↳ condition1 (True)** | | | |
| `validateZiaAnalysisResponse_68` | validate_zia_analysis_response | raw_response `${isZiaAnalysisComplete_66.response}` · trusted_request `${buildAiAnalysisRequest_38}` | — |
| `createOrUpdateModuleEntry_69` | CRM Create/update | reads `validateZiaAnalysisResponse_68` · Raw_Zia_Response `${ziaResultLead.response}` | Validation_Status `valid` |
| **↳ Default** | | | |
| `Wait for Zia Retry 1` | Delay | — | — |
| `fetchTriggerExecution_71` | Fetch trigger execution | Execution ID `${triggerAgentExecution_29.executionId}` | — |
| `isZiaAnalysisComplete_72` | is_zia_analysis_complete | status_value `${fetchTriggerExecution_71.status}` · response_value `${fetchTriggerExecution_71.response}` | — |
| Decision 2 | Decision | `${isZiaAnalysisComplete_72.complete}` is `true` ~ | — |
| **↳↳ Complete (True)** | | | |
| `validateZiaAnalysisResponseContact_74` | validate_zia_analysis_response_contact (cloned name) | raw_response `${isZiaAnalysisComplete_72.response}` · trusted_request `${buildAiAnalysisRequest_38}` | — |
| `createOrUpdateModuleEntry_75` | CRM Create/update | reads `validateZiaAnalysisResponseContact_74` · Raw_Zia_Response `${fetchTriggerExecution_71.response}` | Validation_Status `valid` |
| **↳↳ Default (timeout)** | | | |
| `buildZiaTimeoutFallback_76` | build_zia_timeout_fallback | trusted_request `${buildAiAnalysisRequest_38}` | — |
| `createOrUpdateModuleEntry_77` | CRM Create/update | reads `buildZiaTimeoutFallback_76` · Raw_Zia_Response `${fetchTriggerExecution_71.response}` | Validation_Status `fallback` |

---

## ACCOUNT route ◐

Base variables:

| Role | Variable Name |
| --- | --- |
| AI request | `buildAiAnalysisRequest_34` |
| Trigger agent execution | `ziaTriggerAccount` |
| First fetch | `ziaResultAccount` |
| Retry fetch | `fetchTriggerExecution_89` (Execution ID `${ziaTriggerAccount.executionId}`) |

Context chain ✅ verified: `buildCrmContext_32` (from_email/from_domain ← normalized,
contact_id `${contactId}`, lead_id `${leadId}`, account_id `${accountId}`) →
`associateEmailToCrmRecord_48` (`${normalizeTeaminboxPayload_1}`, `${buildCrmContext_32}`) →
`buildCrmSnapshot_33` (ids as above, open_deals/cases/tasks empty) →
`buildAiAnalysisRequest_34` (`${normalizeTeaminboxPayload_1}`, `${buildCrmContext_32}`, `${buildCrmSnapshot_33}`).

Zia section (matched validator `validate_zia_analysis_response`; complete branches `valid`, timeout `fallback`):

| Block (Variable Name) | Function / Type | Inputs |
| --- | --- | --- |
| `isZiaAnalysisComplete_84` | is_zia_analysis_complete | status `${ziaResultAccount.status}` · response `${ziaResultAccount.response}` |
| Decision 1 | Decision | `${isZiaAnalysisComplete_84.complete}` is `true` |
| `validateZiaAnalysisResponse_38` | validate_zia_analysis_response | raw `${isZiaAnalysisComplete_84.response}` · trusted `${buildAiAnalysisRequest_34}` |
| `persistAccountRecommendation` | CRM Create | reads `_38` · Raw `${ziaResultAccount.response}` · valid |
| `fetchTriggerExecution_89` | Fetch trigger execution | Execution ID `${ziaTriggerAccount.executionId}` |
| `isZiaAnalysisComplete_90` | is_zia_analysis_complete | status `${fetchTriggerExecution_89.status}` · response `${fetchTriggerExecution_89.response}` |
| Decision 2 | Decision | `${isZiaAnalysisComplete_90.complete}` is `true` |
| `validateZiaAnalysisResponse_92` | validate_zia_analysis_response | raw `${isZiaAnalysisComplete_90.response}` · trusted `${buildAiAnalysisRequest_34}` |
| `createOrUpdateModuleEntry_93` | CRM Create | reads `_92` · Raw `${fetchTriggerExecution_89.response}` · valid |
| `buildZiaTimeoutFallback_94` | build_zia_timeout_fallback | trusted `${buildAiAnalysisRequest_34}` |
| `createOrUpdateModuleEntry_95` | CRM Create | reads `_94` · Raw `${fetchTriggerExecution_89.response}` · fallback |

All confirmed by inspection: `validateZiaAnalysisResponse_38` raw_response reads
`${isZiaAnalysisComplete_84.response}`; `persistAccountRecommendation` Execution_Status
`Not Started`; `fetchTriggerExecution_89` Execution ID reads `${ziaTriggerAccount.executionId}`.

---

## NO-MATCH route ✅

Base variables:

| Role | Variable Name |
| --- | --- |
| AI request | `buildAiAnalysisRequestNoMatch` (crm_context `buildCrmContextNoMatch`, crm_snapshot `buildCrmSnapshotNoMatch`, normalized_message `normalizeTeaminboxPayload_1`) |
| Trigger agent execution | `triggerAgentExecution_48` (Query `${buildAiAnalysisRequestNoMatch}`) |
| First fetch | `fetchTriggerExecution_50` (Execution ID `${triggerAgentExecution_48.executionId}`) |
| Retry fetch | `fetchTriggerExecution_79` (Execution ID `${triggerAgentExecution_48.executionId}`) |

Zia section (validator is `validate_zia_analysis_response_no_match` on both; every Create `Validation_Status = fallback`; no `associate_email` block):

| Block (Variable Name) | Function / Type | Inputs |
| --- | --- | --- |
| `isZiaAnalysisComplete_74` | is_zia_analysis_complete | status `${fetchTriggerExecution_50.status}` · response `${fetchTriggerExecution_50.response}` |
| Decision 1 | Decision | `${isZiaAnalysisComplete_74.complete}` is `true` |
| `validateZiaAnalysisResponseNoMatch_51` | validate…_no_match | raw `${isZiaAnalysisComplete_74.response}` · trusted `${buildAiAnalysisRequestNoMatch}` |
| `createOrUpdateModuleEntry_52` | CRM Create | reads `_51` · Raw `${fetchTriggerExecution_50.response}` · fallback |
| `fetchTriggerExecution_79` | Fetch trigger execution | Execution ID `${triggerAgentExecution_48.executionId}` |
| `isZiaAnalysisComplete_80` | is_zia_analysis_complete | status `${fetchTriggerExecution_79.status}` · response `${fetchTriggerExecution_79.response}` |
| Decision 2 | Decision | `${isZiaAnalysisComplete_80.complete}` is `true` |
| `validateZiaAnalysisResponseNoMatch_82` | validate…_no_match | raw `${isZiaAnalysisComplete_80.response}` · trusted `${buildAiAnalysisRequestNoMatch}` |
| `createOrUpdateModuleEntry_85` | CRM Create | reads `_82` · Raw `${fetchTriggerExecution_79.response}` · fallback |
| `buildZiaTimeoutFallback_83` | build_zia_timeout_fallback | trusted `${buildAiAnalysisRequestNoMatch}` |
| `createOrUpdateModuleEntry_84` | CRM Create | reads `_83` · Raw `${fetchTriggerExecution_79.response}` · fallback |

---

## Architecture note — the per-route duplication is the real tech debt

All four routes hand-duplicate the same Zia section with route-specific variable names.
This is the ceiling on scalability and the #1 source of bugs during this build
(cross-route variable contamination from cloning, misplaced blocks, branch swaps). The
verification burden is high precisely because each route must be checked independently.

**Recommended future refactor:** extract the Zia section into a single parameterized
subflow invoked with `(request, executionId, validator, isMatched)` so all routes share
one implementation. Until then, keep the four routes **structurally identical** (same
blocks, same order, same conditions) — uniformity is what makes them debuggable. No-Match
was deliberately built identical to Contact/Lead for this reason, even though its retry
rarely changes the outcome (it always resolves to `manual_review` / `fallback`).

---

## Constant fields on every `Create or update module entry`

Identical across all persistence blocks unless noted:

| Field | Value |
| --- | --- |
| Module | `AI Recommendations` |
| Layout | `Standard` |
| Status | `Pending Review` |
| Created_By_AI | `${true}` |
| Execution_Status | `Not Started` |
| Validation_Status | `valid` (matched/complete) or `fallback` (timeout) |
| Reviewed_By / Reviewed_At / Approved_Action_JSON / Execution_* | blank |

Per-block mapped fields all read the **same** validate/fallback output on that branch:
`Idempotency_Key`, `Message_ID`, `Target_Module` (custom value), `Target_Record_ID`,
`Recommendation_Type` (`.recommendation.action`), `Requires_Approval`
(`.safety.human_approval_required`), `Validated_Analysis_JSON` (whole object),
`Review_Notes` (`.recommendation.review_notes`).

---

## Known inconsistencies (non-breaking)

1. **Validator function naming.** Contact uses `validate_zia_analysis_response_contact`
   on both validates. Lead uses `validate_zia_analysis_response` on condition1 but the
   cloned `validate_zia_analysis_response_contact` on the retry branch (output
   `validateZiaAnalysisResponseContact_74`). Logic is equivalent; names differ because
   of cloning and the Zoho param-duplication workaround.
2. **Contact retry validate raw_response** reads the raw fetch
   (`${ziaResultContactRetry1.response}`) instead of the helper
   (`${isZiaAnalysisComplete_65.response}`). Equal on the Complete branch; optional to
   align.

## Cloning contamination — replacement map (for future routes)

When a route is cloned from another, repoint every field. Contact → Lead map used:

| Cloned-from (Contact) | Replace with (Lead) |
| --- | --- |
| `buildAiAnalysisRequest_33` | `buildAiAnalysisRequest_38` |
| `ziaTriggerContact` | `triggerAgentExecution_29` |
| `ziaResultContactRetry1` | `fetchTriggerExecution_71` |
| `validateZiaAnalysisResponseContactRetry1` | `validateZiaAnalysisResponseContact_74` |
| `buildZiaTimeoutFallback_64` | `buildZiaTimeoutFallback_76` |

## Custom functions (deployed)

`normalize_teaminbox_payload`, `check_ai_recommendation_exists`, `fetch_lead_by_email`,
`fetch_account_by_domain`, `fetch_open_deals_for_contact`, `fetch_open_cases_for_contact`,
`fetch_open_tasks_for_contact`, `fetch_open_tasks_for_lead`, `build_crm_context`,
`build_crm_snapshot`, `build_ai_analysis_request`, `associate_email_to_crm_record`,
`validate_zia_analysis_response`, `validate_zia_analysis_response_no_match`,
`validate_zia_analysis_response_contact`, `is_zia_analysis_complete` (two-arg:
`status_value`, `response_value`), `build_zia_timeout_fallback`.
