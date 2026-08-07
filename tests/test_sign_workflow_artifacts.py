"""Static regression checks for the Zoho Sign + WorkDrive filing functions."""

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


class TestSendQuoteForSignature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "qts" / "send_quote_for_signature.deluge").read_text()

    def test_an_existing_sign_request_id_short_circuits_before_any_external_call(self):
        guard_index = self.source.index('result.put("reason","sign_request_already_exists")')
        first_call_index = self.source.index("invokeurl")
        self.assertLess(guard_index, first_call_index)
        self.assertIn('already_sent = ifnull(existing_sign_request_id,"").trim()', self.source)
        self.assertIn('if(already_sent != "")', self.source)

    def test_a_blank_customer_signer_email_aborts_loudly(self):
        self.assertIn('result.put("reason","customer_signer_email_missing")', self.source)
        self.assertIn('if(safe_customer_email == "" || !safe_customer_email.contains("@"))', self.source)

    def test_the_merge_uses_the_same_live_template_as_the_document_executor(self):
        executor = (SCRIPTS / "generate_and_file_quote_document.deluge").read_text()
        for source in (self.source, executor):
            self.assertIn('template_document_id = "h5zhu2051759ecefd4148816cf61ad65a9cbc"', source)

    def test_the_customer_signs_first_and_signing_is_sequential(self):
        self.assertIn('customer_action.put("signing_order",1)', self.source)
        self.assertIn('internal_action.put("signing_order",2)', self.source)
        self.assertIn('request_inner.put("is_sequential",true)', self.source)

    def test_the_request_name_carries_the_quote_subject_convention(self):
        self.assertIn(
            'request_inner.put("request_name","Kinetic Bridge Quote " + safe_quote_number)',
            self.source,
        )

    def test_the_sign_request_id_is_written_back_for_the_widget_poll(self):
        self.assertIn('writeback.put("Sign_Request_ID",sign_request_id)', self.source)

    def test_a_failed_writeback_never_unsends_the_request(self):
        self.assertIn("catch (writeback_error)", self.source)
        self.assertIn('result.put("reason","sign_request_id_writeback_failed")', self.source)

    def test_workdrive_filing_is_best_effort_and_gated_on_a_folder_id(self):
        self.assertIn('if(safe_quotes_folder != "")', self.source)
        self.assertIn("catch (upload_error)", self.source)

    def test_the_send_path_never_reads_model_authored_fields(self):
        for forbidden in ("AI_Summary", "AI_Rationale", "Raw_Zia_Response"):
            self.assertNotIn(forbidden, self.source)


class TestEnsureWorkdriveFolderPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "ensure_workdrive_folder_path.deluge").read_text()

    def test_the_helper_is_create_only(self):
        self.assertNotIn("DELETE", self.source)
        self.assertNotIn("trash", self.source)
        self.assertNotIn("PATCH", self.source)

    def test_the_mapping_table_is_consulted_before_any_workdrive_call(self):
        map_read_index = self.source.index("zoho.creator.getRecords")
        first_workdrive_index = self.source.index("workdrive/api")
        self.assertLess(map_read_index, first_workdrive_index)

    def test_a_map_hit_returns_without_touching_workdrive(self):
        self.assertIn('result.put("map_action","hit")', self.source)
        hit_index = self.source.index('result.put("map_action","hit")')
        self.assertIn("return result", self.source[hit_index:hit_index + 200])

    def test_folder_names_are_sanitized_for_filesystem_safety(self):
        self.assertEqual(self.source.count('replaceAll("[/\\\\\\\\:*?\\"<>|]"," ",false)'), 2)

    def test_the_deal_folder_carries_the_date_prefix(self):
        self.assertIn('deal_folder_name = safe_deal_date + " " + clean_deal', self.source)

    def test_all_four_subfolders_are_ensured(self):
        for name in ("Quotes", "Signed", "Correspondence", "Attachments"):
            self.assertIn(f'subfolder_names.add("{name}")', self.source)

    def test_a_failed_map_write_degrades_instead_of_failing_the_run(self):
        self.assertIn("catch (map_write_error)", self.source)
        self.assertIn('result.put("map_action","write_failed")', self.source)
        write_failed_index = self.source.index('result.put("map_action","write_failed")')
        self.assertIn('result.put("status","ok")', self.source[write_failed_index:])

    def test_the_root_folder_id_is_a_parameter_not_a_hardcoded_value(self):
        self.assertIn("string accounts_root_folder_id", self.source)
        self.assertIn('result.put("reason","accounts_root_folder_id_missing")', self.source)


class TestHandleSignCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "qts" / "handle_sign_completion.deluge").read_text()

    def test_only_completed_events_are_processed(self):
        self.assertIn('if(safe_status != "completed")', self.source)
        self.assertIn('result.put("reason","not_a_completion_event:" + safe_status)', self.source)

    def test_a_duplicate_webhook_event_is_a_noop(self):
        self.assertIn('completion_marker = "Sign completed: "', self.source)
        self.assertIn("existing_description.contains(completion_marker + safe_sign_id)", self.source)
        self.assertIn('result.put("reason","completion_already_processed")', self.source)

    def test_the_idempotency_check_happens_before_the_download(self):
        marker_index = self.source.index('result.put("reason","completion_already_processed")')
        download_index = self.source.index('"/pdf"')
        self.assertLess(marker_index, download_index)

    def test_the_quote_is_found_by_the_subject_convention(self):
        self.assertIn(
            'zoho.crm.searchRecords("Quotes","(Subject:equals:" + quote_subject + ")")',
            self.source,
        )

    def test_the_creator_backreference_comes_from_the_description_stamp(self):
        self.assertIn('request_ref_marker = "QTS Quote_Request ID: "', self.source)
        self.assertNotIn("zoho.creator.getRecords", self.source)

    def test_workdrive_and_attach_failures_never_block_the_marker_or_status(self):
        self.assertIn("catch (upload_error)", self.source)
        self.assertIn("catch (attach_error)", self.source)
        self.assertIn("catch (creator_update_error)", self.source)

    def test_the_creator_status_becomes_signed(self):
        self.assertIn('status_update.put("Status","Signed")', self.source)

    def test_the_completion_never_reads_model_authored_fields(self):
        for forbidden in ("AI_Summary", "AI_Rationale", "Raw_Zia_Response"):
            self.assertNotIn(forbidden, self.source)


class TestExecutorStaysUntouched(unittest.TestCase):
    def test_the_document_executor_knows_nothing_about_sign_or_workdrive(self):
        executor = (SCRIPTS / "generate_and_file_quote_document.deluge").read_text()
        for forbidden in ("sign.zoho.com", "Sign_Request_ID", "workdrive", "upload.zoho.com"):
            self.assertNotIn(forbidden, executor)


if __name__ == "__main__":
    unittest.main()
