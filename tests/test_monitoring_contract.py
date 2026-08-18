import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ProjectTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        os.environ["TRACKER_DB_PATH"] = str(self.root / "tracker.sqlite3")

        from policy_compliance_tracker import config
        from policy_compliance_tracker.storage import tracker_store

        self.config = importlib.reload(config)
        self.store = importlib.reload(tracker_store)
        self.store.init_db()

    def tearDown(self):
        self.tempdir.cleanup()


class TrackerSchemaExportTests(ProjectTestCase):
    def test_tracker_stores_policy_change_and_source_metadata(self):
        saved = self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-TEST-001",
                "regulation_title": "MFA circular",
                "regulator": "RBI",
                "version": 1,
                "status": "Open",
                "owner": "GRC Team",
                "priority": "High",
                "risk_score": 18,
                "risk_score_max": 25,
                "confidence": 90,
                "regulatory_update": "MFA threshold update",
                "compliance_obligation": "Implement MFA for high-value transactions.",
                "impacted_policy": "Information Security Policy",
                "required_policy_update": "Add high-value transaction MFA coverage.",
                "policy_change_required": True,
                "policy_change_reason": "Information Security Policy needs MFA scope update.",
                "impacted_control": "C001 Multi-Factor Authentication",
                "control_gap": "Existing control does not mention high-value transactions.",
                "recommended_enhancement": "Add transaction-specific MFA control language.",
                "source_path": "data/regulations/RBI_KYC_Master_Direction.pdf",
                "source_url": "https://example.test/rbi-mfa.pdf",
                "feed_name": "RBI Updates",
                "downloaded_at": "2026-07-19T00:00:00Z",
                "regulator_source": "RBI",
            }
        )

        self.assertEqual(saved["policy_change_required"], 1)
        self.assertEqual(saved["source_url"], "https://example.test/rbi-mfa.pdf")

        from policy_compliance_tracker.exports.exports import (
            tracker_entries_to_csv,
            tracker_entries_to_pdf,
            tracker_entries_to_xlsx,
        )

        entries = self.store.fetch_tracker_entries()
        csv_text = tracker_entries_to_csv(entries)
        self.assertIn("policy_change_required", csv_text)
        self.assertIn("source_url", csv_text)
        self.assertGreater(len(tracker_entries_to_xlsx(entries)), 100)
        self.assertGreater(len(tracker_entries_to_pdf(entries)), 100)

    def test_tracker_derives_policy_change_when_policy_is_impacted(self):
        saved = self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-TEST-002",
                "regulation_title": "MFA circular",
                "status": "Open",
                "impacted_policy": "Information Security Policy",
                "required_policy_update": "Add MFA coverage.",
            }
        )

        self.assertEqual(saved["policy_change_required"], 1)
        self.assertEqual(saved["policy_change_reason"], "Add MFA coverage.")

    def test_mark_all_notifications_read_updates_unread_count(self):
        self.store.create_notification(
            None,
            "Critical impact",
            "Review required.",
            "Critical",
        )
        self.store.create_notification(
            None,
            "High impact",
            "Review required.",
            "High",
        )

        self.assertEqual(
            self.store.tracker_summary_counts()["unread_notifications"],
            2,
        )

        updated = self.store.mark_all_notifications_read()

        self.assertEqual(updated, 2)
        self.assertEqual(
            self.store.tracker_summary_counts()["unread_notifications"],
            0,
        )

    def test_clear_tracker_data_resets_notification_sequence(self):
        self.store.create_notification(
            None,
            "Critical impact",
            "Review required.",
            "Critical",
        )
        self.assertEqual(self.store.fetch_notifications(limit=1)[0]["id"], 1)

        self.store.clear_tracker_data()

        self.store.create_notification(
            None,
            "Critical impact",
            "Review required.",
            "Critical",
        )
        self.assertEqual(self.store.fetch_notifications(limit=1)[0]["id"], 1)

    def test_summary_counts_only_open_critical_items(self):
        self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-OPEN-CRITICAL",
                "regulation_title": "Open critical",
                "status": "Open",
                "priority": "Critical",
            }
        )
        self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-CLOSED-CRITICAL",
                "regulation_title": "Closed critical",
                "status": "Closed",
                "priority": "Critical",
            }
        )

        summary = self.store.tracker_summary_counts()

        self.assertEqual(summary["open"], 1)
        self.assertEqual(summary["critical"], 1)

    def test_reanalyzing_same_closed_text_reuses_tracker_without_new_alert(self):
        regulation_text = "RBI requires immediate MFA for all high value transactions."
        analysis = {
            "tracker_record": {
                "regulation_title": "RBI MFA update",
                "status": "Open",
                "priority": "Critical",
                "owner": "IAM Team + GRC Team",
                "risk_score": 20,
                "risk_score_max": 25,
                "confidence": 90,
                "regulatory_update": regulation_text,
                "impacted_policy": "Information Security Policy",
                "required_policy_update": "Add high value transaction MFA coverage.",
                "policy_change_required": True,
            }
        }

        first = self.store.save_analysis_result(analysis, regulation_text)
        self.store.update_tracker_status(first["tracker_id"], "Closed")
        second = self.store.save_analysis_result(analysis, regulation_text)

        entries = self.store.fetch_tracker_entries()
        notifications = self.store.fetch_notifications(limit=10)

        self.assertEqual(first["tracker_id"], second["tracker_id"])
        self.assertEqual(second["status"], "Closed")
        self.assertEqual(second["analysis_action"], "reused_existing_tracker")
        self.assertTrue(second["matched_existing_resolved"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(notifications), 1)

    def test_reanalyzing_legacy_closed_tracker_matches_regulatory_update(self):
        regulation_text = "RBI requires immediate MFA for all high value transactions."
        first = self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-LEGACY-001",
                "regulation_title": "Legacy MFA update",
                "status": "Closed",
                "priority": "Critical",
                "regulatory_update": regulation_text,
                "impacted_policy": "Information Security Policy",
            }
        )
        analysis = {
            "tracker_record": {
                "regulation_title": "RBI MFA update",
                "status": "Open",
                "priority": "Critical",
                "regulatory_update": regulation_text,
                "impacted_policy": "Information Security Policy",
            }
        }

        second = self.store.save_analysis_result(analysis, regulation_text)

        self.assertEqual(first["tracker_id"], second["tracker_id"])
        self.assertEqual(second["status"], "Closed")
        self.assertEqual(len(self.store.fetch_tracker_entries()), 1)

    def test_duplicate_matching_prefers_resolved_tracker(self):
        regulation_text = "RBI requires multi-factor authentication for transactions above INR 10,000."
        self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-OPEN-DUPE",
                "regulation_title": "Open duplicate",
                "status": "Open",
                "priority": "Critical",
                "regulatory_update": regulation_text,
                "impacted_policy": "Information Security Policy",
            }
        )
        closed = self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-CLOSED-DUPE",
                "regulation_title": "Closed duplicate",
                "status": "Closed",
                "priority": "Critical",
                "regulatory_update": regulation_text,
                "impacted_policy": "Information Security Policy",
            }
        )

        matched = self.store.find_tracker_for_regulation_text(
            regulation_text,
            self.store.regulation_fingerprint(regulation_text),
        )

        self.assertEqual(matched["tracker_id"], closed["tracker_id"])
        self.assertEqual(matched["status"], "Closed")

    def test_tracker_fetch_and_summary_dedupe_duplicate_rows(self):
        regulation_text = "RBI requires multi-factor authentication for transactions above INR 10,000."
        self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-OPEN-DUPE",
                "regulation_title": "Manual Input",
                "status": "Open",
                "priority": "Critical",
                "regulatory_update": regulation_text,
                "impacted_policy": "Information Security Policy",
            }
        )
        closed = self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-CLOSED-DUPE",
                "regulation_title": "Manual Input",
                "status": "Closed",
                "priority": "Critical",
                "regulatory_update": regulation_text,
                "impacted_policy": "Information Security Policy",
            }
        )

        entries = self.store.fetch_tracker_entries()
        summary = self.store.tracker_summary_counts()

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["tracker_id"], closed["tracker_id"])
        self.assertEqual(summary["open"], 0)
        self.assertEqual(summary["critical"], 0)

    def test_save_analysis_matches_existing_tracker_by_extracted_update(self):
        stored_update = "RBI requires multi-factor authentication for transactions above INR 10,000."
        pasted_text = (
            "RBI requires multi-factor authentication for transactions above INR 10,000. "
            "Banks must implement the requirement immediately for high-value digital transactions."
        )
        existing = self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-CLOSED-MFA",
                "regulation_title": "Manual Input",
                "status": "Closed",
                "priority": "Critical",
                "regulatory_update": stored_update,
                "impacted_policy": "Information Security Policy",
            }
        )
        analysis = {
            "tracker_record": {
                "regulation_title": "Manual Input",
                "status": "Open",
                "priority": "Critical",
                "regulatory_update": stored_update,
                "impacted_policy": "Information Security Policy",
            }
        }

        saved = self.store.save_analysis_result(analysis, pasted_text)

        self.assertEqual(saved["tracker_id"], existing["tracker_id"])
        self.assertEqual(saved["status"], "Closed")
        self.assertEqual(len(self.store.fetch_tracker_entries(include_duplicates=True)), 1)


class AnalysisExtractionTests(ProjectTestCase):
    def test_deadline_extracts_compact_relative_value(self):
        from policy_compliance_tracker.agent import compliance_agent

        compliance_agent = importlib.reload(compliance_agent)

        deadline = compliance_agent.regulation_deadline(
            "RBI requires banks to update KYC controls within 30 days."
        )

        self.assertEqual(deadline, "Within 30 days")

    def test_tracker_infers_regulator_from_pasted_text(self):
        from policy_compliance_tracker.agent import compliance_agent

        compliance_agent = importlib.reload(compliance_agent)
        state = {
            "regulation": "RBI requires banks to update KYC controls within 30 days.",
            "summary": (
                "Summary:\n"
                "- RBI requires banks to update KYC controls within 30 days.\n\n"
                "Compliance Obligations:\n"
                "- Implement banks to update KYC controls.\n\n"
                "Deadlines:\n"
                "- Within 30 days"
            ),
            "mapping": (
                "Impacted Policies:\n"
                "- Information Security Policy\n\n"
                "Required Updates:\n"
                "- Review KYC control coverage."
            ),
            "control_matrix": "No matching controls found in Control Matrix",
            "regulation_metadata": {},
        }

        record = compliance_agent.build_impact_tracker_record(state)

        self.assertEqual(record["regulator"], "RBI")
        self.assertEqual(record["due_date"], "Within 30 days")


class RAGEvaluationTests(ProjectTestCase):
    def test_evaluation_selector_keeps_strong_secondary_evidence(self):
        from policy_compliance_tracker.retrieval import rag_eval

        rag_eval = importlib.reload(rag_eval)

        candidates = [
            {"source": "policy", "lexical_score": 15, "hybrid_score": 40},
            {"source": "control", "lexical_score": 15, "hybrid_score": 36},
            {"source": "privacy", "lexical_score": 0, "hybrid_score": 10},
        ]

        selected = rag_eval.select_evaluation_candidates(candidates)

        self.assertEqual([candidate["source"] for candidate in selected], ["policy", "control"])

    def test_evaluation_selector_keeps_domain_supported_secondary_evidence(self):
        from policy_compliance_tracker.retrieval import rag_eval

        rag_eval = importlib.reload(rag_eval)
        candidates = [
            {"source": "control", "lexical_score": 7, "hybrid_score": 24},
            {"source": "policy", "lexical_score": 6, "hybrid_score": 22},
        ]

        selected = rag_eval.select_evaluation_candidates(candidates)

        self.assertEqual([candidate["source"] for candidate in selected], ["control", "policy"])

    def test_source_overlap_scores_partial_and_extra_matches(self):
        from policy_compliance_tracker.retrieval import rag_eval

        rag_eval = importlib.reload(rag_eval)

        expected = {"policy", "control"}
        partial = {"policy"}
        extra = {"policy", "control", "unrelated"}

        self.assertEqual(rag_eval.source_overlap_score(expected, partial), 0.5)
        self.assertAlmostEqual(
            rag_eval.source_overlap_score(expected, extra),
            2 / 3,
        )


class FeedIngestionTests(ProjectTestCase):
    def test_feed_download_registers_source_metadata_and_runs_analysis(self):
        from policy_compliance_tracker.ingestion import regulatory_feeds

        regulatory_feeds = importlib.reload(regulatory_feeds)
        feed = {
            "name": "Example Regulator",
            "regulator": "EXR",
            "url": "https://example.test/update.pdf",
        }

        with patch.object(regulatory_feeds, "fetch_url", return_value=b"%PDF-1.4 demo"):
            with patch.object(
                regulatory_feeds,
                "analyze_feed_file",
                return_value={"status": "processed", "tracker_id": "RIT-TEST-002", "change": "Processed"},
            ) as analyze_mock:
                results = regulatory_feeds.ingest_feeds(
                    [feed],
                    destination_dir=str(self.root / "regulations"),
                    analyze_downloads=True,
                )

        self.assertEqual(results[0]["status"], "downloaded")
        self.assertEqual(results[0]["analysis_status"], "processed")
        analyze_mock.assert_called_once()

        record = self.store.fetch_processing_history(limit=1)[0]
        self.assertEqual(record["feed_name"], "Example Regulator")
        self.assertEqual(record["source_url"], "https://example.test/update.pdf")
        self.assertEqual(record["regulator_source"], "EXR")


class RegulationMonitorTests(ProjectTestCase):
    def test_scan_processes_first_pdf_and_marks_exact_duplicate(self):
        from policy_compliance_tracker.ingestion import regulation_monitor

        regulation_monitor = importlib.reload(regulation_monitor)
        regulation_dir = self.root / "regulations"
        regulation_dir.mkdir()
        (regulation_dir / "a.pdf").write_bytes(b"same regulation bytes")
        (regulation_dir / "b.pdf").write_bytes(b"same regulation bytes")

        def fake_analyze(regulation_text, regulation_metadata=None, persist=False, file_id=None):
            metadata = regulation_metadata or {}
            result = {
                "summary": "Summary:\n- MFA threshold update.\n\nCompliance Obligations:\n- Implement MFA.\n\nDeadlines:\n- Immediate.",
                "mapping": "Impacted Policies:\n- Information Security Policy\n\nRequired Updates:\n- Add transaction MFA coverage.",
                "control_matrix": "Impacted Controls:\n- C001 Multi-Factor Authentication\n\nControl Gaps:\n- Existing control does not mention high-value transactions.\n\nRecommended Enhancements:\n- Add transaction scope.",
                "impact_tracker": "",
                "tracker_record": {
                    "regulation_title": metadata.get("title"),
                    "regulator": metadata.get("regulator"),
                    "version": metadata.get("version"),
                    "status": "Open",
                    "owner": "GRC Team",
                    "priority": "Medium",
                    "risk_score": 12,
                    "risk_score_max": 25,
                    "confidence": 85,
                    "regulatory_update": "MFA threshold update.",
                    "compliance_obligation": "Implement MFA.",
                    "impacted_policy": "Information Security Policy",
                    "required_policy_update": "Add transaction MFA coverage.",
                    "policy_change_required": True,
                    "policy_change_reason": "Information Security Policy needs transaction MFA coverage.",
                    "impacted_control": "C001 Multi-Factor Authentication",
                    "control_gap": "Existing control does not mention high-value transactions.",
                    "recommended_enhancement": "Add transaction scope.",
                    "source_path": metadata.get("source_path"),
                },
            }
            if persist:
                saved = self.store.save_analysis_result(
                    result,
                    regulation_text,
                    metadata=metadata,
                    file_id=file_id,
                )
                result["tracker_record"].update(saved)
            return result

        with patch.object(
            regulation_monitor,
            "extract_pdf_text",
            return_value="RBI requires multi-factor authentication for transactions above INR 10,000.",
        ):
            with patch.object(regulation_monitor, "analyze_regulation_text", side_effect=fake_analyze):
                results = regulation_monitor.scan_regulation_directory(str(regulation_dir))

        statuses = sorted(result["status"] for result in results)
        self.assertEqual(statuses, ["duplicate", "processed"])

        entries = self.store.fetch_tracker_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["policy_change_required"], 1)
        self.assertIn("Information Security Policy", entries[0]["impacted_policy"])


if __name__ == "__main__":
    unittest.main()
