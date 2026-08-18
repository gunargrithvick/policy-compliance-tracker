"""Generate the current manual-review artifact for the full evaluation set."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from policy_compliance_tracker.agent import compliance_agent  # noqa: E402
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"Missing project dependency '{exc.name}'. Install dependencies with: "
        "python -m pip install -r requirements.txt"
    ) from exc


DEFAULT_CASES = ROOT / "research" / "evaluation_cases.json"
DEFAULT_OUTPUT_DIR = ROOT / "research" / "results"
KNOWN_POLICIES = [
    "Data Privacy Policy",
    "Information Security Policy",
    "Business Continuity Policy",
    "Data Governance Policy",
    "Financial Crime Policy",
]

EDGE_CASES = {
    "no_matching_policy": "The organization shall maintain quarterly landscaping records for office grounds.",
    "no_matching_control": "The organization must document data lineage and assign a data owner for information assets.",
    "no_explicit_deadline": "The organization must record and manage user consent for personal data processing.",
    "irrelevant_regulation": "The organization shall maintain aquarium water quality records and feeding schedules.",
    "multiple_policies": "The organization must protect personal data and secure access to critical systems.",
    "weak_retrieval_evidence": "The organization shall appoint a lunar dust safety officer for off-world operations.",
}


def load_cases(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)
    if not cases:
        raise ValueError("The evaluation dataset is empty.")
    return cases


def extract_policies(text: str) -> List[str]:
    lowered = (text or "").lower()
    return [policy for policy in KNOWN_POLICIES if policy.lower() in lowered]


def extract_controls(text: str) -> List[str]:
    return sorted(set(re.findall(r"\bC\d{3}\b", text or "")))


def source_set(values: Iterable[str]) -> set[str]:
    return {value.lower() for value in values}


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = compliance_agent.analyze_regulation(
            case["query"],
            persist=False,
            analysis_provider="rule_based",
        )
        record = result.get("tracker_record") or {}
        diagnostics = record.get("retrieval_diagnostics") or {}
        returned_policies = extract_policies(record.get("impacted_policy") or "")
        returned_controls = extract_controls(record.get("impacted_control") or "")
        expected_policies = case.get("expected_policies", [])
        expected_controls = case.get("expected_controls", [])
        failure_flags = []
        if expected_policies and not (source_set(expected_policies) & source_set(returned_policies)):
            failure_flags.append("expected_policy_not_returned")
        if expected_controls and not (source_set(expected_controls) & source_set(returned_controls)):
            failure_flags.append("expected_control_not_returned")
        if (expected_policies or expected_controls) and not record.get("evidence_records"):
            failure_flags.append("missing_evidence_for_expected_mapping")

        return {
            "case_id": case["case_id"],
            "category": case.get("category", "unspecified"),
            "query": case["query"],
            "expected_policies": expected_policies,
            "returned_policies": returned_policies,
            "expected_controls": expected_controls,
            "returned_controls": returned_controls,
            "priority": record.get("priority"),
            "risk_score": record.get("risk_score"),
            "review_required": bool(record.get("review_required")),
            "review_reason": record.get("review_reason") or "",
            "evidence_quality": diagnostics.get("evidence_quality", 0.0),
            "evidence_count": len(record.get("evidence_records") or []),
            "evidence_records": record.get("evidence_records") or [],
            "retrieval_diagnostics": diagnostics,
            "policy_change_required": bool(record.get("policy_change_required")),
            "owner": record.get("owner"),
            "due_date": record.get("due_date"),
            "status": record.get("status"),
            "failure_flags": failure_flags,
            "error": None,
        }
    except Exception as exc:  # keep one failed case visible in the artifact
        return {
            "case_id": case["case_id"],
            "category": case.get("category", "unspecified"),
            "query": case["query"],
            "failure_flags": ["analysis_error"],
            "error": str(exc)[:400],
        }


def edge_review_record(label: str, query: str) -> Dict[str, Any]:
    result = compliance_agent.analyze_regulation(
        query,
        persist=False,
        analysis_provider="rule_based",
    )
    record = result.get("tracker_record") or {}
    diagnostics = record.get("retrieval_diagnostics") or {}
    return {
        "input": query,
        "policy": record.get("impacted_policy"),
        "control": record.get("impacted_control"),
        "priority": record.get("priority"),
        "risk_score": record.get("risk_score"),
        "due_date": record.get("due_date"),
        "review_required": bool(record.get("review_required")),
        "review_reason": record.get("review_reason") or "",
        "evidence_quality": diagnostics.get("evidence_quality", 0.0),
        "evidence_count": len(record.get("evidence_records") or []),
    }


def validate_edge_behavior(label: str, record: Dict[str, Any]) -> List[str]:
    flags = []
    if label in {"no_matching_policy", "irrelevant_regulation", "weak_retrieval_evidence"}:
        if record.get("policy") != "Not available" or record.get("control") != "Not available":
            flags.append("unexpected_mapping_for_unmatched_case")
        if not record.get("review_required"):
            flags.append("unmatched_case_not_sent_to_review")
    elif label == "no_matching_control":
        if record.get("control") != "Not available":
            flags.append("unexpected_control_mapping")
        if not record.get("review_required"):
            flags.append("missing_control_case_not_sent_to_review")
    elif label == "no_explicit_deadline":
        if record.get("due_date") != "Not specified in provided regulation":
            flags.append("unexpected_deadline")
    elif label == "multiple_policies":
        if ";" not in (record.get("policy") or ""):
            flags.append("multiple_policy_case_did_not_return_multiple_policies")
        if not record.get("review_required"):
            flags.append("multiple_policy_case_not_sent_to_review")
    return flags


def find_latest_result(pattern: str) -> str | None:
    matches = sorted((DEFAULT_OUTPUT_DIR).glob(pattern), key=lambda path: path.stat().st_mtime)
    return str(matches[-1]) if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the full manual-review artifact.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    cases = load_cases(args.cases.resolve())
    compliance_agent.USE_LLM_ANALYSIS = False
    case_results = [evaluate_case(case) for case in cases]

    edge_case_results = {}
    edge_failure_flags = []
    for label, query in EDGE_CASES.items():
        record = edge_review_record(label, query)
        record["failure_flags"] = validate_edge_behavior(label, record)
        if record["failure_flags"]:
            edge_failure_flags.append({"case": label, "flags": record["failure_flags"]})
        edge_case_results[label] = record

    hybrid_path = find_latest_result("retrieval_experiment_*.json")
    hybrid_summary = {}
    hybrid_missed = []
    hybrid_unexpected = 0
    if hybrid_path:
        hybrid_payload = json.loads(Path(hybrid_path).read_text(encoding="utf-8"))
        hybrid_summary = hybrid_payload.get("summary", {}).get("rag_hybrid", {})
        hybrid_rows = [
            row for row in hybrid_payload.get("case_results", [])
            if row.get("method") == "rag_hybrid"
        ]
        hybrid_missed = [row["case_id"] for row in hybrid_rows if row.get("missing_sources")]
        hybrid_unexpected = sum(bool(row.get("unexpected_sources")) for row in hybrid_rows)

    end_to_end_path = find_latest_result("end_to_end_mapping_*.json")
    end_to_end_summary = {}
    if end_to_end_path:
        end_to_end_summary = json.loads(Path(end_to_end_path).read_text(encoding="utf-8")).get("summary", {})

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"final_manual_review_{timestamp}.json"
    payload = {
        "created_at": timestamp,
        "dataset": "research/evaluation_cases.json",
        "cases": len(case_results),
        "label_status": "project-maintained-pending-human-review",
        "manual_failure_count": sum(bool(row.get("failure_flags")) for row in case_results),
        "manual_review_flag_count": sum(bool(row.get("failure_flags")) for row in case_results),
        "manual_review_flag_scope": "Broader case-level mapping, evidence, and review flags; not the retrieval error count.",
        "retrieval_error_count": hybrid_summary.get("error_cases"),
        "manual_checks": [
            "policy_mapping",
            "control_mapping",
            "risk_priority_recorded",
            "evidence_source_and_excerpt",
            "weak_evidence_review_gate",
            "unsupported_action_text",
            "edge_case_workflows",
        ],
        "retrieval_experiment": {
            "file": hybrid_path,
            "method": "rag_hybrid",
            "summary": hybrid_summary,
            "miss_count": len(hybrid_missed),
            "missed_case_ids": hybrid_missed,
            "unexpected_source_count": hybrid_unexpected,
        },
        "end_to_end_evaluation": {
            "file": end_to_end_path,
            "summary": end_to_end_summary,
        },
        "retrieval_manual_review": {
            "method": "rag_hybrid",
            "miss_count": len(hybrid_missed),
            "missed_case_ids": hybrid_missed,
            "unexpected_source_count": hybrid_unexpected,
        },
        "case_results": case_results,
        "edge_case_results": edge_case_results,
        "edge_failure_flags": edge_failure_flags,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "cases": payload["cases"],
        "manual_failure_count": payload["manual_failure_count"],
        "edge_failure_count": len(edge_failure_flags),
        "retrieval_miss_count": payload["retrieval_manual_review"]["miss_count"],
        "json": str(output_path),
    }, indent=2))


if __name__ == "__main__":
    main()
