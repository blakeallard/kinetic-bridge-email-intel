# TeamInbox retirement assessment — Zoho Mail direct to CRM

Zoho Task ID: 2543412000001583003 (BI1-T110)

**Status: ASSESSMENT ONLY (Blake, 2026-07-28).** No code, no Flow changes. The go/no-go
and scheduling are a Bill/Bryan meeting outcome.

## Verdict

**Retire TeamInbox and ingest directly from Zoho Mail.** Reasons, in order of weight:

1. **No recorded rationale for TeamInbox exists.** It was inherited from the task
   description's wording ("TeamInbox (communication layer) → Zoho Flow triage → …",
   `TASK.md`); no trade-off analysis or ADR anywhere in the repo chose it.
2. **Thread continuity — project gate #2 — requires what TeamInbox cannot provide.**
   Reply-in-thread and thread grouping need the stable RFC message-id, a thread id, the
   routed inbox to send from, and attachment handles. TeamInbox's `messageId` is proven
   unstable: on 2026-07-24 it issued **two different messageIds for one email** delivered
   to two inbox recipients, producing duplicate CRM records (`docs/audit_log.md`
   §461-500); the dedup key had to be re-based on email identity as a workaround. The
   Zoho Mail API carries the real identifiers natively.
3. **Its unique value doesn't apply here.** TeamInbox's differentiator is shared-inbox
   collaboration UI (assignment, comments). With one shared intake inbox and three
   users, that job is already done by the CRM record (the system of record this project
   built) plus the Cliq notification. CRM is the hub; TeamInbox is a second inbox UI
   nobody needs to live in.
4. **The Mail path is simpler infrastructure.** Zoho Flow has a **native "email
   received" trigger for Zoho Mail** — no TeamInbox rule, no outgoing webhook hop. The
   **Mail eWidget** supplies CRM context inside Mail, replacing the last TeamInbox
   convenience.
5. **One fewer app** — Blake's stated direction: CRM as the communication hub, no
   excessive applications.

## Blast radius (verified against the repo, 2026-07-28)

The pipeline was deliberately built with a channel-agnostic seam: everything downstream
of the adapter reads the normalized contract (`docs/unified_intake_architecture.md` §3).
TeamInbox specifics are confined to:

| Surface | Location | Change |
| --- | --- | --- |
| The adapter (all payload shapes, event gate) | `scripts/normalize_teaminbox_payload.deluge` | Replaced by a `normalize_zoho_mail_payload.deluge` twin |
| Hardcoded `source = "zoho_teaminbox"` | `scripts/build_ai_analysis_request.deluge:17` | Pass through the normalized `source` (one line) |
| `Ingestion_Key` prefix `teaminbox:<portal>:<from>:<sentms>:<subject>` | adapter + `persist_recommendation` / `check_ai_recommendation_exists` (read it opaquely) | New keys `zohomail:<account>:<rfc-message-id>` — simpler and stronger. Old keys stay; dedup is per-email so prefixes never collide |
| Test fixtures | `samples/teaminbox_test_payloads.json`, pinned tests | New sample + tests for the Mail adapter; old ones retire with the adapter |

**Not touched:** gating logic, dedup mechanism, CRM matching, Zia agent, validation,
persistence, Blueprint, Cliq card, executor, QTS — and every existing
`AI_Recommendations` record.

## Migration sketch (for when it's approved)

1. **[REPO]** `scripts/normalize_zoho_mail_payload.deluge` emitting the same normalized
   contract **plus additive keys** the thread-continuity work needs: `rfc_message_id`,
   `thread_id`, `account_id`, `has_attachments` (blank on the form path — contract stays
   backward compatible). Tests: pinned source, behavior specs, and a key-set parity test
   against the TeamInbox adapter.
2. **[BLAKE]** New Flow: Zoho Mail "email received" trigger on the intake inbox →
   first run log-only to capture the real trigger payload shape (finalize the adapter
   against reality, not docs — the TeamInbox lesson) → paste the adapter → wire to the
   **same** downstream functions.
3. **[BLAKE]** Parallel run, a few business days, Mail path in **shadow mode** (stop
   after the match step, no persist — avoids duplicate Cliq pings); diff outcomes per
   email (gate decision, matched record, category).
4. **[BLAKE]** Cutover at a quiet moment: enable persist on the Mail path, disable the
   TeamInbox inbound rule. Manually check the switch-minute's records (only cross-prefix
   dedup exposure).
5. **[BLAKE]** Leave the old Flow disabled one week, then remove TeamInbox from the app
   roster. **[REPO]** mark the old adapter retired; update `docs/zoho_flow_inventory.md`
   + `STATUS.md`.
6. **Bundle the form-path convergence** into the same cutover: wire the form Flow to the
   already-built-and-tested `normalize_form_entry.deluge`, retiring
   `build_form_intake_payload.deluge` (the fake-TeamInbox-email hop) — this closes the
   stage-1 "legacy fake-email hop" gap in the same muscle movement.
7. **[BLAKE, anytime]** Enable the Zoho Mail eWidget for CRM context inside Mail.

## What this unblocks

- **Reply-in-original-thread for quote emails** (parked in `STATUS.md`): needs the Mail
  API + original message id, which the new adapter carries.
- **Thread continuity generally** (replies grouped, matched senders still analyzed):
  the `thread_id` / `rfc_message_id` keys become available to persist when that feature
  is picked up (persisting them to CRM is a Tier-3 field decision, separate).
- **Attachment handling** (0% today): `has_attachments` + Mail API handles.

## Risks / costs

- Mail-trigger payload shape is the only real unknown → resolved by the log-only capture
  in step 2 before any code is finalized.
- Emails arriving in the cutover minute could dedup under both prefixes → bounded, and
  checked manually at cutover.
- TeamInbox assignment/collab history is lost when the app is removed → acceptable: the
  system of record is CRM, and the association API has been writing emails onto records
  since 2026-07-25.
