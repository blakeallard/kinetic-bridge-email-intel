# Flow: `Execute Approved AI Recommendation`

Zoho Task ID: 2543412000001583003 (BI1-T110)

The separate execution stage. After approval, the Flow materializes CRM people/company
records (`materialize_pending_lead` + `associate_email_to_crm_record`) and this function
**claims** the recommendation and marks it `Executed`. It does **not** create a CRM Task
or Event — Bill 2026-07-28: Approve bypasses the Task path.

**Deployment state: DEPLOYED and ON** (as of 2026-07-22; Task-skip paste pending). The
Flow remains live; paste the updated `execute_approved_recommendation` so Approve stops
creating Tasks while still writing `Execution_Status=Executed`.

The trigger is filtered by `Status = Approved AND Execution_Status = Not Started`, so the
executor's own bookkeeping updates cannot re-qualify as new executions.

One assumption remains unverified against live Zoho: the conditional-claim behaviour under
genuine concurrency. See "Operator runbook" at the end of this document.

## Design

```text
CRM record update on AI_Recommendations
        │  (Status becomes Approved)
        ▼
Set Variable — recommendationRecordId          ← the ONLY value passed onward
        ▼
execute_approved_recommendation(record_id)     ← refetches everything from CRM
        ▼
Decision — Execution Result                    ← routes on the returned status
   ├── executed  → stop
   ├── duplicate → stop (no-op)
   ├── blocked   → stop (Execution_Error names the failed checks)
   └── failed    → stop (pre-claim: rerunnable after a fix / post-claim: TERMINAL)
```

The trigger passes **only the record ID**. Everything the executor decides on is
refetched from CRM inside the function, so a tampered or stale trigger payload cannot
influence the outcome.

## Files

| Purpose | Path |
| --- | --- |
| Deployable custom function | `scripts/execute_approved_recommendation.deluge` |
| Executable specification + tests target | `scripts/execution_policy.py` |
| Behavioural tests | `tests/test_execution_policy.py` |
| Python↔Deluge drift guard | `tests/test_deluge_parity.py` |
| CRM inspection / setup utility | `scripts/zoho_crm_admin.py` |
| Verified live metadata | `docs/live_module_inspection_2026-07-19.md` |

## Execution contract

**Input:** `ai_recommendation_record_id` (string). Nothing else.

**Preconditions** — all ten must hold, read from the refetched CRM record:

| # | Field | Required value | Violation identifier |
| --- | --- | --- | --- |
| 1 | `Status` | exactly `Approved` | `status_not_approved` |
| 2 | `Requires_Approval` | exactly true | `requires_approval_not_true` |
| 3 | `Created_By_AI` | exactly true | `created_by_ai_not_true` |
| 4 | `Validation_Status` | exactly `valid` | `validation_status_not_valid` |
| 5 | `Recommendation_Type` | exactly `create_crm_task` | `recommendation_type_not_allowed` |
| 6 | `Target_Module` | `Contacts`, `Leads`, or `Accounts` | `target_module_not_allowed` |
| 7 | `Target_Record_ID` | non-blank | `target_record_id_blank` |
| 8 | `Execution_Status` | blank or `Not Started` | `execution_status_not_claimable` |
| 9 | `Executed_Task_ID` | blank | `executed_task_id_present` |
| 10 | `Execution_Attempts` | below 3 | `execution_attempts_limit_reached` |

All ten are evaluated on every call, so `Execution_Error` records every failed check
rather than only the first.

**Execution key:** `ai-execution:<AI_RECOMMENDATION_RECORD_ID>:create_crm_task`

**Result statuses:**

| Status | Meaning | Task created? | Record writes |
| --- | --- | --- | --- |
| `executed` | Claim succeeded; recommendation marked Executed | no (`task_created=no`) | `Executed_At`, `Execution_Status=Executed`, `Execution_Error` cleared |
| `duplicate` | Already claimed, already executed, or lost the conditional claim race | no | none |
| `blocked` | A policy check failed | no | `Execution_Status=Blocked`, `Execution_Error` = failed checks |
| `failed` (pre-claim) | CRM error before the claim succeeded | no | none, or `Execution_Status=Blocked` on `blocked_write_failed` |
| `failed` (post-claim) | CRM error after the claim succeeded; **terminal** | no | claim fields stay; `Execution_Key` populated; no auto-retry |

### Ordering guarantees

1. The **already-claimed check runs before the policy gate**, so a duplicate
   invocation never rewrites `Execution_Error`, never re-Blocks, and never burns an
   attempt.
2. The **claim happens before Executed is written**, and the claim is *conditional* —
   see the next section.
3. People/company CRM records are created by earlier Flow blocks
   (`materialize_pending_lead`), not by this function.
4. On a post-claim bookkeeping failure the function returns `failed` with
   `post_execution_write_failed`. A blind retry is refused as `already_claimed`.

## How the atomic claim works, in plain English

### The bug this replaces

The first version of this executor claimed a recommendation by reading the record and
then writing the deterministic `Execution_Key` onto it with an ordinary update. That
was **not concurrency-safe**, and the reasoning behind it was wrong.

The mistake was assuming the unique constraint on `Execution_Key` would stop a second
execution. It does not. A unique constraint stops *two different records* holding the
same value. Here there is only ever **one** record, and both callers write the **same**
key to it. The second write is not a duplicate — it is an idempotent overwrite of the
same field on the same row. Zoho accepts it. Both callers then saw a successful update,
both believed they had claimed the work, and both created a Task.

`tests/test_execution_policy.py::TestConcurrentClaim::test_an_unconditional_claim_implementation_is_caught`
reproduces exactly that: it substitutes an unconditional claim and asserts two Tasks
get created. It is there so the old behaviour can never quietly return.

### The mechanism now

The claim uses an **optimistic concurrency check** — a compare-and-set against the
record's last-modified timestamp.

1. The executor reads the recommendation and notes its `Modified_Time` — say
   `18:43:17`. That timestamp is the record's version number.
2. To claim, it does not send a plain update. It sends a conditional one: *"apply these
   changes, but only if this record has not been modified since 18:43:17."* That is the
   HTTP `If-Unmodified-Since` header on the Zoho CRM V8 Update Records call.
3. Zoho evaluates that condition **server-side, as part of the write**. This is the
   part that matters: the check and the write are one indivisible operation, so no
   second caller can slip between them.

Now run two callers at once. Both read the record at version `18:43:17`. Both send a
conditional write demanding that version.

- Caller A's condition holds. Zoho applies the write. The record's `Modified_Time`
  becomes `18:43:19`. A has the claim and proceeds to create the Task.
- Caller B's condition no longer holds — the record is now at `18:43:19`, which is
  later than the `18:43:17` B demanded. Zoho **rejects** B's write and changes nothing,
  answering **HTTP 412** with API error code **`ALREADY_MODIFIED`**. B maps that exact
  code to `duplicate` / `claim_lost_race`, writes nothing, and creates nothing.

Exactly one caller wins, and the loser writes nothing at all — no error, no attempt
burned. The winner is decided by the database, not by application logic that could be
interleaved.

An intuitive way to hold it: the first version asked *"is anyone else here?"* and then
acted on a stale answer. This version says *"I will act only if nothing has changed
since I looked"*, and lets the database enforce it.

### How the claim response is parsed

Zoho documents a failed `If-Unmodified-Since` update as **HTTP 412** with API error
code **`ALREADY_MODIFIED`**. The handler reads both response shapes, because a
per-record result and a top-level error arrive differently:

1. Read top-level `claim_response.get("status")` and `claim_response.get("code")` —
   this is where a 412 error body reports itself.
2. Read `data[0].status` and `data[0].code` — the per-record result on a normal
   Update Records response. When present and non-blank these override the top-level
   values, since they are the more specific answer.
3. Branch on the parsed code:
   - `ALREADY_MODIFIED` → `duplicate` / `claim_lost_race`. No Task, no further CRM
     write, no attempt burned by the loser.
   - `DUPLICATE_DATA` → `duplicate` / `execution_key_conflict`.
   - anything else non-success → `failed` / `claim_failed`, carrying the actual parsed
     code back as `claim_code` so an operator sees what Zoho really said.

The handler does **not** rely on scanning the response text for `"412"`. Matching the
documented error code is exact; substring-matching a status number would also match a
`412` appearing anywhere in a message or record ID.

### What is still unverified about it

`If-Unmodified-Since` behaviour has **not been tested against live Zoho** — there are
no credentials in this environment. Two specific unknowns:

1. **Timestamp granularity.** `Modified_Time` is returned at second precision. If Zoho
   compares against an internally higher-precision value, a claim could be rejected
   spuriously; if two writes land inside the same second, both preconditions could
   pass and the race would reopen for a sub-second window.
2. **Deluge header support.** `zoho.crm.updateRecord()` cannot set custom headers, so
   the claim uses `invokeurl` with the existing named connection
   (`zoho_crm_to_zoho_flow`). The parity
   tests pin this to a single PUT against the recommendation module so it cannot
   become a general-purpose escape hatch.

**If live testing shows either problem, switch to the execution-ledger design**, which
depends on no header semantics: create a separate custom module whose only unique field
is the execution key, have each caller attempt to *create* one ledger record with the
deterministic key, and let only the caller whose create succeeds proceed. Two creates
of the same key are genuinely two different records colliding on a unique constraint,
which is the case a unique index actually prevents. That costs one new custom module
(Tier 3) and is the reason it is the fallback rather than the default.

Acceptance test 9 exercises this path live.

### What it deliberately does not do

No Deal stage change. No Closed Won. No quote generation. No email. No record
deletion. No Blueprint transition. `tests/test_deluge_parity.py` asserts the absence
of each of these from the deployable source.

### Prompt-injection posture

`Raw_Zia_Response` and `Validated_Analysis_JSON` are never read. Task content is
assembled solely from trusted persisted scalars, and the Task description states this
explicitly so a human reader knows the text was not model-authored. The parity test
fails if the executor ever reads either field.

## Failure handling — pre-claim vs post-claim

Not every `failed` result is terminal. **What matters is whether the conditional claim
had already succeeded when the failure happened.** No failure of either kind is retried
automatically; the difference is whether a human may safely rerun it.

| | Pre-claim failure | Post-claim failure |
| --- | --- | --- |
| Reasons | `record_fetch_failed`, `modified_time_unavailable`, `blocked_write_failed`, `claim_failed` | `task_create_failed`, `post_execution_write_failed` |
| Task creation authorized? | No | Claim succeeded; outcome unconfirmed |
| `Execution_Key` | May remain unset — record still claimable | **Populated** — record is claimed |
| Safe to rerun? | **Yes**, after the underlying problem is corrected | **No** — investigate first |
| Automatic retry | None | None |

### Pre-claim failure

The invocation stopped before winning the claim, so it authorized no Task creation and
the record may still be unclaimed. Once the underlying cause is fixed — CRM
unavailable, a transient 5xx, a missing `Modified_Time` — a fresh invocation is safe:
it refetches the record and re-evaluates the claim from scratch, exactly as a first
invocation would.

Rerunning is a deliberate human action. **The Flow performs no automatic retry.**

One nuance: `blocked_write_failed` means the policy gate refused the record *and* the
attempt to record that refusal failed. The record is still unclaimed, but it is also
still a policy violation — fix the policy problem, not just the write error.

### Post-claim failure — terminal, manual repair

This is the case requiring human investigation.

#### What happens on failure

| | |
| --- | --- |
| `Execution_Status` | `Failed` |
| `Execution_Key` | **stays populated** — never cleared automatically |
| `Execution_Attempts` | `1` — the one claimed attempt |
| `Execution_Error` | the sanitized error |

Because `Execution_Key` remains set, the already-claimed guard treats the record as
claimed. A later invocation returns `duplicate` / `already_claimed`: it creates no
Task, performs no record write, and does not advance `Execution_Attempts`.

#### Why it is not retried automatically

**A failed or lost Task-creation response does not prove the Task was not created.**
Zoho may have committed the Task and failed on the way back — a timeout, a dropped
connection, a 5xx after the write landed. A blind retry would then create a *second*
Task against the customer's record, which is precisely the outcome this stage exists
to prevent.

The asymmetry is deliberate: a missed execution is recoverable by a human in minutes,
while silently duplicating customer-facing work is not. So the system stops and asks.

#### Manual repair procedure

1. Look for a Task already linked to the recommendation's target record, created
   around `Execution_Started_At`.
2. **If a Task exists** — the write succeeded and only the response was lost. Set
   `Executed_Task_ID` to that Task's ID and `Execution_Status` to `Executed` by hand.
3. **If no Task exists** — the execution genuinely failed. Read `Execution_Error`, fix
   the cause, then deliberately clear `Execution_Key` and set `Execution_Status` to
   `Not Started` to make the record claimable again.

Never perform step 3 without doing step 1 first.

#### What `Execution_Attempts` actually means

It counts how many times a record has been **claimed** — not how many times execution
was tried. In this version it reaches at most `1`, because a claimed record is never
re-claimed automatically.

The `Execution_Attempts < 3` precondition is retained as a **defensive guard**, not as
a description of behaviour. It exists to bound repeated *manual* resets and to remain
correct if an automatic retry mechanism is added later. **This Flow does not perform
three attempts.**

## Deployment steps (manual, in order)

The picklist verification in step 1 is complete. The remaining deployment steps have
not been performed.

1. **Verify the `Target_Module` picklist — completed 2026-07-21.** Current CRM
   field-editor UI shows `Contacts`, `Leads`, `Deals`, and `Accounts`. No schema change
   is required. The older API metadata result that omitted `Accounts` is superseded as
   current-state evidence; see the dated correction in the inspection document.
2. **Use the existing `zoho_crm_to_zoho_flow` connection.** Its confirmed CRM CRUD,
   Task-create, and custom-module permissions cover the conditional claim and Task
   creation used by this function. Do not create a redundant connection.
3. **Verify execution field metadata:**
   `python3 scripts/zoho_crm_admin.py inspect-execution-fields`
   Expect `missing: []` and `mismatched: []`. All seven execution fields were
   confirmed present on 2026-07-19.
4. **Create the custom function.** Zoho Flow → Custom Functions → new Deluge function
   named `execute_approved_recommendation`, argument `ai_recommendation_record_id`
   (string), return type map. Paste `scripts/execute_approved_recommendation.deluge`
   verbatim.
5. **Create the Flow** named exactly `Execute Approved AI Recommendation`:
   - Trigger: Zoho CRM → *Record updated* on module `AI Recommendations`.
   - Filter/Decision `Approved?`: `Status` equals `Approved`.
   - Set Variable `recommendationRecordId` ← trigger record `id`.
   - Custom Function `execute_approved_recommendation`, mapping
     `ai_recommendation_record_id` ← `recommendationRecordId`. **Map nothing else.**
   - Decision `Execution Result` on the returned `status`, with the four branches
     above. Log each branch; take no further CRM action on any of them.
6. **Leave the Flow OFF** and exercise it with Test & Debug until the acceptance tests
   below pass.

## Acceptance tests to run against live Zoho

None of these have been run.

| # | Scenario | Setup | Expected |
| --- | --- | --- | --- |
| 1 | Approved Contact route | record `6719186000003183001` | `executed`; one Task on Contact `6719186000002999004`; `Execution_Status=Executed`; `Execution_Attempts=1` |
| 2 | Replay after success | re-run test 1 | `duplicate`; still exactly one Task |
| 3 | Rejected record | record `6719186000003185001` | `blocked` / `status_not_approved`; no Task |
| 4 | Pending Review record | any pending record | `blocked` / `status_not_approved`; no Task |
| 5 | **Lead route linkage** | approved Lead-target record | `executed`; Task appears on the Lead's Open Activities. **This settles the `Who_Id` vs `What_Id` conflict — see below.** |
| 6 | **Account route linkage** | approved Account-target record, e.g. `6719186000003181001` once approved | `executed`; Task appears on the Account's Open Activities |
| 7 | Deals target refused | set `Target_Module=Deals` | `blocked` / `target_module_not_allowed` |
| 8 | Attempt limit | set `Execution_Attempts=3` | `blocked` / `execution_attempts_limit_reached` |
| 9 | **Concurrent invocation** | fire the Flow twice simultaneously on one record | one `executed`, one `duplicate` / `claim_lost_race`; **exactly one Task**. Proves `If-Unmodified-Since` actually enforces the precondition. |
| 10 | Adversarial raw response | inject injection text into `Raw_Zia_Response` | Task content byte-identical to test 1 |
| 11 | **Lost-race error code** | force a stale `If-Unmodified-Since` claim | Zoho returns **HTTP 412 / `ALREADY_MODIFIED`**; executor returns `duplicate` / `claim_lost_race`; zero Tasks, zero writes. **Confirms the documented error code is what Zoho actually sends.** |
| 12 | Terminal failure | force a Task-creation failure, then invoke again | first `failed` with `Execution_Key` populated and `Execution_Attempts=1`; second `duplicate` / `already_claimed` with no Task and no write |

Tests 1–4, 7, 8 and 10 are covered offline by `tests/test_execution_policy.py`; running
them live proves the Deluge translation and the Zoho field semantics, which the offline
suite cannot. Tests 5, 6 and 9 have **no offline equivalent** — they test Zoho
behaviour the tests can only assume.

### Lookup value shape (corrected 2026-07-24)

Separate from the routing question below: `Who_Id` and `What_Id` are `json_type:
jsonobject` lookups (live Tasks metadata; Zoho Kaizen #36 examples), so the executor now
passes `{"id": target_record_id}`, not a bare id string. A bare string produces
`Who_Id expected jsonobject but received string`, which is the confirmed cause of the
prior failed live **Lead** Task creation. This value-shape fix is verified offline only;
Test 5 below must still confirm it live.

### Test 5 — RESOLVED by live evidence (2026-07-24)

The routing question is settled. Two independent live facts, both captured 2026-07-24:

1. **Live Tasks field metadata** (`getFields` on `Tasks`): `Who_Id`'s lookup module is
   **`Contacts` only** (`lookup.module.api_name = "Contacts"`); `What_Id` is a polymorphic
   lookup whose module is driven by `$se_module`. A Lead therefore cannot be placed in
   `Who_Id` at all — it is not a Contacts-lookup value.
2. **Live execution error.** A deployed executor variant that routed a **Lead** target into
   `Who_Id` (record `6719186000003573001`, target Lead `6719186000003570001`) returned
   `INVALID_DATA` at `$.data[0].Who_Id.id` — Zoho rejecting the Lead id as an invalid
   Contact id. Confirmed the Lead itself is valid, unconverted, and `Available`.

**Conclusion:** `TASK_LINK_FIELD["Leads"] = "What_Id"` with `$se_module = "Leads"` is
correct, matching the metadata and Kaizen #36. The BI1-T110 brief's `Who_Id` expectation is
**wrong for this org** and must not be applied. The repository already encodes the correct
routing; the failing run came from a **stale/hand-edited deployed function** that used
`Who_Id` for Leads. Fix = redeploy `scripts/execute_approved_recommendation.deluge` verbatim
so live matches the repo. A successful `executed` Lead run is still the final confirmation
that `What_Id` + `$se_module = "Leads"` creates a linked Task (metadata makes it the only
viable path; the create itself has not yet been observed to succeed).

### Test 9 is a decision point too

If both invocations create a Task, `If-Unmodified-Since` is not enforcing the
precondition as assumed, and the execution-ledger fallback described above must be
built before this Flow is switched on.

## Local commands

Run the tests (no dependencies, no network, no credentials):

```bash
python3 -m unittest discover -s tests -v
```

Inspect live CRM (read-only; requires credentials):

```bash
export ZOHO_CRM_CLIENT_ID=...
export ZOHO_CRM_CLIENT_SECRET=...
export ZOHO_CRM_REFRESH_TOKEN=...
export ZOHO_CRM_DC=us

python3 scripts/zoho_crm_admin.py inspect-module
python3 scripts/zoho_crm_admin.py inspect-fields
python3 scripts/zoho_crm_admin.py inspect-layouts
python3 scripts/zoho_crm_admin.py inspect-execution-fields

ZOHO_CRM_SAMPLE_RECORD_ID=6719186000003183001 \
  python3 scripts/zoho_crm_admin.py inspect-blueprint
```

Dry-run the idempotent setup command (writes nothing):

```bash
python3 scripts/zoho_crm_admin.py setup-execution-metadata --dry-run
```

Apply it (only creates fields that are missing; refuses if a live field contradicts
the contract):

```bash
python3 scripts/zoho_crm_admin.py setup-execution-metadata --apply
```

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `ZOHO_CRM_CLIENT_ID` | yes | OAuth client id |
| `ZOHO_CRM_CLIENT_SECRET` | yes | OAuth client secret |
| `ZOHO_CRM_REFRESH_TOKEN` | yes | OAuth refresh token |
| `ZOHO_CRM_DC` | no (default `us`) | Data centre: `us`, `eu`, `in`, `au`, `jp`, `ca`, `sa` |
| `ZOHO_CRM_API_BASE_URL` | no | Explicit API base; must be set together with the next |
| `ZOHO_CRM_ACCOUNTS_BASE_URL` | no | Explicit accounts base |
| `ZOHO_CRM_SAMPLE_RECORD_ID` | only for `inspect-blueprint` | Record whose transitions to list |

Required OAuth scopes: `ZohoCRM.settings.modules.READ`, `ZohoCRM.settings.fields.READ`,
`ZohoCRM.settings.layouts.READ`, and — for `setup-execution-metadata --apply` only —
`ZohoCRM.settings.fields.CREATE` and `ZohoCRM.settings.fields.UPDATE`.

No credential is ever printed. A failed token refresh reports the HTTP status and
error code only, never the response body, because that body can contain a token.

## Risks and limitations

1. **`Status` stays `Approved` after execution.** No API-supported Blueprint
   transition has been proven to exist, so the executor does not move the
   Blueprint-controlled field. `Execution_Status` is the execution source of truth.
   A reviewer scanning the `Status` column alone cannot tell executed from pending —
   use `Execution_Status`. Resolve by running `inspect-blueprint`.
2. **No Task linkage is verified — including Contacts.** The mapping rests on live
   field metadata plus Zoho's Kaizen #36 article, which contradict the BI1-T110 brief
   for Leads and are themselves contradicted by the v8 Insert Records reference on
   which modules `$se_module` accepts. Acceptance tests 5 and 6 are the only
   resolution. Do not treat any route as confirmed until they run.
3. **`post_execution_write_failed` needs a human.** The Task exists but the record
   does not record it. Resolve by hand: set `Executed_Task_ID` and
   `Execution_Status=Executed` on the record. See "Failure handling — pre-claim vs post-claim" above.
4. **A post-claim `failed` record is terminal and needs human investigation.**
   Pre-claim failures may be rerun once corrected. See "Failure handling" below.
   Either way nothing retries automatically, so failures need monitoring.
5. **Ingestion-side idempotency remains racy — and the execution stage cannot fix
   it.** The dedup key is the field labelled `Idempotency_Key` in the UI, whose API
   name is `Name` and which carries **no unique constraint**. Zoho Flow's
   `check_ai_recommendation_exists` guard is a read-then-write, so concurrent delivery
   of the same message can create two recommendation records. Each is a *distinct*
   record with a *distinct* execution key, so each would legitimately execute into its
   own Task. The conditional claim prevents double-execution of **one** recommendation;
   it cannot deduplicate **two** recommendations for the same email. Fixing that
   requires a unique constraint at ingestion — see finding 2 in the inspection doc.
6. **The conditional claim itself is unverified.** See "What is still unverified about
   it" above — timestamp granularity and Deluge header support are both assumptions
   until acceptance test 9 runs.
7. **The parity tests are structural, not behavioural.** They prove the Deluge
   contains the same checks, constants, and bounds as the tested Python, and that it
   performs no forbidden operation. They cannot prove the Deluge behaves identically.
   Only the live acceptance tests can.

## Operator runbook — the two remaining verification steps

Written 2026-07-23. These are the only outstanding items in BI1-T110. Both require
operator access that the repository tooling does not have.

### Step A — Concurrency acceptance test (execution stage)

**Why:** the conditional `If-Unmodified-Since` claim is proven by the offline test suite
but has never been exercised against live Zoho. This is the last unverified assumption in
the execution stage. If it fails, the execution-ledger fallback described above must be
built before this Flow can be trusted under concurrent load.

#### Setup

1. Create or pick an `AI_Recommendations` record that satisfies every precondition:
   `Status = Pending Review`, `Requires_Approval = true`, `Created_By_AI = true`,
   `Validation_Status = valid`, `Recommendation_Type = create_crm_task`,
   `Target_Module` one of Contacts / Leads / Accounts, `Target_Record_ID` non-blank.
2. Confirm its execution fields are clear: `Execution_Status` blank or `Not Started`,
   `Execution_Key` blank, `Executed_Task_ID` blank, `Execution_Attempts` blank or 0.
3. Note the record ID and its target record ID.

#### Run

1. Open the `Execute Approved AI Recommendation` Flow in Test & Debug.
2. Fire the custom function **twice as close to simultaneously as the tooling allows** —
   two browser tabs triggered back to back, or two rapid Postman calls to the Flow's
   webhook if one is configured. The goal is overlapping execution, not sequential.

#### Expected

- Exactly one invocation returns `status = executed` with an `executed_task_id`.
- The other returns `status = duplicate` with reason `claim_lost_race`
  (or `already_claimed` if the first fully finished before the second read).
- The recommendation shows `Execution_Status = Executed`, `Execution_Attempts = 1`.
- **CRM UI shows exactly ONE new open Task** on the target record.

**If two Tasks are created:** the conditional claim is not enforcing the precondition.
Stop, switch the Flow OFF, and build the execution-ledger fallback. Record the actual
response codes both invocations received — that determines whether the problem is
timestamp granularity or header support.

### Step B — Blueprint transition inspection (requirement 17)

**Why:** the executor deliberately does not move the Blueprint-controlled `Status` field
from `Approved` to `Executed`, because no API-invocable transition has been proven to
exist. `Execution_Status` is the execution source of truth until this is settled. The
practical cost of leaving it unresolved: a reviewer scanning the `Status` column alone
cannot tell an executed recommendation from a merely approved one.

#### Run

Export the OAuth credentials into the shell — never into a file in this repository — and
run the inspection command:

```bash
export ZOHO_CRM_CLIENT_ID=...
export ZOHO_CRM_CLIENT_SECRET=...
export ZOHO_CRM_REFRESH_TOKEN=...
export ZOHO_CRM_DC=us

ZOHO_CRM_SAMPLE_RECORD_ID=6719186000003183001 \
  python3 scripts/zoho_crm_admin.py inspect-blueprint
```

Required scope: `ZohoCRM.settings.modules.READ` plus record read on the module. The
sample record must be one currently sitting in an `Approved` Blueprint state.

#### Interpreting the output

- **A transition named something like `Approved → Executed` is listed** → the transition
  exists and is API-invocable. The executor may be extended to call it after a successful
  Task creation. Do this as a *separate* change with its own test, and only after Step A
  passes.
- **Only `Approve Recommendation` / `Reject Recommendation` are listed, or the list is
  empty** → no such transition exists. Keep the current design. Record the result here and
  close requirement 17 as answered.

**Either way, record the raw output in this document** so the question is not reopened.

### After both steps

Update `STATUS.md` with the results, then BI1-T110 has no
remaining verification work.
