"""Run the reproducible research suite and write one paper-ready report.

Run from the repository root:
    python research/run_gap_suite.py

The suite runs the project retrieval comparison, component ablation, labelled
end-to-end mapping evaluation, ClaimRAG-LAW legal retrieval evaluation, and
the full ClaimRAG-LAW pipeline evaluation. Benchmark cases are never persisted
to the tracker database by this runner.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "research" / "results"


COMMANDS = [
    ("retrieval comparison", "retrieval_experiment_", ["research/run_experiments.py"]),
    ("component ablation", "retrieval_ablation_", ["research/run_ablation.py"]),
    ("labelled end-to-end mapping", "end_to_end_mapping_", ["research/evaluate_end_to_end.py"]),
    ("ClaimRAG legal retrieval", "claimrag_evaluation_", ["research/evaluate_claimrag.py"]),
    ("ClaimRAG full pipeline", "claimrag_pipeline_", ["research/evaluate_claimrag_pipeline.py"]),
]


def latest_result(prefix: str, started_at: float | None = None) -> Path:
    candidates = sorted(RESULTS.glob(f"{prefix}*.json"), key=lambda item: item.stat().st_mtime)
    if started_at is not None:
        fresh = [item for item in candidates if item.stat().st_mtime >= started_at]
        if fresh:
            candidates = fresh
    if not candidates:
        raise FileNotFoundError(f"No result found for prefix {prefix!r}")
    return candidates[-1]


def run_command(label: str, prefix: str, command: list[str]) -> dict[str, Any]:
    before = max((item.stat().st_mtime for item in RESULTS.glob(f"{prefix}*.json")), default=0.0)
    completed = subprocess.run(  # nosec B603
        [sys.executable, *command],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result_path = latest_result(prefix, before)
    return {
        "label": label,
        "command": " ".join(command),
        "result": result_path,
        "stdout_tail": completed.stdout[-1000:],
    }


def load_result(entry: dict[str, Any]) -> dict[str, Any]:
    return json.loads(entry["result"].read_text(encoding="utf-8"))


def json_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def build_report(entries: list[dict[str, Any]], test_output: str, created_at: str) -> str:
    loaded = {entry["label"]: load_result(entry) for entry in entries}
    retrieval = loaded["retrieval comparison"].get("summary", {})
    ablation = loaded["component ablation"].get("summary", {})
    end_to_end = loaded["labelled end-to-end mapping"].get("summary", {})
    claimrag = loaded["ClaimRAG legal retrieval"]
    pipeline = loaded["ClaimRAG full pipeline"].get("pipeline_summary", {})
    hybrid = retrieval.get("rag_hybrid", {})
    full_hybrid = ablation.get("full_hybrid", {})

    lines = [
        "# Reproducible Research-Gap Evaluation",
        "",
        f"Generated: `{created_at}`",
        "",
        "This report connects the project's legal-evidence benchmark to the complete in-memory compliance workflow. ClaimRAG-LAW supplies legal retrieval and claim labels; it does not provide gold labels for organization-specific policies or controls.",
        "",
        "## Evidence artifacts",
        "",
    ]
    for entry in entries:
        try:
            artifact = entry["result"].relative_to(ROOT).as_posix()
        except ValueError:
            artifact = str(entry["result"])
        lines.append(f"- {entry['label']}: `{artifact}`")

    lines.extend(
        [
            "",
            "## Main results",
            "",
            "| Evaluation | Result |",
            "|---|---:|",
            f"| Retrieval cases | {json_value(hybrid.get('cases', 'n/a'))} |",
            f"| Hybrid retrieval mean F1 | {json_value(hybrid.get('mean_f1', 'n/a'))} |",
            f"| Full ablation cases | {json_value(full_hybrid.get('cases', 'n/a'))} |",
            f"| End-to-end mapping accuracy | {json_value(end_to_end.get('mean_mapping_accuracy', 'n/a'))} |",
            f"| End-to-end obligation coverage | {json_value(end_to_end.get('mean_obligation_coverage', 'n/a'))} |",
            f"| ClaimRAG legal evidence-hit rate | {json_value(claimrag.get('rag_summary', {}).get('evidence_hit_rate_at_threshold_0_5', 'n/a'))} |",
            f"| ClaimRAG full-pipeline cases | {json_value(pipeline.get('cases', 'n/a'))} |",
            f"| Pipeline tracker-schema completion | {json_value(pipeline.get('tracker_schema_completion_rate', 'n/a'))} |",
            f"| Pipeline evidence-chain completion | {json_value(pipeline.get('evidence_chain_completion_rate', 'n/a'))} |",
            f"| Candidate policy-alignment rate | {json_value(pipeline.get('candidate_policy_alignment_rate', 'n/a'))} |",
            f"| Candidate control-alignment rate | {json_value(pipeline.get('candidate_control_alignment_rate', 'n/a'))} |",
            f"| Human-review gate rate | {json_value(pipeline.get('review_gate_rate', 'n/a'))} |",
            "",
            "## Interpretation",
            "",
            "The implementation now demonstrates a reproducible end-to-end path from legal text to structured obligations, evidence records, candidate policy/control relationships, mapping status, and human-review escalation. The policy/control relationships remain candidate alignments, so these results do not claim legal compliance certification or externally validated organization-specific mappings.",
            "",
            "## Test suite",
            "",
            "```text",
            test_output.strip(),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all research evaluations and write one report.")
    parser.add_argument("--output-dir", type=Path, default=RESULTS)
    args = parser.parse_args()
    args.output_dir.resolve().mkdir(parents=True, exist_ok=True)

    entries = [run_command(*item) for item in COMMANDS]
    tests = subprocess.run(  # nosec B603
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    created_at = datetime.now(timezone.utc).isoformat()
    test_output = "\n".join(part for part in (tests.stdout, tests.stderr) if part)
    report = build_report(entries, test_output, created_at)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir.resolve() / f"gap_evaluation_report_{timestamp}.md"
    output.write_text(report, encoding="utf-8")
    print(json.dumps({"report": str(output), "tests": test_output[-2000:].strip()}, indent=2))


if __name__ == "__main__":
    main()
