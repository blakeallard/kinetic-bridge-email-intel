"""BI1-T110 — tests for the Zoho CRM V8 inspection/setup utility.

Offline only: no test performs network I/O. The focus is configuration resolution,
credential hygiene, and the idempotency of the setup command's planning step.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import zoho_crm_admin as admin

CREDS = {
    "ZOHO_CRM_CLIENT_ID": "id",
    "ZOHO_CRM_CLIENT_SECRET": "secret",
    "ZOHO_CRM_REFRESH_TOKEN": "refresh",
}


class TestBaseUrlResolution(unittest.TestCase):
    def test_defaults_to_the_us_data_centre(self):
        api, accounts = admin.resolve_base_urls({})
        self.assertEqual(api, "https://www.zohoapis.com")
        self.assertEqual(accounts, "https://accounts.zoho.com")

    def test_dc_code_selects_the_matching_pair(self):
        api, accounts = admin.resolve_base_urls({"ZOHO_CRM_DC": "eu"})
        self.assertEqual(api, "https://www.zohoapis.eu")
        self.assertEqual(accounts, "https://accounts.zoho.eu")

    def test_dc_code_is_case_insensitive(self):
        self.assertEqual(admin.resolve_base_urls({"ZOHO_CRM_DC": "IN"})[0],
                         "https://www.zohoapis.in")

    def test_unknown_dc_is_rejected_with_the_valid_set(self):
        with self.assertRaises(admin.ConfigError) as ctx:
            admin.resolve_base_urls({"ZOHO_CRM_DC": "mars"})
        self.assertIn("mars", str(ctx.exception))
        self.assertIn("us", str(ctx.exception))

    def test_explicit_overrides_win_and_are_trimmed(self):
        api, accounts = admin.resolve_base_urls({
            "ZOHO_CRM_DC": "eu",
            "ZOHO_CRM_API_BASE_URL": "https://crm.internal/",
            "ZOHO_CRM_ACCOUNTS_BASE_URL": "https://auth.internal/",
        })
        self.assertEqual(api, "https://crm.internal")
        self.assertEqual(accounts, "https://auth.internal")

    def test_half_an_override_is_rejected(self):
        with self.assertRaises(admin.ConfigError):
            admin.resolve_base_urls({"ZOHO_CRM_API_BASE_URL": "https://crm.internal"})

    def test_every_dc_has_both_bases(self):
        self.assertEqual(set(admin.DC_API_BASE), set(admin.DC_ACCOUNTS_BASE))


class TestCredentialHandling(unittest.TestCase):
    def test_missing_variables_are_named(self):
        with self.assertRaises(admin.ConfigError) as ctx:
            admin.require_credentials({"ZOHO_CRM_CLIENT_ID": "id"})
        message = str(ctx.exception)
        self.assertIn("ZOHO_CRM_CLIENT_SECRET", message)
        self.assertIn("ZOHO_CRM_REFRESH_TOKEN", message)

    def test_error_never_echoes_a_credential_value(self):
        with self.assertRaises(admin.ConfigError) as ctx:
            admin.require_credentials({
                "ZOHO_CRM_CLIENT_ID": "super-secret-value",
                "ZOHO_CRM_CLIENT_SECRET": "",
                "ZOHO_CRM_REFRESH_TOKEN": "",
            })
        self.assertNotIn("super-secret-value", str(ctx.exception))

    def test_blank_is_treated_as_missing(self):
        with self.assertRaises(admin.ConfigError):
            admin.require_credentials({**CREDS, "ZOHO_CRM_REFRESH_TOKEN": "   "})

    def test_client_does_not_fetch_a_token_on_construction(self):
        client = admin.ZohoCrmClient("https://api", "https://accounts", CREDS)
        self.assertIsNone(client._access_token)


class TestFieldSummary(unittest.TestCase):
    def test_summary_keeps_the_facts_that_drive_decisions(self):
        summary = admin.summarize_fields({"fields": [{
            "api_name": "Execution_Key", "id": "1", "data_type": "text", "length": 255,
            "custom_field": True, "unique": {"case_sensitive": False},
            "system_mandatory": False, "pick_list_values": [],
        }]})
        self.assertEqual(summary[0]["api_name"], "Execution_Key")
        self.assertTrue(summary[0]["unique"])

    def test_absent_unique_block_is_false_not_truthy_empty_dict(self):
        summary = admin.summarize_fields({"fields": [{"api_name": "X", "unique": {}}]})
        self.assertFalse(summary[0]["unique"])

    def test_picklist_values_are_flattened(self):
        summary = admin.summarize_fields({"fields": [{
            "api_name": "Execution_Status", "data_type": "picklist",
            "pick_list_values": [{"actual_value": "Executed"}, {"actual_value": "Failed"}],
        }]})
        self.assertEqual(summary[0]["picklist_values"], ["Executed", "Failed"])

    def test_empty_response_is_handled(self):
        self.assertEqual(admin.summarize_fields({}), [])


class TestExecutionFieldDiff(unittest.TestCase):
    @staticmethod
    def live_fields(**overrides):
        fields = []
        for required in admin.REQUIRED_EXECUTION_FIELDS:
            name = required["api_name"]
            fields.append({
                "api_name": name,
                "data_type": overrides.get(f"{name}__type", required["data_type"]),
                "unique": overrides.get(f"{name}__unique", bool(required.get("unique"))),
            })
        return [f for f in fields if f["api_name"] not in overrides.get("drop", ())]

    def test_fully_provisioned_module_reports_nothing_to_do(self):
        diff = admin.diff_execution_fields(self.live_fields())
        self.assertEqual(diff["missing"], [])
        self.assertEqual(diff["mismatched"], [])
        self.assertEqual(len(diff["present"]), len(admin.REQUIRED_EXECUTION_FIELDS))

    def test_missing_fields_are_listed(self):
        diff = admin.diff_execution_fields(self.live_fields(drop=("Executed_At",)))
        self.assertEqual(diff["missing"], ["Executed_At"])

    def test_type_mismatch_is_reported_never_auto_corrected(self):
        diff = admin.diff_execution_fields(self.live_fields(Execution_Attempts__type="text"))
        self.assertTrue(any("Execution_Attempts" in m for m in diff["mismatched"]))
        self.assertEqual(diff["missing"], [])

    def test_lost_unique_constraint_on_the_execution_key_is_reported(self):
        diff = admin.diff_execution_fields(self.live_fields(Execution_Key__unique=False))
        self.assertTrue(any("unique" in m for m in diff["mismatched"]))

    def test_empty_module_reports_every_field_missing(self):
        diff = admin.diff_execution_fields([])
        self.assertEqual(len(diff["missing"]), len(admin.REQUIRED_EXECUTION_FIELDS))
        self.assertEqual(diff["present"], [])


class TestContractShape(unittest.TestCase):
    def test_the_execution_key_is_declared_unique(self):
        by_name = {f["api_name"]: f for f in admin.REQUIRED_EXECUTION_FIELDS}
        self.assertTrue(by_name["Execution_Key"].get("unique"))

    def test_execution_status_declares_every_state_the_executor_writes(self):
        by_name = {f["api_name"]: f for f in admin.REQUIRED_EXECUTION_FIELDS}
        values = {v["actual_value"] for v in by_name["Execution_Status"]["pick_list_values"]}
        self.assertEqual(values, {"Not Started", "In Progress", "Executed", "Failed", "Blocked"})

    def test_mutating_command_requires_an_explicit_apply_flag(self):
        args = admin.build_parser().parse_args(["setup-execution-metadata"])
        self.assertFalse(args.apply, "dry run must be the default")

    def test_inspection_commands_expose_no_apply_flag(self):
        args = admin.build_parser().parse_args(["inspect-fields"])
        self.assertFalse(hasattr(args, "apply"))


if __name__ == "__main__":
    unittest.main()
