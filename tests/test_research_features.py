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

    def test_index_reset_targets_chroma_collection_only(self):
        from policy_compliance_tracker.retrieval import ingest

        with patch("policy_compliance_tracker.retrieval.ingest.Chroma") as chroma:
            ingest.reset_vector_index(object())
            chroma.assert_called_once()
            self.assertEqual(chroma.call_args.kwargs["collection_name"], "langchain")
            chroma.return_value.delete_collection.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
