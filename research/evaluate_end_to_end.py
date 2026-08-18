"""Evaluate policy/control mapping on the labelled compliance cases.

Run from the repository root:
    python research/evaluate_end_to_end.py
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from policy_compliance_tracker.agent import compliance_agent  # noqa: E402
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"Missing project dependency '{exc.name}'. Install the project dependencies with: "
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


def load_cases(path):
    with path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)
    if not cases:
        raise ValueError("The evaluation dataset is empty.")
    return cases


def set_scores(expected, actual):
    expected = {value.lower() for value in expected}
    actual = {value.lower() for value in actual}
    true_positive = expected & actual
    precision = len(true_positive) / len(actual) if actual else (1.0 if not expected else 0.0)
    recall = len(true_positive) / len(expected) if expected else (1.0 if not actual else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def extract_policies(text):
    lowered = (text or "").lower()
    return [policy for policy in KNOWN_POLICIES if policy.lower() in lowered]


def extract_controls(text):
    return sorted(set(re.findall(r"\bC\d{3}\b", text or "")))


def evaluate_case(case):
    start = time.perf_counter()
    result = compliance_agent.analyze_regulation(
        case["query"],
        persist=False,
        analysis_provider="rule_based",
    )
    record = result.get("tracker_record") or {}
    policy_text = record.get("impacted_policy") or ""
    control_text = record.get("impacted_control") or ""
    obligation_text = " ".join(
        [
            record.get("compliance_obligation") or "",
            json.dumps(record.get("obligations_structured") or [], default=str),
        ]
    ).lower()
    expected_obligation_terms = [term.lower() for term in case.get("expected_obligation_terms", [])]
    obligation_coverage = (
        sum(term in obligation_text for term in expected_obligation_terms)
        / len(expected_obligation_terms)
        if expected_obligation_terms
        else 1.0
    )
    policy_scores = set_scores(case.get("expected_policies", []), extract_policies(policy_text))
    control_scores = set_scores(case.get("expected_controls", []), extract_controls(control_text))
    mapping_accuracy = mean([policy_scores[2], control_scores[2], obligation_coverage])
    return {
        "case_id": case["case_id"],
        "category": case.get("category", "unspecified"),
        "query": case["query"],
        "policy_precision": round(policy_scores[0], 3),
        "policy_recall": round(policy_scores[1], 3),
        "policy_f1": round(policy_scores[2], 3),
        "control_precision": round(control_scores[0], 3),
        "control_recall": round(control_scores[1], 3),
        "control_f1": round(control_scores[2], 3),
        "obligation_coverage": round(obligation_coverage, 3),
        "mapping_accuracy": round(mapping_accuracy, 3),
        "returned_policies": extract_policies(policy_text),
        "returned_controls": extract_controls(control_text),
        "review_required": bool(record.get("review_required")),
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        "error": None,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate end-to-end policy and control mapping.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    # The labelled experiment evaluates the fast, deterministic project path.
    compliance_agent.USE_LLM_ANALYSIS = False
    rows = []
    for case in load_cases(args.cases):
        try:
            rows.append(evaluate_case(case))
        except Exception as exc:  # keep one failed case from hiding the rest
            rows.append({"case_id": case["case_id"], "query": case["query"], "error": str(exc)[:400]})

    successful = [row for row in rows if not row.get("error")]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"end_to_end_mapping_{timestamp}.json"
    payload = {
        "created_at": timestamp,
        "dataset": "research/evaluation_cases.json",
        "label_status": "project-maintained-pending-human-review",
        "metrics": [
            "policy_precision", "policy_recall", "policy_f1",
            "control_precision", "control_recall", "control_f1",
            "obligation_coverage", "mapping_accuracy", "latency_ms",
        ],
        "summary": {
            "cases": len(rows),
            "successful_cases": len(successful),
            "error_cases": len(rows) - len(successful),
            "mean_mapping_accuracy": round(mean(row["mapping_accuracy"] for row in successful), 3) if successful else 0.0,
            "mean_obligation_coverage": round(mean(row["obligation_coverage"] for row in successful), 3) if successful else 0.0,
            "mean_latency_ms": round(mean(row["latency_ms"] for row in successful), 2) if successful else 0.0,
        },
        "case_results": rows,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "summary": payload["summary"], "json": str(output_path)}, indent=2))


if __name__ == "__main__":
    main()
