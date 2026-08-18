import unittest


class MappingQualityTests(unittest.TestCase):
    def test_topic_gate_prevents_cross_domain_policy_mapping(self):
        from policy_compliance_tracker.agent import compliance_agent

        policies = [
            {"name": "Data Privacy Policy", "text": "privacy policy reviewed annually"},
            {"name": "Information Security Policy", "text": "security policy reviewed annually"},
        ]

        privacy = compliance_agent.select_relevant_policies(
            "privacy policy reviewed annually",
            policies,
        )
        security = compliance_agent.select_relevant_policies(
            "security policy reviewed annually",
            policies,
        )

        self.assertEqual([policy["name"] for policy in privacy], ["Data Privacy Policy"])
        self.assertEqual([policy["name"] for policy in security], ["Information Security Policy"])

    def test_topic_gate_prevents_generic_access_from_selecting_controls(self):
        from policy_compliance_tracker.agent import compliance_agent

        controls = [
            {"id": "C001", "name": "Multi-Factor Authentication", "description": "Require MFA for privileged accounts."},
            {"id": "C003", "name": "Access Review", "description": "Conduct quarterly access reviews."},
        ]

        selected = compliance_agent.select_relevant_controls(
            "access to personal data restricted to authorized personnel",
            controls,
        )

        self.assertEqual(selected, [])

    def test_low_evidence_result_requires_review(self):
        from policy_compliance_tracker.agent import compliance_agent

        result = compliance_agent.analyze_regulation(
            "passwords changed periodically",
            persist=False,
            analysis_provider="rule_based",
        )
        record = result["tracker_record"]

        self.assertLess(record["retrieval_diagnostics"]["evidence_quality"], 35)
        self.assertTrue(record["review_required"])

    def test_unspecified_obligation_does_not_leak_into_action_text(self):
        from policy_compliance_tracker.agent import compliance_agent

        result = compliance_agent.analyze_regulation(
            "privacy policy reviewed annually",
            persist=False,
            analysis_provider="rule_based",
        )
        record = result["tracker_record"]

        self.assertNotIn("not specified in provided regulation", record["required_policy_update"].lower())
        self.assertIn("new regulatory requirement", record["required_policy_update"].lower())

    def test_hybrid_retrieval_keeps_supported_policy_control_pair(self):
        from policy_compliance_tracker.retrieval.rag_eval import select_evaluation_candidates

        candidates = [
            {
                "source": "data/policies\\Information_Security_Policy.pdf",
                "lexical_score": 10,
                "hybrid_score": 20,
            },
            {
                "source": "data/controls\\Core_Control_Matrix.pdf",
                "lexical_score": 6,
                "hybrid_score": 10,
            },
        ]

        selected = select_evaluation_candidates(candidates)

        self.assertEqual(len(selected), 2)


if __name__ == "__main__":
    unittest.main()
