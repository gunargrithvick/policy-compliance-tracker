import unittest

from research.evaluate_claimrag_pipeline import (
    evidence_chain_complete,
    summarize_pipeline,
    tracker_schema_complete,
)


class ClaimRAGPipelineTests(unittest.TestCase):
    def test_tracker_schema_requires_auditable_components(self):
        tracker = {
            "obligations_structured": [],
            "evidence_records": [],
            "mapping_graph": [],
            "claim_evidence": {},
            "mapping_validation": {},
            "review_required": True,
        }
        self.assertTrue(tracker_schema_complete(tracker))
        self.assertFalse(tracker_schema_complete({"review_required": True}))

    def test_evidence_chain_requires_source_and_verified_claim(self):
        tracker = {
            "obligations_structured": [
                {"obligation_id": "OBL-001", "validation_status": "source_grounded"}
            ],
            "evidence_records": [
                {
                    "evidence_type": "regulation",
                    "obligation_id": "OBL-001",
                    "verification_status": "source_grounded",
                }
            ],
            "claim_evidence": {
                "claims": [
                    {"claim_id": "OBL-001", "status": "verified_source_span"}
                ]
            },
        }
        self.assertTrue(evidence_chain_complete(tracker))
        tracker["claim_evidence"]["claims"][0]["status"] = "unsupported"
        self.assertFalse(evidence_chain_complete(tracker))

    def test_summary_reports_structural_completion_rates(self):
        summary = summarize_pipeline(
            [
                {
                    "obligations_extracted": 1,
                    "source_grounded_obligations": 1,
                    "candidate_policy_count": 1,
                    "candidate_control_count": 0,
                    "mapping_validation_status": "candidate_alignment",
                    "review_required": True,
                    "tracker_schema_complete": True,
                    "evidence_chain_complete": True,
                    "latency_ms": 10,
                }
            ]
        )
        self.assertEqual(summary["tracker_schema_completion_rate"], 1.0)
        self.assertEqual(summary["evidence_chain_completion_rate"], 1.0)
        self.assertEqual(summary["review_gate_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
