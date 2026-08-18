import unittest
import json
from pathlib import Path
from unittest.mock import patch

from research.keyword_baseline import score_source
from research.metrics import metric_record
from research.run_experiments import run_method_cases
from research.validate_labels import validate_case


class ResearchEvaluationTests(unittest.TestCase):
    def test_labelled_dataset_has_expected_fields(self):
        path = Path(__file__).resolve().parents[1] / "research" / "evaluation_cases.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 200)
        self.assertTrue(all(case["case_id"] and "expected_sources" in case for case in cases))
        self.assertTrue(
            all(
                case.get("expected_policies") is not None
                and case.get("expected_controls") is not None
                and case.get("expected_obligation_terms") is not None
                for case in cases
            )
        )

    def test_keyword_score_is_based_on_query_overlap(self):
        self.assertGreater(
            score_source("authentication for privileged accounts", "Require authentication for privileged accounts."),
            0,
        )
        self.assertEqual(score_source("encryption", "Quarterly access review."), 0)

    def test_metric_record_exposes_missing_and_unexpected_sources(self):
        case = {
            "case_id": "case-1",
            "category": "test",
            "query": "query",
            "expected_sources": ["policy.pdf", "control.pdf"],
        }
        result = metric_record(
            case,
            "keyword_baseline",
            ["policy.pdf", "unrelated.pdf"],
            2.5,
            0.5,
        )
        self.assertEqual(result["error_type"], "mixed")
        self.assertEqual(result["missing_sources"], ["control.pdf"])
        self.assertEqual(result["unexpected_sources"], ["unrelated.pdf"])

    def test_latency_phases_restart_for_each_method(self):
        cases = [{"case_id": "case-1", "query": "query", "expected_sources": ["policy.pdf"]}]
        with patch("research.run_experiments.evaluate_rag", return_value={"method": "rag_hybrid", "latency_ms": 1}), \
             patch("research.run_experiments.evaluate_semantic", return_value={"method": "semantic_top_k", "latency_ms": 2}), \
             patch("research.run_experiments.evaluate_keyword", return_value={"method": "keyword_baseline", "latency_ms": 3}):
            for method in ("rag_hybrid", "semantic_top_k", "keyword_baseline"):
                rows = run_method_cases(cases, method)
                self.assertEqual(rows[0]["latency_phase"], "cold_start")

    def test_label_validation_separates_query_terms_from_source_terms(self):
        case = {
            "case_id": "mfa-high-value-transactions",
            "query": "multi factor authentication for high value transactions",
            "expected_sources": ["data/policies\\Information_Security_Policy.pdf"],
            "expected_policies": ["Information Security Policy"],
            "expected_controls": [],
            "expected_obligation_terms": ["authentication", "transactions"],
        }
        result = validate_case(
            case,
            {"data/policies\\Information_Security_Policy.pdf": "information security policy authentication access"},
        )
        self.assertEqual(result["status"], "consistent")
        self.assertEqual(result["source_unsupported_obligation_terms"], ["transactions"])


if __name__ == "__main__":
    unittest.main()
