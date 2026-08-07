"""Static regression checks for the QTS quote document generation functions."""

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
SAMPLES = REPO / "samples"


class TestQuoteMergePayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "build_quote_merge_payload.deluge").read_text()
        cls.sample = json.loads((SAMPLES / "quote_merge_sample.json").read_text())

    def test_reads_the_deal_and_its_products_not_a_crm_quote(self):
        self.assertIn('zoho.crm.getRecordById("Deals",safe_deal_id.toLong())', self.source)
        self.assertIn('deal.get("Associated_Products")', self.source)
        self.assertNotIn('"Quotes"', self.source)

    def test_quote_identity_comes_from_the_creator_trigger_not_the_model(self):
        self.assertIn(
            "map build_quote_merge_payload(string deal_id, string contact_id,"
            " string quote_number, string quote_date, string valid_until,"
            " string payment_terms_days)",
            self.source,
        )

    def test_every_sample_key_is_written_to_the_merge_map(self):
        for key in self.sample:
            self.assertRegex(self.source, rf'(merge|money_fields)\.put\("{key}"')

    def test_payment_terms_come_from_the_days_argument(self):
        self.assertIn('payment_terms_text = "Payment Terms: Net " + payment_days + "."', self.source)
        self.assertIn('merge.put("payment_terms",payment_terms_text)', self.source)
        self.assertIn("payment_days = 30", self.source)

    def test_money_amounts_gain_thousands_separators(self):
        self.assertEqual(self.source.count('for each grouping_pass in {1,2,3,4}'), 2)
        self.assertIn('amount_grouped = "," + amount_int.subString(amount_int.length() - 3) + amount_grouped', self.source)

    def test_line_items_are_also_published_as_table_rows(self):
        self.assertIn('merge.put("line_items",line_items)', self.source)
        for field in ("name", "qty", "unit_price", "total"):
            self.assertIn(f'line_row.put("line_items.{field}"', self.source)

    def test_line_items_render_as_a_single_newline_joined_block(self):
        self.assertIn('newline = hexToText("0A")', self.source)
        self.assertIn('merge.put("line_items_block",line_items_block)', self.source)

    def test_the_block_carries_name_quantity_and_prices(self):
        self.assertIn('line_count + ". " + product_name', self.source)
        self.assertIn(
            '"      Qty " + quantity_text + "  x  $" + line_money.get("list_price")'
            ' + "   =   $" + line_money.get("total")',
            self.source,
        )

    def test_zero_quantity_lines_are_dropped(self):
        self.assertIn('quantity = ifnull(item.get("Quantity"),0).toDecimal()', self.source)
        self.assertIn("if(quantity > 0)", self.source)

    def test_totals_are_computed_from_lines_with_the_deal_amount_preferred(self):
        self.assertIn("sub_total_amount = sub_total_amount + line_total_amount", self.source)
        self.assertIn('grand_total_amount = ifnull(deal.get("Amount"),0).toDecimal()', self.source)
        self.assertIn("grand_total_amount = sub_total_amount", self.source)

    def test_blank_line_total_is_qty_times_unit_price(self):
        self.assertIn('unit_price_amount = ifnull(item.get("List_Price"),0).toDecimal()', self.source)
        self.assertIn('line_total_amount = ifnull(item.get("Total"),0).toDecimal()', self.source)
        self.assertIn("if(line_total_amount == 0 && unit_price_amount != 0)", self.source)
        self.assertIn("line_total_amount = (quantity * unit_price_amount).round(2)", self.source)
        # Writer keys live on line_row; internal format map keeps short names so
        # "$" + line_money.get("total") cannot become the literal "$null".
        self.assertIn('line_money.put("total",line_total_amount)', self.source)
        self.assertNotIn('line_money.put("line_items.total"', self.source)
        self.assertIn('line_row.put("line_items.total","$" + line_money.get("total"))', self.source)

    def test_money_values_are_rounded_to_two_decimals_and_padded(self):
        self.assertIn(".toDecimal().round(2)", self.source)
        self.assertIn('amount_text = amount_text + ".00"', self.source)
        self.assertIn('amount_text = amount_text + "0"', self.source)

    def test_never_reads_model_authored_fields(self):
        for field in ("AI_Summary", "AI_Rationale", "Raw_Zia_Response", "Reviewer_Guidance"):
            self.assertNotIn(field, self.source)

    def test_contact_email_is_normalized(self):
        self.assertIn(
            'contact_email = ifnull(contact_record.get("Email"),"").trim().toLowerCase()',
            self.source,
        )

    def test_billing_address_comes_from_the_contact_mailing_address(self):
        self.assertIn('billing_street = ifnull(contact_record.get("Mailing_Street"),"")', self.source)
        self.assertIn('billing_code = ifnull(contact_record.get("Mailing_Zip"),"")', self.source)

    def test_terminal_reasons_are_pinned(self):
        for reason in ("deal_id_missing", "deal_not_found", "no_line_items"):
            self.assertIn(f'result.put("reason","{reason}")', self.source)

    def test_success_contract_carries_the_routing_scalars(self):
        for field in ("deal_id", "contact_id", "contact_email", "merge_data", "line_count"):
            self.assertIn(f'result.put("{field}"', self.source)
        self.assertIn('result.put("status","ready")', self.source)

    def test_an_empty_deal_produces_no_merge_output(self):
        no_lines = self.source.index('result.put("reason","no_line_items")')
        publish = self.source.index('merge.put("line_items_block"')
        self.assertLess(no_lines, publish)


class TestGenerateAndFileQuoteDocument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "generate_and_file_quote_document.deluge").read_text()

    def test_merges_against_the_verified_live_template_document(self):
        self.assertIn('template_document_id = "h5zhu2051759ecefd4148816cf61ad65a9cbc"', self.source)
        self.assertIn('"https://writer.zoho.com/writer/api/v1/documents/" + template_document_id + "/merge"', self.source)

    def test_output_is_pdf_via_the_writer_connection(self):
        self.assertIn('merge_params.put("output_settings","{\\"format\\":\\"pdf\\"}")', self.source)
        self.assertIn('connection : "writer_to_flow"', self.source)

    def test_a_quote_record_is_created_and_carries_the_pdf(self):
        self.assertIn('zoho.crm.createRecord("Quotes",quote_map)', self.source)
        self.assertIn(
            'zoho.crm.attachFile("Quotes",quote_record_id.toLong(),merged_file,"zoho_crm_to_zoho_flow")',
            self.source,
        )
        self.assertIn('quote_map.put("Deal_Name",deal_lookup)', self.source)
        self.assertIn('quote_map.put("Quoted_Items",quoted_items)', self.source)

    def test_quote_line_items_come_from_the_deal_products_with_real_ids(self):
        self.assertIn('products = ifnull(deal_record.get("Associated_Products"),List())', self.source)
        self.assertIn('product_lookup.put("id",ifnull(product.get("id"),"").toString())', self.source)
        self.assertIn('quoted_item.put("Product_Name",product_lookup)', self.source)
        self.assertIn("if(quantity > 0)", self.source)

    def test_lookups_are_id_objects_not_bare_strings(self):
        self.assertNotIn('quote_map.put("Deal_Name",safe_deal_id)', self.source)
        self.assertNotIn('quote_map.put("Contact_Name",safe_contact_id)', self.source)
        self.assertNotIn('quoted_item.put("Product_Name",ifnull(product.get("id")', self.source)

    def test_the_deal_attach_is_the_fallback_and_its_failure_is_terminal(self):
        self.assertIn('if(result.get("attached_to_quote") != "yes")', self.source)
        self.assertIn('zoho.crm.attachFile("Deals",safe_deal_id.toLong(),merged_file,"zoho_crm_to_zoho_flow")', self.source)
        self.assertIn('result.put("reason","deal_attach_failed")', self.source)
        quote_attach = self.source.index('zoho.crm.attachFile("Quotes"')
        deal_attach = self.source.index('zoho.crm.attachFile("Deals"')
        self.assertLess(quote_attach, deal_attach)

    def test_quote_creation_failures_never_lose_the_document(self):
        for handler in ("catch (deal_refetch_error)", "catch (quote_create_error)",
                        "catch (quote_attach_error)"):
            self.assertIn(handler, self.source)

    def test_the_result_reports_where_the_pdf_landed(self):
        for key in ("attached_to_quote", "attached_to_deal", "quote_record_id"):
            self.assertIn(f'result.put("{key}"', self.source)

    def test_first_quote_fields_are_stamped_only_when_blank(self):
        self.assertIn('ifnull(contact_record.get("First_Quote_Number"),"") == ""', self.source)
        self.assertIn('stamp_fields.put("First_Quote_Number",quote_number)', self.source)
        self.assertIn('stamp_fields.put("First_Quote_Created_At",stamp)', self.source)

    def test_the_email_is_gated_on_the_flow_flag_and_a_recipient(self):
        self.assertIn('if(send_email && safe_contact_email != "")', self.source)
        # Two sendmail blocks (owner + admin fallback); ignore comment mentions.
        self.assertEqual(self.source.count("\tsendmail"), 2)
        self.assertIn("Attachments : file:merged_file", self.source)

    def test_the_email_sends_from_the_deal_owner_with_admin_fallback(self):
        self.assertIn('deal_owner_email = ifnull(owner_ref.get("email"),"").toString().trim()', self.source)
        self.assertIn("mail_from = deal_owner_email;", self.source)
        self.assertIn("catch (owner_send_error)", self.source)
        self.assertIn('result.put("email_from","admin_fallback")', self.source)

    def test_the_routed_mailbox_is_ccd_with_a_safe_default(self):
        self.assertIn('quote_cc = ifnull(cc_email,"").trim()', self.source)
        self.assertIn('quote_cc = "info@kinetic-bridge.com"', self.source)
        self.assertEqual(self.source.count("cc : quote_cc"), 2)

    def test_the_creator_date_format_is_normalized_for_valid_till(self):
        self.assertIn('quote_map.put("Valid_Till",valid_till_value.toDate().toString("yyyy-MM-dd"))', self.source)
        self.assertIn("catch (valid_till_error)", self.source)

    def test_a_regenerated_quote_emails_a_revision_not_a_duplicate(self):
        self.assertIn('is_revision = result.get("quote_action") == "updated"', self.source)
        self.assertIn(
            '"Your updated Kinetic Bridge quote " + quote_number',
            self.source,
        )
        self.assertIn("This replaces the previous version.", self.source)

    def test_the_email_body_uses_html_breaks_not_plain_newlines(self):
        self.assertIn('email_body = "Hello,<br><br>";', self.source)
        self.assertIn(
            'email_body = email_body + "Best regards,<br>The Kinetic Bridge Team<br>a BEVCO company"',
            self.source,
        )
        # Plain \\n bodies collapse in Flow sendmail / Proton — must not be the send path.
        self.assertNotIn('email_body = "Hello," + newline', self.source)

    def test_outbound_quote_email_is_associated_to_contact_and_account(self):
        self.assertIn('email_item.put("sent",true)', self.source)
        self.assertIn('email_item.put("mail_format","html")', self.source)
        self.assertIn("/actions/associate_email", self.source)
        self.assertIn(
            'url :"https://www.zohoapis.com/crm/v8/Contacts/" + safe_contact_id + "/actions/associate_email"',
            self.source,
        )
        self.assertIn(
            'url :"https://www.zohoapis.com/crm/v8/Accounts/" + account_id_text + "/actions/associate_email"',
            self.source,
        )
        self.assertIn('result.put("email_associated","yes")', self.source)
        self.assertIn('result.put("email_associated_account","yes")', self.source)
        self.assertIn('assoc_message_id = "qts-quote-" + quote_number + "-"', self.source)
        # Association failures must never abort the filed result.
        self.assertIn("catch (assoc_contact_error)", self.source)
        self.assertIn("catch (assoc_account_error)", self.source)

    def test_deal_name_is_updated_to_the_current_quote_number(self):
        self.assertIn('deal_name_update.put("Deal_Name",deal_label_company + " - " + quote_number)', self.source)
        self.assertIn('zoho.crm.updateRecord("Deals",safe_deal_id.toLong(),deal_name_update)', self.source)
        self.assertIn('result.put("deal_renamed","yes")', self.source)
        self.assertIn("catch (deal_rename_error)", self.source)
        # Must use the package quote_number, not First_Quote_* (which stays on the Contact).
        rename_block = self.source[
            self.source.index("deal_name_update = Map()") : self.source.index("safe_contact_email = ifnull")
        ]
        self.assertIn("quote_number", rename_block)
        self.assertNotIn("First_Quote_Number", rename_block)

    def test_email_content_is_static_boilerplate_plus_trusted_scalars_only(self):
        for field in ("AI_Summary", "AI_Rationale", "Raw_Zia_Response"):
            self.assertNotIn(field, self.source)
        self.assertNotIn('get("Description")', self.source)

    def test_the_quote_records_its_creator_request_reference(self):
        self.assertIn(
            "map generate_and_file_quote_document(string deal_id, string contact_id,"
            " string contact_email, map merge_data, bool send_email, string quote_request_id, string cc_email)",
            self.source,
        )
        self.assertIn(
            'quote_map.put("Description","QTS Quote_Request ID: " + safe_quote_request_id)',
            self.source,
        )
        self.assertIn('if(safe_quote_request_id != "")', self.source)

    def test_terminal_reasons_are_pinned(self):
        for reason in ("deal_id_missing", "merge_data_missing", "merge_failed", "deal_attach_failed"):
            self.assertIn(f'result.put("reason","{reason}")', self.source)
        self.assertIn('result.put("status","filed")', self.source)


class TestQuoteRegeneration(unittest.TestCase):
    """A re-saved quote must refresh the existing CRM Quote record, not create
    a sibling. Dedup is by Subject, which embeds the quote number — one CRM
    search per run, no Creator API calls, no deletes (old PDFs stay as
    attachment history).
    """

    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "generate_and_file_quote_document.deluge").read_text()

    def test_the_executor_searches_for_an_existing_quote_by_subject(self):
        self.assertIn(
            'zoho.crm.searchRecords("Quotes","(Subject:equals:" + quote_subject.trim() + ")")',
            self.source,
        )

    def test_a_found_quote_is_updated_in_place(self):
        self.assertIn('zoho.crm.updateRecord("Quotes",existing_quote_id.toLong(),quote_map)', self.source)
        self.assertIn('result.put("quote_action","updated")', self.source)

    def test_an_absent_quote_falls_through_to_the_create_path(self):
        self.assertIn('result.put("quote_action","created")', self.source)
        search = self.source.index('zoho.crm.searchRecords("Quotes"')
        update = self.source.index('zoho.crm.updateRecord("Quotes"')
        create = self.source.index('zoho.crm.createRecord("Quotes"')
        self.assertLess(search, update)
        self.assertLess(update, create)

    def test_a_failed_search_degrades_to_create_never_a_lost_document(self):
        self.assertIn("catch (quote_search_error)", self.source)
        self.assertIn("catch (quote_update_error)", self.source)

    def test_the_executor_never_deletes_prior_pdfs(self):
        self.assertNotIn("deleteRecord", self.source)
        self.assertNotIn("delete_record", self.source)

    def test_the_executor_makes_no_creator_api_calls(self):
        self.assertNotIn("zoho.creator", self.source)
        self.assertNotIn("creator.zoho.com", self.source)


class TestLeadConversionOnQuote(unittest.TestCase):
    """Quoting a Lead in QTS is the human 'this is real' decision, so the
    CRM_Bridge converts it: reuse an existing Contact (by email) and Account
    (by name) when present, convert with the Deal created in the same call,
    and fall through to the plain Deal create when the Lead is already
    converted. Decision: Blake, 2026-07-27.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "qts" / "crm_bridge" / "create_deal.deluge").read_text()

    def test_conversion_runs_only_for_a_lead_quote_without_a_contact(self):
        self.assertIn('lead_id_text = ifnull(payload.get("lead_id"),"").toString().trim()', self.source)
        self.assertIn('if(lead_id_text != "" && contact_id_text == "")', self.source)

    def test_an_existing_contact_is_reused_by_email_before_converting(self):
        self.assertIn(
            'zoho.crm.searchRecords("Contacts","(Email:equals:" + lead_email + ")")',
            self.source,
        )
        self.assertIn('lead_email = ifnull(lead_rec.get("Email"),"").toString().trim().toLowerCase()', self.source)

    def test_an_existing_account_is_reused_by_company_name_before_converting(self):
        self.assertIn(
            'zoho.crm.searchRecords("Accounts","(Account_Name:equals:" + lead_company + ")")',
            self.source,
        )
        self.assertIn('if(account_id_text == "" && lead_company != "")', self.source)

    def test_an_already_converted_lead_is_never_converted_again(self):
        self.assertIn('is_converted = ifnull(lead_rec.get("$converted"),false)', self.source)
        self.assertIn("if(is_converted == false)", self.source)

    def test_the_deal_is_created_inside_the_convert_call_not_separately(self):
        self.assertIn(
            "conv = zoho.crm.convertLead(lead_id_text.toLong(),convert_values)",
            self.source,
        )
        self.assertIn('convert_values.put("Deals",potential)', self.source)
        self.assertIn('potential.put("Deal_Name",deal_name_text)', self.source)
        self.assertIn('potential.put("Stage","Proposal/Price Quote")', self.source)
        self.assertIn('converted_deal_id = ifnull(conv.get("Deals"),"").toString().trim()', self.source)

    def test_existing_ids_ride_inside_the_convert_values_map(self):
        self.assertIn('convert_values.put("overwrite",true)', self.source)
        self.assertIn('convert_values.put("Accounts",account_id_text)', self.source)
        self.assertIn('convert_values.put("Contacts",contact_id_text)', self.source)

    def test_conversion_failures_are_terminal_for_the_deal_create(self):
        self.assertIn('lead_block_error = "CRM Lead " + lead_id_text + " not found"', self.source)
        self.assertIn('lead_block_error = "CRM Lead conversion returned null"', self.source)
        self.assertIn('if(lead_block_error != "")', self.source)

    def test_the_result_reports_the_converted_ids(self):
        self.assertIn('out.put("lead_converted","yes")', self.source)
        self.assertIn('out.put("contact_id",contact_id_text)', self.source)
        self.assertIn('out.put("account_id",account_id_text)', self.source)


class TestQuoteLoadFromCrm(unittest.TestCase):
    """LOAD QUOTE reads CRM, not Creator: the CRM Quote is the durable record
    (a deleted Quote_Request must never orphan a quote), and CRM carries the
    back-reference to the Creator record via the Description stamp. Cost: two
    CRM calls per load, zero Creator API calls. Decision: Blake, 2026-07-27.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "qts" / "crm_bridge" / "get_quote_by_number.deluge").read_text()
        cls.deploy = (SCRIPTS / "qts" / "crm_bridge" / "DEPLOY.md").read_text()

    def test_the_action_is_registered(self):
        self.assertIn("get_quote_by_number", self.deploy)
        self.assertIn("get_quote_by_number.deluge", self.deploy)

    def test_the_quote_is_found_by_its_subject_then_fetched_once(self):
        self.assertIn(
            'found_quotes = zoho.crm.searchRecords("Quotes","(Subject:equals:" + quote_subject_text + ")")',
            self.source,
        )
        self.assertIn('quote_subject_text = "Kinetic Bridge Quote " + quote_number_text', self.source)
        self.assertIn('quote_rec = zoho.crm.getRecordById("Quotes",quote_id_text.toLong())', self.source)

    def test_the_response_carries_lines_lookups_and_the_creator_reference(self):
        self.assertIn('out.put("line_items",line_items)', self.source)
        self.assertIn('quoted_rows = ifnull(quote_rec.get("Quoted_Items"),List())', self.source)
        self.assertIn('qline.put("product_id",ifnull(row_product.get("id"),"").toString())', self.source)
        self.assertIn('out.put("description",ifnull(quote_rec.get("Description"),"").toString())', self.source)

    def test_missing_inputs_and_missing_quote_are_distinct_errors(self):
        self.assertIn(
            'out.put("error","get_quote_by_number requires a quote number in Query_Text or deal_id in Payload_JSON")',
            self.source,
        )
        self.assertIn('out.put("error","No CRM Quote found for " + lookup_label)', self.source)

    def test_a_deal_id_loads_that_deals_latest_quote(self):
        self.assertIn('zoho.crm.getRelatedRecords("Quotes","Deals",quote_deal_id_text.toLong())', self.source)
        self.assertIn("if(related_id_long > latest_quote_id)", self.source)
        self.assertIn(
            'quote_number_text = related_subject.replaceFirst("Kinetic Bridge Quote ","",false).trim()',
            self.source,
        )

    def test_the_number_path_wins_when_both_inputs_are_present(self):
        self.assertIn('if(quote_number_text != "")', self.source)
        number_branch = self.source.index('quote_subject_text = "Kinetic Bridge Quote " + quote_number_text')
        deal_branch = self.source.index('zoho.crm.getRelatedRecords("Quotes","Deals",quote_deal_id_text.toLong())')
        self.assertLess(number_branch, deal_branch)


class TestQuoteTemplateV4(unittest.TestCase):
    """v4 replaces the line_items_block text box with a bordered table whose
    single data row repeats per line_items[] entry at merge time. All v3
    scalar fields survive; the block field is gone.
    """

    @classmethod
    def setUpClass(cls):
        import re
        import zipfile
        xml = zipfile.ZipFile(REPO / "artifacts" / "qts_quote_template_v4.docx").read("word/document.xml").decode()
        cls.fields = re.findall(r'MERGEFIELD  "([^"]+)"', xml)
        cls.xml = xml

    def test_line_items_are_a_repeating_table_row_not_a_text_block(self):
        for f in ("line_items.name", "line_items.qty", "line_items.unit_price", "line_items.total"):
            self.assertIn(f, self.fields)
        self.assertNotIn("line_items_block", self.fields)

    def test_all_scalar_fields_survive_from_v3(self):
        for f in ("quote_number", "quote_date", "valid_till", "contact_name", "company_name",
                  "sub_total", "discount", "tax", "adjustment", "grand_total", "payment_terms"):
            self.assertIn(f, self.fields)

    def test_the_table_row_uses_complex_field_encoding(self):
        self.assertIn('w:instrText xml:space="preserve"> MERGEFIELD  "line_items.name"', self.xml)
        self.assertIn("DESCRIPTION", self.xml)


class TestCrmBridgeSplit(unittest.TestCase):
    """One Creator workflow per Action_field so no single Deluge function holds
    the old ~25 external-call statements (dev exhaustion after modest QTS use).
    """

    ACTIONS = (
        "search_customers", "search_leads", "get_customer", "get_lead",
        "create_customer", "search_deals", "get_deal", "create_deal",
        "get_quote_by_number", "get_quote_lines", "expand_kit", "get_tax",
        "books_diag",
    )

    @classmethod
    def setUpClass(cls):
        cls.bridge_dir = SCRIPTS / "qts" / "crm_bridge"
        cls.deploy = (cls.bridge_dir / "DEPLOY.md").read_text()
        cls.monolith = (SCRIPTS / "qts" / "crm_bridge_on_create.deluge").read_text()

    def test_every_action_has_its_own_paste_file(self):
        for action in self.ACTIONS:
            path = self.bridge_dir / f"{action}.deluge"
            self.assertTrue(path.is_file(), action)
            text = path.read_text()
            self.assertIn(f'Action_field,"").trim() != "{action}"', text)
            self.assertIn(action, self.deploy)

    def test_no_action_file_exceeds_eight_external_call_statements(self):
        import re
        for action in self.ACTIONS:
            text = (self.bridge_dir / f"{action}.deluge").read_text()
            count = len(re.findall(r"zoho\.crm\.|invokeurl", text))
            self.assertLessEqual(count, 8, f"{action} has {count} external stmts")

    def test_search_customers_is_a_single_or_query(self):
        text = (self.bridge_dir / "search_customers.deluge").read_text()
        self.assertEqual(text.count('zoho.crm.searchRecords("Contacts"'), 1)
        self.assertIn("Email:starts_with:", text)
        self.assertIn("Last_Name:starts_with:", text)

    def test_the_monolith_is_marked_obsolete_and_has_no_crm_calls(self):
        self.assertIn("OBSOLETE AS A LIVE PASTE", self.monolith)
        self.assertNotIn("zoho.crm.searchRecords", self.monolith)
        self.assertNotIn("zoho.crm.getRecordById", self.monolith)
        self.assertNotIn("zoho.crm.createRecord", self.monolith)
        # Comment may mention invokeurl; live integration tasks must not remain.
        self.assertNotRegex(self.monolith, r"(?m)^(?!//).*invokeurl")

    def test_deploy_doc_tells_blake_to_delete_the_mega_workflow(self):
        self.assertIn("**Disable** or **delete**", self.deploy)
        self.assertIn("Do **not** paste", self.deploy)

class TestQuoteMergeSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = json.loads((SAMPLES / "quote_merge_sample.json").read_text())

    def test_sample_money_values_are_comma_grouped_two_decimal_strings(self):
        for key in ("sub_total", "discount", "tax", "adjustment", "grand_total"):
            self.assertRegex(self.sample[key], r"^\d{1,3}(,\d{3})*\.\d{2}$")
        self.assertIn(",", self.sample["grand_total"])

    def test_sample_line_items_carry_table_row_fields(self):
        self.assertEqual(len(self.sample["line_items"]), 3)
        for row in self.sample["line_items"]:
            self.assertEqual(sorted(row), ["line_items.name", "line_items.qty", "line_items.total", "line_items.unit_price"])

    def test_sample_block_is_multiline_with_one_numbered_entry_per_product(self):
        lines = self.sample["line_items_block"].split("\n")
        numbered = [line for line in lines if line[:1].isdigit()]
        self.assertEqual(len(numbered), 3)


if __name__ == "__main__":
    unittest.main()
