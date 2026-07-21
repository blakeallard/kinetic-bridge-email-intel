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


if __name__ == "__main__":
    unittest.main()
