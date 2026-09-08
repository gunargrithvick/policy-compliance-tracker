import unittest

from research.evaluate_claimrag import overlap, summarize_claim_labels, tokens


class ClaimRAGEvaluationTests(unittest.TestCase):
    def test_token_overlap_is_bounded_and_uses_shared_terms(self):
        score = overlap(
            "The controller must notify the supervisory authority within 72 hours",
            "A controller must notify the supervisory authority within 72 hours",
        )
        self.assertGreaterEqual(score, 0.9)
        self.assertLessEqual(score, 1.0)
        self.assertIn("controller", tokens("The controller must notify"))

    def test_claim_summary_preserves_nonstandard_labels(self):
        summary = summarize_claim_labels(
            [
                {
                    "claims": [
                        {
                            "claim_correctness": "Correct",
                            "claim_entailment": "Entailment",
                        },
                        {
                            "claim_correctness": "",
                            "claim_entailment": "Doesn't Make Sense",
                        },
                    ]
                }
            ]
        )
        self.assertEqual(summary["claims"], 2)
        self.assertEqual(summary["missing_or_nonstandard_label_counts"]["claim_correctness"], 1)
        self.assertEqual(summary["missing_or_nonstandard_label_counts"]["claim_entailment"], 1)


if __name__ == "__main__":
    unittest.main()
