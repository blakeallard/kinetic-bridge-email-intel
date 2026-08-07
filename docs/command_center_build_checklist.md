# Command Center — post-meeting build checklist

Zoho Task ID: 2543412000001583003 (BI1-T110)

Click-by-click CRM setup for the "Command Center" Home page designed in
`docs/crm_home_page_plan.md`. Everything here is CRM UI configuration — no code, no
schema changes except the one Tier-3 item flagged at the end. Prerequisite inputs from
the Bill/Bryan meeting are marked **[MEETING]**.

## 1. AI_Recommendations list views (Setup-free — from the module's list view page)

Open the `AI_Recommendations` module → list view dropdown → **Create New View** (four
times):

| View name | Criteria | Sort | Columns |
| --- | --- | --- | --- |
| Approval Queue | `Status = Pending Review` AND `Validation_Status = valid` | Created Time **asc** (oldest waiting first) | Name · AI_Category · AI_Summary · Target_Module · Safety_Summary · Created Time |
| Blocked / Failed | `Execution_Status` in (`Failed`, `Blocked`) | Modified Time desc | Name · Execution_Error · Execution_Attempts · Executed_At · Target_Module |
| Recently Executed | `Execution_Status = Executed` | Executed_At desc | Name · Target_Module · Executed_Task_ID · Executed_At |
| Fallback Review | `Validation_Status = fallback` | Created Time desc | Name · AI_Category · AI_Summary · Created Time |

Share each view with **All Users** (3-person org — no reason to scope).

## 2. Quotes list views

Open `Quotes` → Create New View (twice):

| View name | Criteria | Sort | Columns |
| --- | --- | --- | --- |
| Open Quotes | `Quote Stage` / `Status` not terminal *(exact field per current layout)* | Valid_Till **asc** (expiring first) | Subject · Deal_Name · Contact_Name · Grand_Total · Valid_Till |
| Signed Quotes (ledger) | `Status = Signed` *(value arrives with the Sign integration — create the view then; it will be empty until)* | Modified Time desc | Subject · Deal_Name · Contact_Name · Grand_Total · Modified Time |

## 3. Deals list views + funnel **[MEETING: D7 stage lists]**

After Bill's three-pipeline restructure lands:

1. `Deals` → Create New View **"Needs Attention"**: open stages only, `Closing_Date`
   within 14 days (or no-activity filter), sort Closing_Date asc.
2. Home component: **funnel chart by Stage** — one per pipeline (Services / BMS
   Distribution / Cell-Battery Distribution) or one segmented, per Bill's preference.

## 4. The Home layout ("Command Center") — built in development, nobody's homepage touched

**Rule (Blake, 2026-07-28): do not modify or replace anyone's existing Home layout.**
The Command Center is created as a **new, separate layout**, assigned only to Blake
during development. Bill and Bryan keep their current homepages untouched until the
finished layout is demoed and they opt in.

Setup → Customization → **Home Customization** → **Create New Home layout** (never edit
an existing one) → name it **Command Center (dev)**.

Add components top-to-bottom (component type: List View unless noted):

1. **Approval Queue** — AI_Recommendations / "Approval Queue" view (hero, full width).
2. **Blocked / Failed** — AI_Recommendations / "Blocked / Failed" (half width) —
   side-by-side with:
3. **Recently Executed** — AI_Recommendations / "Recently Executed" (half width).
4. **Fallback Review** — AI_Recommendations / "Fallback Review" (half width) —
   side-by-side with:
5. **My Open Tasks** — Tasks / "Overdue & Due Today", owner = logged-in user (half).
6. **Deals funnel(s)** — chart component(s), per §3 **[MEETING]**.
7. **Open Quotes** — Quotes / "Open Quotes" view.
8. **New / Uncontacted Leads** — Leads view: `Lead_Status` in
   (`Not Contacted`, `Attempted to Contact`), sort Created Time desc.

Then assign the layout to the **Standard profile only** (Blake — conveniently the only
Standard user, so Bill/Bryan's Administrator homepages are untouched by construction).
Iterate on it there.

**Rollout (after the demo, opt-in):** once Bill/Bryan approve the layout, rename it
**Command Center**, assign it to the Administrator profile as well, and only then set it
as their default Home tab. Their previous layouts are left in place (not deleted) so
reverting is one click.

## 5. QTS launcher **[MEETING: D9 mechanism]**

Setup → Customization → **Web Tabs** → Create:
- Name: `QTS Quote Builder`; URL: the QTS Creator app URL (dev or stage per current
  environment); visible to all three users.
- If the widget renders poorly embedded, fall back to a Link component / bookmark and
  revisit.

Optional same screen: a **Zoho Mail Web Tab** for the shared intake inbox (D4).

## 6. Tier-3 item — needs Bill before doing

**"Open Target" formula URL field** on `AI_Recommendations` (new CRM field = Tier 3):
formula text field concatenating
`"https://crm.zoho.com/crm/org6719186000000020005/tab/" + Target_Module + "/" + Target_Record_ID`.
Add it to the Approval Queue columns once created. Until then, reviewers reach the target
by opening the recommendation record first (one extra click).

## 7. Verification

- Dev phase (Blake's login): the Command Center (dev) layout renders; an approvable
  recommendation is reachable in ≤2 clicks (queue row → record), and the Blueprint
  **Approve / Reject** buttons work from there. Bill/Bryan's homepages are unchanged.
- Post-rollout (after opt-in): same checks from Bill's or Bryan's login.
- The Approval Queue count matches `AI_Recommendations` where Status = Pending Review /
  valid.
- Open Quotes shows the live QTS quotes with PDFs on their records.
- QTS launcher opens the widget and a quote can be loaded from it.
