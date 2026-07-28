"""BI1-T110 — structural parity between the Python spec and the Deluge artifact.

`scripts/execution_policy.py` is the executable specification and carries the
behavioural tests. `scripts/execute_approved_recommendation.deluge` is what actually
gets deployed to Zoho, and cannot be executed here.

These tests do not prove the Deluge behaves identically — only Zoho can prove that.
They catch the drift that matters most: a policy check, a status value, a bound, or a
safety invariant present in one file and missing from the other.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from execution_policy import (
    ALLOWED_RECOMMENDATION_TYPE,
    ALLOWED_TARGET_MODULES,
    ERROR_MAX_LEN,
    FALLBACK_TASK_OWNER_ID,
    MAX_EXECUTION_ATTEMPTS,
    POLICY_CHECKS,
    REVIEW_NOTES_MAX_LEN,
    TASK_DESCRIPTION_MAX_LEN,
    TASK_DUE_DAYS,
    TASK_SUBJECT_MAX_LEN,
    evaluate_policy,
)

DELUGE = (REPO / "scripts" / "execute_approved_recommendation.deluge").read_text()

CODE = "\n".join(
    line for line in DELUGE.splitlines() if not line.lstrip().startswith("//")
)


class TestPolicyCheckParity(unittest.TestCase):
    def test_every_python_violation_exists_in_the_deluge(self):
        missing = [v for v in POLICY_CHECKS if f'"{v}"' not in CODE]
        self.assertEqual(missing, [], f"policy checks missing from the Deluge: {missing}")

    def test_deluge_defines_no_violation_the_python_gate_lacks(self):
        in_deluge = set(re.findall(r'violations\.add\("([a-z_]+)"\)', CODE))
        self.assertEqual(
            sorted(in_deluge - set(POLICY_CHECKS)), [],
            "the Deluge blocks on a check the Python specification does not",
        )

    def test_the_gate_covers_all_ten_contract_preconditions(self):
        self.assertEqual(len(POLICY_CHECKS), 10, POLICY_CHECKS)

    def test_every_declared_check_is_actually_reachable(self):
        """POLICY_CHECKS must describe the gate, not aspire to it."""
        tripped = set(evaluate_policy({
            "Execution_Status": "Blocked",
            "Executed_Task_ID": "1",
            "Execution_Attempts": MAX_EXECUTION_ATTEMPTS,
        }))
        self.assertEqual(tripped, set(POLICY_CHECKS))


class TestConstantParity(unittest.TestCase):
    def test_execution_key_format_matches(self):
        self.assertIn('"ai-execution:" + record_id + ":" + allowed_recommendation_type', CODE)
        self.assertIn(f'allowed_recommendation_type = "{ALLOWED_RECOMMENDATION_TYPE}"', CODE)

    def test_attempt_limit_matches(self):
        self.assertIn(f"max_execution_attempts = {MAX_EXECUTION_ATTEMPTS}", CODE)

    def test_target_module_allow_list_matches(self):
        for module in ALLOWED_TARGET_MODULES:
            self.assertIn(f'target_module != "{module}"', CODE)

    def test_deals_is_not_in_the_deluge_allow_list(self):
        self.assertNotIn('"Deals"', CODE)

    def test_bounds_match(self):
        for bound in (TASK_SUBJECT_MAX_LEN, TASK_DESCRIPTION_MAX_LEN,
                      REVIEW_NOTES_MAX_LEN, ERROR_MAX_LEN):
            self.assertIn(f"> {bound}", CODE, f"missing a {bound}-char bound")

    def test_execution_status_values_match(self):
        for status in ("Not Started", "In Progress", "Executed", "Failed", "Blocked"):
            self.assertIn(f'"{status}"', CODE)

    def test_task_due_days_match(self):
        self.assertIn(f"task_due_days = {TASK_DUE_DAYS}", CODE)

    def test_fallback_task_owner_matches(self):
        self.assertIn(f'fallback_task_owner_id = "{FALLBACK_TASK_OWNER_ID}"', CODE)


class TestTaskAssignmentParity(unittest.TestCase):
    """The Task must land on the approver, be readable, and carry a due date."""

    def test_the_deluge_owns_the_task_to_the_approver(self):
        self.assertIn('reviewed_by_id = ifnull(reviewed_by_raw.get("id")', CODE)
        self.assertIn("task_owner_id = reviewed_by_id", CODE)
        self.assertIn('task.put("Owner",task_owner)', CODE)

    def test_the_deluge_falls_back_rather_than_leaving_the_owner_unset(self):
        self.assertIn('if(task_owner_id == "")', CODE)
        self.assertIn("task_owner_id = fallback_task_owner_id", CODE)

    def test_the_owner_is_an_id_object_not_a_bare_string(self):
        self.assertIn('task_owner.put("id",task_owner_id)', CODE)
        self.assertNotIn('task.put("Owner",task_owner_id)', CODE)

    def test_the_deluge_sets_a_due_date(self):
        self.assertIn(
            'task.put("Due_Date",zoho.currentdate.addDay(task_due_days)'
            '.toString("yyyy-MM-dd"))',
            CODE,
        )

    def test_the_subject_is_readable_not_a_raw_message_id(self):
        self.assertIn('subject = "Follow up: " + subject_topic', CODE)
        self.assertNotIn('"AI Recommendation: follow up on email " + message_id', CODE)

    def test_the_subject_never_reads_untrusted_model_output(self):
        self.assertIn('ai_category = ifnull(record.get("AI_Category")', CODE)
        for untrusted in ("AI_Summary", "AI_Rationale", "Raw_Zia_Response"):
            self.assertNotIn(untrusted, CODE)

    def test_the_subject_names_the_target_record_and_survives_a_failed_lookup(self):
        """The display name is read from the CRM record, not from model output,
        so it stays inside the trusted-scalars rule. A lookup failure must never
        abort execution — it degrades to the sender address.
        """
        self.assertIn(
            "target_record = zoho.crm.getRecordById(target_module,target_record_id.toLong())",
            CODE,
        )
        self.assertIn('subject_who = ifnull(target_record.get("Full_Name"),"").toString().trim()', CODE)
        self.assertIn('subject_who = ifnull(target_record.get("Account_Name"),"").toString().trim()', CODE)
        self.assertIn("catch (subject_lookup_error)", CODE)
        self.assertIn("subject_who = sender_email;", CODE)

    def test_the_target_lookup_happens_after_the_claim(self):
        """A pre-claim lookup would burn an API call for a caller that loses the
        race; the claim is what authorizes any further work.
        """
        claim = CODE.index("If-Unmodified-Since")
        lookup = CODE.index("target_record = zoho.crm.getRecordById")
        self.assertLess(claim, lookup)


class TestSafetyInvariants(unittest.TestCase):
    def test_deluge_never_reads_the_raw_model_output(self):
        for field in ("Raw_Zia_Response", "Validated_Analysis_JSON"):
            self.assertNotIn(f'record.get("{field}")', CODE,
                             f"{field} must never be read by the executor")

    def test_deluge_creates_only_tasks_and_meetings(self):
        """The executor's blast radius is deliberately two modules and no more.

        Events joined Tasks on 2026-07-26 so a "Meeting Request" arrives with the
        participants, related record and the customer's stated preference already
        filled in. Both are internal activity records: neither notifies the
        customer, and an Event only reaches anyone when a human opens it and
        sends the invite. Adding any further module here is a policy decision,
        not a refactor — which is why this asserts equality rather than
        membership.
        """
        created = set(re.findall(r'zoho\.crm\.createRecord\("(\w+)"', CODE))
        self.assertEqual(created, {"Tasks", "Events"})

    def test_the_meeting_is_created_only_for_a_meeting_request(self):
        self.assertIn('if(ai_category == "Meeting Request")', CODE)

    def test_the_meeting_never_proposes_a_time_as_confirmed(self):
        """The AI does not pick meeting times. The slot is a placeholder the
        human corrects, and the Description says so before anything else.

        The marker string is defined once and reused both as the Description
        opener and as the dedup fingerprint, so the two can never drift apart.
        """
        self.assertIn(
            'placeholder_marker = "Proposed time only - confirm with the customer'
            ' before sending the invite."',
            CODE,
        )
        self.assertIn("event_description = placeholder_marker", CODE)
        self.assertIn("Customer's stated preference, from the source email:", CODE)

    def test_a_failed_meeting_create_never_blocks_the_task(self):
        """The Task is the claimed critical path; the Event is best-effort.
        A meeting failure must not strand a claimed recommendation.
        """
        self.assertIn("catch (event_create_error)", CODE)
        event_create = CODE.index('zoho.crm.createRecord("Events",event)')
        task_create = CODE.index('zoho.crm.createRecord("Tasks",task)')
        self.assertLess(event_create, task_create)

    def test_the_meeting_is_covered_by_the_same_claim_as_the_task(self):
        """No Executed_Event_ID field exists, so re-run safety comes from the
        claim rather than a stored id: a second caller never reaches either
        create. Adding a second Event on replay would be the failure mode.
        """
        claim = CODE.index("If-Unmodified-Since")
        event_create = CODE.index('zoho.crm.createRecord("Events",event)')
        self.assertLess(claim, event_create)

    def test_deluge_updates_only_the_recommendation_and_events_modules(self):
        """Events joined the update allowlist on 2026-07-26 for meeting dedup:
        a second Meeting Request on the same record refreshes the existing
        placeholder Event instead of creating a sibling. Equality, not
        membership — a third updatable module is a policy decision.
        """
        updated = set(re.findall(r'zoho\.crm\.updateRecord\((\w+)', CODE))
        self.assertEqual(updated, {"module_api_name", "events_module"})
        self.assertIn('events_module = "Events"', CODE)

    def test_deluge_performs_no_forbidden_action(self):
        for forbidden in ("sendmail", "Closed Won", "Quotes", "postUrl",
                          "deleteRecord", "convertLead"):
            self.assertNotIn(forbidden, CODE, f"forbidden operation present: {forbidden}")

    def test_the_only_raw_http_call_is_the_conditional_claim(self):
        """invokeurl bypasses the Deluge CRM wrapper, so its use must be pinned."""
        self.assertEqual(CODE.count("invokeurl"), 1)
        self.assertIn('headers : claim_headers', CODE)
        self.assertIn('type : PUT', CODE)
        self.assertIn('url : "https://www.zohoapis.com/crm/v8/" + module_api_name', CODE)


class TestMeetingDedup(unittest.TestCase):
    """A repeat Meeting Request on the same record must update the existing
    placeholder Event, not create a sibling. The fingerprint is the marker
    sentence the executor itself writes into every placeholder Description.
    """

    def test_the_executor_searches_the_target_record_for_a_placeholder_event(self):
        self.assertIn(
            "related_events = zoho.crm.getRelatedRecords"
            "(events_module,target_module,target_record_id.toLong())",
            CODE,
        )
        self.assertIn("rel_description.contains(placeholder_marker)", CODE)

    def test_a_found_placeholder_is_updated_not_duplicated(self):
        self.assertIn('if(existing_event_id != "")', CODE)
        self.assertIn('event_update.put("Description",updated_description)', CODE)
        self.assertIn("new_event_id = existing_event_id", CODE)
        self.assertIn('event_action = "updated"', CODE)

    def test_the_update_appends_the_new_request_to_the_existing_description(self):
        self.assertIn("updated_description = existing_event_description", CODE)
        self.assertIn("Follow-up from a later email in this thread:", CODE)
        self.assertIn("updated_description + new_line + review_notes", CODE)

    def test_the_update_never_moves_the_time_owner_or_participants(self):
        """The human owns the slot. A later email must not silently reschedule
        a meeting someone may have already confirmed.
        """
        for field in ("Start_DateTime", "End_DateTime", "Owner",
                      "Participants", "Event_Title", "Who_Id", "What_Id"):
            self.assertNotIn(f'event_update.put("{field}"', CODE)

    def test_a_failed_lookup_degrades_to_creating_a_new_event(self):
        """Dedup is best-effort: a lookup failure falls through to the create
        path rather than dropping the meeting. Worst case is the old behavior
        (a duplicate), never a lost meeting.
        """
        self.assertIn("catch (event_lookup_error)", CODE)
        self.assertIn('existing_event_id = ""', CODE)

    def test_a_failed_event_update_never_blocks_the_task(self):
        self.assertIn("catch (event_update_error)", CODE)
        self.assertLess(
            CODE.index("catch (event_update_error)"),
            CODE.index('zoho.crm.createRecord("Tasks",task)'),
        )

    def test_the_event_lookup_happens_after_the_claim(self):
        self.assertLess(
            CODE.index("If-Unmodified-Since"),
            CODE.index("zoho.crm.getRelatedRecords"),
        )

    def test_the_result_reports_whether_the_event_was_created_or_updated(self):
        self.assertIn('result.put("event_action",event_action)', CODE)


class TestAtomicClaim(unittest.TestCase):
    """The claim must be conditional. An unconditional update double-executes."""

    def test_claim_sends_the_if_unmodified_since_precondition(self):
        self.assertIn('claim_headers.put("If-Unmodified-Since",modified_time)', CODE)

    def test_claim_declares_json_content_type(self):
        self.assertIn('claim_headers.put("Content-Type","application/json")', CODE)

    def test_claim_reads_modified_time_from_the_refetched_record(self):
        self.assertIn('modified_time = ifnull(record.get("Modified_Time")', CODE)

    def test_claim_refuses_when_modified_time_is_unavailable(self):
        self.assertIn('"modified_time_unavailable"', CODE)

    def test_a_lost_race_is_a_duplicate_not_a_failure(self):
        self.assertIn('"claim_lost_race"', CODE)

    def test_the_lost_race_check_uses_zohos_documented_error_code(self):
        """Zoho answers a failed If-Unmodified-Since with HTTP 412 ALREADY_MODIFIED."""
        self.assertIn('claim_code == "ALREADY_MODIFIED"', CODE)

    def test_superseded_guesses_at_the_error_code_are_gone(self):
        for wrong in ("RECORD_MODIFIED", "PRECONDITION_FAILED"):
            self.assertNotIn(wrong, CODE, f"{wrong} is not a Zoho error code")

    def test_the_claim_does_not_rely_on_scanning_response_text_for_412(self):
        self.assertNotIn('contains("412")', CODE)
        self.assertNotIn("contains('412')", CODE)

    def test_top_level_claim_response_code_and_status_are_parsed(self):
        self.assertIn('claim_code = ifnull(claim_response.get("code")', CODE)
        self.assertIn('claim_status = ifnull(claim_response.get("status")', CODE)

    def test_row_level_claim_response_code_and_status_are_still_parsed(self):
        self.assertIn('row_status = ifnull(claim_row.get("status")', CODE)
        self.assertIn('row_code = ifnull(claim_row.get("code")', CODE)

    def test_row_level_values_override_top_level_when_present(self):
        self.assertIn('if(row_status != "")', CODE)
        self.assertIn('if(row_code != "")', CODE)

    def test_an_unexpected_claim_error_fails_and_reports_the_parsed_code(self):
        self.assertIn('result.put("reason","claim_failed")', CODE)
        self.assertIn('result.put("claim_code",claim_code)', CODE)
        self.assertIn('result.put("claim_message",claim_message)', CODE)
        self.assertIn('result.put("claim_details",claim_details)', CODE)

    def test_lost_race_is_handled_before_any_task_creation(self):
        self.assertLess(
            CODE.index('claim_code == "ALREADY_MODIFIED"'),
            CODE.index('zoho.crm.createRecord("Tasks"'),
            "the lost-race branch must return before a Task can be created",
        )


class TestPostClaimFailureIsTerminal(unittest.TestCase):
    """Finding 2: a POST-CLAIM failure is terminal and needs a human."""

    def test_the_failure_path_never_clears_the_execution_key(self):
        failure_block = CODE[CODE.index('failed_update = Map()'):
                             CODE.index('result.put("status","failed")')]
        self.assertNotIn("Execution_Key", failure_block)

    def test_nothing_resets_a_record_to_not_started(self):
        self.assertNotIn('put("Execution_Status","Not Started")', CODE)

    def test_a_populated_execution_key_alone_marks_a_record_claimed(self):
        self.assertIn('if(existing_execution_key != "")', CODE)
        self.assertIn("already_claimed = true", CODE)

    def test_the_claim_does_not_use_the_unconditional_update_wrapper(self):
        claim_block = CODE[CODE.index("new_attempts = execution_attempts + 1"):
                           CODE.index("if(review_notes.length()")]
        self.assertNotIn("zoho.crm.updateRecord", claim_block,
                         "the claim must not fall back to an unconditional update")

    def test_deluge_does_not_move_the_blueprint_status_field(self):
        for update_map in ("blocked_update", "claim_update", "failed_update", "success_update"):
            self.assertNotIn(f'{update_map}.put("Status"', CODE)

    def test_duplicate_guard_precedes_the_policy_gate(self):
        self.assertLess(
            CODE.index('result.put("status","duplicate")'),
            CODE.index("violations = List()"),
            "the already-claimed check must run before the policy gate",
        )

    def test_claim_precedes_task_creation(self):
        self.assertLess(
            CODE.index('claim_fields.put("Execution_Key"'),
            CODE.index('zoho.crm.createRecord("Tasks"'),
            "the execution must be claimed before a Task is created",
        )

    def test_failure_path_does_not_reset_the_attempt_count(self):
        failure_block = CODE[CODE.index('failed_update = Map()'):CODE.index('result.put("status","failed")')]
        self.assertNotIn("Execution_Attempts", failure_block)


class TestTaskLookupStructure(unittest.TestCase):
    """Who_Id/What_Id are jsonobject lookups — the Deluge must pass {"id": ...}.

    A bare id string produces "expected jsonobject but received string" and was the
    confirmed cause of the failed live Lead Task creation. Verified against the live
    Tasks field metadata (both fields json_type=jsonobject) and Zoho Kaizen #36.
    """

    def test_deluge_wraps_the_target_id_in_an_id_object(self):
        self.assertIn('target_lookup = Map()', CODE)
        self.assertIn('target_lookup.put("id",target_record_id)', CODE)

    def test_deluge_never_assigns_a_bare_string_to_a_lookup_field(self):
        self.assertNotIn('task.put("Who_Id",target_record_id)', CODE)
        self.assertNotIn('task.put("What_Id",target_record_id)', CODE)

    def test_deluge_links_contacts_via_who_id_and_others_via_what_id(self):
        self.assertIn('task.put("Who_Id",target_lookup)', CODE)
        self.assertIn('task.put("What_Id",target_lookup)', CODE)

    def test_deluge_sets_se_module_for_every_route(self):
        self.assertEqual(CODE.count('task.put("$se_module",target_module)'), 1)

    def test_deluge_reads_the_durable_key_from_ingestion_key_not_the_name_title(self):
        self.assertIn('idempotency_key = ifnull(record.get("Ingestion_Key")', CODE)
        self.assertNotIn('idempotency_key = ifnull(record.get("Name")', CODE)


class TestTaskDescriptionNewlines(unittest.TestCase):
    """The Task Description must render real line breaks in CRM.

    Deluge does not interpret a "\\n" string literal as a newline — it emits a
    literal backslash-n. The Python spec joins the same lines with a real newline,
    so the Deluge must build the Description with hexToText("0A") to match.
    """

    def test_deluge_uses_a_real_newline_character(self):
        self.assertIn('new_line = hexToText("0A")', CODE)

    def test_no_literal_backslash_n_survives_in_the_deluge(self):
        self.assertNotIn("\\n", CODE, "a literal backslash-n would print as text in CRM")

    def test_the_description_is_assembled_from_the_newline_variable(self):
        self.assertIn(
            'description = description + new_line + "Idempotency key: " + idempotency_key',
            CODE,
        )
        self.assertIn(
            '"Reviewer notes:" + new_line + review_notes',
            CODE,
        )

    def test_the_python_spec_joins_description_lines_with_a_real_newline(self):
        spec = (REPO / "scripts" / "execution_policy.py").read_text()
        self.assertIn('"\\n".join(description_lines)', spec)


if __name__ == "__main__":
    unittest.main()
