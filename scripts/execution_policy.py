"""BI1-T110 — approved-action execution contract.

This module is the *executable specification* for the separate execution stage that
turns an approved `AI_Recommendations` CRM record into exactly one Zoho CRM Task.

It is deliberately free of network code: all CRM access goes through the `CrmPort`
protocol, so the full decision path is testable offline. The Deluge deployment
artifact `execute_approved_recommendation.deluge` is a line-for-line translation of
the logic here; `tests/test_deluge_parity.py` guards against drift.

Security posture
----------------
* The caller supplies only an AI Recommendation record ID. Every value used for a
  decision is refetched from CRM (`CrmPort.get_record`). No incoming action payload
  is trusted.
* `Raw_Zia_Response` is never parsed, never interpreted, and never reaches the Task
  payload. Task content is built solely from persisted, trusted scalar fields.
* The only side effects are: updates to the recommendation record's `Execution_*`
  fields, and the creation of one Task. No Deal stage change, no Closed Won, no
  quote, no email.

Failure policy — the claim boundary is what matters
---------------------------------------------------
A `failed` result is **not uniformly terminal**. What matters is whether the record
had already been claimed when the failure happened.

**Pre-claim failures** (`record_fetch_failed`, `modified_time_unavailable`,
`blocked_write_failed`, `claim_failed`) happen before the conditional claim succeeds.
No Task creation was authorized, and the record may still be unclaimed. Once the
underlying problem is corrected, a fresh invocation is safe: it refetches the record
and re-evaluates the claim from scratch. Nothing retries automatically — rerunning is
a deliberate human action.

**Post-claim failures** (`task_create_failed`, `post_execution_write_failed`) happen
after the claim succeeded. `Execution_Key` stays populated, so `is_already_claimed()`
treats the record as claimed and a later invocation returns `duplicate` rather than
retrying. **These are terminal and require human investigation.**

The reason post-claim failures are terminal: a lost or failed Task-creation *response*
does not prove the Task was not created. Zoho may have committed the Task and failed
on the way back. A blind retry would then create a second Task against the customer's
record, which is exactly the outcome this stage exists to prevent. Losing an execution
is recoverable by a human; silently duplicating customer-facing work is not.

So a post-claim failure requires a human to check whether a Task actually exists
*before* changing any execution field, then either record it by hand or deliberately
clear `Execution_Key` and `Execution_Status`. Nothing in this module clears them, and
nothing moves a `Failed` record back to `Not Started`.

`Execution_Attempts` records how many times a record was *claimed*. In this version
that is at most one, because a claimed record is never re-claimed automatically. The
`MAX_EXECUTION_ATTEMPTS` check is retained as a defensive guard against a future
retry mechanism or manual reset, not because this version performs three attempts.

Field API names below were verified live against the Bevco CRM org on 2026-07-19
via the Zoho CRM metadata API. See docs/live_module_inspection_2026-07-19.md.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Protocol

MODULE_API_NAME = "AI_Recommendations"
TASKS_MODULE_API_NAME = "Tasks"

ALLOWED_RECOMMENDATION_TYPE = "create_crm_task"

ALLOWED_TARGET_MODULES = ("Contacts", "Leads", "Accounts")

TASK_LINK_FIELD = {
    "Contacts": "Who_Id",
    "Leads": "What_Id",
    "Accounts": "What_Id",
}

MAX_EXECUTION_ATTEMPTS = 3

CLAIMED_EXECUTION_STATUSES = ("In Progress", "Executed")

CLAIMABLE_EXECUTION_STATUSES = ("", "Not Started")

PRE_CLAIM_FAILURE_REASONS = (
    "record_fetch_failed",
    "modified_time_unavailable",
    "blocked_write_failed",
    "claim_failed",
)

POST_CLAIM_FAILURE_REASONS = (
    "task_create_failed",
    "post_execution_write_failed",
)

POLICY_CHECKS = (
    "status_not_approved",
    "requires_approval_not_true",
    "created_by_ai_not_true",
    "validation_status_not_valid",
    "recommendation_type_not_allowed",
    "target_module_not_allowed",
    "target_record_id_blank",
    "execution_status_not_claimable",
    "executed_task_id_present",
    "execution_attempts_limit_reached",
)

TASK_SUBJECT_MAX_LEN = 255
TASK_DESCRIPTION_MAX_LEN = 4000

TASK_DUE_DAYS = 2
FALLBACK_TASK_OWNER_ID = "6719186000002395001"
REVIEW_NOTES_MAX_LEN = 1000
FIELD_MAX_LEN = 255
ERROR_MAX_LEN = 500

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_SECRETISH = re.compile(
    r"Zoho-oauthtoken\s+\S+"
    r"|\b[A-Za-z0-9]{10,}\.[A-Za-z0-9._-]{20,}\b"
    r"|\b(?=[A-Za-z0-9_-]{32,}\b)(?=[^\s]*\d)(?=[^\s]*[A-Z])[A-Za-z0-9_-]{32,}\b",
    re.IGNORECASE,
)


class ExecutionError(Exception):
    """Raised by a `CrmPort` implementation when a CRM call fails."""


class DuplicateKeyError(ExecutionError):
    """Raised when the unique `Execution_Key` constraint rejects a claim."""


class PreconditionFailed(ExecutionError):
    """Raised when a conditional claim loses the race.

    The record was modified between the read and the conditional write, so another
    execution won. The loser must treat this as a duplicate no-op.
    """


class CrmPort(Protocol):
    """The narrow CRM surface the executor is allowed to touch."""

    def get_record(self, module: str, record_id: str) -> dict[str, Any] | None: ...

    def claim_record(
        self,
        module: str,
        record_id: str,
        payload: dict[str, Any],
        if_unmodified_since: str,
    ) -> dict[str, Any]:
        """Conditionally update. Must raise PreconditionFailed if the record changed.

        This is the executor's mutual-exclusion primitive. An implementation that
        performs an unconditional update is incorrect and silently reintroduces the
        double-execution race.
        """
        ...

    def update_record(
        self, module: str, record_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]: ...

    def create_record(self, module: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class Clock(Protocol):
    def now_iso(self) -> str: ...


def due_date_from(clock: Clock) -> str:
    """Task due date: the clock's date plus TASK_DUE_DAYS, as yyyy-MM-dd.

    Derived from the injected clock rather than the wall clock so execution stays
    deterministic under test. Returns "" if the clock's stamp is unparseable, which
    leaves Due_Date unset rather than inventing a date.
    """
    stamp = text_of(clock.now_iso())[:10]
    try:
        return (date.fromisoformat(stamp) + timedelta(days=TASK_DUE_DAYS)).isoformat()
    except ValueError:
        return ""


def build_execution_key(record_id: str) -> str:
    """The deterministic, unique-per-recommendation execution key."""
    return f"ai-execution:{record_id}:{ALLOWED_RECOMMENDATION_TYPE}"




def strict_true(value: Any) -> bool:
    """True only for a real boolean True or the exact strings "true"/"True".

    Anything else — None, "", 0, "yes", "1" — is not true. Zoho returns real JSON
    booleans; the string forms are accepted because Zoho Flow variable mapping can
    stringify a checkbox on the way into a custom function.
    """
    if value is True:
        return True
    return isinstance(value, str) and value.strip() in ("true", "True")


def text_of(value: Any) -> str:
    """Flatten a CRM field to a trimmed string.

    Lookup fields (userlookup, picklist objects) arrive as dicts; take their
    display value rather than the raw dict repr.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "display_value", "id"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def int_of(value: Any, default: int = 0) -> int:
    """Flatten a CRM integer field; blank/unparseable becomes `default`."""
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def sanitize(value: str, max_len: int) -> str:
    """Strip control characters and truncate. Used on every outbound string."""
    cleaned = _CONTROL_CHARS.sub(" ", value or "")
    cleaned = cleaned.strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def sanitize_error(value: str) -> str:
    """Redact anything token-shaped, then truncate. Errors land in a CRM field."""
    redacted = _SECRETISH.sub("[redacted]", value or "")
    return sanitize(redacted, ERROR_MAX_LEN)




def evaluate_policy(record: dict[str, Any]) -> list[str]:
    """Return the list of failed policy checks. Empty list means "may execute".

    Every check reads a trusted, refetched CRM value. Checks are evaluated in full
    (not short-circuited) so the recorded `Execution_Error` names every reason the
    record was refused, not just the first.
    """
    violations: list[str] = []

    if text_of(record.get("Status")) != "Approved":
        violations.append("status_not_approved")

    if not strict_true(record.get("Requires_Approval")):
        violations.append("requires_approval_not_true")

    if not strict_true(record.get("Created_By_AI")):
        violations.append("created_by_ai_not_true")

    if text_of(record.get("Validation_Status")) != "valid":
        violations.append("validation_status_not_valid")

    if text_of(record.get("Recommendation_Type")) != ALLOWED_RECOMMENDATION_TYPE:
        violations.append("recommendation_type_not_allowed")

    if text_of(record.get("Target_Module")) not in ALLOWED_TARGET_MODULES:
        violations.append("target_module_not_allowed")

    if text_of(record.get("Target_Record_ID")) == "":
        violations.append("target_record_id_blank")

    if text_of(record.get("Execution_Status")) not in CLAIMABLE_EXECUTION_STATUSES:
        violations.append("execution_status_not_claimable")

    if text_of(record.get("Executed_Task_ID")) != "":
        violations.append("executed_task_id_present")

    if int_of(record.get("Execution_Attempts")) >= MAX_EXECUTION_ATTEMPTS:
        violations.append("execution_attempts_limit_reached")

    return violations


def is_already_claimed(record: dict[str, Any]) -> bool:
    """True when another execution already owns or completed this record.

    Distinguished from a policy violation: a claimed record is a benign duplicate
    invocation, not a misconfiguration, so it must not overwrite `Execution_Error`
    or burn an attempt.
    """
    return (
        text_of(record.get("Execution_Status")) in CLAIMED_EXECUTION_STATUSES
        or text_of(record.get("Executed_Task_ID")) != ""
        or text_of(record.get("Execution_Key")) != ""
    )




def build_task_payload(
    record: dict[str, Any], record_id: str, due_date: str = ""
) -> dict[str, Any]:
    """Build the Task from persisted trusted scalars only.

    `Raw_Zia_Response` and `Validated_Analysis_JSON` are intentionally not read.
    The model's free text never becomes Task content, so a prompt-injection payload
    in the email cannot reach a human reading the Task.
    """
    def field(name: str) -> str:
        return sanitize(text_of(record.get(name)), FIELD_MAX_LEN)

    message_id = field("Message_ID")
    target_module = field("Target_Module")
    target_record_id = field("Target_Record_ID")
    reviewed_by = field("Reviewed_By")
    reviewed_at = field("Reviewed_At")
    idempotency_key = field("Ingestion_Key")
    review_notes = sanitize(text_of(record.get("Review_Notes")), REVIEW_NOTES_MAX_LEN)

    ai_category = field("AI_Category")
    sender_email = field("Email")
    subject_topic = ai_category if ai_category else "AI Recommendation"
    subject_text = f"Follow up: {subject_topic}"
    if sender_email:
        subject_text = f"{subject_text} - {sender_email}"
    subject = sanitize(subject_text, TASK_SUBJECT_MAX_LEN)

    reviewed_by_id = text_of((record.get("Reviewed_By") or {}).get("id"))
    task_owner_id = reviewed_by_id if reviewed_by_id else FALLBACK_TASK_OWNER_ID

    description_lines = [
        "Created by the BI1-T110 approved-action executor.",
        "",
        f"AI Recommendation record: {record_id}",
        f"Idempotency key: {idempotency_key}",
        f"Source message ID: {message_id}",
        f"Recommendation type: {ALLOWED_RECOMMENDATION_TYPE}",
        f"Target: {target_module} / {target_record_id}",
        f"Approved by: {reviewed_by}",
        f"Approved at: {reviewed_at}",
        "",
        "Reviewer notes:",
        review_notes if review_notes else "(none)",
        "",
        (
            "This Task was generated only from persisted, human-approved recommendation "
            "fields. The raw AI response was not interpreted and its instructions were "
            "not executed. Open the AI Recommendation record to read the original "
            "analysis."
        ),
    ]

    payload: dict[str, Any] = {
        "Subject": subject,
        "Description": sanitize("\n".join(description_lines), TASK_DESCRIPTION_MAX_LEN),
        "Status": "Not Started",
        "Priority": "Normal",
        "Owner": {"id": task_owner_id},
    }
    if due_date:
        payload["Due_Date"] = due_date

    payload[TASK_LINK_FIELD[target_module]] = {"id": target_record_id}
    payload["$se_module"] = target_module

    return payload




def _result(status: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"status": status}
    out.update(extra)
    return out


def execute_approved_recommendation(
    record_id: str,
    crm: CrmPort,
    clock: Clock,
) -> dict[str, Any]:
    """Execute one approved recommendation. Returns a result map, never raises.

    Result `status` is one of:
      * `executed`  — a Task was created and the record was marked Executed.
      * `duplicate` — already claimed or already executed; no Task created.
      * `blocked`   — a policy check failed; no Task created.
      * `failed`    — a CRM error; no Task confirmed. Whether this is recoverable
                      depends on where it happened relative to the claim:

                      PRE-CLAIM  (`record_fetch_failed`, `modified_time_unavailable`,
                      `blocked_write_failed`, `claim_failed`) — no Task creation was
                      authorized and the record may remain unclaimed. A fresh
                      invocation is safe once the underlying problem is corrected,
                      because it refetches and re-evaluates the claim. Nothing
                      reruns automatically.

                      POST-CLAIM (`task_create_failed`,
                      `post_execution_write_failed`) — `Execution_Key` stays
                      populated and the record must not be retried automatically.
                      TERMINAL: a human must check whether Zoho created the Task
                      before changing any execution field.

    See PRE_CLAIM_FAILURE_REASONS / POST_CLAIM_FAILURE_REASONS.
    """
    record_id = text_of(record_id)
    if record_id == "":
        return _result("blocked", reason="record_id_blank", violations=["record_id_blank"])

    try:
        record = crm.get_record(MODULE_API_NAME, record_id)
    except ExecutionError as exc:
        return _result("failed", reason="record_fetch_failed", error=sanitize_error(str(exc)))

    if not record:
        return _result("blocked", reason="record_not_found", violations=["record_not_found"])

    execution_key = build_execution_key(record_id)

    if is_already_claimed(record):
        return _result(
            "duplicate",
            reason="already_claimed",
            record_id=record_id,
            execution_key=execution_key,
            executed_task_id=text_of(record.get("Executed_Task_ID")) or None,
        )

    violations = evaluate_policy(record)
    if violations:
        error = "policy_violation: " + ", ".join(violations)
        try:
            crm.update_record(
                MODULE_API_NAME,
                record_id,
                {
                    "Execution_Status": "Blocked",
                    "Execution_Error": sanitize_error(error),
                },
            )
        except ExecutionError as exc:
            return _result(
                "failed",
                reason="blocked_write_failed",
                violations=violations,
                error=sanitize_error(str(exc)),
            )
        return _result("blocked", reason="policy_violation", violations=violations, record_id=record_id)

    modified_time = text_of(record.get("Modified_Time"))
    if modified_time == "":
        return _result(
            "failed",
            reason="modified_time_unavailable",
            record_id=record_id,
            error="cannot claim atomically without Modified_Time",
        )

    attempts = int_of(record.get("Execution_Attempts")) + 1
    try:
        crm.claim_record(
            MODULE_API_NAME,
            record_id,
            {
                "Execution_Key": execution_key,
                "Execution_Status": "In Progress",
                "Execution_Started_At": clock.now_iso(),
                "Execution_Attempts": attempts,
            },
            if_unmodified_since=modified_time,
        )
    except PreconditionFailed:
        return _result(
            "duplicate",
            reason="claim_lost_race",
            record_id=record_id,
            execution_key=execution_key,
        )
    except DuplicateKeyError:
        return _result(
            "duplicate",
            reason="execution_key_conflict",
            record_id=record_id,
            execution_key=execution_key,
        )
    except ExecutionError as exc:
        return _result("failed", reason="claim_failed", error=sanitize_error(str(exc)))

    task_payload = build_task_payload(record, record_id, due_date_from(clock))
    try:
        created = crm.create_record(TASKS_MODULE_API_NAME, task_payload)
        task_id = text_of((created or {}).get("id"))
        if task_id == "":
            raise ExecutionError("task_create_returned_no_id")
    except ExecutionError as exc:
        try:
            crm.update_record(
                MODULE_API_NAME,
                record_id,
                {
                    "Execution_Status": "Failed",
                    "Execution_Error": sanitize_error(str(exc)),
                },
            )
        except ExecutionError:
            pass
        return _result(
            "failed",
            reason="task_create_failed",
            record_id=record_id,
            attempts=attempts,
            error=sanitize_error(str(exc)),
        )

    try:
        crm.update_record(
            MODULE_API_NAME,
            record_id,
            {
                "Executed_Task_ID": task_id,
                "Executed_At": clock.now_iso(),
                "Execution_Status": "Executed",
                "Execution_Error": None,
            },
        )
    except ExecutionError as exc:
        return _result(
            "failed",
            reason="post_execution_write_failed",
            record_id=record_id,
            executed_task_id=task_id,
            error=sanitize_error(str(exc)),
        )

    return _result(
        "executed",
        record_id=record_id,
        executed_task_id=task_id,
        execution_key=execution_key,
        attempts=attempts,
    )
