"""Static regression checks for source-controlled Zoho ingestion functions."""

from pathlib import Path
import re
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

    def test_searches_the_live_module_by_the_unique_ingestion_key(self):
        self.assertIn('criteria = "(Ingestion_Key:equals:" + idempotency_key + ")"', self.source)
        self.assertIn('zoho.crm.searchRecords("AI_Recommendations",criteria)', self.source)
        self.assertNotIn('(Name:equals:', self.source)

    def test_reads_the_first_existing_record(self):
        self.assertIn("existing_record = records.get(0)", self.source)
        self.assertIn('existing_record.get("Status")', self.source)

    def test_returns_the_duplicate_guard_contract(self):
        for field in ("exists", "record_id", "status", "idempotency_key"):
            self.assertIn(f'result.put("{field}"', self.source)


class TestRecommendationPersist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "persist_recommendation.deluge").read_text()

    def test_writes_the_key_to_the_unique_ingestion_field(self):
        self.assertIn('record.put("Ingestion_Key",ifnull(validated.get("idempotency_key"),""))', self.source)

    def test_writes_a_human_readable_display_name(self):
        self.assertIn('display_name = "AI Recommendation: " + action_label + " - " + category_label', self.source)
        self.assertIn('record.put("Name",display_name)', self.source)
        self.assertNotIn('record.put("Name",ifnull(validated.get("idempotency_key"),""))', self.source)

    def test_display_name_is_capped_at_the_field_length(self):
        self.assertIn("if(display_name.length() > 120)", self.source)

    def test_maps_the_ai_summary_fields(self):
        for field in ("AI_Category", "AI_Summary", "AI_Rationale"):
            self.assertIn(f'record.put("{field}"', self.source)

    def test_safety_summary_is_a_list_of_picklist_values(self):
        self.assertIn("safety_values = List()", self.source)
        self.assertIn('record.put("Safety_Summary",safety_values)', self.source)
        for value in (
            "Human Approval Required",
            "Closed Won Change Requested",
            "Quote Generation Requested",
            "Insufficient Context",
            "Conflict Detected",
        ):
            self.assertIn(f'safety_values.add("{value}")', self.source)

    def test_review_notes_carry_action_and_reason(self):
        self.assertIn('new_line = hexToText("0A")', self.source)
        self.assertIn(
            'review_block = "Recommended Action: " + action_label + new_line + "Reason: " + review_reason',
            self.source,
        )
        self.assertNotIn("\\n", self.source)

    def test_treats_a_datastore_duplicate_as_already_recorded(self):
        self.assertIn('api_code == "DUPLICATE_DATA"', self.source)
        self.assertIn('duplicate_record = details.get("duplicate_record")', self.source)

    def test_persisted_is_only_true_on_a_fresh_create(self):
        self.assertIn('result.put("persisted",api_code == "SUCCESS" && record_id != "")', self.source)

    def test_returns_the_duplicate_flag(self):
        self.assertIn('result.put("duplicate",duplicate)', self.source)


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


class TestNormalizeMessageDirection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "normalize_teaminbox_payload.deluge").read_text()

    def test_recognizes_both_internal_company_domains(self):
        self.assertIn('from_domain == "bevco-tech.com"', self.source)
        self.assertIn('from_domain == "kinetic-bridge.com"', self.source)

    def test_internal_sender_cannot_pass_the_processing_gate(self):
        self.assertIn(
            "should_process = is_inbound && !is_finance_inbox && !is_internal_sender"
            " && !is_automated_sender",
            self.source,
        )

    def test_internal_outgoing_copy_has_an_explicit_skip_reason(self):
        self.assertIn('skip_reason = "internal_sender_outbound_copy"', self.source)
        self.assertIn(
            'normalized.put("is_internal_sender",is_internal_sender)', self.source
        )

    def test_recognizes_the_conservative_automated_sender_tokens(self):
        for token in (
            "noreply",
            "no-reply",
            "donotreply",
            "do-not-reply",
            "mailer-daemon",
            "postmaster",
            "dmarc",
            "bounce",
        ):
            self.assertIn(f'automated_sender_tokens.add("{token}")', self.source)

    def test_automated_senders_are_matched_on_the_local_part_only(self):
        self.assertIn("from_local = email_parts.get(0).toLowerCase()", self.source)
        self.assertIn("from_local.contains(automated_token)", self.source)

    def test_automated_sender_has_an_explicit_skip_reason(self):
        self.assertIn('skip_reason = "automated_sender"', self.source)
        self.assertIn(
            'normalized.put("is_automated_sender",is_automated_sender)', self.source
        )

    def test_the_observed_dmarc_robots_would_be_blocked(self):
        tokens = re.findall(r'automated_sender_tokens\.add\("([^"]+)"\)', self.source)
        for local_part in (
            "noreply-dmarc",
            "dmarcreport",
            "noreply-dmarc-support",
        ):
            self.assertTrue(
                any(token in local_part for token in tokens),
                f"{local_part} would still reach the CRM",
            )

    def test_an_ordinary_sender_is_not_blocked(self):
        tokens = re.findall(r'automated_sender_tokens\.add\("([^"]+)"\)', self.source)
        for local_part in ("blake", "kurtis", "sean.wood", "richard", "info"):
            self.assertFalse(
                any(token in local_part for token in tokens),
                f"{local_part} would be dropped before reaching review",
            )


class TestFormIntakeSenderResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "normalize_teaminbox_payload.deluge").read_text()

    def test_only_known_relay_addresses_trigger_body_extraction(self):
        self.assertIn("is_relay_sender = form_intake_relays.contains(envelope_email)", self.source)
        self.assertIn("if(is_relay_sender)", self.source)

    def test_the_relay_allow_list_is_explicit(self):
        self.assertIn('form_intake_relays.add("blake@kinetic-bridge.com")', self.source)
        self.assertIn('form_intake_relays.add("info@bevco-tech.com")', self.source)

    def test_markup_is_stripped_before_the_email_marker_is_located(self):
        self.assertIn('body_text = body_html.replaceAll("<[^>]*>"," ")', self.source)
        self.assertIn('marker_index = body_text.indexOf("Email:")', self.source)

    def test_a_mailto_prefix_is_removed_from_the_candidate(self):
        self.assertIn('candidate.replaceAll("^mailto:","")', self.source)

    def test_the_candidate_must_look_like_an_address(self):
        self.assertIn(
            'candidate_parts.size() == 2 && candidate_parts.get(1).contains(".")',
            self.source,
        )

    def test_extraction_failure_leaves_the_envelope_sender_intact(self):
        self.assertIn('is_form_intake = form_sender_email != ""', self.source)
        self.assertIn("from_email = envelope_email;", self.source)

    def test_the_extracted_sender_replaces_the_relay_for_matching(self):
        self.assertIn("relay_email = envelope_email;", self.source)
        self.assertIn("from_email = form_sender_email;", self.source)

    def test_the_internal_gate_is_evaluated_after_sender_substitution(self):
        substitution = self.source.index("from_email = form_sender_email;")
        gate = self.source.index("is_internal_sender = from_domain ==")
        self.assertLess(substitution, gate)

    def test_the_domain_is_recomputed_from_the_resolved_sender(self):
        substitution = self.source.index("from_email = form_sender_email;")
        recompute = self.source.index("email_parts = from_email.toList")
        self.assertLess(substitution, recompute)

    def test_both_the_relay_and_the_form_flag_are_published(self):
        self.assertIn('normalized.put("is_form_intake",is_form_intake)', self.source)
        self.assertIn('normalized.put("relay_email",relay_email)', self.source)


class TestFormBodyNewlines(unittest.TestCase):
    """Deluge does not interpret a literal backslash-n; both form adapters must use hexToText."""

    @classmethod
    def setUpClass(cls):
        cls.relay = (SCRIPTS / "build_form_intake_payload.deluge").read_text()
        cls.entry = (SCRIPTS / "normalize_form_entry.deluge").read_text()

    def test_neither_form_adapter_emits_a_literal_backslash_n(self):
        for name, source in (("build_form_intake_payload", self.relay),
                             ("normalize_form_entry", self.entry)):
            self.assertNotIn("\\n", source, f"{name} still builds a literal backslash-n")

    def test_both_form_adapters_join_on_a_real_newline(self):
        for source in (self.relay, self.entry):
            self.assertIn('new_line = hexToText("0A")', source)
            self.assertIn("body_lines.toString(new_line)", source)
            self.assertIn("body_text + new_line + new_line + comment_text", source)


class TestFormIntakePayloadBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "build_form_intake_payload.deluge").read_text()
        cls.normalizer = (SCRIPTS / "normalize_teaminbox_payload.deluge").read_text()

    def test_signature_matches_the_fields_the_form_exposes(self):
        self.assertTrue(
            self.source.startswith(
                "map build_form_intake_payload(string form_id, string submitter_email, "
                "string first_name, string last_name, string company, string phone, "
                "string area_of_interest, string comments, string submitted_at_ms, "
                "string intake_address)"
            )
        )

    def test_emits_every_block_the_normalizer_reads(self):
        read = set(re.findall(r'payload\.get\("([^"]+)"\)', self.normalizer))
        written = set(re.findall(r'payload\.put\("([^"]+)"', self.source))
        self.assertEqual(set(), read - written)

    def test_nested_keys_match_what_the_normalizer_extracts(self):
        for block, key in (
            ("from_block", "fromAddress"),
            ("from_block", "senderName"),
            ("to_block", "toAddress"),
            ("date_block", "sentDateInGMT"),
            ("date_block", "receivedTime"),
            ("event_block", "eventName"),
            ("content_block", "mailContent"),
        ):
            self.assertIn(f'{block}.put("{key}"', self.source)
            self.assertIn(f'"{key}"', self.normalizer)

    def test_the_event_name_passes_the_inbound_gate(self):
        self.assertIn('event_block.put("eventName","NEW_INBOUND_MESSAGE")', self.source)
        self.assertIn('is_inbound = event_name == "NEW_INBOUND_MESSAGE"', self.normalizer)

    def test_the_real_submitter_is_the_envelope_sender(self):
        self.assertIn('from_block.put("fromAddress",sender_email)', self.source)

    def test_the_message_id_is_namespaced_and_bounded(self):
        self.assertIn('message_id = "zohoform-" + form_key', self.source)
        self.assertIn("if(message_id.length() > 200)", self.source)

    def test_the_message_id_is_sanitised(self):
        self.assertIn('message_id.replaceAll("[^A-Za-z0-9._@-]","-")', self.source)

    def test_the_intake_address_avoids_the_finance_inbox_gate(self):
        self.assertIn('to_address = "bms@kinetic-bridge.com"', self.source)
        self.assertIn('is_finance_inbox = to_email.startsWith("ap@")', self.normalizer)

    def test_the_body_carries_the_structured_fields(self):
        for label in ("Name: ", "Company: ", "Email: ", "Phone: ", "Area of Interest: "):
            self.assertIn(f'body_lines.add("{label}"', self.source)

    def test_bounded_subject_and_summary(self):
        self.assertIn("if(subject.length() > 255)", self.source)
        self.assertIn("if(summary_text.length() > 500)", self.source)


class TestNoMatchValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.no_match = (
            SCRIPTS / "validate_zia_analysis_response_no_match.deluge"
        ).read_text()
        cls.shared = (SCRIPTS / "validate_zia_analysis_response.deluge").read_text()

    def test_has_a_clean_two_argument_signature(self):
        self.assertTrue(
            self.no_match.startswith(
                "map validate_zia_analysis_response_no_match("
                "string raw_response, map trusted_request)"
            )
        )

    def test_forces_manual_review_and_clears_untrusted_targets(self):
        for source in (self.no_match, self.shared):
            self.assertIn('recommendation.put("action","manual_review")', source)
            self.assertIn('recommendation.put("target_module","")', source)
            self.assertIn('recommendation.put("target_record_id","")', source)

    def test_marks_no_match_as_insufficient_context(self):
        self.assertIn('else if(match_status != "matched")', self.no_match)
        self.assertIn('safety.put("contains_insufficient_context",true)', self.no_match)

    def test_records_the_no_match_conflict(self):
        self.assertIn('conflicts.add("crm_record_not_found")', self.no_match)


class TestEnsureCrmMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            SCRIPTS / "ensure_crm_match.deluge"
        ).read_text()

    def test_takes_the_normalized_message_and_the_resolve_result(self):
        self.assertTrue(
            self.source.startswith(
                "map ensure_crm_match(map normalized, map resolve_result)"
            )
        )

    def test_passes_an_existing_match_through_untouched(self):
        self.assertIn(
            'ifnull(resolve_result.get("match_status"),"") == "matched"', self.source
        )
        self.assertIn("return resolve_result;", self.source)

    def test_creates_a_lead_on_the_named_flow_connection(self):
        self.assertIn(
            'zoho.crm.createRecord("Leads",lead_map,Map(),"zoho_crm_to_zoho_flow")',
            self.source,
        )

    def test_stamps_the_configured_owner(self):
        self.assertIn('lead_owner_id = "6719186000002395001"', self.source)
        self.assertIn('owner_map.put("id",lead_owner_id)', self.source)

    def test_source_is_website_for_form_and_email_otherwise(self):
        self.assertIn('lead_source = "Email"', self.source)
        self.assertIn("if(is_form_intake == true)", self.source)
        self.assertIn('lead_source = "Website"', self.source)

    def test_last_name_falls_back_to_the_email_local_part(self):
        self.assertIn("local_parts = safe_email.toList", self.source)
        self.assertIn("last_name = email_local", self.source)

    def test_company_is_required_and_defaults_to_unknown(self):
        self.assertIn('lead_map.put("Company",company_name)', self.source)
        self.assertIn('company_name = "Unknown"', self.source)

    def test_returns_a_lead_match_shape_when_created(self):
        self.assertIn('match_type = "lead"', self.source)
        self.assertIn('matched_module = "Leads"', self.source)
        self.assertIn('result.put("matched_record_id",matched_record_id)', self.source)

    def test_reports_whether_a_record_was_actually_created(self):
        self.assertIn("created = false", self.source)
        self.assertIn('result.put("created",created)', self.source)


class TestCliqNotification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "notify_cliq_new_recommendation.deluge").read_text()

    def test_takes_the_recommendation_record_id(self):
        self.assertTrue(
            self.source.startswith(
                "void notify_cliq_new_recommendation(string recommendation_id)"
            )
        )

    def test_reads_the_record_from_crm(self):
        self.assertIn(
            'zoho.crm.getRecordById("AI_Recommendations",rec_id.toLong())', self.source
        )

    def test_only_announces_pending_review_records(self):
        self.assertIn('if(status != "Pending Review")', self.source)
        self.assertIn("return;", self.source)

    def test_posts_to_the_configured_cliq_channel_through_a_connection(self):
        self.assertIn(
            'zoho.cliq.postToChannel("airecommendationstest",message_text,"blake_cliq_connection")',
            self.source,
        )

    def test_includes_a_clickable_record_link(self):
        self.assertIn(
            'record_url = "https://crm.zoho.com/crm/org883125891/tab/CustomModule1/" + rec_id',
            self.source,
        )

    def test_carries_the_trusted_scalar_fields(self):
        for field in ("Recommendation_Type", "Target_Module", "Target_Record_ID"):
            self.assertIn(f'record.get("{field}")', self.source)


class TestLeadOutboundAdvance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "advance_lead_on_first_outbound.deluge").read_text()

    def test_has_a_single_lead_id_signature(self):
        self.assertTrue(
            self.source.startswith(
                "map advance_lead_on_first_outbound(string lead_id)"
            )
        )

    def test_operates_on_the_leads_module_only(self):
        self.assertIn('module_api_name = "Leads"', self.source)
        updated = set(re.findall(r"zoho\.crm\.updateRecord\((\w+)", self.source))
        self.assertEqual(updated, {"module_api_name"})

    def test_only_advances_from_exactly_not_contacted(self):
        self.assertIn('eligible_status = "Not Contacted"', self.source)
        self.assertIn("if(current_status != eligible_status)", self.source)

    def test_the_ineligible_branch_returns_without_updating(self):
        skip_branch = self.source[
            self.source.index("if(current_status != eligible_status)"):
            self.source.index("update_map = Map()")
        ]
        self.assertIn('result.put("reason","status_not_eligible")', skip_branch)
        self.assertIn("return result;", skip_branch)
        self.assertNotIn("updateRecord", skip_branch)

    def test_advances_to_contacted(self):
        self.assertIn('advanced_status = "Contacted"', self.source)
        self.assertIn('update_map.put("Lead_Status",advanced_status)', self.source)

    def test_writes_only_the_lead_status_field(self):
        put_fields = set(re.findall(r"update_map\.put\(\"(\w+)\"", self.source))
        self.assertEqual(put_fields, {"Lead_Status"})

    def test_never_converts_or_creates_downstream_records(self):
        for forbidden in ("convertLead", "createRecord", "Deals", "Contacts", "Deal"):
            self.assertNotIn(forbidden, self.source)


def _idempotency_key(portal_id, from_email, sent_at_ms, subject):
    return "teaminbox:" + portal_id + ":" + from_email + ":" + sent_at_ms + ":" + subject


class TestIngestionIdempotencyKey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (SCRIPTS / "normalize_teaminbox_payload.deluge").read_text()

    def test_the_deluge_builds_the_key_from_sender_timestamp_and_subject(self):
        self.assertIn(
            'idempotency_key = "teaminbox:" + portal_id + ":" + from_email + ":" '
            '+ sent_at_ms + ":" + ifnull(payload.get("subject"),"");',
            self.source,
        )
        self.assertIn(
            'normalized.put("idempotency_key",idempotency_key)', self.source
        )

    def test_the_key_no_longer_depends_on_the_teaminbox_message_id(self):
        self.assertNotIn(
            '"teaminbox:" + portal_id + ":" + message_id', self.source
        )

    def test_dual_delivery_of_one_email_collapses_to_one_key(self):
        first = _idempotency_key(
            "901489292", "sender@example.com", "1784333133430111003", "DEDUP TEST 001"
        )
        second = _idempotency_key(
            "901489292", "sender@example.com", "1784333133430111003", "DEDUP TEST 001"
        )
        self.assertEqual(first, second)

    def test_a_different_subject_yields_a_different_key(self):
        base = _idempotency_key(
            "901489292", "sender@example.com", "1784333133430111003", "DEDUP TEST 001"
        )
        other = _idempotency_key(
            "901489292", "sender@example.com", "1784333133430111003", "DEDUP TEST 002"
        )
        self.assertNotEqual(base, other)

    def test_a_different_sender_yields_a_different_key(self):
        base = _idempotency_key(
            "901489292", "sender@example.com", "1784333133430111003", "DEDUP TEST 001"
        )
        other = _idempotency_key(
            "901489292", "other@example.com", "1784333133430111003", "DEDUP TEST 001"
        )
        self.assertNotEqual(base, other)

    def test_a_different_send_timestamp_yields_a_different_key(self):
        base = _idempotency_key(
            "901489292", "sender@example.com", "1784333133430111003", "DEDUP TEST 001"
        )
        other = _idempotency_key(
            "901489292", "sender@example.com", "1784333133430111999", "DEDUP TEST 001"
        )
        self.assertNotEqual(base, other)


if __name__ == "__main__":
    unittest.main()
