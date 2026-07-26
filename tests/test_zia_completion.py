"""Static regression checks for the Zia completion / bounded-polling functions."""

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


class TestZiaCompletionCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "is_zia_analysis_complete.deluge").read_text()

    def test_has_the_expected_signature(self):
        self.assertTrue(
            self.source.startswith(
                "map is_zia_analysis_complete(string status_value, string response_value)"
            )
        )

    def test_terminal_failure_states_are_never_complete(self):
        self.assertIn(
            'failed_states = {"FAILED","FAILURE","ERROR","CANCELLED","CANCELED","TIMEOUT","TIMED_OUT"}',
            self.source,
        )
        self.assertIn("if(status_says_failed)", self.source)

    def test_requires_a_payload_to_be_complete(self):
        self.assertIn("status_says_done && has_payload", self.source)
        self.assertIn("status_unknown && has_payload", self.source)

    def test_returns_the_completion_contract(self):
        for field in ("complete", "failed", "has_payload", "status", "response"):
            self.assertIn(f'result.put("{field}"', self.source)


class TestZiaTimeoutFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "build_zia_timeout_fallback.deluge").read_text()

    def test_has_the_expected_signature(self):
        self.assertTrue(
            self.source.startswith("map build_zia_timeout_fallback(map trusted_request)")
        )

    def test_forces_manual_review_and_blank_targets(self):
        self.assertIn('recommendation.put("action","manual_review")', self.source)
        self.assertIn('recommendation.put("target_module","")', self.source)
        self.assertIn('recommendation.put("target_record_id","")', self.source)

    def test_records_the_timeout_conflict_and_insufficient_context(self):
        self.assertIn('safety.put("contains_insufficient_context",true)', self.source)
        self.assertIn('conflicts.add("zia_analysis_timeout")', self.source)

    def test_forces_human_approval(self):
        self.assertIn('safety.put("human_approval_required",true)', self.source)

    def test_restores_trusted_identity_from_the_request(self):
        self.assertIn('trusted_message = ifnull(trusted_request.get("message"),Map())', self.source)
        self.assertIn('trusted_message.get("message_id")', self.source)
        self.assertIn('trusted_message.get("idempotency_key")', self.source)

    def test_matches_the_validator_output_shape(self):
        for field in (
            "schema_version",
            "message_id",
            "idempotency_key",
            "intent",
            "opportunity_signals",
            "lifecycle_interpretation",
            "recommendation",
            "safety",
        ):
            self.assertIn(f'validated.put("{field}"', self.source)


if __name__ == "__main__":
    unittest.main()
