import tempfile
import unittest
from pathlib import Path

from research.run_gap_suite import build_report


class GapSuiteTests(unittest.TestCase):
    def test_report_mentions_candidate_mapping_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entries = []
            labels = [
                ("retrieval comparison", "retrieval_experiment_", {"summary": {"cases": 1, "rag_hybrid": {"f1": 1.0}}}),
                ("component ablation", "retrieval_ablation_", {"summary": {"cases": 1}}),
                ("labelled end-to-end mapping", "end_to_end_mapping_", {"summary": {"mapping_accuracy": 1.0, "obligation_coverage": 1.0}}),
                ("ClaimRAG legal retrieval", "claimrag_evaluation_", {"rag_summary": {"evidence_hit_rate_at_threshold_0_5": 1.0}}),
                ("ClaimRAG full pipeline", "claimrag_pipeline_", {"pipeline_summary": {"cases": 1, "tracker_schema_completion_rate": 1.0, "evidence_chain_completion_rate": 1.0, "candidate_policy_alignment_rate": 1.0, "candidate_control_alignment_rate": 0.0, "review_gate_rate": 1.0}}),
            ]
            for index, (label, prefix, payload) in enumerate(labels):
                path = root / f"{prefix}{index}.json"
                path.write_text(__import__("json").dumps(payload), encoding="utf-8")
                entries.append({"label": label, "result": path})
            report = build_report(entries, "43 passed", "now")
            self.assertIn("candidate alignments", report)
            self.assertIn("43 passed", report)


if __name__ == "__main__":
    unittest.main()
