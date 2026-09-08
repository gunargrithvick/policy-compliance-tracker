"""Run ClaimRAG-LAW passages through the project's full compliance pipeline.

This is a structural integration evaluation, not a policy/control accuracy
benchmark. ClaimRAG-LAW supplies legal retrieval/claim labels, but it does not
provide organization-specific policy or control gold labels. Therefore policy
and control outputs are measured as candidate alignments and review gates.

Run from the repository root:
    python research/evaluate_claimrag_pipeline.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (ROOT, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from policy_compliance_tracker.agent.compliance_agent import analyze_regulation  # noqa: E402
from research.evaluate_claimrag import (  # noqa: E402
    BENCHMARK_DIR,
    DATASET_URL,
    GDPR_SOURCE,
    ensure_benchmark,
    load_records,
)


REQUIRED_TRACKER_FIELDS = {
    "obligations_structured",
    "evidence_records",
    "mapping_graph",
    "claim_evidence",
    "mapping_validation",
    "review_required",
}


def tracker_schema_complete(tracker: dict[str, Any]) -> bool:
    """Return whether the tracker has every auditable pipeline component."""

    return REQUIRED_TRACKER_FIELDS.issubset(tracker) and all(
        tracker.get(field) is not None for field in REQUIRED_TRACKER_FIELDS
    )


def evidence_chain_complete(tracker: dict[str, Any]) -> bool:
    """Check the minimum source-to-claim evidence chain for this case."""

    obligations = tracker.get("obligations_structured") or []
    evidence = tracker.get("evidence_records") or []
    claim_evidence = tracker.get("claim_evidence") or {}
    regulatory_evidence = {
        item.get("obligation_id")
        for item in evidence
        if item.get("evidence_type") == "regulation"
        and item.get("verification_status") == "source_grounded"
    }
    verified_claims = {
        item.get("claim_id")
        for item in claim_evidence.get("claims", [])
        if item.get("status") == "verified_source_span"
    }
    obligation_ids = {
        item.get("obligation_id")
        for item in obligations
        if item.get("obligation_id")
    }
    return bool(obligation_ids) and obligation_ids <= regulatory_evidence and obligation_ids <= verified_claims


def evaluate_pipeline_case(record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one benchmark passage without persisting it to SQLite."""

    metadata = {
        "title": f"ClaimRAG-LAW GDPR passage {record.get('query_id')}",
        "source_path": GDPR_SOURCE,
        "source_url": DATASET_URL,
        "feed_name": "ClaimRAG-LAW",
        "regulator_source": "EU GDPR",
    }
    started = time.perf_counter()
    # The graph prints node timings. Suppress those during batch evaluation so
    # the command output remains a compact summary for the researcher.
    with contextlib.redirect_stdout(io.StringIO()):
        result = analyze_regulation(
            record["relevant_chunk"],
            regulation_metadata=metadata,
            persist=False,
            analysis_provider="rule_based",
        )
    tracker = result.get("tracker_record") or {}
    obligations = tracker.get("obligations_structured") or []
    diagnostics = tracker.get("retrieval_diagnostics") or {}
    validation = tracker.get("mapping_validation") or {}
    return {
        "query_id": record.get("query_id"),
        "answer_correctness_label": record.get("answer_correctness"),
        "input_characters": len(record.get("relevant_chunk", "")),
        "obligations_extracted": len(obligations),
        "source_grounded_obligations": sum(
            item.get("validation_status") == "source_grounded"
            for item in obligations
        ),
        "candidate_policy_count": diagnostics.get("selected_policies", 0),
        "candidate_control_count": diagnostics.get("selected_controls", 0),
        "mapping_edge_count": len(tracker.get("mapping_graph") or []),
        "mapping_validation_status": validation.get("status"),
        "review_required": bool(tracker.get("review_required")),
        "tracker_schema_complete": tracker_schema_complete(tracker),
        "evidence_chain_complete": evidence_chain_complete(tracker),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def summarize_pipeline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize structural completion and review-gate behavior."""

    count = len(rows)

    def rate(field: str) -> float:
        return round(sum(bool(row.get(field)) for row in rows) / count, 3) if count else 0.0

    obligations = sum(row["obligations_extracted"] for row in rows)
    grounded = sum(row["source_grounded_obligations"] for row in rows)
    return {
        "cases": count,
        "cases_with_obligations": sum(row["obligations_extracted"] > 0 for row in rows),
        "obligations_extracted": obligations,
        "source_grounded_obligation_rate": round(grounded / obligations, 3) if obligations else 0.0,
        "tracker_schema_completion_rate": rate("tracker_schema_complete"),
        "evidence_chain_completion_rate": rate("evidence_chain_complete"),
        "candidate_policy_alignment_rate": round(
            sum(row["candidate_policy_count"] > 0 for row in rows) / count, 3
        ) if count else 0.0,
        "candidate_control_alignment_rate": round(
            sum(row["candidate_control_count"] > 0 for row in rows) / count, 3
        ) if count else 0.0,
        "review_gate_rate": rate("review_required"),
        "mapping_validation_status_counts": {
            status: sum(row.get("mapping_validation_status") == status for row in rows)
            for status in sorted({row.get("mapping_validation_status") for row in rows})
        },
        "mean_latency_ms": round(
            sum(row["latency_ms"] for row in rows) / count, 2
        ) if count else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ClaimRAG-LAW GDPR passages through the full project pipeline."
    )
    parser.add_argument("--benchmark-dir", type=Path, default=BENCHMARK_DIR)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research" / "results")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optionally evaluate only the first N cases for a quick smoke test.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")

    benchmark_dir = args.benchmark_dir.resolve()
    manifest = ensure_benchmark(benchmark_dir)
    rag_records, _ = load_records(benchmark_dir)
    records = rag_records[: args.limit] if args.limit else rag_records
    rows = [evaluate_pipeline_case(record) for record in records]
    summary = summarize_pipeline(rows)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": manifest,
        "evaluation_mode": "full_pipeline_in_memory_rule_based",
        "scope": (
            "Measures whether verified GDPR passages can flow through obligation "
            "extraction, evidence, candidate policy/control alignment, mapping "
            "validation, and review gating. ClaimRAG-LAW does not provide gold "
            "labels for organization-specific policy/control mappings."
        ),
        "actual_cases_evaluated": len(records),
        "pipeline_summary": summary,
        "case_results": rows,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = output_dir / f"claimrag_pipeline_{timestamp}.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "pipeline_summary": summary}, indent=2))


if __name__ == "__main__":
    main()
