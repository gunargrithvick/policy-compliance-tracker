import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ResearchFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["TRACKER_DB_PATH"] = str(Path(self.tempdir.name) / "tracker.sqlite3")
        from policy_compliance_tracker import config
        from policy_compliance_tracker.storage import tracker_store

        self.config = importlib.reload(config)
        self.store = importlib.reload(tracker_store)
        self.store.init_db()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_structured_research_fields_round_trip_through_sqlite(self):
        saved = self.store.save_tracker_entry(
            {
                "tracker_id": "RIT-RESEARCH-001",
                "regulation_title": "MFA update",
                "status": "Open",
                "priority": "Critical",
                "review_required": True,
                "review_reason": "Critical impact requires human approval before policy action.",
                "analysis_provider": "gemini",
                "obligations_structured": [
                    {"obligation_id": "OBL-001", "text": "Banks must implement MFA immediately."}
                ],
                "evidence_records": [
                    {"evidence_type": "policy", "source": "policy.pdf", "relevance_score": 12}
                ],
                "retrieval_diagnostics": {"strategy": "hybrid", "evidence_quality": 60},
                "mapping_graph": [
                    {"from": "OBL-001", "relation": "mapped_to_policy", "to": "Information Security Policy"}
                ],
            }
        )

        self.assertEqual(saved["review_required"], 1)
        self.assertEqual(saved["analysis_provider"], "gemini")
        self.assertEqual(json.loads(saved["obligations_structured"])[0]["obligation_id"], "OBL-001")
        self.assertEqual(json.loads(saved["retrieval_diagnostics"])["strategy"], "hybrid")
        self.assertEqual(json.loads(saved["mapping_graph"])[0]["relation"], "mapped_to_policy")

    def test_research_metrics_include_f1_and_mrr(self):
        from research.metrics import metric_record

        result = metric_record(
            {
                "case_id": "case-1",
                "category": "test",
                "query": "mfa",
                "expected_sources": ["policy.pdf", "control.pdf"],
            },
            "hybrid",
            ["unrelated.pdf", "policy.pdf", "control.pdf"],
            10,
            0.75,
        )

        self.assertAlmostEqual(result["f1"], 0.8)
        self.assertAlmostEqual(result["mrr"], 0.5)

    def test_source_role_bonus_recognizes_renamed_control_matrices(self):
        from policy_compliance_tracker.retrieval.rag_eval import source_role_bonus

        self.assertGreater(
            source_role_bonus(
                "audit logging controls",
                "data/controls\\Core_Control_Matrix.pdf",
            ),
            0,
        )
        self.assertGreater(
            source_role_bonus(
                "audit logging controls",
                "data/controls\\Supplemental_Control_Matrix.pdf",
            ),
            0,
        )

    def test_obligation_extraction_preserves_explicit_structure(self):
        from policy_compliance_tracker.agent.compliance_agent import extract_regulatory_obligations

        obligations = extract_regulatory_obligations(
            "Under GDPR Article 33, controllers must notify the supervisory authority within 72 hours if a breach occurs."
        )

        self.assertEqual(len(obligations), 1)
        self.assertEqual(obligations[0]["actor"], "controllers")
        self.assertEqual(obligations[0]["action"], "notify")
        self.assertEqual(obligations[0]["target"], "the supervisory authority")
        self.assertEqual(obligations[0]["deadline"], "Within 72 hours")
        self.assertEqual(obligations[0]["condition"], "if a breach occurs")
        self.assertEqual(obligations[0]["validation_status"], "source_grounded")

    def test_non_obligation_fallback_is_not_called_verified(self):
        from policy_compliance_tracker.agent import compliance_agent

        result = compliance_agent.analyze_regulation(
            "A privacy notice exists.",
            persist=False,
            analysis_provider="rule_based",
        )

        self.assertEqual(
            result["tracker_record"]["claim_evidence"]["status"],
            "not_applicable",
        )

    def test_mapping_output_distinguishes_candidate_alignment_from_source_grounding(self):
        from policy_compliance_tracker.agent import compliance_agent

        result = compliance_agent.analyze_regulation(
            "Controllers must delete personal data according to the retention schedule.",
            persist=False,
            analysis_provider="rule_based",
        )
        record = result["tracker_record"]

        self.assertEqual(record["claim_evidence"]["status"], "source_grounded")
        self.assertEqual(record["mapping_validation"]["status"], "candidate_alignment")
        self.assertTrue(record["mapping_graph"])
        self.assertTrue(all(
            edge["validation_status"] == "candidate_alignment"
            for edge in record["mapping_graph"]
            if edge["relation"] in {"mapped_to_policy", "mapped_to_control"}
        ))

    def test_empty_vector_db_bootstraps_from_reference_documents(self):
        from langchain_core.documents import Document

        from policy_compliance_tracker.agent.compliance_agent import _populate_empty_vector_db

        class Collection:
            def count(self):
                return 0

        class EmptyVectorDb:
            def __init__(self):
                self._collection = Collection()
                self.documents = []

            def add_documents(self, documents):
                self.documents.extend(documents)

        vector_db = EmptyVectorDb()
        with patch(
            "policy_compliance_tracker.retrieval.ingest.load_documents",
            return_value=[Document(page_content="Policy evidence for access review.")],
        ):
            _populate_empty_vector_db(vector_db)

        self.assertTrue(vector_db.documents)

    def test_new_research_metrics_are_bounded(self):
        from research.metrics import (
            evidence_coverage,
            obligation_field_completeness,
            unsupported_claim_rate,
        )

        self.assertEqual(
            obligation_field_completeness([{
                "actor": "controllers",
                "action": "notify",
                "target": "authority",
                "condition": None,
                "deadline": "Within 72 hours",
                "source_span": "Controllers must notify authority within 72 hours.",
            }]),
            0.833,
        )
        self.assertEqual(evidence_coverage(4, 3), 0.75)
        self.assertEqual(
            unsupported_claim_rate({"claims": [
                {"claim_type": "regulatory_obligation", "status": "unsupported"},
                {"claim_type": "regulatory_obligation", "status": "verified_source_span"},
            ]}),
            0.5,
        )

    def test_index_reset_targets_chroma_collection_only(self):
        from policy_compliance_tracker.retrieval import ingest

        with patch("policy_compliance_tracker.retrieval.ingest.Chroma") as chroma:
            ingest.reset_vector_index(object())
            chroma.assert_called_once()
            self.assertEqual(chroma.call_args.kwargs["collection_name"], "langchain")
            chroma.return_value.delete_collection.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
