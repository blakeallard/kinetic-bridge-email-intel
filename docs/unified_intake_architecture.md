# Unified Intake Architecture — two front doors, one hardened pipeline

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Status: DESIGN OF RECORD for the intake consolidation + deferred-lead work.**
Written 2026-07-24. The deferred-lead (Model C) half described in §4 is **implemented in
the repo and deployed to live Zoho** as of 2026-07-25; the form-channel convergence in §2
is **not built**. This document supersedes the earlier `deferred_lead_creation_spec.md`,
which was retired on 2026-07-25 once its content was absorbed here (see git history for
the original).

## 1. Principle

There are two ways a stranger reaches Bevco:

1. **External email** → Zoho TeamInbox → webhook.
2. **Website form** → Zoho Forms → (today) `build_form_intake_payload` → webhook.

The design goal is **one hardened pipeline with two thin adapters at the front**, not two
parallel pipelines. Every channel converges as early as possible onto a single
**normalized-message contract**, and from that point on there is exactly one code path to
harden, test, and deploy. Anything channel-specific lives only in the adapter that produces
the normalized contract.

```
 External email ──► normalize_teaminbox_payload ─┐
                                                 ├─► ONE shared pipeline ──►
 Website form  ──► normalize_form_entry ─────────┘   (dedup → match → defer-lead →
                                                      Zia → validate → persist →
                                                      approve → materialize-lead → execute)
```

## 2. The convergence decision (recommended change)

**Today** the form path fakes an email: `build_form_intake_payload` packs the structured
form fields into a TeamInbox-shaped body (`Name: … / Company: … / Phone: …`), POSTs it to
the ingestion webhook, and `normalize_teaminbox_payload` + `ensure_crm_match` then
**re-parse the body** with `indexOf("Company:")` to recover the fields. This is fragile and
lossy, and it adds an extra webhook hop.

**Recommended:** converge at the **normalized contract**, not by faking an email. The form
Flow calls **`normalize_form_entry`** (which already emits the same normalized map, and
preserves `company_name` / `phone` / `area_of_interest` as real fields) and then continues
directly into the shared pipeline — either as one combined Flow or as a Flow that hands the
normalized map to the same downstream custom functions.

Why this is more bulletproof:

- **No body round-trip.** Structured form fields stay structured; no `indexOf` parsing of a
  reflowed HTML body, which is the most breakable step in the current form path.
- **One less failure point.** Drops the form→webhook→re-ingest hop and its retry/latency and
  the literal-`\n` corruption (see §5.2).
- **Better Lead quality.** The deferred-lead materializer can use the form's clean
  `company`/`phone` directly, and fall back to body-derivation only for email.

`build_form_intake_payload` (the fake-email adapter) is retired once the form Flow points at
`normalize_form_entry`. Keep `normalize_teaminbox_payload` as the email adapter.

> If collapsing into a single Flow is operationally awkward in Zoho, the fallback is to keep
> two trigger Flows that both call the identical downstream custom functions — the win is the
> shared **contract + functions**, not necessarily a single Flow canvas.

## 3. The normalized-message contract (the seam)

Both adapters MUST emit the same keys so everything downstream is channel-agnostic. Current
producers already largely agree; this pins the contract.

| Key | Email adapter | Form adapter | Notes |
| --- | --- | --- | --- |
| `schema_version` | "1.0" | "1.0" | |
| `source` | `zoho_teaminbox` | `zoho_forms` | the only field downstream may branch on for provenance |
| `idempotency_key` | `teaminbox:…` | `zohoform:…` | unique per submission; drives dedup |
| `message_id` | thread/message id | synthetic form id | |
| `from_email` / `from_name` / `from_domain` | parsed | from fields | |
| `subject` / `body_html` / `summary` | parsed | assembled | |
| `should_process` / `skip_reason` | gate result | gate result | internal-sender + validity gate |
| `is_form_intake` | false | true | provenance flag |
| `company_name` / `phone` / `area_of_interest` | "" (unknown) | **populated** | structured extras; email leaves blank |

Downstream reads only this contract. The structured extras are additive: email senders leave
them blank and the Lead materializer falls back to body-derivation; form senders populate
them and the materializer uses them directly.

## 4. Deferred-lead (Model C) inside the unified pipeline

Model C serves both channels because both converge before the match step. The chosen
implementation:

- **No Zoho schema change.** Pending contact data rides in the existing unused
  `Approved_Action_JSON` field + `Email`.
- **The security-critical executor is left byte-for-byte untouched** — no JSON parsing added
  to it, `test_deluge_parity.py` unaffected.
- A **new `materialize_pending_lead`** function runs at approval *before* the executor:
  reads the pending payload, creates the Lead (owner Blake), stamps `Target_Record_ID`. The
  executor then runs on a normal matched Lead exactly as it does today.
- `ensure_crm_match` becomes **read-only** (no `createRecord`); it emits
  `match_status = "pending_lead"` plus the contact fields (structured for forms, derived for
  email).
- The tagged validator treats `pending_lead` as `valid` + `create_crm_task`;
  `persist_recommendation` stores the pending payload with `Target_Module = "Leads"` and a
  blank `Target_Record_ID`.
- Rejected recommendations create **nothing** — the core win, now uniform across both
  channels.

## 5. Bulletproofing checklist — every stage, both channels

Each row is a known failure mode, whether each channel is covered, and where.

### 5.1 Ingestion & gating
| Concern | Email | Form | Status / action |
| --- | --- | --- | --- |
| Invalid / missing sender email | `normalize_teaminbox_payload` gate | `normalize_form_entry` gate (`is_valid_sender`) | ✅ both gate to `should_process=false` |
| Internal sender loop (our own domains) | internal-sender skip | `is_internal_sender` skip | ✅ both |
| Automated / no-reply sender (DMARC reports, bouncers, postmaster) | `is_automated_sender` skip → `skip_reason = "automated_sender"` | **not gated** | ⚠️ email only, by design. Three DMARC robots reached the CRM as Leads before this gate existed (2026-07-24/25). A web-form submitter typing a no-reply address is not a realistic junk source, and the form gate's `is_valid_sender` already rejects malformed input — so the parity gap here is deliberate, not an oversight. Revisit if form junk ever appears. |
| Duplicate delivery of same submission | `Ingestion_Key` unique + dedup guard | same | ⚠️ read-then-write is racy; unique `Ingestion_Key` is the real guard (known risk #5) |

### 5.2 Normalization correctness
| Concern | Action |
| --- | --- |
| Literal `\n` in Deluge strings (does NOT render as newline) | **Bug present** in `build_form_intake_payload` / `normalize_form_entry` body assembly; fix with `hexToText("0A")` as already done in `persist_recommendation`. Moot for form once §2 drops body assembly, but fix `normalize_form_entry` if it stays the seam. |
| Body re-parsing (`indexOf("Company:")`) breaks on odd formatting | Eliminated for forms by §2 (use structured fields); remains best-effort for email only. |

### 5.3 CRM match & related lookups
| Concern | Status |
| --- | --- |
| `getRelatedRecords` throws on a record with no related items | ✅ fixed today — `fetch_open_related` guards null/size + try/catch. Same guard belongs in the standalone `fetch_open_tasks_for_*` twins. |
| Unmatched sender must still yield an actionable recommendation | ✅ `pending_lead` state (Model C) keeps it `create_crm_task` instead of downgrading to `manual_review`. |

### 5.4 Analysis (Zia)
| Concern | Status |
| --- | --- |
| Zia never returns / times out | ✅ bounded retry + `build_zia_timeout_fallback` persists a safe fallback record. |
| Blank Zia Query mapping (live Flow config) | ⚠️ known live defect — Query must map to `${buildAiAnalysisRequest_8}`; repo already specifies it. |
| Prompt injection in email/form body | ✅ executor never reads `Raw_Zia_Response` / `Validated_Analysis_JSON`; Task built from trusted scalars; parity-tested. Materializer uses only contact scalars, never interprets body as instructions. |

### 5.5 Persist & approval
| Concern | Status |
| --- | --- |
| Two recommendations for one submission → two Leads/Tasks | ⚠️ same residual as today; deferral makes it no worse (only approved ones create). Real fix = unique constraint at ingestion. |
| Reviewer can't tell executed from approved by `Status` alone | ⚠️ `Execution_Status` is source of truth; Blueprint transition inspection (runbook Step B) still open. |

### 5.6 Execution
| Concern | Status |
| --- | --- |
| Lead Task routing (`Who_Id` vs `What_Id`) | ✅ resolved live — Leads use `What_Id` + `$se_module=Leads`; `Who_Id` is Contacts-only. |
| Double execution under concurrency | ✅ conditional `If-Unmodified-Since` claim; ⚠️ live concurrency test (runbook Step A) still open. |
| Lead created but Task fails (new, from materializer) | Post-claim/terminal handling: `Target_Record_ID` stamped on Lead-create success so a rerun never re-creates the Lead; Task-create failure stays terminal for human repair. |

### 5.7 Deployment drift — the recurring root cause
Both live defects fixed today were **repo-ahead-of-live**: the deployed function differed from
the source. This is the single biggest systemic risk.
- **Action:** every function in this pipeline gets deployed from the repo verbatim, and the
  deploy checklist in `zoho_flow_inventory.md` is the gate. Consider a periodic parity spot-check
  (paste live source back, diff against repo) until a real deploy automation exists.

## 6. What is repo vs. live

- **Repo (this work):** the custom-function sources, the executable spec parity, and offline
  tests. All safe to build and verify without Zoho.
- **Live (Blake, after review):** re-pointing the form Flow at `normalize_form_entry` (or
  merging the two Flows), and redeploying every changed function. No OAuth scope, connection,
  or Blueprint change is required by this design.

## 7. Build order

1. This doc (design of record) — done.
2. Converge the form adapter on `normalize_form_entry`; fix the literal-`\n` bug; retire
   `build_form_intake_payload` (repo).
3. Model C functions: read-only `ensure_crm_match`, `materialize_pending_lead`, tagged
   validator, `persist_recommendation` (repo).
4. Offline tests + parity green.
5. STATUS.md + reconcile `single_path_refactor_spec.md` block table (it still shows eager
   match and predates `ensure_crm_match`).
6. Hand off the live deploy checklist (form Flow rewire + function redeploys).

## 8. Open decisions for Blake

1. **Combine the two Flows into one canvas, or keep two triggers calling shared functions?**
   Either satisfies the architecture; one canvas is tidier, two triggers are lower-risk to
   change. (Default: two triggers, shared functions.)
2. **Form node red markers** in the live `KB Website Form to AI Recommendations` Flow — are
   `build_form_intake_payload` and `Send Webhook` actually erroring, or is that just node
   styling? If erroring, the form channel may not be completing today and should be triaged
   like the two defects fixed on 2026-07-24. (Moot for the function if §2 retires it, but the
   Flow itself needs to be known-good.)
