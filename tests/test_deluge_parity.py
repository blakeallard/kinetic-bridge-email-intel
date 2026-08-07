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
    MAX_EXECUTION_ATTEMPTS,
    POLICY_CHECKS,
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

    def test_execution_status_values_match(self):
        # Failed is no longer written by the executor (Task path removed); claim /
        # block / execute still use these four.
        for status in ("Not Started", "In Progress", "Executed", "Blocked"):
            self.assertIn(f'"{status}"', CODE)


class TestNoTaskOrEventCreation(unittest.TestCase):
    """Approve marks the recommendation Executed; CRM people/company materialize
    upstream (materialize_pending_lead). This function must not create Tasks or Events.
    """

    def test_deluge_creates_no_crm_records(self):
        created = set(re.findall(r'zoho\.crm\.createRecord\("(\w+)"', CODE))
        self.assertEqual(created, set())

    def test_deluge_never_mentions_task_or_event_create_payloads(self):
        for fragment in (
            'createRecord("Tasks"',
            'createRecord("Events"',
            'task.put(',
            'event.put(',
            "fallback_task_owner_id",
            "task_due_days",
        ):
            self.assertNotIn(fragment, CODE, fragment)

    def test_result_reports_task_created_no(self):
        self.assertIn('result.put("task_created","no")', CODE)
        self.assertIn('result.put("executed_task_id","")', CODE)

    def test_success_path_marks_executed_without_executed_task_id(self):
        self.assertIn('success_update.put("Execution_Status","Executed")', CODE)
        self.assertNotIn('success_update.put("Executed_Task_ID"', CODE)


class TestSafetyInvariants(unittest.TestCase):
    def test_deluge_never_reads_the_raw_model_output(self):
        for field in ("Raw_Zia_Response", "Validated_Analysis_JSON"):
            self.assertNotIn(f'record.get("{field}")', CODE,
                             f"{field} must never be read by the executor")

    def test_deluge_updates_only_the_recommendation_module(self):
        updated = set(re.findall(r'zoho\.crm\.updateRecord\((\w+)', CODE))
        self.assertEqual(updated, {"module_api_name"})

    def test_deluge_performs_no_forbidden_action(self):
        for forbidden in ("sendmail", "Closed Won", "Quotes", "postUrl",
                          "deleteRecord", "convertLead"):
            self.assertNotIn(forbidden, CODE, f"forbidden operation present: {forbidden}")

    def test_the_only_raw_http_call_is_the_conditional_claim(self):
        self.assertEqual(CODE.count("invokeurl"), 1)
        self.assertIn('headers : claim_headers', CODE)
        self.assertIn('type : PUT', CODE)
        self.assertIn('url : "https://www.zohoapis.com/crm/v8/" + module_api_name', CODE)


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

    def test_lost_race_is_handled_before_success_write(self):
        self.assertLess(
            CODE.index('claim_code == "ALREADY_MODIFIED"'),
            CODE.index('success_update.put("Execution_Status","Executed")'),
            "the lost-race branch must return before Executed is written",
        )


class TestPostClaimFailureIsTerminal(unittest.TestCase):
    """A POST-CLAIM bookkeeping failure is terminal and needs a human."""

    def test_nothing_resets_a_record_to_not_started(self):
        self.assertNotIn('put("Execution_Status","Not Started")', CODE)

    def test_a_populated_execution_key_alone_marks_a_record_claimed(self):
        self.assertIn('if(existing_execution_key != "")', CODE)
        self.assertIn("already_claimed = true", CODE)

    def test_the_claim_does_not_use_the_unconditional_update_wrapper(self):
        claim_block = CODE[CODE.index("new_attempts = execution_attempts + 1"):
                           CODE.index("if(claim_status != \"success\")")]
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

    def test_claim_precedes_executed_write(self):
        self.assertLess(
            CODE.index('claim_fields.put("Execution_Key"'),
            CODE.index('success_update.put("Execution_Status","Executed")'),
            "the execution must be claimed before Executed is written",
        )

    def test_post_claim_write_failure_is_named(self):
        self.assertIn('"post_execution_write_failed"', CODE)


if __name__ == "__main__":
    unittest.main()
