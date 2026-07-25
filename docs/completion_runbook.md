# BI1-T110 Completion Runbook

Explicit, ordered, click-by-click steps to finish the AI email intelligence workflow.

Ground rules for every step:
- Do steps in order. Each phase assumes the prior one is done.
- Where a step says **STOP**, do not continue until the check passes.
- Where a step branches **A / B**, pick based on the check immediately above it.
- "Ingestion flow" = the live single-path flow whose webhook is
  `https://flow.zoho.com/901489292/flow/webhook/incoming`.
- Do not paste webhook URLs, zapikeys, or tokens into chat, commits, or screenshots.

---

## PHASE 1 — Stop active damage

### Step 1 — Fix Quote Intake Deal creation (`Account_Name` error)

Symptom: every form submission throws `required field not found. Check the input for
Account_Name` at the Deal-creation block.

1. Zoho Flow → open the flow named **Quote Intake**.
2. Click the block labelled **Create module entry** (the one whose Module is `Deals`).
3. Find the field row **Account Name**.
4. Determine its type — click the value box:
   - If it offers a free-text/variable input → it is a **plain field**.
   - If it forces you to pick an existing Account record → it is a **lookup**.

**STOP. The fix differs by type.**

**Branch A — plain field:**
5A. Set **Account Name** value to the mapped variable `${trigger.SingleLine}` (the form's
   Company field; confirm it is Company in the trigger sample, not another single-line field).
6A. Save the block. Go to Step 1 verification.

**Branch B — lookup field:** a Deal cannot be created without an existing Account ID, so
you must find-or-create the Account first.
5B. Before the Deal block, add a **Zoho CRM → Search Records** action:
   - Module: `Accounts`
   - Criteria: `Account_Name` equals `${trigger.SingleLine}`
6B. Add a **Decision** after the search: condition = search result count is greater than 0.
7B. On the **false** branch, add **Zoho CRM → Create Records**:
   - Module: `Accounts`
   - `Account_Name` = `${trigger.SingleLine}`
   - capture the new Account ID as a variable.
8B. Merge both branches so an Account ID is available (either the found one or the created one).
9B. In the **Create module entry** Deal block, set **Account Name** to that Account ID variable.
10B. Save.

**Step 1 verification:**
- Submit the form once with a unique Company value (e.g. `Runbook Test 01`).
- Quote Intake History → newest run → the **Create module entry** block must show
  status success and return a Deal ID.
- **STOP** if it still errors; capture the exact block error text before continuing.

### Step 2 — Kill duplicate intake (form → TeamInbox forward)

Goal: one submission must hit the ingestion pipeline exactly once (via the new
form→webhook flow), never also via the old form→shared-inbox→TeamInbox forward.

1. Identify the duplicate channel. Two candidates — check both:
   a. Zoho Forms → **KB_Website_Form** → Settings → **Integrations** — look for any
      integration that emails or pushes to `bms@kinetic-bridge.com` or a shared inbox.
   b. Zoho Mail → the shared inbox that feeds TeamInbox → **Filters/Forwarding rules** —
      look for a rule forwarding form-notification mail into TeamInbox.
2. For whichever exists and feeds TeamInbox from the form: **disable it** (toggle off; do
   not delete yet — you may need to confirm nothing else depends on it).
3. Leave the new **KB Website Form → AI Recommendation** flow ON.

**Step 2 verification:**
- Submit the form once.
- Ingestion flow History: exactly **one** new run.
- TeamInbox: **no** new `New … Inquiry` message appears for this submission.
- **STOP** if a TeamInbox message still appears — the forward is still active; find and
  disable the remaining source.

### Step 3 — Rotate the exposed zapikey

The key `1001.2994ee1127701a03f335bcd7a57708da.7587b7c6d109c321378dafad9886d86f` was
exposed in plaintext and must be treated as compromised.

1. Zoho Flow → ingestion flow → the **Webhook** trigger block.
2. Find the option to **regenerate / reset** the webhook URL or its key.
3. Regenerate. Copy the new URL (do not paste it into chat).
4. Open the **KB Website Form → AI Recommendation** flow → **Send Webhook** block.
5. Replace the URL's `zapikey=` value with the new key. Save.
6. If any other caller uses the old URL (TeamInbox webhook config, Postman, other flows),
   update each.

**Step 3 verification:**
- Submit the form once. Ingestion flow History shows a new run (proves the new key works).
- **STOP** if the run does not appear — the form flow still holds the old key.

### Step 4 — Fix the form autoresponder "From"

Currently sends from `blake@kinetic-bridge.com` (the form owner fallback) because the
template's From is unset/unverified.

1. Zoho Forms → **KB_Website_Form** → **Email & Notifications** → **Email** → open **My Template**.
2. Click the **From** dropdown at the top.
3. Select a verified `info@kinetic-bridge.com` sender.
   - If `info@` is not in the list, it is not a verified sender: go to Zoho Forms sender
     settings, add and verify `info@kinetic-bridge.com`, then return here.
4. Save.
5. (Optional) If no customer-facing acknowledgment is wanted at all, toggle the template
   **off** instead.

**Step 4 verification:**
- Submit the form with a real external email you control.
- The acknowledgment email arrives **From `info@kinetic-bridge.com`**, not `blake@`.

**PHASE 1 DONE when:** one submission creates one Deal (no error), one ingestion run, no
duplicate TeamInbox message, and the autoresponder is correctly branded.

---

## PHASE 2 — One message = one CRM record (the core seam)

These three are build work (Deluge + Flow wiring), not just clicks. Each needs a decision
recorded before building.

### Step 5 — No-match → create Contact + Lead (plan 5b-ELSE)

Decision to confirm first:
- On an unknown sender, create **both** a Contact and a Lead (plan says both), or only a Lead?
- Owner for created records?
- Lead Source value to stamp (e.g. `Website` for form, `Email` for inbound)?

Build:
1. New Deluge function `create_crm_record_for_unmatched(map normalized)`:
   - Create a Contact: `Last_Name` from `from_name` (fallback to email local-part),
     `Email` = `from_email`.
   - Create a Lead: `Last_Name`, `Company` (from parsed body Company if present else
     "Unknown"), `Email`, `Lead_Source`.
   - Return both IDs.
2. In the ingestion flow, on the **no-match** branch (currently → `manual_review`
   fallback), insert this function BEFORE validation.
3. Feed the created Contact/Lead ID into the same association + analysis path the match
   branches use, so the email attaches and Zia runs against a real record.
4. Add a static test asserting the function creates exactly one Contact and one Lead and
   returns both IDs.

**Verification:** submit from a brand-new external email with no CRM record → a Contact and
a Lead are created, the email is attached, and a `create_crm_task` recommendation (not
`manual_review`) is persisted against the new record.

### Step 6 — Cross-channel dedup (form + email = one recommendation)

Problem: the same inquiry arriving by form and by email produces two `Ingestion_Key`s and
two recommendations.

Decision to confirm first:
- Dedup window (e.g. same sender + similar subject within N hours = same conversation)?
- Or thread-based only (requires Step 7 threading)?

Build (minimum viable):
1. In `check_ai_recommendation_exists`, add a secondary lookup: same `from_email` + same
   normalized subject within a time window, in addition to the exact-key check.
2. If a recent match exists, short-circuit to the existing record instead of creating a new
   recommendation.
3. Add tests for: exact-key duplicate (existing behavior) and near-duplicate within window.

**Verification:** submit the form, then send an email from the same address with the same
subject within the window → only one recommendation exists.

### Step 7 — Thread preservation for the form path

Problem: `build_form_intake_payload` fabricates a `messageId`, so a later email reply does
not thread to the form-originated record.

Decision to confirm first:
- Key threading on sender+subject, or introduce a stable conversation ID stamped on the
  created Lead/Contact?

Build:
1. When a form creates/attaches a record, store a conversation key (e.g. on a custom field
   or note) derived from sender+subject.
2. When a later email arrives, `resolve_crm_match` also checks that conversation key and
   attaches to the same record/thread rather than creating a parallel one.

**Verification:** submit the form, then reply by email as the customer → both land on the
same CRM record, in order.

**PHASE 2 DONE when:** any message — form or email, known or unknown sender — becomes or
attaches to exactly one CRM record, with no duplicates and correct threading.

---

## PHASE 3 — Close the remaining plan items

### Step 8 — Zoho Sign confirmation path (plan step 6)

For closed/won or quote-generating recommendations, require a Zoho Sign confirmation in
addition to / instead of Blueprint approval.
1. Decide which recommendation types route to Sign vs Blueprint approval.
2. Build the Sign request + a callback that only marks the recommendation actionable once
   the document is signed.
3. Executor must refuse to act on a Sign-required recommendation until signed.

### Step 9 — Owner routing by inbox

1. Map each intake (@battery, @BMS, @AR, @AP, @services, @info) to a CRM owner/queue.
2. In persistence, set the recommendation Owner from the destination inbox (`to_email`).
3. Verify a @battery message and a @BMS message land with different owners.

### Step 10 — Email attachments

1. Extend `normalize_teaminbox_payload` to carry attachment references from the TeamInbox
   payload.
2. On association, attach files to the CRM record.
3. Verify an email with a PDF attaches that PDF to the record.

---

## PHASE 4 — Operational hardening

### Step 11 — Silent-failure alerting
1. Add a failure/dead-letter path on every flow (Quote Intake, ingestion, form flow).
2. On any block error, post to a monitoring channel (Cliq/email) with flow name, run ID,
   block, and error text.
3. Verify by forcing one failure and confirming the alert.

### Step 12 — Reprocess path for manual_review / fallback
1. Provide a way to re-run analysis on a `manual_review`/`fallback` record after the
   underlying issue is fixed (button, scheduled sweep, or manual re-trigger).
2. Verify a timed-out record can be reprocessed to a valid recommendation.

### Step 13 — Reporting
1. Build a CRM report/dashboard: recommendation volume, approval rate, intent mix,
   time-to-action, per-inbox breakdown.

---

## PHASE 5 — Additive

### Step 14 — Lifecycle write-back
1. Decide governance: which Zia lifecycle/opportunity signals may auto-advance a CRM stage
   or create a Deal, and which require approval.
2. Build stage-advance / Deal-creation on approved recommendations.
3. Verify with full human-in-the-loop gating; never let closed/won auto-execute.

---

## FINALIZE

### Step 15 — Commit
Uncommitted work: `scripts/build_form_intake_payload.deluge`,
`scripts/normalize_teaminbox_payload.deluge` (form-intake sender resolution),
`tests/test_ingestion_artifacts.py` (form tests),
this runbook, and STATUS.md updates.
1. `cd` to the repo.
2. `git status` — confirm the expected files.
3. `python3 -m unittest discover -s tests -q` — must pass.
4. `ruff check .` — must pass.
5. Commit on the working branch (not main without Bill's approval).

### Step 16 — Full E2E acceptance
Run the cleaned single path end to end and record results in the acceptance-test
block in `STATUS.md`:
1. Unknown external sender (email) → Contact+Lead created, one recommendation, approve, one Task.
2. Known sender (email) → matched, one recommendation, approve, one Task.
3. Form submission, unknown sender → same as (1) via form.
4. Form + email duplicate of same inquiry → exactly one recommendation.
5. Confirm no duplicate Deals, no silent failures.
