"""Static regression checks for source-controlled Zoho ingestion functions."""

from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


class TestLeadEmailLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "fetch_lead_by_email.deluge").read_text()

    def test_uses_the_normalized_sender_email_as_the_search_criterion(self):
        self.assertIn('safe_email = ifnull(email,"").trim().toLowerCase()', self.source)
        self.assertIn('"(Email:equals:" + safe_email + ")"', self.source)

    def test_searches_leads_using_the_named_flow_connection(self):
        self.assertIn('zoho.crm.searchRecords("Leads"', self.source)
        self.assertIn('"zoho_crm_to_zoho_flow"', self.source)

    def test_includes_approved_and_converted_records(self):
        self.assertIn('search_options.put("converted","both")', self.source)
        self.assertIn('search_options.put("approved","both")', self.source)

    def test_verifies_exact_email_before_returning_the_id(self):
        self.assertIn('record_email == safe_email', self.source)
        self.assertIn('lead.get("id")', self.source)


class TestCrmSnapshotLeadField(unittest.TestCase):
    def test_uses_the_live_lead_status_api_name(self):
        source = (SCRIPTS / "build_crm_snapshot.deluge").read_text()
        self.assertIn('lead_record.get("Lead_Status")', source)
        self.assertNotIn('lead_record.get("Status")', source)


class TestRecommendationDuplicateLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "check_ai_recommendation_exists.deluge").read_text()

    def test_searches_the_live_module_by_the_name_api_field(self):
        self.assertIn('criteria = "(Name:equals:" + idempotency_key + ")"', self.source)
        self.assertIn('zoho.crm.searchRecords("AI_Recommendations",criteria)', self.source)

    def test_reads_the_first_existing_record(self):
        self.assertIn("existing_record = records.get(0)", self.source)
        self.assertIn('existing_record.get("Status")', self.source)

    def test_returns_the_duplicate_guard_contract(self):
        for field in ("exists", "record_id", "status", "idempotency_key"):
            self.assertIn(f'result.put("{field}"', self.source)


class TestLeadOpenTaskLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "fetch_open_tasks_for_lead.deluge").read_text()

    def test_returns_an_empty_list_for_a_blank_lead_id(self):
        self.assertIn('lead_id == null || lead_id.trim() == ""', self.source)
        self.assertIn("return open_tasks", self.source)

    def test_fetches_tasks_related_to_the_lead(self):
        self.assertIn(
            'zoho.crm.getRelatedRecords("Tasks","Leads",lead_id.toLong(),1,200)',
            self.source,
        )

    def test_excludes_completed_tasks(self):
        self.assertIn('task_status != "Completed"', self.source)

    def test_returns_the_snapshot_task_contract(self):
        for field in ("id", "subject", "status", "due_date"):
            self.assertIn(f'task_item.put("{field}"', self.source)


if __name__ == "__main__":
    unittest.main()
