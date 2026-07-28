# QTS Quote → Document → Deal → Email (plan of record, 2026-07-26)

Closes the `QTS quote` execution target from `TASK.md` (0% as of the 2026-07-26 completion
map). Scope: once a QTS quote is draft-saved as a CRM `Quotes` record, produce the branded
quote document, file it on the Deal/Quote in CRM, and send it to the client.

## App decision: Zoho Writer

**Zoho Writer merge is the right tool.** Evaluated against the one realistic alternative:

| Option | Verdict |
| --- | --- |
| **Zoho Writer merge template** | Chosen. Template already exists (`Kinetic Bridge Quote Template`, id `arkte656353cdeff74057a4576834d3eddd1d`). The Merge & Store API outputs PDF and files it into WorkDrive — which simultaneously starts the `WorkDrive` execution target, also at 0%. Merge & Email can send the merged PDF directly. Zoho Flow has native Writer actions, so no new OAuth scopes or secrets are needed in code. |
| CRM native inventory templates on `Quotes` | Rejected. Layout control is limited, output cannot be filed into WorkDrive, and automating "render + email on record event" requires workflow email templates that cannot carry the merged PDF cleanly. |

## Blocker found 2026-07-26: the template has no merge fields

`Get_All_Fields` on both Writer templates returns `{"merge": [], "sign": {}, "fill": []}`.
The placeholders in `Kinetic Bridge Quote Template` are plain text, not Writer merge fields,
so a merge call would return the document unchanged. Nothing downstream can be wired until
this is fixed, and it can only be fixed in the Writer UI (template editing is not exposed
through the MCP tools).

Fix, in Writer (Blake):

1. Open the template → **Tools → Merge fields** (or Insert → Merge Fields).
2. Choose **JSON** as the data source and upload `samples/quote_merge_sample.json` from this
   repo — Writer derives the field list, including the `line_items` repeating region, from it.
3. Replace each typed placeholder with the corresponding inserted merge field.
4. For line items: select the products table row and mark it as a **repeating region** bound
   to `line_items`.
5. Verify: `Get_All_Fields` must return the field names below. That check is the gate for
   any Flow work.

## Design revision (2026-07-26, evening): line items are a text block, not a repeating row

Live probing killed the repeating-row design. Verified against the real Merge API, all in
free test mode: typed `${...}` placeholders never merge; MERGEFIELDs in a .docx **do**
register on upload and merge correctly — but only as flat fields. Writer repeats a table
row only for fields inserted as a grouped subform region in its own UI; that grouping does
not survive .docx import, the data-source/Import Fields path rejected both JSON shapes
("unable to read csv"), and HTML passed through a field is escaped, not rendered. What
**does** work: `\n` in a merged value renders as a real line break.

Therefore: the template carries one field, `line_items_block`, and the payload builder owns
the formatting — one numbered entry per product (`1. <name>  -  Part <code>`, an indented
`Qty x $price = $total` line, an indented `Note:` line when the CRM line has a
description). Zero Writer UI involvement; the template is `artifacts/qts_quote_template_v3.docx`
and a plain Writer upload registers its 18 fields (no merge-template conversion, no data
source — `Merge_Document` works against an ordinary document id).

## Merge data contract

Field names are the contract between the template and `build_quote_merge_payload`. Scalars:

`quote_number`, `quote_subject`, `quote_date`, `valid_till`, `contact_name`,
`company_name`, `contact_email`, `billing_street`, `billing_city`, `billing_state`,
`billing_code`, `billing_country`, `sub_total`, `discount`, `tax`, `adjustment`,
`grand_total`, `terms_and_conditions`

Repeating region `line_items[]`:

`sequence`, `product_code`, `product_name`, `description`, `quantity`, `list_price`,
`total`

Money values are pre-formatted strings (plain two decimals, e.g. `5976.32`) — formatting is
code's job, not the template's. Zero-quantity lines are dropped from the document (the live
test quote carries two `Quantity = 0` optional lines that must not print as $0.00 rows).
Source of truth for shapes: live Quote `6719186000003545021`.

## Pipeline design

New Zoho Flow, separate from ingestion and approval ("Quote Document Flow"):

1. **Trigger:** CRM `Quotes` record created. QTS draft-saves the quote into CRM; that create
   is the event.
2. **`build_quote_merge_payload`** (new Deluge + tests, built 2026-07-26): fetch the Quote with
   `Quoted_Items`, resolve `Contact_Name` → email + mailing address, format money, drop
   zero-qty lines, emit the merge JSON above plus routing scalars (`contact_email`,
   `deal_id`, `quote_id`).
3. **Writer Merge & Store** (native Flow action): template id above, output PDF, filed to a
   WorkDrive quotes folder.
4. **`file_quote_on_crm`** (new Deluge): attach the PDF to the Quote record (Attachments
   API), and stamp `First_Quote_Number` / `First_Quote_Created_At` on the Contact (and Lead
   when still unconverted) **only if blank** — the fields exist for email→quote cycle time
   and nothing populates them today.
5. **Send to client** — see the open decision below.

## Open decision: when does the email go out (Blake)

This is the **first customer-facing automated send in the entire system**. Everything built
so far keeps the executor's blast radius at internal records (Tasks, Events) with a human
approval gate in front of anything a customer could see. Two options:

- **A. Email on draft-save** (as requested): fastest cycle time, but a mis-priced or
  half-finished draft goes straight to the client with no human between save and send.
- **B. Generate + attach on draft-save; email on `Quote_Stage` → e.g. `Delivered`**
  (recommended): the document is ready and filed instantly; sending is one deliberate stage
  change in CRM, consistent with the approval-gate model. QTS "draft" then means what it
  says.

Either way the send itself is Writer **Merge & Email** or Zoho Mail with the stored PDF —
decided at build time, no architectural difference.

## Flow wiring (built 2026-07-26, not deployed)

**Corrected 2026-07-26 after the first live attempt:** QTS (a Zoho Creator app, link name
`qts`) does **not** create CRM `Quotes` records — its CRM_Bridge log shows `create_deal`,
`get_quote_lines`, `search_*`, `expand_kit` and no quote action; the TEST-QUOTE0001 CRM
Quote was hand-made during testing. A QTS draft-save creates a **Deal** (with the
`Associated_Products` subform) and a Creator `Quote_Request` record carrying
`Quote_Number`, `Quote_Date`, `Valid_Until`, `CRM_Deal_ID`, `CRM_Contact_ID`,
`CRM_Account_ID`, `Status = Draft`. The Flow therefore triggers from Creator and the Deal
is the document's home. The Deal subform carries no part numbers, so the document lists
product name + qty + prices only.

New Zoho Flow **"Quote Document Flow"**, separate from ingestion and approval:

| # | Block | Detail |
| --- | --- | --- |
| 1 | Trigger | Zoho Creator — record **created or updated** in app `QTS`, form `Quote_Request` (environment must match where QTS actually runs) |
| 2 | `build_quote_merge_payload` | inputs from the trigger: `deal_id` ← `CRM_Deal_ID`, `contact_id` ← `CRM_Contact_ID`, `quote_number`, `quote_date`, `valid_until`; reads the Deal + `Associated_Products` + Contact; returns `status`, `merge_data`, `contact_email` |
| 3 | Decision | proceed only when `status == "ready"` (optional — block 4 no-ops safely) |
| 4 | `generate_and_file_quote_document` | inputs from blocks 1–2 plus `send_email` (see the email decision below) and `quote_request_id` ← the trigger record's **ID**; attaches the PDF to the **Deal** (terminal on failure) |

**LOAD QUOTE reads CRM (decision, Blake 2026-07-27).** The CRM Quote is the durable
record; QTS loads a quote for editing through the CRM_Bridge action `get_quote_by_number`
(search by Subject + one fetch = 2 CRM calls, 0 Creator API calls), which returns the
header, `Quoted_Items` lines, Deal/Contact lookups, and the Description carrying
`QTS Quote_Request ID: <id>` — the CRM→Creator back-reference the executor stamps on
every create/update. A deleted `Quote_Request` therefore no longer orphans a quote. A
dedicated `Creator_Quote_Request_ID` field on Quotes would be cleaner but is a schema
change (Tier 3, Bill); the Description stamp is the approved interim. QTS front-end work
(outside this repo): point LOAD QUOTE at `get_quote_by_number`, fall back to the native
Creator record when CRM has no quote yet (saved but Flow never ran).

Connections required (create in Flow, no secrets in code):

- `writer_to_flow` — Zoho Writer OAuth connection (created by Blake 2026-07-26); used by
  `invokeUrl` for the merge call against template document
  `gx3mq1bd0a0083f0847fe8d6696a136a0b11b` (`qts_quote_template_v4`, bordered line-items
  table, live-verified by test merge 2026-07-28; superseded v3
  `17lprde927fb42bd64ee9b3dce7724fad3909`).
- `zoho_crm_to_zoho_flow` — already exists; used for `attachFile` / record reads/writes.

What block 4 does: Writer merge → PDF (`Kinetic_Bridge_Quote_<number>.pdf`) → attach to the
Quote (terminal on failure) → attach to the Deal (best-effort) → stamp
`First_Quote_Number` / `First_Quote_Created_At` on the Contact **only if blank** (first
email→quote cycle-time datapoint) → optionally email the client.

**The email step is a Flow-configurable flag, not code.** The send is static boilerplate +
the quote number + the PDF, addressed to the Quote's Contact email. `sendmail` sends as
the Flow's authorizing user (`zoho.adminuserid`).

**Decision (Blake, 2026-07-27, revised same day): email on every save — creation and
edits.** Set `send_email = true` in the Flow. The first save sends "Your Kinetic Bridge
quote `n`"; a re-save sends "Your **updated** Kinetic Bridge quote `n`" whose body says it
replaces the previous version, so the client can tell revisions from duplicates. An
earlier same-day guard suppressed the email on `quote_action = "updated"`; Blake reversed
it — revisions should reach the client too. Known consequence, accepted: every edit
re-save emails the client, so batch edits before saving. Pinned by
`test_a_regenerated_quote_emails_a_revision_not_a_duplicate`.

Known limitation: the stamp targets the Contact only. A Quote created against an
unconverted Lead has no Contact and gets no stamp; acceptable because QTS quotes are
Deal-linked, and Deals only exist post-Convert.

## Regeneration on edit (added 2026-07-27)

The trigger is **created or updated**, so re-saving an edited quote regenerates its
document. The executor dedups on the CRM side, not the Creator side, because the
`Quote_Request` record is a disposable pointer (one was already deleted during testing)
while the CRM `Quotes` record is the durable artifact:

- Before creating a Quote, the executor runs one `searchRecords` on `Quotes` for
  `Subject = "Kinetic Bridge Quote <number>"`. Found → `updateRecord` refreshes
  `Quoted_Items`, `Valid_Till`, and the lookups in place. Not found → the original create
  path. The result map reports `quote_action` = `created` / `updated` / empty.
- This also makes the chain safe if QTS saves an edit as a **new** `Quote_Request`
  record with the same quote number — either trigger shape lands on the same CRM Quote.
- Dedup is best-effort, mirroring the meeting-dedup posture: a failed search degrades to
  create (worst case a duplicate Quote record, never a lost document), a failed update
  drops to the Deal-attach fallback.
- Cost discipline: the regeneration path adds exactly **one CRM search call** and **zero
  Creator API calls** — the executor never reads or writes Creator; everything it needs
  arrives on the Flow trigger. The External Call budget cost per save stays ~5.
- Old PDFs are never deleted (deletes are Tier 3). A regenerated quote accumulates
  attachments with the same filename, distinguished by attachment date — accepted; a
  revision suffix would cost an extra read per run to number correctly.
- The Contact stamp is naturally regeneration-safe: `First_Quote_*` writes only when
  blank, so an edit never rewrites the first-quote datapoint.

## Order of work

1. Blake: fix the template merge fields (blocker above), decide A vs B.
2. Repo: `build_quote_merge_payload` + tests (buildable now against the recorded live shape).
3. Repo: `file_quote_on_crm` + tests.
4. Live (approval needed): create the Flow, wire the Writer action, run against a fresh QTS
   draft, verify PDF on the Quote, WorkDrive copy, stamps on Contact, then the email step.

Note: `Quote_Stage` was null on the live test quote. QTS should set it to `Draft` on save so
option B has a real stage ladder; confirm what the picklist offers before wiring.
