"""Check evaluation labels against the bundled policy and control PDFs.

This is a source-consistency check, not independent legal or expert validation.
Run from the repository root:
    python research/validate_labels.py
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "research" / "evaluation_cases.json"
OUTPUT_DIR = ROOT / "research" / "results"
SOURCE_FILES = {
    "data/policies\\Data_Privacy_Policy.pdf": ROOT / "data" / "policies" / "Data_Privacy_Policy.pdf",
    "data/policies\\Information_Security_Policy.pdf": ROOT / "data" / "policies" / "Information_Security_Policy.pdf",
    "data/policies\\Business_Continuity_Policy.pdf": ROOT / "data" / "policies" / "Business_Continuity_Policy.pdf",
    "data/policies\\Data_Governance_Policy.pdf": ROOT / "data" / "policies" / "Data_Governance_Policy.pdf",
    "data/policies\\Financial_Crime_Policy.pdf": ROOT / "data" / "policies" / "Financial_Crime_Policy.pdf",
    "data/controls\\Core_Control_Matrix.pdf": ROOT / "data" / "controls" / "Core_Control_Matrix.pdf",
    "data/controls\\Supplemental_Control_Matrix.pdf": ROOT / "data" / "controls" / "Supplemental_Control_Matrix.pdf",
}


def normalize(text):
    text = (text or "").lower().replace("multi-factor", "multi factor")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def load_source_text(path):
    return normalize("\n".join(page.extract_text() or "" for page in PdfReader(path).pages))


def contains_phrase(text, phrase):
    return normalize(phrase) in text


def contains_control_id(text, control_id):
    return bool(re.search(
        rf"(?<![a-z0-9]){re.escape(normalize(control_id))}(?![a-z0-9])",
        text,
    ))


def validate_case(case, source_text):
    missing_files = [source for source in case["expected_sources"] if source not in source_text]
    expected_source_text = " ".join(
        source_text.get(source, "") for source in case.get("expected_sources", [])
    )
    missing_policies = [
        policy for policy in case.get("expected_policies", [])
        if not contains_phrase(expected_source_text, policy)
    ]
    control_text = " ".join(
        text for source, text in source_text.items()
        if source.startswith("data/controls\\")
    )
    missing_controls = [
        control for control in case.get("expected_controls", [])
        if not contains_control_id(control_text, control)
    ]
    query_or_source_text = f"{normalize(case['query'])} {expected_source_text}"
    missing_terms = [
        term for term in case.get("expected_obligation_terms", [])
        if not contains_phrase(query_or_source_text, term)
    ]
    source_unsupported_terms = [
        term for term in case.get("expected_obligation_terms", [])
        if not contains_phrase(expected_source_text, term)
    ]
    return {
        "case_id": case["case_id"],
        "status": "consistent" if not (missing_files or missing_policies or missing_controls or missing_terms) else "needs_review",
        "missing_files": missing_files,
        "missing_policies": missing_policies,
        "missing_controls": missing_controls,
        "missing_obligation_terms": missing_terms,
        "source_unsupported_obligation_terms": source_unsupported_terms,
        "label_status": case.get("label_status"),
    }


def main():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    source_text = {
        source: load_source_text(path)
        for source, path in SOURCE_FILES.items()
        if path.exists()
    }
    rows = [validate_case(case, source_text) for case in cases]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"label_consistency_{timestamp}.json"
    consistent = sum(row["status"] == "consistent" for row in rows)
    payload = {
        "created_at": timestamp,
        "review_type": "source_consistency_check",
        "independent_expert_validation": False,
        "dataset": str(CASES_PATH.relative_to(ROOT)),
        "source_files": sorted(source_text),
        "summary": {
            "cases": len(rows),
            "consistent_cases": consistent,
            "needs_review_cases": len(rows) - consistent,
            "cases_with_source_unsupported_obligation_terms": sum(
                bool(row["source_unsupported_obligation_terms"]) for row in rows
            ),
        },
        "case_results": rows,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"summary": payload["summary"], "json": str(output_path)}, indent=2))


if __name__ == "__main__":
    main()
