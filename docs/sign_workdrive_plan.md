# Zoho Sign + WorkDrive filing — design and wiring

Zoho Task ID: 2543412000001583003 (BI1-T110)

Closes the end-to-end chain: quote approved by the client → human clicks **Send for
signature…** in QTS → Zoho Sign request → client signs → signed PDF auto-filed into a
structured WorkDrive tree + attached to the CRM Quote. Repo code is complete and pinned
by `tests/test_sign_workflow_artifacts.py`; everything below the "Blake config" line is
Zoho-side wiring.

## Flow diagram

```text
QTS widget: "Send for signature…" click
  └─ sets Quote_Request Status = "Send for Signature" + Recipient_Name/Email
       (existing widget leg; polls Sign_Request_ID afterwards)
        │
        ▼  Zoho Flow: Quote_Request created-or-updated, decision Status == "Send for Signature"
  build_quote_merge_payload  (existing, reused as-is)
        │
  ensure_workdrive_folder_path        ← Creator WorkDrive_Folder_Map consulted first
        │     Accounts/<Account>/Deals/<YYYY-MM-DD Deal>/{Quotes,Signed,Correspondence,Attachments}
        ▼
  send_quote_for_signature
        ├─ guard: Sign_Request_ID already set → noop (no double-send)
        ├─ guard: blank customer email → failed loudly
        ├─ Writer merge (v4 template, same id as the document executor — pinned)
        ├─ Sign request: customer signs first, internal signer second, sequential
        ├─ Sign_Request_ID written back onto Quote_Request (widget poll goes green)
        └─ quote PDF filed to WorkDrive Quotes/ (best-effort)

Zoho Sign completion webhook (all signers done)
        ▼  Zoho Flow: webhook trigger
  ensure_workdrive_folder_path  (map hit — no folder creation on the happy path)
        ▼
  handle_sign_completion
        ├─ gate: request_status == "completed" only
        ├─ CRM Quote found by Subject "Kinetic Bridge Quote <n>"
        ├─ idempotency: Description marker "Sign completed: <request_id>" → noop
        ├─ signed PDF downloaded → WorkDrive Signed/ → attached to the CRM Quote
        ├─ Quote_Request.Status = "Signed" (via the Description back-reference stamp)
        └─ Cliq notification
```

## Design decisions (log)

| Decision | Choice | Why |
| --- | --- | --- |
| Send trigger | Human click in QTS (existing widget leg) | Preserves the approval-gate model; the client-facing send always has a human decision behind it |
| Filing trigger | Zoho Sign completion webhook | Blake 2026-07-28: "when the client field is signed" — native, no email parsing of returned copies |
| Folder bookkeeping | Creator `WorkDrive_Folder_Map` table (Folder_JSON per Deal) | No CRM schema change (Tier 3); survives folder renames; 1 read on the happy path |
| Folder structure | `Accounts/<Account>/Deals/<YYYY-MM-DD DealName>/{Quotes, Signed, Correspondence, Attachments}` | Mirrors CRM so documents and records share one shape |
| Ledger of signed quotes | CRM list view / Analytics over `Quotes` where `Status = Signed` | One-database rule — no Sheet copy (considered and rejected) |
| `fn_generate_pdf` | Build fresh, not export | Every live run produced documents via the Flow executor; no Sign request has ever existed — the Creator middle described in widget comments never ran |
| Executor | `generate_and_file_quote_document` stays byte-untouched | The Sign path is a sibling of the Package-Requested path; pinned by test |
| Signing order | Customer first, internal signer second, sequential | The client's approval is the event; the internal countersign follows it |

## Repo artifacts

| File | Role |
| --- | --- |
| `scripts/qts/send_quote_for_signature.deluge` | Merge → Sign request → writeback → Quotes/ filing |
| `scripts/ensure_workdrive_folder_path.deluge` | Idempotent folder-path ensure + mapping table |
| `scripts/qts/handle_sign_completion.deluge` | Webhook → download → Signed/ → attach → statuses → Cliq |
| `tests/test_sign_workflow_artifacts.py` | 26 pins: guards, no-double-send, webhook idempotency, create-only, sanitization, executor-untouched |

## Blake config (deploy checklist)

1. **Creator (QTS app, dev):**
   - `WorkDrive_Folder_Map` form: `Module` (text), `Record_ID` (text), `Folder_JSON`
     (multi-line), `Path` (text); report `WorkDrive_Folder_Map_Report`.
   - `Quote_Request`: ensure a `Sign_Request_ID` field exists (single line, admin-only is
     fine — the bridge already reads it); add `Signed` to the Status dropdown.
2. **Connections in Flow:** `sign_to_flow` (Zoho Sign OAuth), `workdrive_to_flow`
   (WorkDrive), `creator_to_flow` (Creator) — `writer_to_flow` and
   `zoho_crm_to_zoho_flow` already exist.
3. **Send Flow:** in the existing QTS Flow (or a sibling), add a decision branch
   `Status == "Send for Signature"` → `ensure_workdrive_folder_path` (inputs: deal id,
   account name, deal name, quote date, **accounts root folder id** — create an
   `Accounts` folder in the chosen WorkDrive Team Folder once and paste its id here) →
   `send_quote_for_signature` (map trigger fields + `quotes_folder_id` from the ensure
   block; `existing_sign_request_id` ← trigger `Sign_Request_ID`).
4. **Completion Flow:** new Flow, webhook trigger. Register the webhook in Zoho Sign
   (Settings → Developer → Webhooks; event: RequestCompleted) pointing at the Flow URL →
   `ensure_workdrive_folder_path` → `handle_sign_completion` (inputs: request id/status/
   name from the webhook payload, `signed_folder_id` from ensure, Cliq channel
   `ai-recs-test`). **Capture one real webhook payload log-only first** and confirm the
   field names (`request_id`, `request_status`, `request_name` assumed) before mapping.
5. **Approval note (Bill):** WorkDrive folder creation is create-only — the helper never
   deletes, moves, or renames (pinned by test). Flag as Tier 1–2.

## Deploy-time verification

1. Dry-run `ensure_workdrive_folder_path` on a test Deal — inspect the WorkDrive tree;
   run twice — second run must be a map hit that creates nothing.
2. Full loop with Blake as the client signer: quote → Generate → Send for signature →
   `Sign_Request_ID` on the record (widget poll green) → sign → webhook → PDF in
   `Signed/` → CRM Quote attachment + `Signed` status → Cliq ping.
3. Re-fire the webhook manually → `completion_already_processed`, nothing duplicated.
   Re-click Send → `sign_request_already_exists`, no second request.

## Assumptions to confirm live (the `attachFile`-arity class)

- Zoho Sign create-request API shape: multipart `file` + `data` (request JSON), response
  `requests.request_id`, then `/submit`. Confirm against one live call.
- Sign completion webhook payload key names.
- WorkDrive v1 `POST /files` folder-create body (`data.attributes.{name,parent_id}`) and
  `upload.zoho.com/workdrive-api/v1/upload` param names.
- `zoho.creator.updateRecord` argument shape in Flow's Deluge (owner, app, report, id,
  map, params, connection).
