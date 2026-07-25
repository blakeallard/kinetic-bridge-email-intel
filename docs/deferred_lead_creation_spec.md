# Spec: Deferred Lead Creation (Model C — approval-gated)

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Status: PROPOSED — not yet implemented. No Deluge changed by this document.**

Written 2026-07-24. This is a design/decision document to be reviewed before any code or
live-flow change. It supersedes the eager-Lead behavior described in
`single_path_refactor_spec.md` once implemented.

## 1. The decision

Move Lead creation for unmatched senders **out of ingestion and into the approval/execution
stage**, so a Lead is minted only when a human approves the recommendation. Rejected
recommendations create nothing. (Model C from the 2026-07-24 architecture discussion.)

Low-confidence / cold inbound may additionally defer even the Task until the prospect
replies; that is a **later, optional** second gate and is out of scope for this spec, which
only moves the *Lead-creation trigger* from ingestion to approval.

## 2. Current behavior — where the eager create lives

The Lead is created during **ingestion**, as a side effect of the CRM-match step, not in a
block named "create lead":

- `resolve_crm_match(from_email, from_domain)` — read-only. Returns `matched` (existing
  Contact/Account/Lead found) or `no_match`. Contains no `createRecord`.
- `ensure_crm_match(normalized, resolve_result)` — if `resolve_result` is already matched,
  returns it unchanged; otherwise **creates a Lead immediately** at
  `scripts/single_path/ensure_crm_match.deluge:85`
  (`zoho.crm.createRecord("Leads", lead_map, Map(), "zoho_crm_to_zoho_flow")`) and returns a
  synthetic `matched → Leads → <new id>` result.

Confirmed live: Lead `6719186000003570001` (created for the last test email) is owned by
Blake (`6719186000002395001`), which is the owner id hardcoded in `ensure_crm_match` line 13.
`create_lead_for_unmatched.deluge` is a **dead duplicate** (stamps Bill,
`6719186000000503001`) that is not wired into the live flow and also violates the
"test data owner is Blake" rule. It is removed as part of this work.

### Timeline (why the approval gate has no say today)

```
webhook → normalize → dedup
  → resolve_crm_match      (read only → no_match)
  → ensure_crm_match       ← LEAD CREATED HERE (ingestion, line 85)
  → fetch_open_related → build_crm_context → associate_email → build_crm_snapshot
  → Trigger Zia → wait → fetch → validate → persist_recommendation
  ─────────────── (separate flow, later) ───────────────
  → human Approve → execute_approved_recommendation → Task created
```

The Lead exists before Zia runs, before the recommendation is persisted, and long before
approval. Reject the recommendation and the junk Lead remains.

> Note: the block table in `single_path_refactor_spec.md` (block 6 = `resolve_crm_match`
> straight into block 7) predates `ensure_crm_match` and does not show it. That table is
> stale and should be reconciled when this ships.

## 3. The complication that makes this non-trivial

The eager create is load-bearing for the *classification*, not just for data. Today an
unmatched sender is turned into a Lead so that, by the time Zia analyzes and the validator
runs, `match_status = "matched"`. The tagged validator
(`validate_zia_analysis_response_tagged`) sets `validation_status = "valid"` only when
matched, and **forces `manual_review` when unmatched**. It also needs a real
`target_record_id` for the `create_crm_task` recommendation.

If we simply delete the create and leave `match_status = "no_match"`, every new-sender email
becomes a `manual_review` recommendation with no actionable target — we would trade "junk
Leads" for "no Leads and no tasks." So the refactor must introduce an explicit **pending-lead**
state that the validator, persistence, and executor all understand: "no existing record, but
a Lead is intended and its details are captured — create it on approval."

## 4. Design — the pending-lead state

Introduce one new match state, `pending_lead`, carried end to end. It means: *no CRM record
exists yet; a Lead should be created from the captured sender fields when (and only when) a
human approves.*

### 4.1 Data model — no schema change (recommended)

Reuse two existing, currently-unused `AI_Recommendations` fields so this stays a Tier-1
change (no custom-field creation, which would be Tier 2/3):

| Field (existing) | Pending-lead use |
| --- | --- |
| `Target_Record_ID` | left **blank** while pending (the record does not exist yet) |
| `Target_Module` | `Leads` (the module that *will* be created) |
| `Email` | the sender email (currently null on records) |
| `Approved_Action_JSON` | JSON blob holding the captured Lead fields, e.g. `{"pending_lead":{"first_name":"Blake","last_name":"Allard","company":"Unknown","email":"…","lead_source":"Email"}}` |

**Pending signal** = `Target_Record_ID` is blank **and** `Approved_Action_JSON` contains a
non-empty `pending_lead` object. No sentinel string in `Target_Record_ID` (it is parsed with
`toLong()` downstream, so a non-numeric sentinel would break it).

Alternative (cleaner but requires approval): add one checkbox field
`Pending_Lead_Creation` and dedicated text fields for the captured contact. This is more
explicit and reportable but is a **schema change (Tier 2/3)**. Recommendation: ship with the
field-reuse approach first; promote to explicit fields later if the overload proves awkward.

### 4.2 Function-by-function changes

**`ensure_crm_match` → becomes read-only (rename to `classify_crm_match` suggested).**
- Delete the `createRecord("Leads", …)` block (lines ~68–95).
- When `resolve_result` is matched, return it unchanged (as today).
- When unmatched, return `match_status = "pending_lead"`, `matched_module = "Leads"`,
  `matched_record_id = ""`, `contact_id = ""`, `lead_id = ""`, **plus** the derived
  `pending_contact` map (the `first_name`/`last_name`/`company`/`email`/`lead_source`
  extraction it already computes stays; only the write is removed).
- Downstream blocks already tolerate blank `contact_id`/`lead_id`
  (`fetch_open_related` now guards; `build_crm_context`/`build_crm_snapshot` accept blanks).

**`validate_zia_analysis_response_tagged` → treat `pending_lead` as valid + actionable.**
- Currently: `validation_status = "valid"` iff `match_status == "matched"`, else `fallback`
  + forced `manual_review`.
- New: `pending_lead` is also `valid`, and the recommendation stays `create_crm_task` with
  `target_module = "Leads"`, `target_record_id = ""`, and a `pending_lead = true` flag +
  the `pending_contact` payload carried into the validated object.
- Matched and truly-unclassifiable cases are unchanged.

**`persist_recommendation` → persist the pending payload.**
- When `pending_lead`, write `Target_Module = "Leads"`, `Target_Record_ID = ""`, `Email =
  <sender email>`, and `Approved_Action_JSON = {"pending_lead":{…}}`.
- Everything else (idempotency via `Ingestion_Key`, Status `Pending Review`, etc.) unchanged.

**`execute_approved_recommendation` / `execution_policy.py` → create the Lead on approval.**
This is the load-bearing change. New ordering inside the executor:
1. Refetch record, run the **already-claimed** guard (unchanged).
2. Run the **policy gate** (amended preconditions — see 4.3).
3. Perform the **conditional claim** (`If-Unmodified-Since`) — unchanged.
4. **New step (winner only, after the claim):** if the record is a pending-lead, create the
   Lead from `Approved_Action_JSON.pending_lead` (owner = Blake, `Lead_Source`,
   `Lead_Status = "Not Contacted"`, same field-map `ensure_crm_match` used to use). On
   success, immediately write the new Lead id to `Target_Record_ID` on the recommendation so
   a later manual rerun sees it and never double-creates. On failure, return `failed` /
   `lead_create_failed` (post-claim; terminal — see 4.4).
5. Build the Task exactly as today, using the now-populated `Target_Record_ID` and the
   existing routing (Leads → `What_Id` + `$se_module = "Leads"`, just validated live).
6. Record `Executed_Task_ID` / `Executed_At` / `Execution_Status = Executed` — unchanged.

### 4.3 Precondition changes (executor policy gate)

Two of the ten preconditions must change; the rest are unchanged.

| # | Field | Today | New |
| --- | --- | --- | --- |
| 6 | `Target_Module` | in {Contacts, Leads, Accounts} | unchanged |
| 7 | `Target_Record_ID` | non-blank | non-blank **OR** (`pending_lead` and a valid `pending_contact` with a non-blank email) |

Add a guard that a pending-lead record's `pending_contact` has at least an email and a
last_name before it is claimable; otherwise `blocked / pending_contact_incomplete`.

## 5. Downstream effects to decide on

1. **Email association.** `associate_email_to_crm_record` (ingestion block 9) currently
   attaches the inbound email to the freshly-created Lead. With deferral, an unmatched
   sender has no record to attach to at ingestion. Options: (a) skip association for
   pending-lead senders and re-associate inside the executor after the Lead is created
   (preferred — keeps the email linked once the record exists), or (b) accept that
   never-approved emails are never associated (also defensible). Pick one; (a) is the fuller
   fix and belongs in the executor's new step 4.
2. **Zia sees an unmatched sender.** The snapshot/context carry blank ids, which the
   validator already handles. Classification quality for cold senders should be re-checked
   once live, but the AI already reasons from email content, not just CRM state.
3. **Duplicate leads across two recommendations for the same email.** Ingestion idempotency
   is still racy (known risk #5 in the executor flow doc): two recommendations for one email
   could, if both approved, create two Leads. This is no worse than today's two-Tasks risk
   and is arguably improved (only approved ones create Leads). Not solved here; note it.
4. **Executor now reads email-derived data.** The Lead's name/company come from untrusted
   email-body parsing (the same parsing `ensure_crm_match` does today). This is a **scalar
   data** read, not instruction execution — the prompt-injection posture is unchanged in
   substance; the values were already flowing into a Lead, only the timing moves. The
   executor must still never read `Raw_Zia_Response` / `Validated_Analysis_JSON`.

## 6. Failure & idempotency handling for the new Lead-create step

- The Lead create happens **after** the conditional claim, so only the single claim-winner
  runs it — no concurrent double-create of the Lead for one recommendation.
- **Lead created, Task failed** = post-claim failure, terminal. `Target_Record_ID` now holds
  the created Lead id and `Execution_Key` stays set, so a rerun returns
  `duplicate / already_claimed` and creates nothing. Manual repair: the Lead exists; either
  finish the Task by hand or clear the claim to retry (the Task-create is now idempotent-safe
  because `Target_Record_ID` is populated — a rerun would not re-create the Lead).
- **Lead create failed outright** = post-claim `failed / lead_create_failed`. No Task, no
  linked record. Human clears `Execution_Key` + `Execution_Status = Not Started` to retry
  after fixing the cause. `Target_Record_ID` stays blank so the retry re-attempts the Lead.

## 7. Testing & parity plan

- **`execution_policy.py`** remains the executable spec; mirror every Deluge change there and
  keep `tests/test_deluge_parity.py` green. Add the pending-lead branch to the policy sim.
- New offline tests:
  - pending-lead record with complete contact → executor creates Lead then Task, links Task
    to the new Lead via `What_Id`.
  - pending-lead with blank email/last_name → `blocked / pending_contact_incomplete`.
  - matched record (existing Contact/Lead/Account) → unchanged behavior.
  - rejected pending-lead recommendation → no Lead, no Task (assert no `createRecord`).
  - `ensure_crm_match`/`classify_crm_match` → asserts **no** `createRecord("Leads")` remains
    in the source (the inverse of today's assumption).
- `tests/test_ingestion_artifacts.py` currently asserts the getRelatedRecords string and the
  match contract; update the match-function assertions to the read-only shape.
- Live acceptance: one cold-sender email end to end — recommendation persists as pending,
  approval creates exactly one Blake-owned Lead **and** one linked Task; a rejected pending
  recommendation creates neither.

## 8. Rollout order

1. Land the code + tests in the repo (this spec → implementation), offline suite green.
2. Deploy the read-only match function, updated validator, and updated
   `persist_recommendation` to the live single-path Flow.
3. Deploy the updated executor.
4. Run the live acceptance pair (approve-path and reject-path) before switching reliance.
5. Reconcile `single_path_refactor_spec.md` block table and remove
   `create_lead_for_unmatched.deluge`.

## 9. Scope guard — what this does NOT change

No change to OAuth scopes, connections, Blueprint transitions, the Zia agent, or the
approval UX. No new Deal/Account creation. The wait-for-reply second gate for low-confidence
inbound is explicitly deferred to a future spec.
