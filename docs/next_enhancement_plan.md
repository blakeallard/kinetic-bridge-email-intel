# BI1-T110 — Next bounded enhancement plan

Drafted 2026-07-24. Two independent parts. Nothing here has been deployed to live Zoho.
The repo-side code changes (Part A newline fix, Part B proposed function) and their tests
are committed to the repo only; all live-Zoho steps are documented as wiring instructions
for a human to perform in the UI.

Source-of-evidence convention used throughout:

- **CONFIRMED** — proven by repo code, tests, or a prior live validation recorded in
  `STATUS.md` / `docs/`.
- **ASSUMPTION** — believed true, not yet proven here; safe to build against but flag.
- **VERIFY LIVE** — must be checked in the Zoho UI before or during wiring.

---

## Part A — CRM presentation cleanup (`AI_Recommendations`)

UI-only, plus one repo code fix. **No API names change** — only field *labels*, layout
section grouping, and a list view. Renaming labels never affects Deluge, Flow mappings, or
tests, all of which reference API names.

### A1. Proposed field labels (API name unchanged → new UI label)

CONFIRMED field set from `docs/live_module_inspection_2026-07-19.md` plus the unique
`Ingestion_Key` added 2026-07-23.

| API name | Current/known label | Proposed UI label | Section |
| --- | --- | --- | --- |
| `Recommendation_Type` | Recommendation Type | **Recommended Action** | 1 Summary |
| `Target_Module` | Target Module | **CRM Target Module** | 1 Summary |
| `Target_Record_ID` | Target Record ID | **CRM Target Record** | 1 Summary |
| `Validation_Status` | Validation Status | **AI Validation Result** | 1 Summary |
| `Status` | Status | **Review Status** | 2 Review and Approval |
| `Requires_Approval` | Requires Approval | **Requires Human Approval** | 2 Review and Approval |
| `Reviewed_By` | Reviewed By | **Reviewed By** | 2 Review and Approval |
| `Reviewed_At` | Reviewed At | **Reviewed At** | 2 Review and Approval |
| `Review_Notes` | Review Notes | **Reviewer Notes** | 2 Review and Approval |
| `Execution_Status` | Execution Status | **Execution Status** | 3 Execution |
| `Executed_Task_ID` | Executed Task ID | **Created Task ID** | 3 Execution |
| `Execution_Started_At` | Execution Started At | **Execution Started At** | 3 Execution |
| `Executed_At` | Executed At | **Executed At** | 3 Execution |
| `Execution_Attempts` | Execution Attempts | **Execution Attempts** | 3 Execution |
| `Execution_Error` | Execution Error | **Execution Error** | 3 Execution |
| `Execution_Key` | Execution Key | **Execution Idempotency Key** | 3 Execution |
| `Name` | Idempotency_Key | **Recommendation Key** | 4 Technical Metadata |
| `Message_ID` | Message ID | **Source Message ID** | 4 Technical Metadata |
| `Ingestion_Key` | Ingestion Key | **Ingestion Idempotency Key** | 4 Technical Metadata |
| `Created_By_AI` | Created By AI | **Created by AI** | 4 Technical Metadata |
| `Validated_Analysis_JSON` | Validated Analysis JSON | **Validated Analysis (JSON)** | 5 Raw AI Data |
| `Raw_Zia_Response` | Raw Zia Response | **Raw Zia Response (JSON)** | 5 Raw AI Data |
| `Approved_Action_JSON` | Approved Action JSON | **Approved Action (JSON)** | 5 Raw AI Data |

Notes:

- `Name` is the module's display field (system-mandatory), so it also renders as the record
  title regardless of section. Its live UI label is already `Idempotency_Key`; relabeling to
  **Recommendation Key** reads better in the title bar. VERIFY LIVE that the display-field
  label can be changed (display fields sometimes lock the label).
- `Requires_Approval` and `Approved_Action_JSON` are read by the executor / seen in
  inspection but were not in the 2026-07-19 field-table excerpt — VERIFY LIVE they exist and
  sit in the sections above; if absent, drop those rows.
- System fields `Created_Time`, `Modified_Time`, `Modified_By`, `Record Owner` → keep in
  **4 Technical Metadata**.

### A2. Layout sections (top to bottom)

1. **Recommendation Summary** — Recommended Action, CRM Target Module, CRM Target Record,
   AI Validation Result.
2. **Review and Approval** — Review Status, Requires Human Approval, Reviewed By,
   Reviewed At, Reviewer Notes.
3. **Execution** — Execution Status, Created Task ID, Execution Started At, Executed At,
   Execution Attempts, Execution Error, Execution Idempotency Key.
4. **Technical Metadata** — Recommendation Key, Source Message ID, Ingestion Idempotency
   Key, Created by AI, plus system audit fields.
5. **Raw AI Data** — Validated Analysis (JSON), Raw Zia Response (JSON), Approved Action
   (JSON). Collapsed by default; this is the untrusted model output a reviewer opens only
   when they want the original analysis.

The **required** move — `Validated_Analysis_JSON` and `Raw_Zia_Response` into Raw AI Data —
is captured in section 5.

### A3. Proposed default list view — "Review Queue"

Columns, left to right (all CONFIRMED fields):

1. Recommended Action (`Recommendation_Type`)
2. CRM Target (`Target_Module`, with `Target_Record_ID` as a second column if the view
   allows two)
3. Review Status (`Status`)
4. AI Validation Result (`Validation_Status`)
5. Execution Status (`Execution_Status`)
6. Created Time (`Created_Time`)

Sort: **Created Time, descending** (newest first). Criteria: none (show all) for the default
view. Recommend also cloning it to a **"Pending Review"** view with criteria
`Review Status is Pending Review` — that is the human reviewer's actual work queue and pairs
with the Cliq notification.

### A4. Repo code fix — Task Description newlines — DONE (in this change)

CONFIRMED root cause: Deluge does not interpret a `"\n"` string literal as a newline, so
CRM Task Descriptions rendered literal backslash-n. `execute_approved_recommendation.deluge`
now builds the Description with `new_line = hexToText("0A")` (the same pattern the Cliq
function uses). The Python spec `execution_policy.py` already joins with a real newline, so
this only closes a Deluge-vs-spec presentation gap — no policy or bound changed.

Regression coverage added in `tests/test_deluge_parity.py`
(`TestTaskDescriptionNewlines`): asserts `hexToText("0A")` is used, that **no** literal
backslash-n survives in the Deluge, that the Description is assembled from the `new_line`
variable, and that the Python spec still joins with a real newline.

### A5. Live UI wiring steps for Part A (human, in CRM)

1. **Setup → Customization → Modules and Fields → AI Recommendations → Layout editor.**
2. Rename each field's label per the A1 table (double-click the field → edit label). Do
   **not** touch API names.
3. Create/rename the five sections in A2 and drag fields into them; set **Raw AI Data** to
   collapsed.
4. Move `Validated_Analysis_JSON` and `Raw_Zia_Response` (and `Approved_Action_JSON`) into
   **Raw AI Data**. Save the layout.
5. **List views:** create view "Review Queue" with the A3 columns, sorted by Created Time
   desc, no criteria; set as default if desired. Clone to "Pending Review" with criteria
   `Status is Pending Review`.
6. Re-deploy the executor function body (`execute_approved_recommendation.deluge`) so the
   newline fix reaches live — this is the only live change that carries code, and it is a
   pure Description-formatting change with identical policy behavior.
7. Sanity check: approve one test recommendation and confirm the resulting Task Description
   shows real line breaks.

---

## Part B — outbound-response Lead lifecycle (`Not Contacted` → `Contacted`)

Goal: when a Kinetic Bridge user sends the **first outbound response** to a Lead's inquiry,
advance that Lead's `Lead_Status` from `Not Contacted` to `Contacted`. Separate automation;
the inbound ingestion path is untouched.

### B1. Design invariants (all enforced by the proposed function)

- CONFIRMED: only Leads currently at **exactly** `Not Contacted` are updated
  (`if(current_status != eligible_status)` returns `skipped`).
- CONFIRMED: later statuses never regress — the function writes only when the source state
  is `Not Contacted`, and only ever writes the single value `Contacted`.
- CONFIRMED: **idempotent** — a second (or concurrent duplicate) trigger finds the Lead
  already `Contacted` and no-ops. Because the update writes a fixed target value from a
  single eligible source state, even an overlapping double-write is a semantic no-op; no
  conditional `If-Unmodified-Since` claim is needed (unlike the executor, which creates a
  Task and therefore must guard against duplicates).
- CONFIRMED: no Lead conversion, no Deal creation, no later lifecycle stages — the function
  writes only `Lead_Status` (test `test_writes_only_the_lead_status_field`), and contains
  none of `convertLead` / `createRecord` / `Deals`.
- "First" is enforced by the status guard, not by counting sends — the second outbound to an
  already-`Contacted` Lead is a no-op.

### B2. Proposed implementation

`scripts/advance_lead_on_first_outbound.deluge` (new, in repo, **not deployed**):

- `map advance_lead_on_first_outbound(string lead_id)`
- Blank-guard → fetch `Leads` record → read `Lead_Status` → if `!= "Not Contacted"` return
  `skipped`/`status_not_eligible` → else update `Lead_Status = "Contacted"` → return
  `advanced`. Returns a diagnostic map (`previous_status`, `new_status`, `reason`) in all
  paths.

The function takes only a Lead ID. The **trigger** is responsible for (a) detecting an
outbound response and (b) resolving it to the right Lead, then calling this function.

### B3. Trigger source evaluation

Three candidate signals for "a Kinetic Bridge user sent the first outbound response":

**Option 1 — CRM email activity on the Lead (RECOMMENDED).**
When the outbound reply is associated to / sent from the Lead in CRM, an Email activity
exists on the Lead. This is the closest signal to "responded" and stays entirely inside
CRM, where the function already runs.

- CONFIRMED: this org supports email association to Leads and the executor/association
  stack already writes received email to Leads (`associate_email_to_crm_record.deluge`,
  `ASSOC-LEAD-026`).
- ASSUMPTION: outbound replies from a Kinetic Bridge user land on the Lead as an Email
  activity (either via CRM "Send Mail" on the Lead, or an outbound association analogous to
  the inbound one with `sent=true`).
- VERIFY LIVE: whether a CRM **Workflow Rule** can trigger on email activity directly.
  Standard CRM workflow triggers are record actions (Create/Edit/Field Update) on a module;
  "email sent" is available as a workflow trigger in some editions but must be confirmed in
  Setup → Automation → Workflow Rules → (new rule) → When. If email-sent is not an available
  trigger, fall back to Option 3.

**Option 2 — TeamInbox outbound event.**
Mirror the inbound architecture: a Zoho Flow triggered by a TeamInbox "reply sent" webhook
resolves the Lead and calls the function.

- CONFIRMED: TeamInbox → Zoho Flow webhooks are the proven inbound mechanism.
- CONFIRMED (caveat): an internal outgoing copy has been observed arriving as
  `NEW_INBOUND_MESSAGE` (see STATUS) — i.e. TeamInbox's event typing for outbound is not
  clean in our evidence.
- VERIFY LIVE: whether TeamInbox exposes a distinct **outbound/sent** trigger with a payload
  that carries the thread/Lead linkage. Until verified, treat as ASSUMPTION. Risk: rebuilding
  thread→Lead resolution outside CRM duplicates matching logic.

**Option 3 — CRM Lead field/record edit + a "responded" marker (robust fallback).**
If neither a clean email-sent trigger nor a TeamInbox outbound event is available, drive the
advance from a small explicit signal: a workflow/button that sets a checkbox (e.g. a
`First_Response_Sent` boolean) which a Field-Update workflow rule reacts to by calling the
function. Fully inside CRM, no new webhook, but requires the user action (or a Flow) to set
the marker.

**Recommendation:** pursue **Option 1** first (closest to intent, no new webhook, reuses CRM
email activity), with **Option 3** as the guaranteed-available fallback. Option 2 only if the
operator wants the signal to originate in TeamInbox and confirms a clean outbound event.

### B4. Live UI wiring steps for Part B (human, in CRM) — pending trigger choice

Common to all options:

1. Create the custom function from `scripts/advance_lead_on_first_outbound.deluge` (category
   per the editor; argument `lead_id` as String — same pattern as the Cliq function's
   `recommendation_id`).
2. Point the chosen trigger at it, mapping the Lead's `Id` to `lead_id`.

Option 1 (email activity): Setup → Automation → Workflow Rules → module **Leads** → When =
email-sent (VERIFY LIVE it exists) → Instant Action = this function → map `lead_id` to the
Lead `Id`.

Option 3 (marker fallback): add a `First_Response_Sent` checkbox to Leads → Workflow Rule on
Leads, When = Field Update of that checkbox to true → Instant Action = this function.

3. Validate: on a Lead at `Not Contacted`, send/mark the first outbound response → confirm
   `Lead_Status` becomes `Contacted`; repeat the trigger → confirm no change and no error;
   manually set a different Lead to `Qualified` → fire the trigger → confirm it stays
   `Qualified`.

### B5. Reuse note

If Option 1/2 needs to *associate* the outbound email (not just detect it),
`associate_email_to_crm_record.deluge` is reusable with `sent=true` and the from/to reversed
(Kinetic Bridge user = from, Lead = to). That association is optional for the status advance
itself and is out of scope unless the operator wants outbound emails logged on the Lead.

---

## Unresolved lifecycle decisions for Bill/Bryan

1. **Confirm the trigger source for Part B.** Option 1 (CRM email-sent) vs Option 3 (marker
   checkbox) vs Option 2 (TeamInbox outbound). Needs the live-UI check on whether an
   email-sent workflow trigger exists, plus their preference on where the signal originates.
2. **What counts as an "outbound response"?** Any email from a Kinetic Bridge user to the
   Lead, or only a genuine reply in the inquiry thread? (Affects Option 1/2 scoping.)
3. **Lead owner routing** (carried over): production owner Bill vs Bryan by inbox/area —
   still deferred; testing owner is Blake.
4. **When does a Lead advance past `Contacted`?** This enhancement stops at `Contacted`.
   `Contacted → Qualified/Convert`, Deal creation, and later stages remain manual/deferred
   pending their decision (consistent with the no-match Lead-creation decisions already
   logged in STATUS).
5. **Part A label wording** — the proposed labels are a first pass; confirm any house-style
   naming (e.g. "Recommended Action" vs "AI Action", "Created Task ID" vs "CRM Task").
6. **Promote the Cliq channel** — add Bill/Bryan and move off `ai-recs-test` once they want
   live notifications (already tracked; listed here so it is decided alongside the rest).
