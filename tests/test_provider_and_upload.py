import os
import unittest
from pathlib import Path
from unittest.mock import patch


class ProviderAndUploadTests(unittest.TestCase):
    def test_uploaded_pdf_extracts_text_without_writing_a_file(self):
        from policy_compliance_tracker.ingestion.regulation_monitor import extract_pdf_bytes

        pdf_path = Path(__file__).resolve().parents[1] / "data" / "policies" / "Data_Privacy_Policy.pdf"
        text = extract_pdf_bytes(pdf_path.read_bytes())

        self.assertIn("privacy", text.lower())
        with self.assertRaises(ValueError):
            extract_pdf_bytes(b"not a pdf")

    def test_gemini_adapter_uses_key_and_parses_response_text(self):
        from policy_compliance_tracker.providers.analysis_providers import invoke_provider

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}, clear=False):
            with patch(
                "policy_compliance_tracker.providers.analysis_providers._post_json",
                return_value={
                    "candidates": [
                        {"content": {"parts": [{"text": "grounded response"}]}}
                    ]
                },
            ) as request_mock:
                response = invoke_provider("gemini", "test prompt")

        self.assertEqual(response.content, "grounded response")
        self.assertEqual(response.model, "test-model")
        self.assertEqual(request_mock.call_args.args[0], "gemini")
        self.assertEqual(request_mock.call_args.args[3]["generationConfig"]["temperature"], 0)

    def test_gemini_adapter_requires_key(self):
        from policy_compliance_tracker.providers.analysis_providers import ProviderError, invoke_provider

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with self.assertRaises(ProviderError):
                invoke_provider("gemini", "test prompt")


if __name__ == "__main__":
    unittest.main()
