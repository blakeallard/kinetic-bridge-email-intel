# Zia completion / bounded-polling pattern — BI1-T110

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Last updated:** 2026-07-22

**Status: IMPLEMENTED and live-validated on all four routes (2026-07-22).** All of
Contact, Lead, Account, and No-Match now run the completion-check + bounded-retry +
safe-timeout pattern below. Every block mapping is recorded in
`docs/zoho_flow_variable_map.md`.

## Why this exists

Originally only the Contact route checked whether Zia actually finished before
validating; Lead, Account, and No-Match ran a single fixed `Wait for Zia Analysis`
delay then a blind `Fetch Zia Result` → `Validate` → persist. If Zia was still running
when the delay elapsed, those routes validated an empty or partial response and
persisted a degraded recommendation.

This pattern makes all four routes identical: **poll a bounded number of times
(initial wait + one retry), then fall through to an explicit safe-timeout fallback**
that is human-reviewable and can never be auto-executed. It resolved STATUS Next
Action 6 and removed the route divergence called out in the Flow inventory.

## Custom functions

| Function | Signature | Source |
| --- | --- | --- |
| `is_zia_analysis_complete` | `(string status_value, string response_value)` → map | `scripts/is_zia_analysis_complete.deluge` |
| `build_zia_timeout_fallback` | `(map trusted_request)` → map | `scripts/build_zia_timeout_fallback.deluge` |

### `is_zia_analysis_complete(status_value, response_value)`

Takes the two fields the Zia Agent `Fetch trigger execution` block exposes —
`status` and `response` — as separate string arguments (a whole-map argument could not
be reliably mapped from the fetch block in Zoho Flow, so the two scalars are passed
directly). Returns:

| Key | Meaning |
| --- | --- |
| `complete` | `true` only when the analysis is finished **and** carries a payload |
| `failed` | `true` when the status is a terminal error/cancel/timeout state |
| `has_payload` | `true` when a non-empty response string was found |
| `status` | the trimmed status string that was passed in |
| `response` | the trimmed response text — **use this as the validator's `raw_response`** |

Done states (case-insensitive): `COMPLETED`, `COMPLETE`, `SUCCESS`, `SUCCEEDED`,
`DONE`, `FINISHED`. The live Zia connector reports `success` on completion. Failed
states: `FAILED`, `FAILURE`, `ERROR`, `CANCELLED`, `CANCELED`, `TIMEOUT`, `TIMED_OUT`.
If the status is blank but a payload is present, that is treated as complete.

**Flow mapping:** `status_value` = `${<Fetch trigger execution>.status}`,
`response_value` = `${<Fetch trigger execution>.response}`. Do **not** map these to the
`Trigger agent execution` output — that stays `inprogress` / `Executing Query`.

### `build_zia_timeout_fallback(trusted_request)`

Returns a validated-analysis map with the **exact shape** that
`validate_zia_analysis_response` returns, forced to:

- `recommendation.action = manual_review`, both target fields blank,
- `safety.contains_insufficient_context = true`, `safety.conflicts = [zia_analysis_timeout]`,
- trusted `message_id` and `idempotency_key` restored from the request.

Because the shape is identical, the timeout branch's persistence block maps the same way
as any other route — only the constants differ (see below).

## Canonical Zia section (applies to every route)

Replace each route's `Wait for Zia Analysis` → `Fetch Zia Result` → `Validate` → persist
tail with the blocks below. `<Route>` is `Contact`, `Lead`, `Account`, or `NoMatch`.
Variable names are per route to preserve the no-copy-paste-mapping discipline.

```
Build AI Analysis Request - <Route>              -> zia<Route>Request
Trigger Zia Analysis - <Route>                   -> zia<Route>ExecutionId   (Trigger returns executionId)
Wait for Zia Analysis - <Route>                  (Delay, initial; e.g. 60s)
Fetch Zia Result 1 - <Route>                     input = zia<Route>ExecutionId  -> zia<Route>Fetch1
Zia Complete 1? - <Route>                        is_zia_analysis_complete(zia<Route>Fetch1) -> zia<Route>Check1
Decision: Zia Analysis Complete 1? - <Route>
    condition1:  zia<Route>Check1.complete == true
        Validate Zia Analysis - <Route>          validate(zia<Route>Check1.response, zia<Route>Request) -> zia<Route>Valid1
        Create or update module entry - <Route>  (VALID mapping)
    Default:
        Wait for Zia Retry 1 - <Route>           (Delay; e.g. 60s)
        Fetch Zia Result 2 - <Route>             input = zia<Route>ExecutionId  -> zia<Route>Fetch2
        Zia Complete 2? - <Route>                is_zia_analysis_complete(zia<Route>Fetch2) -> zia<Route>Check2
        Decision: Zia Analysis Complete 2? - <Route>
            condition1: zia<Route>Check2.complete == true
                Validate Zia Analysis Retry - <Route>   validate(zia<Route>Check2.response, zia<Route>Request) -> zia<Route>Valid2
                Create or update module entry Retry - <Route>  (VALID mapping)
            Default:   (bounded wait exhausted -> explicit timeout)
                Zia Timeout Fallback - <Route>          build_zia_timeout_fallback(zia<Route>Request) -> zia<Route>Timeout
                Create or update module entry Timeout - <Route>  (FALLBACK mapping)
```

Notes:

- **Feed the validator from the completion check, not the raw fetch.**
  Use `zia<Route>Check1.response` / `zia<Route>Check2.response` as `raw_response`.
  This guarantees the same payload key the completion check read is the one validated.
- **`validate` per route:** matched routes call `validate_zia_analysis_response`;
  the No Match route calls `validate_zia_analysis_response_no_match`. The timeout
  fallback is `build_zia_timeout_fallback` on **all** routes.
- **Two retries deep is intentional and bounded.** One initial wait + one retry matches
  the Contact route today. To poll longer, repeat the `Wait → Fetch → Complete? → Decision`
  triple; the Default of the last decision is always the timeout fallback.
- **`failed == true`** (Zia reported a terminal error) also falls to the Default path and
  reaches the timeout fallback — a failed run must not validate an error string.

## Persistence field mappings

VALID mapping (both `complete == true` branches) is unchanged from
`teaminbox_flow_complete_breakdown.md` §13. Only the source variable changes to the
route's validator output (`zia<Route>Valid1` or `zia<Route>Valid2`).

FALLBACK mapping (timeout Default branch):

| CRM UI field (API name) | Value |
| --- | --- |
| `Idempotency_Key` (`Name`) | `zia<Route>Timeout.idempotency_key` |
| `Message_ID` | `zia<Route>Timeout.message_id` |
| `Target_Module` | `""` (from fallback recommendation) |
| `Target_Record_ID` | `""` (from fallback recommendation) |
| `Recommendation_Type` | `manual_review` |
| `Status` | constant `Pending Review` |
| `Requires_Approval` | constant `true` |
| `Created_By_AI` | constant `true` |
| `Validation_Status` | constant **`fallback`** |
| `Validated_Analysis_JSON` | entire `zia<Route>Timeout` |
| `Raw_Zia_Response` | `zia<Route>Fetch2.response` (or blank) |
| `Review_Notes` | `zia<Route>Timeout.recommendation.review_notes` |
| `Execution_Status` | constant `Not Started` |

`Validation_Status=fallback` guarantees the record cannot satisfy the approved-action
executor's allow-list, so a timed-out recommendation can never auto-execute even if a
reviewer approves it.

## Contact-route correction

The Contact route already has both completion decisions. Change **only** its final
Default branch: today it flows `validate_zia_analysis` → `Create or update`. Repoint it to
`build_zia_timeout_fallback` → `Create or update` with the FALLBACK mapping above, so a
genuine Contact timeout is recorded explicitly instead of validating partial text.

## Acceptance tests (run in Test & Debug — no local Zoho credentials)

For each of Contact, Lead, Account, No Match:

1. **Fast complete.** Zia returns before the initial wait. Expect `complete == true` at
   decision 1, a `valid` recommendation persisted with the correct target.
2. **Slow complete.** Zia returns only after the retry wait. Expect Default at decision 1,
   `complete == true` at decision 2, a `valid` recommendation persisted.
3. **Timeout.** Zia never completes within both waits. Expect the timeout fallback:
   `Validation_Status=fallback`, `Recommendation_Type=manual_review`, both targets blank,
   conflict `zia_analysis_timeout`, `Execution_Status=Not Started`, and no CRM Task.
4. **Failed run.** Fetch reports a terminal error state. Expect the same timeout-fallback
   record (must not validate the error payload).

Confirm no duplicate `AI_Recommendations` record is created on any branch (the early
`check_ai_recommendation_exists` guard still runs before all of this).
