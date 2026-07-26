# CRM duplicate merge — checklist for Blake + Bill

Zoho Task ID: 2543412000001583003 (BI1-T110, data cleanup)

**Status: READY FOR REVIEW. Nothing has been merged or deleted.** Every record id below was
verified by COQL against live Zoho CRM on 2026-07-25. No live record was modified to
produce this document.

## Why this matters

`scripts/resolve_crm_match.deluge` resolves an inbound sender by exact email
and takes **the first record the API returns**. There is no `size() > 1` check, no sort,
and no ambiguity flag anywhere in the pipeline (lines 15-27, 40-51, 79-86). When two
Contacts hold the same address, which copy an inbound email associates to — and which copy
an approved AI recommendation attaches its Task to — is unstable between runs.

Merging is therefore a correctness fix, not tidiness.

## Approval

| Action | Tier | Who |
| --- | --- | --- |
| Merge Contacts / Accounts | 2 (bulk write) | Bill approves, Blake executes |
| Delete the 12 junk Contacts | 3 (delete) | **Bill only** |

## Method — use native Merge, never delete-and-recreate

Zoho CRM's built-in **Merge** (record → ⋯ → Merge, up to 3 records) carries related lists —
Deals, Tasks, Emails, Notes, Attachments — from *all* copies onto the master. Deleting a
duplicate instead would orphan whatever hangs off it.

For each merge: open the **Keep** record, Merge, add the **Retire** record, confirm the
master is the Keep record, and take the non-blank value on any field where they differ.

---

## Part 1 — Contacts sharing an email (4 merges)

These are the only duplicates that can currently corrupt matching. Both copies hold the
same address; the matcher lowercases both sides, so the Schnell casing difference still
collides. `Modified_Time == Created_Time` on all eight — none has ever been edited, so no
manual work is at risk.

| # | Person | Email | Retire (Apr 2025) | **Keep** (migrated) |
| --- | --- | --- | --- | --- |
| 1 | Julia Turner | `julia@neros.tech` | `6719186000000618370` | `6719186000003471904` |
| 2 | Jonathan Nicols | `jonathan.nicols@davisnicols.com` | `6719186000000632100` | `6719186000003471921` |
| 3 | Richard Phamdo | `richard@voltaicmarine.com` | `6719186000000632068` | `6719186000003471969` |
| 4 | Rob → Robert Schnell | `Robert.schnell@sk.com` → `robert.schnell@sk.com` | `6719186000000632085` | `6719186000003473004` |

**Why the newer copy is master:** Deals reference the new ids (e.g. `Voltaic Marine -
Battery Design & Supply Leadership` → Richard Phamdo `6719186000003471969`), and the new
copies link to the Accounts that carry Website values.

**Decision for Bill (#4):** the surviving record is named *Robert Schnell*, the retired one
*Rob Schnell*. Confirm which he goes by before merging — the master's name wins.

---

## Part 2 — Duplicate Accounts (5 merges)

No matching impact today (see Backlog), but Contacts and Deals are split across the two
copies, so a company page shows only half its history.

| # | Company | Retire | **Keep** | Why |
| --- | --- | --- | --- | --- |
| 5 | Neros | `6719186000000618367` | `6719186000003471773` | website set; holds 4 contacts + deals |
| 6 | Voltaic Marine | `6719186000000632063` | `6719186000003471818` | holds the surviving Phamdo |
| 7 | SK On | `6719186000000632075` | `6719186000003471837` | holds the surviving Schnell |
| 8 | Davis Nicols | `6719186000000632097` | `6719186000003471786` | holds the surviving Nicols |
| 9 | ReJoule / Rejoule | see below | see below | **both hold a contact — decide first** |

**Decision for Bill (#9):** two records differ only in casing.

- `6719186000003471771` — "ReJoule", holds Zora Chung
- `6719186000003469022` — "Rejoule", has the website `https://rejouleenergy.com/`, holds
  Steven Chung

Merge either direction — the master's name and casing wins, and the other contact carries
over. Pick whichever matches their actual branding.

**Order matters:** do Part 1 before Part 2. Merging Contacts first means each Account merge
sees one contact per person instead of two.

---

## Part 3 — Delete the broken import of 2026-07-24 16:52:59 (Bill only)

Twelve Contacts created in one batch, all owned by Bill, all with **null email and null
Account** — strictly worse copies of records that already existed. They cannot affect
matching (the matcher re-checks `record_email == safe_email`, and null never equals a real
address), so this is clutter, not corruption.

| Delete | Name | Duplicate of |
| --- | --- | --- |
| `6719186000003563040` | Mike Ferry | `6719186000003471929` |
| `6719186000003563041` | Blake Rosengren | `6719186000003471930` (SpaceVector) |
| `6719186000003563043` | John Konig | `6719186000003471948` (Osh Kosh) |
| `6719186000003563044` | Dan Walmsley | `6719186000003471949` (ESOX) |
| `6719186000003563045` | Fan Hou | `6719186000003471950` (Prologium) |
| `6719186000003563047` | Diana Zhao | `6719186000003471975` (New Vista Capital) |
| `6719186000003563048` | Rich Byczek | `6719186000003471979` (Intertek) |
| `6719186000003563049` | Chad Sweet | `6719186000003471980` (ModalAI) |
| `6719186000003563050` | Ronnie Ta0 | `6719186000003471981` (Amprius) |
| `6719186000003563051` | Marcus Rossi | `6719186000003471982` |
| `6719186000003563055` | Criswell Choi | `6719186000003473001` |
| `6719186000003563056` | Teddy Kang | `6719186000003473012` (Network Environments) |

> ### ⚠️ Do NOT mass-delete by that Created_Time
>
> The batch contains **13** records. The thirteenth — `6719186000003563057`,
> **Jonah Bliss**, `jonahbliss@gmail.com`, Account **Curbivore** — has real data and is not
> a duplicate. Any list-view mass action filtered on `Created_Time = 2026-07-24 16:52:59`
> would delete him too. Select the twelve ids above explicitly.

**Also check before starting:** the id sequence skips `...042`, `...046`, `...052`,
`...053`, `...054`. Those five records went somewhere. Look for Leads or Accounts created
at the same timestamp before assuming that import only touched Contacts.

---

## Verification — run after the merges

Both of these are read-only COQL and can be run from the CRM API or an MCP session.

```sql
select Full_Name, Email, Account_Name from Contacts
where Email in ('julia@neros.tech','jonathan.nicols@davisnicols.com',
                'richard@voltaicmarine.com','robert.schnell@sk.com')
```

Expect **4 rows, not 8.**

```sql
select Account_Name, Website from Accounts
where Account_Name in ('Neros','Voltaic Marine','SK On','Davis Nicols','ReJoule','Rejoule')
```

Expect **5 rows, not 11.**

Then confirm:

- Contact count dropped from **154** to about **138** (12 deletions + 4 merges).
- `6719186000003563057` (Jonah Bliss) **still exists**.
- Open Neros and SK On and confirm each shows all its contacts and deals on one page.

---

## Backlog — found during this audit, deliberately not fixed here

1. **`Email_Domain` is null on all 80 Accounts.** `resolve_crm_match` stage 3 searches
   `(Email_Domain:equals:<domain>)`, so the Account-by-domain fallback **never matches a
   real record in production**. A new person at a known company — Neros, SK On, Meyers Manx
   — falls through Contact lookup, Lead lookup and Account lookup, and becomes a brand-new
   pending Lead instead of being recognised as an existing customer. Given multi-contact
   companies are the dominant shape of this data (Neros has 4 contacts, Harbinger 3,
   AmigoTec 3, About:Energy 3), this is the highest-value follow-up. Approach proposed by
   Blake: backfill the field from **Zoho Mail records**, using existing correspondence to
   tie a sending domain to a company.
2. **The matcher has no ambiguity detection.** After this cleanup the data is correct, but
   the next duplicate that appears will again be resolved silently and non-deterministically.
   A deterministic tie-break plus a `match_ambiguous` flag on the returned map would make it
   visible. Deferred by Blake, 2026-07-25.
