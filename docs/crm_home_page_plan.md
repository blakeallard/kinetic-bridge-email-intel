# Bevco CRM Home Page — design plan

Zoho Task ID: 2543412000001583003 (BI1-T110, related enhancement)

**Status: PLANNING ONLY.** Nothing in this document has been built. No live Zoho system,
OAuth scope, field, list view, Home layout, or record was created or modified to produce
it. It reasons from this repository's verified evidence (`STATUS.md`,
`docs/live_module_inspection_2026-07-19.md`, `docs/zoho_flow_inventory.md`,
`docs/single_path_refactor_spec.md`, and the `scripts/` field maps) plus general Zoho
platform knowledge. Every "open decision" is left for Blake.

**Goal.** One landing surface where the 3-person Bevco team (Blake, Bill, Bryan) can see
and act on everything tied to a client relationship: the AI recommendation approval queue
this project produces, recent client email threads, tasks, deals/pipeline, and
leads/contacts/accounts — organized for a low-volume, high-value-deal B2B shop.

---

## 1. The data model this page must surface

### 1.1 `AI_Recommendations` — the module this project built (the centerpiece)

Verified live schema (module ID `6719186000003163020`, API name `AI_Recommendations`,
display field `Name`; see `docs/live_module_inspection_2026-07-19.md` and the persist
field map in `scripts/persist_recommendation.deluge`). Fields that matter for
a home page:

| API name | Type | Meaning on the page |
| --- | --- | --- |
| `Name` (UI label `Idempotency_Key`) | text 120 | Now a **human-readable title** — e.g. `AI Recommendation: Create CRM Task - Request Information`. Safe to show as the row label. |
| `Status` | picklist | Approval state: `Pending Review` → `Approved` / `Rejected` / `Executed`. Drives the approval queue. |
| `Validation_Status` | picklist | `valid` / `invalid` / `fallback`. Only `valid` is approvable; `fallback` = no CRM match / manual review. |
| `Execution_Status` | picklist | `Not Started` / `In Progress` / `Executed` / `Failed` / `Blocked`. Drives the "needs attention" view. |
| `Recommendation_Type` | text | Action slug, currently always `create_crm_task`. |
| `AI_Category` | text | Title-cased intent category (e.g. `Quote Request`). |
| `AI_Summary` | textarea | One-line "what this email is asking for". |
| `AI_Rationale` | textarea | Why the AI recommended the action. |
| `Safety_Summary` | multi-select | Flags: `Human Approval Required`, `Quote Generation Requested`, `Closed Won Change Requested`, `Insufficient Context`, `Conflict Detected`. |
| `Requires_Approval`, `Created_By_AI` | boolean | Both true for engine output. |
| `Target_Module` | picklist | `Contacts` / `Leads` / `Accounts` (`Deals` defined but never produced/blocked). |
| `Target_Record_ID` | **text 255** | The matched CRM record's id — **stored as plain text, NOT a native lookup.** This is the single most important design constraint (see §1.5). |
| `Message_ID`, `Ingestion_Key` (unique) | text | Source email identity / idempotency. |
| `Reviewed_By`, `Reviewed_At`, `Review_Notes` | user / datetime / text | Approval audit, set through the Blueprint. |
| `Executed_Task_ID`, `Executed_At`, `Execution_Attempts`, `Execution_Error` | text / datetime / int / text | Execution outcome; `Executed_Task_ID` points at the created CRM Task. |
| `AI_Confidence` | (exists, currently unmapped) | Reserved for a confidence score; **not written today** — see §5 open decisions. |

Lifecycle governance already exists and should be respected by the page, not
re-implemented:

- **Blueprint `AI Recommendation Review`** (published, active): `Pending Review` →
  `Approve Recommendation` / `Reject Recommendation`, both requiring `Reviewed_By`,
  `Reviewed_At`, `Review_Notes`. Both end states are terminal. Approval/rejection is done
  from the record via the Blueprint transition buttons — the home page's job is to *route
  a human to the record*, not to add a second approval mechanism.
- **Cliq notification** already fires on every new `Pending Review` record
  (`scripts/notify_cliq_new_recommendation.deluge`, channel `ai-recs-test`, Blake-only
  today). The home page is the persistent, at-a-glance complement to that push alert.

### 1.2 Tasks

CRM Tasks are the concrete output of an approved recommendation (`Executed_Task_ID` links
to one). Standard `Tasks` module; linkage is `Who_Id` for Contacts, `What_Id` +
`$se_module` for Leads/Accounts (see `docs/live_module_inspection_2026-07-19.md`).
Zoho **Projects** tasks (the BI1 internship/board work) live in a different product and
are not natural CRM-Home content — surface them, if at all, via an embedded Web Tab, not a
CRM component (see §4).

### 1.3 Deals / pipeline — and the CRM-vs-Bigin split (business-critical)

CRM has a `Deals` module with a full pipeline (Qualification → … → Closed Won). **But
Bevco's actual live opportunities — SK On, Motive Workforce, Meyers Manx, Voltaic Marine,
Electricfish — are tracked in Bigin, not CRM Deals** (per the org's own account notes).
The AI workflow operates against **CRM**, and unmatched senders become **CRM Leads**
(`scripts/create_lead_for_unmatched.deluge`). So a CRM Home page that shows
"Deals" would today be nearly empty while the real pipeline sits in Bigin. This tension is
the single biggest open business decision (see §5) and the page design must not paper over
it.

### 1.4 Leads / Contacts / Accounts

Standard CRM modules, natively supported by Home components and list views. The engine
resolves an inbound sender to a Contact → Lead → Account (by domain) in that precedence
(`scripts/resolve_crm_match.deluge`), and creates a Lead for unknown senders.
Leads/Contacts/Accounts are the click-through destinations from a recommendation.

### 1.5 TeamInbox threads — NOT a CRM module

TeamInbox is a separate Zoho product. There is **no CRM module** for its threads, so they
cannot be shown by a native Home component or list view. The project already solves the
*record-level* version of this: `scripts/associate_email_to_crm_record.deluge` writes the
inbound email into the matched Contact/Lead/Account's **Emails related list** via the CRM
V8 Associate Email API (verified live). So the client's recent thread is visible *inside
the CRM record*, which is reachable from a recommendation. A *cross-inbox* "recent threads
awaiting reply" panel, independent of a specific record, requires either the TeamInbox API
or an embedded TeamInbox Web Tab (§3, §4).

### 1.6 The load-bearing constraint: `Target_Record_ID` is text, not a lookup

Because the recommendation stores its target as a **text id** rather than a native CRM
lookup relationship:

- There is **no native related list** from a Contact/Lead/Account back to its
  AI Recommendations, and **no one-click** jump from a recommendation row to its target
  record out of the box.
- A native list view can *display* `Target_Module` and `Target_Record_ID`, but the id is
  not clickable.
- Two low-maintenance ways to restore clickability without self-hosting anything:
  1. **Formula (URL) field** on `AI_Recommendations` that concatenates the CRM deep-link
     (`https://crm.zoho.com/crm/org<ORG>/tab/<Module>/<Target_Record_ID>`) so the list
     view row carries a working "Open target" link. Zero code, zero hosting.
  2. **Convert `Target_Record_ID` to a real lookup** (or add parallel lookup fields per
     module). Cleaner and gives native related lists, but is a schema change touching the
     persist path and is more than an MVP needs.
  This choice is an open decision (§5); option 1 is the recommended MVP.

---

## 2. Implementation options in the Zoho stack

Weighed for a 3-user ZohoOne Enterprise org that wants the **lowest maintenance surface
that still connects everything**.

| Option | What it is | Connects AI_Recs | Connects Tasks/Deals/Leads | Connects TeamInbox threads | Cross-links (rec → thread → target) | Code / hosting | Maintenance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **(a) Native CRM Home tab** — custom components + custom list views | Built-in CRM Home layout with per-module list/chart components | Yes (list view component) | Yes (native) | No native; only via the record's Emails related list | Weak (text id; fixable with a formula URL field) | **None** | **Lowest** |
| **(b) CRM Canvas page** | No-code visual designer for a module's list/detail view | Yes, prettier `AI_Recommendations` list/detail | No (Canvas is per-module, not cross-module) | No | No | None | Low, but not a cross-module home |
| **(c) Web Tab / Sigma widget** (self-hosted HTML/JS calling Zoho + TeamInbox APIs) | Custom page embedded as a CRM tab | Yes (COQL) | Yes (COQL) | **Yes** (TeamInbox API) | **Strong** — you control every link | Yes, self-hosted, OAuth, CSP | High for a 3-person shop |
| **(d) Zoho Creator page/app** | Low-code app pulling CRM/Bigin/TeamInbox via connections, embeddable as a Web Tab | Yes | Yes (incl. **Bigin**) | Yes (API) | Strong | Low-code, but a separate app to own | Medium |
| **(e) External dashboard** (Analytics / third-party) | BI dashboard | Read-only | Read-only | Via connectors | None (read-only, no record actions) | Yes | Medium–High, and can't *act* |

### Recommendation

**Start with (a) the native CRM Home tab, and add one formula URL field for
clickability.** It is the only zero-code, zero-hosting option that co-locates the approval
queue, tasks, deals, and leads on one screen, respects the existing Blueprint/Cliq
governance, and gives all three users a shared landing page with no new system to
maintain. It is also the correct *system of record* surface: approvals must happen on the
CRM record (Blueprint), and the Home tab drives humans straight there.

Its two honest gaps — a cross-inbox "recent threads" panel and truly rich rec→target
navigation — are **enhancements**, not blockers, and are best filled by **(d) a small
Creator page embedded as a Web Tab** if and when the pain justifies it, because Creator is
the only option that can *also* pull **Bigin** (the real pipeline) and TeamInbox into the
same custom surface with low-code rather than self-hosted maintenance. Prefer (d) over (c)
for Bevco: a 3-person team should not own a hosted web app and its OAuth/CSP lifecycle if a
low-code embed does the job.

(b) Canvas is worth doing as a *supporting* polish on the `AI_Recommendations` list/detail
view (it makes the approval record readable) but is not the home surface. (e) External is
rejected: it cannot take approval actions and adds a system with no offsetting benefit.

---

## 3. Proposed page design

A CRM **Home layout** named **"Command Center,"** assigned to both the Administrator and
Standard profiles so all three users share it. Components top-to-bottom put the highest-
urgency, project-specific work first.

### 3.1 Section-by-section

**A. AI Recommendations — Approval Queue (hero component).**
- Source: `AI_Recommendations` list view **"Approval Queue"** =
  `Status = Pending Review AND Validation_Status = valid AND Recommendation_Type = create_crm_task`.
- Sort: `Created Time` ascending (oldest waiting first — an SLA/aging view). If/when
  `AI_Confidence` is populated, offer a secondary sort by confidence desc (open decision).
- Columns: `Name` (title) · `AI_Category` · `AI_Summary` · `Target_Module` ·
  `Safety_Summary` · `Created Time` · **"Open target"** (formula URL, §1.6).
- Action: click the row → the record → Blueprint **Approve / Reject** buttons. No second
  approval path.
- Business logic: this is the queue the whole system exists to feed. Oldest-first surfaces
  the recommendation a client has been waiting on longest.

**B. AI Recommendations — Needs Attention.**
- Source: list view **"Blocked / Failed"** = `Execution_Status IN (Failed, Blocked)`.
- Sort: `Modified Time` desc. Columns include `Execution_Error`, `Executed_At`,
  `Execution_Attempts`.
- Business logic: post-approval execution failures are **terminal and require a human**
  (per the failure policy in `STATUS.md`) — they must not hide. Small count, high
  importance.

**C. Recently Executed (confidence/audit strip).**
- Source: list view **"Recently Executed"** = `Execution_Status = Executed`, sort
  `Executed_At` desc, last ~10. Columns: `Name`, `Target_Module`, `Executed_Task_ID`,
  `Executed_At`.
- Business logic: proof the loop closed; a quick "what did the AI do for us this week."

**D. Manual Review / Fallback.**
- Source: list view **"Fallback"** = `Validation_Status = fallback` (unmatched senders,
  timeouts). These can't be approved and need a human to decide (often: qualify the new
  Lead). Sort `Created Time` desc.

**E. My Open Tasks.**
- Source: native `Tasks` component, **"Overdue & Due Today,"** owner = current user, sort
  `Due_Date` asc. This is where an executed recommendation lands, so it closes the loop
  visually next to the queue that created it.

**F. Deals Needing Attention** *(conditional on the CRM-vs-Bigin decision, §5)*.
- If CRM Deals is chosen as the pipeline of record: list view "Needs Attention" =
  open stage AND (`Closing_Date` within 14 days OR no activity in N days), sort
  `Closing_Date` asc; plus a pipeline **funnel chart** component by `Stage`.
- If Bigin remains the pipeline: replace this with an **embedded Bigin Web Tab** (§4) —
  do not show an empty CRM Deals component.

**G. New / Uncontacted Leads.**
- Source: `Leads` list view = `Lead_Status IN (Not Contacted, Attempted to Contact)`,
  sort `Created Time` desc. Catches engine-created Leads from unknown senders
  (`create_lead_for_unmatched`) so they get worked, and pairs with the enhancement that
  advances `Not Contacted → Contacted` on first outbound reply
  (`scripts/advance_lead_on_first_outbound.deluge`).

**H. Recent Client Threads** *(enhancement — not native)*.
- MVP: **omit** from the native Home tab; the thread is visible inside each Contact/Lead/
  Account's Emails related list, one click from a recommendation.
- Enhancement: an **embedded TeamInbox Web Tab** for the raw shared inbox, and/or a
  Creator/Sigma panel listing recent inbound threads awaiting reply via the TeamInbox API.

### 3.2 Cross-linking model (how the pieces connect)

```
AI Recommendation (Approval Queue row)
   │  click row
   ▼
AI_Recommendations record ──── Blueprint: Approve / Reject
   │
   ├─ "Open target" formula URL ──► Contact / Lead / Account record
   │                                   ├─ Emails related list ──► the source client thread
   │                                   ├─ Open Activities ──────► Tasks (incl. the executed one)
   │                                   └─ (Deals related list / Bigin) ─► related pipeline
   │
   └─ Executed_Task_ID ────────────► the created CRM Task (also in "My Open Tasks")
```

The chain the brief asks for — *recommendation → source email thread → target
Lead/Contact → related deals/tasks* — is fully reachable in the native design **once the
formula URL field exists**, because the engine already associates the email into the
record and links the executed Task to it. The only piece that is not one-click natively is
the recommendation-list → target hop, which the formula field restores.

### 3.3 Text wireframe

```
┌───────────────────────────── COMMAND CENTER (CRM Home) ─────────────────────────────┐
│                                                                                      │
│  ┌── A. AI RECOMMENDATIONS — APPROVAL QUEUE ───────────────────────  (Pending·valid)│
│  │ Title                         Category      Summary            Target      Open  ▸│
│  │ AI Rec: Create Task - Quote   Quote Request "Wants fleet px"   Lead ▸SK…   [link]│
│  │ AI Rec: Create Task - Info    Request Info  "Spec sheet ask"   Contact ▸…  [link]│
│  │ …oldest waiting first (aging)                                                     │
│  └──────────────────────────────────────────────────────────────────────────────────│
│  ┌── B. NEEDS ATTENTION (Failed/Blocked) ──┐  ┌── C. RECENTLY EXECUTED ────────────┐ │
│  │ Rec · Error · Attempts · When           │  │ Rec · Target · Task · Executed at   │ │
│  └─────────────────────────────────────────┘  └─────────────────────────────────────┘ │
│  ┌── D. MANUAL REVIEW / FALLBACK ──────────┐  ┌── E. MY OPEN TASKS (overdue/today)─┐ │
│  │ Unmatched senders · timeouts            │  │ Subject · Related to · Due          │ │
│  └─────────────────────────────────────────┘  └─────────────────────────────────────┘ │
│  ┌── F. DEALS / PIPELINE  (CRM funnel  OR  embedded Bigin Web Tab — see §5) ────────┐ │
│  └──────────────────────────────────────────────────────────────────────────────────│
│  ┌── G. NEW / UNCONTACTED LEADS ───────────┐  ┌── H. RECENT CLIENT THREADS (enh.) ─┐ │
│  │ Name · Company · Source · Created        │  │ (embedded TeamInbox / Creator)      │ │
│  └─────────────────────────────────────────┘  └─────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Data-access realities & permissions

| Surface | Native CRM component? | How it's actually surfaced |
| --- | --- | --- |
| `AI_Recommendations` queue/views | **Yes** | Custom list views on the module; Home list-view components. |
| CRM Tasks | **Yes** | Native Tasks component / list views. |
| CRM Deals | **Yes** | Native component + funnel chart. **But may be empty** (real pipeline is in Bigin). |
| Leads / Contacts / Accounts | **Yes** | Native components / list views. |
| Rec → target record link | **No** (text id) | Add a **formula URL field**, or convert `Target_Record_ID` to a lookup. |
| Client email thread (per record) | **No module** | Already written into the record's **Emails related list** by `associate_email_to_crm_record` (CRM V8 Associate Email API). One click from the rec's target. |
| Cross-inbox "recent threads awaiting reply" | **No** | TeamInbox API (Creator/Sigma) or an **embedded TeamInbox Web Tab**. |
| Bigin pipeline | **No** (separate product) | Embedded Bigin **Web Tab**, or a Creator page reading Bigin. |
| Zoho Projects tasks | **No** (separate product) | Embedded Projects **Web Tab** if wanted; not native Home content. |

**Auth / permissions (3-user org).**
- Home **layouts are assigned per profile**; assign "Command Center" to both
  **Administrator** (Bill, Bryan) and **Standard** (Blake) so all three see it. Component
  visibility follows each user's module permissions; both profiles already have access to
  `AI_Recommendations` (confirmed in the module inspection).
- List-view **"my" filters** (owner = current user) personalize Tasks/Leads without
  separate layouts.
- Blueprint transitions enforce who can approve; the Home tab changes none of that.
- A **formula URL field** needs no extra scope (it's computed CRM data). An **embedded Web
  Tab** to TeamInbox/Bigin/Creator uses each product's own session — no new CRM OAuth
  scope, no secrets in this repo. Any **Creator/Sigma** option that reads the TeamInbox API
  introduces a connection/scope and is therefore a deliberate phase-2 decision, not MVP.
- Do not surface `Raw_Zia_Response` / `Validated_Analysis_JSON` (raw model output) in
  shared components — keep the queue business-readable; those stay on the record detail for
  audit only.

---

## 5. Phased build plan & open decisions

### Phase 0 — MVP, zero custom code (native CRM Home)

1. Create `AI_Recommendations` list views: **Approval Queue**, **Blocked / Failed**,
   **Recently Executed**, **Fallback** (filters/sorts/columns per §3.1).
2. Create the **"Command Center"** Home layout; add components A–E and G; assign to both
   profiles.
3. Add Deals component/funnel **only if** CRM is chosen as the pipeline of record
   (decision D1); otherwise leave a placeholder for the Bigin Web Tab.
All achievable in the CRM setup UI with no Deluge, no hosting, no new scope.

### Phase 1 — clickability & polish (tiny, still low-code)

4. Add the **formula URL field** "Open Target" on `AI_Recommendations` (§1.6 option 1) and
   put it in the Approval Queue columns.
5. Optional **Canvas** view on `AI_Recommendations` list/detail for a cleaner reviewer
   record (pairs with the presentation cleanup already noted in
   `docs/next_enhancement_plan.md`).

### Phase 2 — connect the non-CRM surfaces (only if the pain justifies it)

6. Embed a **TeamInbox Web Tab** (raw shared inbox) and/or a **Bigin Web Tab** (real
   pipeline) as CRM Web Tabs — no code, uses each product's own auth.
7. If a true unified panel is wanted (recent inbound threads awaiting reply + Bigin + AI
   recs in one custom view with rich links), build a **Zoho Creator page embedded as a Web
   Tab** — preferred over a self-hosted Sigma widget for a 3-person team.

### Phase 3 — richer relationships (schema, optional)

8. Convert `Target_Record_ID` to a real **lookup** (or add per-module lookups) to get
   native related lists from Contacts/Leads/Accounts back to their recommendations. Touches
   the persist path (`scripts/persist_recommendation.deluge`) — deliberate, not
   MVP.

### Open decisions for Blake

- **D1 — Pipeline of record: CRM Deals vs Bigin.** The AI workflow feeds CRM; the live
  deals (SK On, Motive, Meyers Manx, …) are in Bigin. Decide whether the Home page's
  pipeline section shows CRM Deals (and migrate/mirror opportunities there) or embeds
  Bigin. This shapes section F and whether Phase 2 is needed early.
- **D2 — Clickability mechanism:** formula URL field (fast, MVP) vs converting
  `Target_Record_ID` to a lookup (richer, schema change). Recommend formula for MVP.
- **D3 — Confidence sort:** map `AI_Confidence` in `persist_recommendation` so the queue
  can sort by confidence, or keep oldest-first aging only. (Field exists but is unwritten.)
- **D4 — TeamInbox surfacing depth:** rely on the per-record Emails related list (MVP) vs
  invest in a cross-inbox "awaiting reply" panel (Creator/API, Phase 2).
- **D5 — Who sees what:** confirm the single shared "Command Center" layout for all three
  users (recommended) vs per-role variants, and whether Bill/Bryan want owner-scoped Task/
  Lead components. Ties to the deferred "owner-by-inbox routing" enhancement.
- **D6 — Zoho Projects tasks:** include an embedded Projects Web Tab on this page at all,
  or keep project work off the client-relationship home. Recommend keeping it off.

---

## 6. Recommended approach in one paragraph

Build the home page as a **native CRM Home layout ("Command Center")** using custom
`AI_Recommendations` list views plus native Tasks/Leads/Deals components — zero code, zero
hosting, shared by all three users, and respectful of the Blueprint + Cliq governance
already in place. Add **one formula URL field** so each recommendation row links straight
to its target record, which already carries the source email thread (Emails related list)
and the executed Task (Open Activities) — completing the *recommendation → thread → target
→ tasks* chain the brief wants without any self-hosted component. Defer TeamInbox "recent
threads" and the Bigin pipeline to an embedded **Web Tab / low-code Creator** phase, and
only consider a self-hosted widget if that low-code embed proves insufficient. The two
decisions that most change the shape of the page are **CRM Deals vs Bigin as the pipeline
of record (D1)** and **how the recommendation links to its target (D2)**.
