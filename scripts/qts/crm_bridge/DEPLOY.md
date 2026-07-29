# CRM_Bridge — Creator clicks (match your screen)

You are on **Run workflow on any event in the form**. Good.

**Wrong choice right now:** `Field rules` (that is for show/hide fields, not CRM).

**Right choice:** `Successful form submission` under **After form submission**.

---

## First workflow only (do this once, then repeat)

### A. Trigger screen (the popup you have open)

1. **Choose form:** leave **`CRM_Bridge`**.
2. **Run when a record is:** leave **`Created`** selected.
3. Open **When to trigger workflow**.
4. Scroll past **Before form submission** and **On form submission**.
5. Under **After form submission**, click **`Successful form submission`**.
6. **Name the workflow:** type  
   `CRM Bridge — search_customers`
7. Click the button that continues / creates the workflow (often **Create Workflow** / **Next** / **Done** — whatever your UI shows).

### B. Inside the new workflow editor

Creator usually opens a builder with a trigger already set. Do this:

1. If there is a **Criteria** / **Condition** / **Run only when** step:
   - Add rule: **`Action_field`** **equals** **`search_customers`**
   - Exact spelling, no spaces.
2. Add an action of type **Deluge script** / **Execute Deluge** / **Custom function** (wording varies).
3. On your Mac, open this file and copy **everything**:

   `scripts/qts/crm_bridge/search_customers.deluge`

4. Paste into the Deluge box (entire file).
5. **Save** the workflow.
6. Make sure it is **On / Enabled**.

You now have workflow #1 of 13.

---

## Repeat for the other 12

Same A + B every time. Only change:

| Workflow name | Criteria: `Action_field` equals | File to paste |
| --- | --- | --- |
| `CRM Bridge — search_customers` | `search_customers` | `search_customers.deluge` |
| `CRM Bridge — search_leads` | `search_leads` | `search_leads.deluge` |
| `CRM Bridge — get_customer` | `get_customer` | `get_customer.deluge` |
| `CRM Bridge — get_lead` | `get_lead` | `get_lead.deluge` |
| `CRM Bridge — create_customer` | `create_customer` | `create_customer.deluge` |
| `CRM Bridge — search_deals` | `search_deals` | `search_deals.deluge` |
| `CRM Bridge — get_deal` | `get_deal` | `get_deal.deluge` |
| `CRM Bridge — create_deal` | `create_deal` | `create_deal.deluge` |
| `CRM Bridge — get_quote_by_number` | `get_quote_by_number` | `get_quote_by_number.deluge` |
| `CRM Bridge — get_quote_lines` | `get_quote_lines` | `get_quote_lines.deluge` |
| `CRM Bridge — expand_kit` | `expand_kit` | `expand_kit.deluge` |
| `CRM Bridge — get_tax` | `get_tax` | `get_tax.deluge` |
| `CRM Bridge — books_diag` | `books_diag` | `books_diag.deluge` |

Every time on the trigger popup:

- Form = `CRM_Bridge`
- Record event = **Created**
- When to trigger = **Successful form submission** (not Field rules)

---

## Before you finish — kill the old mega workflow

1. Go back to the workflow list for `CRM_Bridge`.
2. Find the old big one (long script with many actions in one body).
3. **Disable** or **delete** it so only the 13 small ones run.

If the mega one is still on, you can still hit the external-call limit.

---

## Done check

1. Open QTS quote builder in **dev**.
2. Search a customer (e.g. `dana`).
3. Matches should return. No `External Call Statements exceeded` / `Webhook call exceeded`.

No widget zip needed.

---

## Do not

- Do **not** paste `scripts/qts/crm_bridge_on_create.deluge` — obsolete pointer only.
- Do **not** put all actions back into one mega workflow.

---

## If you see `Webhook call exceeded` at line 7

That almost always means **more than one workflow is running** on the same
`CRM_Bridge` create. `get_tax` / `books_diag` start with `invokeurl` (~line 7).
A customer search should never run those.

**Fix:**

1. Open **each** of the 13 workflows.
2. Confirm **Criteria** is set: `Action_field` **equals** that workflow’s action
   name (e.g. `search_customers` only on the search_customers workflow).
3. If criteria was missing, add it, save, and re-paste the matching `.deluge`
   (files now also `return` immediately when `Action_field` does not match).
4. Optional quick test: **Disable** `get_tax` and `books_diag`, search again.
   If search works, criteria was the problem — turn them back on after criteria
   is fixed on all 13.
5. If it still fails with Webhook exceeded on a *correctly* filtered search,
   check Creator **Settings → Usage** (daily webhook/external-call quota may
   already be burned from earlier testing; wait for daily reset).

---

## If you cannot find “Criteria”

Some Creator layouts put the condition on the **action** instead of the trigger. Either works:

- Workflow runs on every Created record, **and** the Deluge starts with  
  `if (input.Action_field != "search_customers") { return; }`  

— but our pasted files assume the **workflow criteria** already filtered to that action. Prefer the criteria rule on `Action_field`.

If the UI asks you to pick criteria and you are stuck, screenshot that next screen and we can match the exact clicks.
