# BI1-T110 audit log — historical evidence

Zoho Task ID: 2543412000001583003

**This file is the archive of resolved audits and completed workstreams.** It was split out
of `STATUS.md` on 2026-07-25, which had grown to 831 lines of mixed current-state and
history. Nothing here is a pending action.

`STATUS.md` remains the canonical current-state and next-steps document. Read it first;
come here only for the evidence behind a claim it makes.

Entries are in the order they appeared in `STATUS.md`, newest workstream first.

---

## BI1-T110 end-to-end audit — 2026-07-24

### 1. Current State

Three live defects were diagnosed and repository fixes landed (repo only — **not yet
deployed to live Zoho**). Offline suite: **217 tests pass**, `ruff` clean,
`git diff --check` clean. The project is **NOT done**: the fresh live acceptance matrix
below has not run.

### 2. Confirmed Live Evidence

- The live `Trigger agent execution` block had a **completely blank Query field** (Zoho
  Flow UI screenshots). Its intended mapping is `${buildAiAnalysisRequest_8}`.
  `Fetch trigger execution` is already correctly mapped to
  `${triggerAgentExecution_11.executionId}`.
- Because Zia received no analysis request, the fleet-expansion/pricing email was
  misclassified as `support_request` / "customer requests assistance with product
  setup". **That result is invalid evidence** — Zia never saw the intended request, so
  it proves nothing about classification quality.
- A prior approved **Lead** recommendation failed Task creation with
  `Who_Id expected jsonobject but received string`.
- **Lead Task routing resolved by live evidence (2026-07-24).** An approved Lead
  recommendation (`6719186000003573001`, target Lead `6719186000003570001`) executed and
  failed with `INVALID_DATA` at `$.data[0].Who_Id.id`. Live `getFields` on Tasks shows
  `Who_Id`'s lookup module is **Contacts only**; `What_Id` is `$se_module`-driven. So a
  Lead cannot go in `Who_Id` — it must use `What_Id` + `$se_module = "Leads"`, which is
  what the repo already encodes (`TASK_LINK_FIELD["Leads"] = "What_Id"`). The failing run
  came from a **stale/hand-edited deployed function routing Leads into `Who_Id`**; the repo
  is correct. Fix = redeploy the repo executor verbatim. This settles the flow doc's
  "Test 5" routing question against the BI1-T110 brief's `Who_Id` expectation.
- Cliq recommendation notifications are working. Blueprint approval has been proven to run.
- **Ingestion crashed on Lead-matched emails** in `fetch_open_related` with
  `Data type of the argument of the function 'get' did not match the required data type of
  '[BIGINT]' at line number 58` (live log 2026-07-24 17:02, input `match.lead_id =
  6719186000003570001`). Root cause: `zoho.crm.getRelatedRecords("Tasks","Leads",…)`
  returns a No-Content/empty response (not a list of maps) whenever the Lead has no
  related Tasks, and the unguarded `for each … get("Status")` treated the empty result as
  a list of records. A Lead created by `create_lead_for_unmatched` always has zero related
  Tasks, so every Lead-matched email hit this. Confirmed live: the Tasks related list for
  `6719186000003570001` is empty. This aborted the snapshot build, so the recommendation
  was never produced/converted.

### 3. Repository Changes Made

- **`scripts/execute_approved_recommendation.deluge`** — Task `Who_Id`/`What_Id` are now
  built as `{"id": target_record_id}` objects via a `target_lookup` map instead of a bare
  id string. Field routing is unchanged (Contacts→`Who_Id`, Leads/Accounts→`What_Id`,
  `$se_module` set for all three) — it already matched the official Zoho Kaizen #36 Tasks
  API examples and the live Tasks field metadata (`Who_Id`/`What_Id` are both
  `json_type: jsonobject`). The executor's `idempotency_key` used in the Task description
  now reads `Ingestion_Key` (the durable key) instead of `Name` (now a human title).
- **`scripts/execution_policy.py`** — same two changes in the executable spec, kept in
  parity with the Deluge.
- **`tests/test_execution_policy.py`, `tests/test_deluge_parity.py`** — updated the
  lookup assertions to the `{"id": ...}` object shape and added focused tests: lookup
  fields are id-objects not strings, the Deluge wraps the id and never assigns a bare
  string to a lookup, and the description reads `Ingestion_Key` not the `Name` title.

- **`scripts/fetch_open_related.deluge`** — each related-records fetch (contact
  deals/cases/tasks and lead tasks) is now guarded with a `!= null && size() > 0` check and
  wrapped in try/catch, so an empty or non-list `getRelatedRecords` response degrades to "no
  open items" instead of throwing. This unblocks ingestion for Lead-matched emails, whose
  freshly-created Leads always have zero related Tasks. Repo only — **not yet deployed to
  live Zoho**. The identical latent pattern in `scripts/fetch_open_tasks_for_lead.deluge` and
  `scripts/fetch_open_tasks_for_contact.deluge` is not yet guarded (twin bug, unverified live).

The **blank Query** defect is a **live Flow configuration fix**, not a code change — the
repository already specifies `Query = ${request}` (single-path spec block 12). No code
change fixes or is required for it.

### 4. Offline Validation Results

- `python3 -m unittest discover -s tests -q` → **217 passed**.
- `ruff check scripts tests` → All checks passed.
- `git diff --check` → clean.

Offline tests assert the Deluge/Python contract only. **They do not confirm live Zoho
behavior.**

### 5. Remaining Live Zoho Tests

The full acceptance matrix in "Fresh live acceptance test — 2026-07-24" below must pass,
in particular a fresh **Lead** execution proving the `{"id": ...}` lookup creates a Task
linked to Lead `6719186000003423001` with `status=executed`, `Execution_Attempts=1`,
blank `Execution_Error`, and a duplicate replay creating no second Task. The corrected
executor Deluge and the `Query = ${buildAiAnalysisRequest_8}` mapping must both be
deployed to live Zoho first — the repo is ahead of live.

### 6. Known Risks or Unverified Assumptions

- The `{"id": ...}` lookup fix is verified against official docs and offline tests only,
  not against a live Lead Task creation.
- `build_ai_analysis_request` preserves the full email body (HTML tags stripped, no
  truncation, summary/subject used only as fallbacks when the body is empty). It was not
  the cause of the misclassification — the blank Query was.
- The validator does **not** semantically detect unsupported claims (e.g. "product
  setup" absent from the email); see the NO-CHANGE analysis below.
- The Zia agent instructions live in the live Zia agent config
  (`28302000000011001`, v3), not in this repo, and were not modified.

### 7. Exact Declaration-of-Done Criteria

Done only when every step of the fresh live acceptance test below passes: the fleet email
classifies as `quote_request` (or the approved equivalent) with no unsupported
product-setup claim, the recommendation persists as `Pending Review` with correct fields,
the Cliq card is correct, approval runs through Blueprint, execution returns
`status=executed` with `Executed_Task_ID` populated, `Execution_Status=Executed`,
`Execution_Error` blank, `Execution_Attempts=1`, the Task is linked to Lead
`6719186000003423001` and visible in its Open Activities, and a replay returns
`duplicate`/`already_claimed` with the original Task id and creates no second Task.

### 8. Next Action

Deploy the corrected executor Deluge and set `Query = ${buildAiAnalysisRequest_8}` in the
live Flow, then run the fresh live acceptance test below.

### Verified live in Zoho

- TeamInbox webhook ingestion, normalization, and processing gate.
- Contact, Lead, and Account routes revalidated through `Pending Review` persistence
  on 2026-07-21. Native Fetch Lead was replaced by the verified
  `fetch_lead_by_email` custom function after the connector discarded its Email input.
- No-match route validated through `manual_review` / `fallback` persistence; duplicate
  replay stopped at the early guard. Record: `6719186000003254001`.
- The operator confirmed the ingestion Flow was ON throughout development and had at
  least one natural TeamInbox execution before the 2026-07-21 corrections. Controlled
  validation remains Test & Debug evidence; production behavior is not fully audited.
- A natural outgoing-copy event from an internal legacy-domain sender reached
  TeamInbox as `NEW_INBOUND_MESSAGE`, followed the no-match route, and safely persisted
  fallback recommendation `6719186000003262001`. This proves the natural no-match
  path, while exposing that the processing gate does not distinguish internal
  outgoing copies from external inbound customer messages.
- Internal-sender gate verified in Test & Debug: a `bevco-tech.com` outgoing-copy
  payload returned `is_internal_sender=true`, `should_process=false`,
  `skip_reason=internal_sender_outbound_copy`, and stopped at the Processing Gate.
- Natural BMS test `NATURAL-CONTACT-021` reached TeamInbox, triggered the live Flow,
  and resolved Contact `6719186000002999004`. Persistence failed because the shared
  validator returned no-match fallback data despite receiving a correctly matched
  trusted request; live validator source/metadata inspection is now required.
- Natural external Contact test `NATURAL-CONTACT-024` passed end to end after replacing
  duplicated Zoho action metadata with a clean Contact-only validator. Contact
  `6719186000003265001` matched and recommendation `6719186000003249008` persisted as
  valid `create_crm_task` / `Pending Review` / `Not Started` with no conflicts.
- CRM UI inspection of Contact `6719186000003265001` showed no records in its Emails
  related list after `NATURAL-CONTACT-024`. Sender matching and recommendation
  persistence do not currently associate the TeamInbox email to the CRM record.
- An older Contact test displayed a received external TeamInbox email in the CRM
  Emails related list. Email association is supported in this org, but current evidence
  does not show that the live Flow performed that older association automatically.
- Automated Contact email association passed in Test & Debug: message
  `ASSOC-CONTACT-025` was associated to Contact `6719186000003265001` through the CRM
  API with `SUCCESS` / `Your mail has been added successfully`; CRM UI then confirmed
  the received external email in the Contact's Emails related list.
- Automated Lead email association passed in Test & Debug: message `ASSOC-LEAD-026`
  returned `SUCCESS` / `associated` for Lead `6719186000003163012`; CRM UI confirmed
  the received external email in the Lead's Emails related list.
- Automated Account-domain email association passed in Test & Debug: sender domain
  `bi1-t110-account.invalid` resolved Account `6719186000003265003`, and message
  `ASSOC-ACCOUNT-027` returned `SUCCESS` / `associated`; CRM UI confirmed the received
  external email in the Account's Emails related list.
- Natural Contact message `1784682407563110400` matched, completed AI analysis, and
  persisted valid recommendation `6719186000003272001`, but email association failed
  because TeamInbox's natural `sentDateInGMT` normalized seven hours into the future.
  The association function was corrected to prefer `received_at_ms`.
- Natural retest `BI1-T110 NATURAL-ASSOC-CONTACT-029` then returned `SUCCESS` /
  `associated` for Contact `6719186000003265001` with CRM timestamp
  `2026-07-21T18:16:17-07:00`; CRM UI confirmed it as a received external email in
  the Contact's Emails related list.
- Durable early duplicate guard (`check_ai_recommendation_exists` +
  `Recommendation Already Exists?`); `exists=true` stops, `exists=false` continues.
- Contact → Lead → Account-domain CRM matching, plus the no-match case.
- CRM context and snapshot construction; controlled AI request; async Zia execution;
  trusted response validation. All three matched routes validated.
- `AI_Recommendations` custom module `6719186000003163020`, its full field set,
  and the `AI Recommendation Review` Blueprint (published, active).
- Approval test: record `6719186000003183001` → `Approved`, audit fields set.
- Rejection test: record `6719186000003185001` → `Rejected`, audit fields set, no CRM
  action performed.
- Read-only metadata inspection of the module, its fields, and a real approved record
  (2026-07-19) — recorded in `docs/live_module_inspection_2026-07-19.md`.
- Current CRM field-editor UI inspection on 2026-07-21 confirmed that
  `Target_Module` defines `Contacts`, `Leads`, `Deals`, and `Accounts`. The older
  2026-07-19 API result that omitted `Accounts` is superseded as current-state
  evidence; no picklist change is required.
- Approved Contact recommendation `6719186000003249008` executed to CRM Task
  `6719186000003239002` on Contact `6719186000003265001`. CRM UI confirmed exactly
  one open Task. Replaying the same recommendation returned `duplicate` /
  `already_claimed` with the existing Task ID and created no second Task.
- Approved Lead recommendation `6719186000003247001` executed to CRM Task
  `6719186000003287001`. CRM UI confirmed `Related To = BI1-T110 Lead Test - Leads`;
  replay returned `duplicate` / `already_claimed` and created no second Task.
- Approved Account recommendation `6719186000003250001` executed to CRM Task
  `6719186000003293001`. CRM UI confirmed `Related To = TEST CO - Accounts`; replay
  returned `duplicate` / `already_claimed` and created no second Task.
- No-match/fallback recommendation `6719186000003254001` exposed only the Blueprint
  `Reject Recommendation` transition. It was rejected with reviewer audit fields;
  `Execution_Status` stayed `Not Started`, execution identifiers remained blank, and
  no Task was created.
- Final natural acceptance message `BI1-T110 FINAL-E2E-CONTACT-031` entered TeamInbox,
  matched Contact `6719186000003265001`, persisted approved recommendation
  `6719186000003302001`, and executed once to Task `6719186000003237002`. The
  recommendation recorded `Execution_Status=Executed`, `Execution_Attempts=1`, no
  execution error, and the CRM Contact showed both the received email and exactly one
  corresponding new open Task. A Test & Debug replay returned `duplicate` /
  `already_claimed` with that same Task ID.
- The execution Flow trigger is now filtered by `Status=Approved AND
  Execution_Status=Not Started`, preventing the executor's own bookkeeping updates
  from qualifying as new executions.
- **Concurrency acceptance test passed live (2026-07-23).** Approving recommendation
  `6719186000003380001` produced **two** Zoho Flow invocations in the 5:00–5:02 PM
  window — one completed, one filtered — and the target Lead `6719186000003163012`
  received **exactly one** Task (`6719186000003388001`), with
  `Execution_Status=Executed` and `Execution_Attempts=1`. The second invocation is the
  executor's own claim write re-firing the module-edit webhook while the first run was
  still in flight. Caveat: the overlap was rejected by the **Flow trigger filter**
  (`Status=Approved AND Execution_Status=Not Started`), so the Deluge
  `If-Unmodified-Since` conditional claim was not itself exercised against live Zoho.
  Defense in depth holds; only the outer layer is live-proven. The inner layer remains
  covered offline by the two-caller test in the suite.
- **Blueprint inspection answered by UI (requirement 17, 2026-07-23).** The
  `AI Recommendation Review` blueprint diagram shows `Pending Review` →
  `Approve Recommendation` / `Reject Recommendation` → `Approved` / `Rejected`, with
  both end states **terminal**. There is no `Approved → Executed` transition, so none
  can be invoked. The current design is correct: `Execution_Status` stays the execution
  source of truth and the executor does not touch the Blueprint-controlled `Status`
  field. This closes requirement 17 without the OAuth credentials.
- **Execution trigger is a Zoho Flow webhook, not a CRM function.** CRM Setup →
  Functions is empty; execution is driven by the read-only, Zoho Flow-managed workflow
  rule `AI_Recommendations_ZohoFlow_Execute Approved AI Recommendation` on
  `AI Recommendations`, which fires an instant webhook on **every edit of every record**
  with no rule-level condition. Gating happens downstream in the Flow trigger filter and
  again in the executor's own policy checks. Verified 2026-07-23: saving an unrelated
  field edit on a `Pending Review` record left `Execution_Status = Not Started`, i.e. the
  Flow filter turned it away before the executor ran.
- Ingestion idempotency is now datastore-enforced (2026-07-23). The unique
  `Ingestion_Key` field is live; a fresh message (`teaminbox:901489292:1784900000000119001`)
  persisted once as record `6719186000003380001` (`persisted=true`), and a manual
  attempt to create a second record with the same `Ingestion_Key` was rejected by CRM
  with "Duplicate values are not allowed." The updated `persist_recommendation` function
  is deployed in the live single-path Flow.

### Full live audit — 2026-07-23 (evidence of record)

This section is the **source of truth for execution correctness**. It was produced by
direct COQL queries against live Zoho CRM, not by trusting earlier entries in this file.
The underlying test records were scheduled for deletion immediately afterward, so these
results are not reproducible from CRM; this record replaces them.

**Execution integrity — 7 executed recommendations, 7 Tasks, exact 1:1.**

| Recommendation | Task | Target | Attempts | Error |
| --- | --- | --- | --- | --- |
| `6719186000003380001` | `6719186000003388001` | Lead `6719186000003163012` | 1 | none |
| `6719186000003364001` | `6719186000003368001` | Lead `6719186000003163012` | 1 | none |
| `6719186000003302001` | `6719186000003237002` | Contact `6719186000003265001` | 1 | none |
| `6719186000003250001` | `6719186000003293001` | Account `6719186000002999003` | 1 | none |
| `6719186000003247001` | `6719186000003287001` | Lead `6719186000003163012` | 1 | none |
| `6719186000003249008` | `6719186000003239002` | Contact `6719186000003265001` | 1 | none |
| `6719186000003183001` | `6719186000003200001` | Contact `6719186000002999004` | 1 | none |

Across all 37 recommendations in the module:

- **Zero duplicate Tasks.** Every Task `Subject` was unique; no message executed twice.
- **Zero orphans.** No Task lacked a matching `Executed_Task_ID`; no `Executed_Task_ID`
  pointed at a non-existent Task.
- **`Execution_Attempts` was 1 on every executed record** — never 2, never 3.
- **`Execution_Error` was null on every record.** No execution has ever failed.
- **Related-record linkage was correct in every case:** Contacts in `Who_Id`, Leads and
  Accounts in `What_Id`, matching `execute_approved_recommendation.deluge` lines 272-279.

**Live schema confirmed:**

- `Execution_Key` — unique, case-insensitive.
- `Ingestion_Key` — unique, case-insensitive (deployed 2026-07-23 as designed).
- `Target_Module` picklist: `Contacts`, `Leads`, `Deals`, `Accounts`.
- `Execution_Status` picklist: `Not Started`, `In Progress`, `Executed`, `Failed`,
  `Blocked` — covering every value the executor writes.

**Offline at the same commit:** 154 tests passing, ruff clean, all Python compiling.

**Two known state-representation quirks, both harmless:**

1. Six pre-2026-07-21 records carry `Execution_Status = null` rather than `Not Started`.
   The executor treats `""` as claimable (line 102), so both represent the same state.
2. `Target_Module` offers `Deals`, but the executor rejects it (line 94,
   `target_module_not_allowed`). This narrowing is deliberate — Deals execution was never
   in scope — but the picklist does not advertise the restriction.

`Ingestion_Key` was null on 36 of 37 records. This is expected, not a defect: the field
went live 2026-07-23, so datastore-enforced ingestion idempotency applies to messages
ingested from that date forward. Zoho permits multiple nulls in a unique field.

### Repository audit — 2026-07-21

- Reconciled `build_crm_snapshot.deluge` with the verified live `Lead_Status` API
  field.
- Corrected stale function signatures and the retired native Fetch Lead block in the
  Flow inventory.
- Added static regression coverage for the custom Lead lookup and Lead status field.
- Kept `plan/flows/` local-only because its diagnostic screenshots include a
  credential-bearing webhook URL; the directory is now ignored by Git.
- Removed generated `.DS_Store` and Python bytecode cache files. Material flow
  screenshots were preserved.

## Done — no-match Lead creation (plan step 5b-ELSE), live-validated 2026-07-23

Closes the last plan gap: an unknown sender (no Contact, Lead, or Account match) used to
dead-end at `manual_review`. It now creates a Lead and flows through the normal
Lead → Zia → recommendation path, producing an actionable `create_crm_task`.

**Live proof (Test & Debug, 2026-07-23):** unknown sender
`newprospect.test@northwind-example.com` →
`ensure_crm_match` created Lead `6719186000003404001` (Last_Name `Prospect`, Company
`Northwind Example Co` extracted from body, Lead_Source `Email`, Status `Not Contacted`,
Owner Bill) → recommendation `6719186000003405001`: `create_crm_task`, `Target_Module`
`Leads`, `Target_Record_ID` `6719186000003404001`, `Validation_Status` `valid`. Not
`manual_review`. **These two records are test data — delete after review.**

Decisions locked with the operator:

- Unknown sender → create a **Lead only** (not Contact+Lead). Rationale: Lead and Contact
  are two stages of the same person; creating both duplicates the record and produces a
  second Contact on later conversion. Standard lifecycle is Lead → native **Convert** to
  Contact when qualified. This intentionally deviates from the handwritten 5b-ELSE, which
  said "create contact and lead".
- Lead → Contact and Deal-creation **timing** are left as manual/human decisions
  (native Convert; Deal deferred to QTS quote generation), pending Bill/Bryan preference.
  Nothing about lifecycle timing is automated.
- Owner: a single constant `lead_owner_id`, a one-line swap. **Set to Blake
  (`6719186000002395001`) for TESTING so test Leads never land on Bill/Bryan.** Production
  target is Bill/Bryan; owner-by-inbox routing (Bill vs Bryan by area) deferred to Step 9.
- Lead Source: `Website` for form intake, `Email` for inbound (from `is_form_intake`).

Code (deployed and live-validated):

- `scripts/ensure_crm_match.deluge` — pass-through gate. If
  `resolve_crm_match` already matched, returns it untouched; otherwise creates the Lead
  and returns a Lead-match-shaped map with the same keys downstream reads. This shape lets
  it drop into the single-path flow without adding a branch.
- `tests/test_ingestion_artifacts.py` — `TestEnsureCrmMatch` added. Full suite 183 tests,
  ruff clean.

Wiring (live single-path flow, done 2026-07-23):

1. Custom function `ensure_crm_match(map normalized, map resolve_result)` created.
2. Placed immediately after `resolve_crm_match`; inputs = `${normalizeTeaminboxPayload_*}`
   + `${resolveCrmMatch_3}` (whole maps, typed by hand — the leaf picker only exposes
   parsed scalars).
3. Re-pointed the two blocks that actually read `resolve_crm_match` — `fetch_open_related`
   (`match`) and `build_crm_context` (`contact_id`/`lead_id`/`account_id`) — to
   `ensureCrmMatch_26`. `associate_email_to_crm_record` needed **no** change: it reads
   `build_crm_context` output, which already carries the resolved target.
4. Test & Debug validated end-to-end (see live proof above).

## Done — reviewer notification via Cliq (live-validated 2026-07-24)

Started 2026-07-23. Closes the "first error if live as-is" gap: a recommendation reaches
`Pending Review` but nothing tells a human to review it, so the human-approval step —
which the whole system depends on — never gets triggered.

Design: notify off the **record**, not the flow. A CRM workflow rule on
`AI_Recommendations` (on create) calls a Deluge function that posts to a Cliq channel.
This catches every recommendation from every path (engine, form, future flows) and
touches the fragile ingestion flow zero times.

- Channel: `ai-recs-test` (unique name `airecommendationstest`), **Blake-only for now** —
  Bill/Bryan added once confirmed, to avoid spamming them during validation.
- Cliq call confirmed by operator: `zoho.cliq.postToChannel("airecommendationstest", msg)`.
- Code: `scripts/notify_cliq_new_recommendation.deluge` — reads the record, guards on
  `Status == "Pending Review"`, posts action + target + validation + a CRM deep link.
  Tests: `TestCliqNotification`. Full suite 189, ruff clean.

Cliq facts (confirmed live 2026-07-23):

- Channel `ai-recs-test`, unique name `airecommendationstest`, Channel ID
  `O6165045000001641001`, Chat ID `CT_1424735400674246738_889992103`, Cliq company
  `889992103`. Blake-only membership.
- CRM connection for Cliq: link name **`blake_cliq_connection`** (created under CRM Setup →
  Developer Space → Connections). `zoho.cliq.postToChannel` requires this connection as its
  third argument — a bare call errors with "not allowed to be used without connection".
- The code's Cliq call is:
  `zoho.cliq.postToChannel("airecommendationstest",message_text,"blake_cliq_connection")`.

**Phase 1 — function paste + live post (DONE 2026-07-23).** The CRM function editor
accepted the full namespaced signature with the argument inline
(`void salessignals.notify_cliq_new_recommendation(string recommendation_id)`); body-only
was not required (the earlier `standalone`-category and `rec_id is not defined` errors were
just a category/signature mismatch, gone once category `salessignals` and the full
namespaced signature were used). The saved copy inlines the empty-check and drops the repo
file's cosmetic `.trim()`; the repo keeps the portable plain
`void notify_cliq_new_recommendation(...)` form and CRM adds the `salessignals.` namespace.
First Execute returned `getRecordById` 200 but `postToChannel` **401**
because `blake_cliq_connection` was not yet authorized. After re-authorizing the
connection with a Cliq channel message-post scope, Execute against pending record
`6719186000003401001` posted the formatted card to `ai-recs-test`. The live message
layout was upgraded (section headers, `hexToText("0A")` newlines, empty-target fallbacks
"Manual review" / "No CRM record matched"); the repo `.deluge` mirrors it while keeping
the portable plain signature and test-pinned tokens.

**Phase 2 — create-only Workflow Rule (DONE 2026-07-24).** A CRM Workflow Rule on module
`AI Recommendations` was created: trigger = record action **Create**, condition =
`Status is Pending Review`, instant action = the Automation-category function
`notify_cliq_new_recommendation`, argument `recommendation_id` mapped to the
`AI Recommendation Id` merge field. The first run **failed** because `recommendation_id`
was initially mapped to `Idempotency_Key` (the `Name` display field), so `.toLong()`
failed on a non-numeric value. Remapping to `AI Recommendation Id` fixed it; retrying the
failed execution then posted the Cliq notification.

**Phase 3 — end-to-end validation (DONE 2026-07-24).**

- A fresh website submission created a new recommendation and auto-posted **exactly one**
  Cliq notification with no manual Execute/Retry; the deep link opened the correct record.
- Editing `Review_Notes` produced **no** second notification, confirming create-only
  behavior (the edit-triggered executor rule is separate and did not fire this function).
- Full lifecycle: a fresh website inquiry created Lead `6719186000003423001`;
  recommendation `6719186000003415011` persisted as valid `create_crm_task` /
  `Pending Review`; human approval moved it to `Approved`; the executor created Task
  `6719186000003430001`. The recommendation finished `Execution_Status=Executed`,
  `Execution_Attempts=1`, `Execution_Error` blank, `Executed_Task_ID=6719186000003430001`.
  The Task was correctly related to Lead `6719186000003423001`; the Lead showed the
  inbound website inquiry in Emails and exactly one open Task. Approval and execution
  produced no additional Cliq notification.

Deferred (unchanged): add Bill and Bryan to the channel and promote `ai-recs-test` to a
production channel only after broader validation — until then it would spam them.

## Done — CC ingestion + duplicate-event idempotency (resolved 2026-07-24)

A natural test email (`From blakeallard@blakeallard.com`, `To blake@kinetic-bridge.com`,
`CC bms@kinetic-bridge.com`) surfaced two sequential problems in the TeamInbox → Flow
trigger path. Both are now resolved; the webhook URL, CC routing, inbox conditions, and
duplicate TeamInbox rules were each ruled out along the way and are **not** the cause.

**Problem 1 — CC-only delivery did not reach Zoho Flow (rule-level).** The shared inbox
was CC'd rather than the direct To recipient, and the outgoing-webhook rule did not fire.
The cause was rule-level, not CC-eligibility: TeamInbox rules *do* fire on CC'd mail (a
separate `TAG_BMS` rule tagged the same thread), there is only one shared inbox
("Zoho Mail Intake"; the "Zoho Mail Shared Inbox Intake" breadcrumb is a display label for
it), and the condition already matched. Resolved by consolidating to a **single active
inbound rule** on `Inbox is Zoho Mail Intake` carrying **both** actions — apply the `@BMS`
tag and the outgoing webhook to Zoho Flow — which removes any two-rule ordering/exclusivity
dependency. The old separate webhook rule was disabled/removed. CC-only delivery now
reaches Flow.

**Problem 2 — duplicate `AI_Recommendations` from one email (idempotency-key
granularity).** Once CC delivery worked, one email produced **two** completed Flow
executions seconds apart and **two** CRM records. Deduction from the schema: a second
record persisted *despite* the unique `Ingestion_Key` constraint, which is only possible
if the two webhook payloads carried **different** `Ingestion_Key`s. The old key was
`teaminbox:{portal_id}:{message_id}`, and TeamInbox issued **two different `messageId`s**
for the one email (delivered to two inbox-associated recipients). The datastore
idempotency layer behaved correctly — it was handed two genuinely different keys. Not a
retry, not a race, not a guard bug.

**Root cause.** `idempotency_key` was derived from TeamInbox's per-delivery `messageId`,
so duplicate deliveries of the same email were treated as separate ingestion events.

**Fix** (`scripts/normalize_teaminbox_payload.deluge:131-132`) — re-key on stable email
identity instead of the per-delivery `messageId`:

```text
idempotency_key = "teaminbox:" + portal_id + ":" + from_email + ":" + sent_at_ms + ":" + ifnull(payload.get("subject"),"");
normalized.put("idempotency_key",idempotency_key);
```

Both delivered copies of one email share the same sender, send timestamp, and subject, so
both now produce an identical `Ingestion_Key`; the unique constraint blocks the second at
persistence. The repo is synced with the live Zoho function. The key propagates unchanged
downstream (`build_ai_analysis_request.deluge` → `validate_zia_analysis_response_tagged.deluge`
→ `persist_recommendation.deluge`), so no other script changed.

**Validation.**

- Offline: `tests/test_ingestion_artifacts.py` gained `TestIngestionIdempotencyKey`
  (+6 tests) proving two payloads differing only in `messageId` collapse to one key, that
  differing sender/subject/send-timestamp each diverge, and that the Deluge no longer
  references `message_id` in the key. Stale `teaminbox:{portal}:{messageId}` fixtures in
  `tests/test_execution_policy.py` were updated to the new format. **206 unittest tests
  passing, ruff clean.**
- Live E2E confirmed: TeamInbox again generated duplicate webhook events for one email;
  **both events produced an identical `idempotency_key`**; the first persist succeeded and
  the second returned `DUPLICATE_DATA`, blocked by `Ingestion_Key` uniqueness — **exactly
  one** `AI_Recommendations` record.

**Status: resolved.** Residual to keep in mind (not a defect): the composite key depends on
`sent_at_ms` being populated, and two genuinely distinct emails from the same sender with
the same subject and send timestamp would collapse to one recommendation — an accepted
narrow tradeoff versus the per-delivery `messageId`.

---

## persist_recommendation display rework — landed 2026-07-24, deployed 2026-07-25

Deployed to live Zoho on 2026-07-25.

- **`persist_recommendation` display/presentation rework.** Only the field mapping
  changed; the API endpoint, `DUPLICATE_DATA` duplicate handling, the `Ingestion_Key`
  idempotency write, the `result` contract, and the executor are untouched.
  - `Name` is now a human-readable title — `AI Recommendation: Create CRM Task -
    Request Information` — built by title-casing `recommendation.action` and
    `intent.category`, capped at the field's 120 chars.
  - `AI_Category`, `AI_Summary`, and `AI_Rationale` are now written (category,
    what the email is requesting, why the AI recommended the action). These fields
    exist live — confirmed by a CRM `getFields` read on 2026-07-24 — along with
    `AI_Confidence`, which remains unmapped.
  - `Safety_Summary` (multi-select picklist) is written as a Deluge `List`, which the
    existing `request_body.toString()` serializes to a JSON array as CRM v8 expects.
  - `Review_Notes` is now `Recommended Action: <action>` + LF + `Reason: <review_notes>`,
    using `hexToText("0A")` (a literal `"\n"` renders as backslash-n in Deluge).
  - **`check_ai_recommendation_exists` repointed to the unique key.** Its search criteria
    moved from `(Name:equals:<key>)` to `(Ingestion_Key:equals:<key>)`, because `Name` is
    now a human-readable title and would no longer match a replay. This keeps the
    Flow-level fast-path guard cost-saving (short-circuits a replay before Zia runs);
    datastore correctness never depended on it (the unique `Ingestion_Key` rejects the
    duplicate create with `DUPLICATE_DATA` regardless).
  - 210 tests pass.

  **Live-Zoho state:**
  1. `Safety_Summary`'s picklist was corrected in the CRM UI on 2026-07-24 to the five
     values the code emits (`Human Approval Required`, `Closed Won Change Requested`,
     `Quote Generation Requested`, `Insufficient Context`, `Conflict Detected`) —
     confirmed by screenshot. The earlier `Option 1`/`Option 2` placeholders are gone,
     so creates no longer fail with `INVALID_DATA`.
  2. Both edited functions (`persist_recommendation`, `check_ai_recommendation_exists`)
     still need to be pushed to their live Zoho Flow custom-function bodies; the repo is
     ahead of live.
