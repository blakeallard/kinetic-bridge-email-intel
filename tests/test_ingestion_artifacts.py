"""Static regression checks for source-controlled Zoho ingestion functions."""

import re
import unittest
from pathlib import Path
from typing import ClassVar

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

    def test_the_automated_gate_is_evaluated_after_sender_substitution(self):
        substitution = self.source.index("from_email = form_sender_email;")
        gate = self.source.index("from_local = email_parts.get(0)")
        self.assertLess(substitution, gate)

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

    def test_is_read_only_and_never_creates_a_lead(self):
        # Deferred-lead (Model C): the match step must NOT create any CRM record.
        # Lead creation moves to materialize_pending_lead at approval time.
        self.assertNotIn("createRecord", self.source)
        self.assertNotIn("zoho.crm.createRecord", self.source)

    def test_emits_a_pending_lead_state_for_an_unmatched_sender(self):
        self.assertIn('match_status = "pending_lead"', self.source)
        self.assertIn('result.put("match_status",match_status)', self.source)
        self.assertIn('result.put("matched_module","Leads")', self.source)
        self.assertIn('result.put("matched_record_id","")', self.source)

    def test_carries_the_pending_contact_fields_for_later_creation(self):
        for field in ("first_name", "last_name", "company", "email", "phone", "lead_source"):
            self.assertIn(f'pending_contact.put("{field}"', self.source)
        self.assertIn('result.put("pending_contact",pending_contact)', self.source)

    def test_downgrades_to_no_match_when_the_email_is_blank(self):
        # Cannot defer a Lead with no email; fall back so no actionable pending record.
        self.assertIn('if(safe_email == "")', self.source)
        self.assertIn('match_status = "no_match"', self.source)

    def test_prefers_structured_form_fields_over_body_parsing(self):
        self.assertIn('structured_company = ifnull(normalized.get("company_name")', self.source)
        self.assertIn("company_name = structured_company", self.source)

    def test_source_is_website_for_form_and_email_otherwise(self):
        self.assertIn('lead_source = "Email"', self.source)
        self.assertIn("if(is_form_intake == true)", self.source)
        self.assertIn('lead_source = "Website"', self.source)

    def test_leaves_unknown_fields_blank_for_downstream_enrichment(self):
        """Fallbacks moved to the validator so Zia can fill a real value first.

        If this function collapsed a miss to "Unknown" it would beat Zia's
        extraction, because it runs before the analysis.
        """
        self.assertNotIn('company_name = "Unknown"', self.source)
        self.assertNotIn('last_name = "Unknown"', self.source)
        self.assertNotIn("last_name = email_local", self.source)

    def test_still_derives_what_it_can_without_the_model(self):
        self.assertIn("company_name = structured_company", self.source)
        self.assertIn('company_index = body_text.indexOf("Company:")', self.source)

    def test_a_single_token_sender_name_is_a_first_name_not_a_surname(self):
        self.assertNotIn("last_name = sender_name;", self.source)
        self.assertIn("last_name = sender_name.subString(", self.source)
        single_token_branch = self.source.index("first_name = sender_name;")
        multi_token_branch = self.source.index("first_name = name_parts.get(0).trim()")
        self.assertLess(multi_token_branch, single_token_branch)


class TestMaterializePendingLead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            SCRIPTS / "materialize_pending_lead.deluge"
        ).read_text()

    def test_takes_the_recommendation_record_id(self):
        self.assertTrue(
            self.source.startswith(
                "map materialize_pending_lead(string ai_recommendation_record_id)"
            )
        )

    def test_is_idempotent_when_the_target_is_already_set(self):
        self.assertIn('existing_target = ifnull(record.get("Target_Record_ID")', self.source)
        self.assertIn('if(existing_target != "")', self.source)
        self.assertIn('result.put("reason","target_already_set")', self.source)

    def test_reads_the_pending_payload_from_approved_action_json(self):
        self.assertIn('record.get("Approved_Action_JSON")', self.source)
        self.assertIn('action_map.get("pending_lead")', self.source)

    def test_blocks_when_the_pending_contact_has_no_email(self):
        self.assertIn('if(lead_email == "")', self.source)
        self.assertIn('result.put("reason","pending_contact_incomplete")', self.source)

    def test_returns_an_association_payload_for_the_new_lead(self):
        self.assertIn('action_map.get("pending_message")', self.source)
        self.assertIn('result.put("normalized_message",pending_message)', self.source)

    def test_description_comes_from_the_carried_summary_not_the_raw_body(self):
        self.assertIn('lead_description = ifnull(pending_message.get("summary")', self.source)
        for forbidden in ('pending_message.get("body_html")', "raw_zia_response"):
            self.assertNotIn(forbidden, self.source)

    def test_description_is_capped_to_the_crm_field_length(self):
        self.assertIn("if(lead_description.length() > 32000)", self.source)
        self.assertIn("lead_description.subString(0,32000)", self.source)

    def test_website_prefers_a_stated_value_over_the_email_domain(self):
        stated = self.source.index('lead_website = ifnull(pending.get("website")')
        fallback = self.source.index('if(lead_website == "")')
        self.assertLess(stated, fallback)

    def test_website_falls_back_to_the_sender_domain(self):
        self.assertIn("email_parts = lead_email.toList(\"@\")", self.source)
        self.assertIn("if(email_parts.size() == 2)", self.source)

    def test_blank_optional_fields_are_omitted_rather_than_written_empty(self):
        for guard in ('if(lead_website != "")', 'if(lead_description != "")'):
            self.assertIn(guard, self.source)

    def test_industry_is_never_written(self):
        self.assertNotIn("Industry", self.source)

    def test_lifecycle_stage_is_the_constant_intake(self):
        self.assertIn('lead_map.put("Lifecycle_Stage","Intake")', self.source)

    def test_routed_mailbox_comes_from_the_carried_recipient(self):
        self.assertIn(
            'routed_mailbox = ifnull(pending_message.get("to_email")', self.source
        )
        self.assertIn("if(routed_mailbox.length() > 255)", self.source)
        self.assertIn('if(routed_mailbox != "")', self.source)

    def test_area_of_interest_is_whitelisted_against_the_live_picklist(self):
        for allowed in (
            "Service/Advisory",
            "Battery Management Systems",
            "Low Voltage Manufacturing",
            "Cell/Production Distribution",
            "Other",
        ):
            self.assertIn(f'allowed_areas.add("{allowed}")', self.source)
        self.assertNotIn('allowed_areas.add("-None-")', self.source)
        self.assertIn("if(!allowed_areas.contains(area_of_interest))", self.source)

    def test_area_of_interest_is_carried_from_the_structured_form_field(self):
        matcher = (SCRIPTS / "ensure_crm_match.deluge").read_text()
        self.assertIn(
            'pending_contact.put("area_of_interest",'
            'ifnull(normalized.get("area_of_interest"),"").toString().trim())',
            matcher,
        )

    def test_the_association_payload_is_still_emitted(self):
        self.assertIn('result.put("crm_context",association_context)', self.source)

    def test_every_return_path_carries_the_association_maps(self):
        """A skipped/blocked return must still emit both maps, or the next Flow
        block receives null and `ifnull(x.get(...))` throws before it can guard —
        observed live 2026-07-25 as "Value is empty and 'get' function cannot be
        applied at line number 7" on a target_already_set rerun.
        """
        init = self.source.index('result = Map();')
        seeded_message = self.source.index('result.put("normalized_message",Map());')
        seeded_context = self.source.index('result.put("crm_context",Map());')
        first_return = self.source.index("return result;")
        self.assertLess(init, seeded_message)
        self.assertLess(seeded_message, seeded_context)
        self.assertLess(seeded_context, first_return)

    def test_the_association_context_satisfies_the_associate_function_guard(self):
        guard = (
            SCRIPTS / "associate_email_to_crm_record.deluge"
        ).read_text()
        self.assertIn(
            'if(matched_status != "matched" || matched_module == ""'
            ' || matched_record_id == "")',
            guard,
        )
        self.assertIn('association_context.put("match_status","matched")', self.source)
        self.assertIn('association_context.put("matched_module","Leads")', self.source)
        self.assertIn(
            'association_context.put("matched_record_id",new_lead_id)', self.source
        )

    def test_the_association_payload_is_only_built_after_the_lead_exists(self):
        created = self.source.index('result.put("lead_id",new_lead_id)')
        payload = self.source.index('result.put("crm_context",association_context)')
        self.assertLess(created, payload)

    def test_creates_the_lead_on_the_named_flow_connection(self):
        self.assertIn(
            'zoho.crm.createRecord("Leads",lead_map,Map(),"zoho_crm_to_zoho_flow")',
            self.source,
        )

    def test_stamps_blake_as_the_lead_owner(self):
        self.assertIn('lead_owner_id = "6719186000002395001"', self.source)
        self.assertIn('owner_map.put("id",lead_owner_id)', self.source)

    def test_writes_the_new_lead_id_back_onto_the_recommendation(self):
        self.assertIn('update_map.put("Target_Record_ID",new_lead_id)', self.source)
        self.assertIn('update_map.put("Target_Module","Leads")', self.source)


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


class TestDeferredLeadThreading(unittest.TestCase):
    """Model C: the pending_lead state must survive build_crm_context -> validator -> persist."""

    @classmethod
    def setUpClass(cls):
        cls.context = (SCRIPTS / "build_crm_context.deluge").read_text()
        cls.validator = (
            SCRIPTS / "validate_zia_analysis_response_tagged.deluge"
        ).read_text()
        cls.persist = (SCRIPTS / "persist_recommendation.deluge").read_text()

    def test_context_accepts_and_carries_the_pending_contact(self):
        self.assertIn(
            "map build_crm_context(string from_email, string from_domain, "
            "string contact_id, string lead_id, string account_id, map pending_contact)",
            self.context,
        )
        self.assertIn('match_status = "pending_lead"', self.context)
        self.assertIn('result.put("pending_contact",safe_pending)', self.context)

    def test_context_only_pends_when_a_pending_email_is_present(self):
        self.assertIn(
            '!safe_pending.isEmpty() && ifnull(safe_pending.get("email"),"").toString().trim() != ""',
            self.context,
        )

    def test_validator_keeps_pending_lead_actionable(self):
        self.assertIn('else if(match_status == "pending_lead")', self.validator)
        self.assertIn('recommendation.put("action","create_crm_task")', self.validator)
        self.assertIn('recommendation.put("target_module","Leads")', self.validator)
        self.assertIn('recommendation.put("target_record_id","")', self.validator)

    def test_validator_marks_pending_lead_valid_not_fallback(self):
        self.assertIn('else if(match_status == "pending_lead")', self.validator)
        self.assertIn('validation_status = "valid"', self.validator)

    def test_validator_does_not_flag_pending_lead_as_missing_context(self):
        self.assertIn(
            'else if(match_status != "matched" && match_status != "pending_lead")',
            self.validator,
        )

    def test_validator_forwards_the_pending_contact(self):
        self.assertIn('validated.put("pending_contact",pending_contact)', self.validator)

    def test_persist_stores_the_pending_payload_only_when_pending(self):
        self.assertIn("is_pending_lead = ", self.persist)
        self.assertIn('pending_wrapper.put("pending_lead",pending_contact)', self.persist)
        self.assertIn('record.put("Approved_Action_JSON",pending_json)', self.persist)
        self.assertIn('record.put("Email",ifnull(pending_contact.get("email"),"").toString())', self.persist)

    def test_validator_forwards_the_source_message_for_later_association(self):
        for field in (
            "message_id",
            "from_email",
            "from_name",
            "to_email",
            "cc_email",
            "subject",
            "summary",
            "received_at_ms",
        ):
            self.assertIn(f'pending_message.put("{field}"', self.validator)
        self.assertIn('validated.put("pending_message",pending_message)', self.validator)

    def test_validator_maps_the_stripped_body_onto_the_association_key(self):
        self.assertIn(
            'pending_body_text = ifnull(trusted_message.get("body_text"),"").toString()',
            self.validator,
        )
        self.assertIn('pending_message.put("body_html",pending_body_html)', self.validator)

    def test_the_carried_body_renders_as_html_not_one_run_on_block(self):
        associate = (SCRIPTS / "associate_email_to_crm_record.deluge").read_text()
        self.assertIn('email_item.put("mail_format","html")', associate)
        self.assertIn(
            'pending_body_html = pending_body_text.replaceAll(hexToText("0A"),"<br>")',
            self.validator,
        )

    def test_validator_only_carries_the_message_when_a_lead_is_pending(self):
        self.assertIn("if(!pending_contact.isEmpty())", self.validator)

    def test_validator_fills_contact_gaps_from_the_model(self):
        self.assertIn('zia_contact = ifnull(analysis.get("contact"),Map())', self.validator)
        for field in ("first_name", "last_name", "company"):
            self.assertIn(f'zia_contact.get("{field}")', self.validator)

    def test_model_extraction_never_overwrites_a_derived_value(self):
        """Precedence: form fields / sender name / Company: label beat the model."""
        for guard in (
            'if(pending_first == "")',
            'if(pending_last == "")',
            'if(pending_company == "")',
        ):
            self.assertIn(guard, self.validator)

    def test_model_extraction_is_ignored_when_the_response_did_not_parse(self):
        self.assertIn("if(parse_ok)", self.validator)

    def test_model_supplied_values_are_capped_to_the_crm_field_lengths(self):
        for bound in (40, 80, 100):
            self.assertIn(f".length() > {bound}", self.validator)

    def test_domain_fallback_applies_only_after_the_model(self):
        model_step = self.validator.index('zia_contact.get("company")')
        fallback = self.validator.index("domain_parts = email_domain.toList")
        self.assertLess(model_step, fallback)
        self.assertIn("pending_company = domain_parts.get(0).trim().proper()", self.validator)

    def test_last_name_still_falls_back_to_the_email_local_part(self):
        self.assertIn("pending_last = email_local", self.validator)

    def test_persist_caps_the_stored_body_against_the_field_limit(self):
        self.assertIn("if(pending_body.length() > 24000)", self.persist)
        self.assertIn("pending_body.subString(0,24000)", self.persist)
        self.assertIn('pending_message.put("body_truncated",true)', self.persist)

    def test_persist_drops_the_message_rather_than_overflow_the_field(self):
        self.assertIn("if(pending_json.length() > 32000)", self.persist)
        self.assertIn('pending_wrapper.remove("pending_message")', self.persist)

    def test_the_association_function_itself_is_unchanged(self):
        associate = (SCRIPTS / "associate_email_to_crm_record.deluge").read_text()
        self.assertTrue(
            associate.startswith(
                "map associate_email_to_crm_record(map normalized_message, map crm_context)"
            )
        )
        self.assertNotIn("pending_lead", associate)
        self.assertNotIn("pending_message", associate)


if __name__ == "__main__":
    unittest.main()


class TestDelugeVariablesAreDefined(unittest.TestCase):
    """Catch reads of an undefined variable before Zoho does.

    Deluge is not compiled anywhere in this repo, so a typo like `parsed.get(...)`
    where the variable is actually `analysis` only surfaces as a live runtime error
    ("Variable 'parsed' is not defined"). This walks every .deluge file and flags any
    identifier used as `X.get(` that is never assigned, passed in as a parameter, or
    bound by a `for each` / `catch`.
    """

    BUILTINS: ClassVar[set[str]] = {
        "zoho", "Map", "List", "if", "for", "each", "while",
        "try", "catch", "return", "null", "true", "false", "info", "thisapp",
    }

    def test_no_deluge_file_reads_an_undefined_variable(self):
        offenders = {}
        for path in sorted((REPO / "scripts").glob("*.deluge")):
            source = path.read_text()
            signature = source.split("{", 1)[0]
            known = set(re.findall(r"\b\w+\s+(\w+)\s*[,)]", signature))
            known |= set(re.findall(r"^\s*(\w+)\s*=", source, re.MULTILINE))
            known |= set(re.findall(r"for\s+each\s+(\w+)\s+in", source))
            known |= set(re.findall(r"catch\s*\(\s*(\w+)", source))
            used = set(re.findall(r"\b(\w+)\.get\(", source))
            unknown = sorted(used - known - self.BUILTINS)
            if unknown:
                offenders[path.name] = unknown
        self.assertEqual(offenders, {}, f"undefined variables read: {offenders}")
