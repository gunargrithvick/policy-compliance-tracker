"""Run the controlled retrieval-component ablation on the 200-case set.

Run from the repository root after building the Chroma index:
    python research/run_ablation.py
"""

import argparse
import csv
import json
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (ROOT, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

try:
    from policy_compliance_tracker.retrieval.rag_eval import (  # noqa: E402
        ABLATION_VARIANTS,
        EVAL_CANDIDATE_SOURCES,
        context_relevance,
        retrieve_ablation_docs,
    )
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"Missing project dependency '{exc.name}'. Install dependencies with: "
        "python -m pip install -r requirements.txt"
    ) from exc

from research.metrics import metric_record  # noqa: E402


DEFAULT_CASES = ROOT / "research" / "evaluation_cases.json"
DEFAULT_OUTPUT_DIR = ROOT / "research" / "results"


def load_cases(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)
    if not cases:
        raise ValueError("The evaluation dataset is empty.")
    return cases


def evaluate_variant(case: Dict[str, Any], variant: str) -> Dict[str, Any]:
    start = time.perf_counter()
    docs = retrieve_ablation_docs(case["query"], EVAL_CANDIDATE_SOURCES, variant)
    latency_ms = (time.perf_counter() - start) * 1000
    returned = [doc.metadata.get("source", "") for doc in docs if doc.metadata.get("source")]
    result = metric_record(
        case,
        variant,
        returned,
        latency_ms,
        context_relevance(case["query"], docs, case.get("expected_terms", [])),
    )
    result["ablation_stage"] = {
        "semantic_only": "semantic",
        "semantic_plus_lexical": "semantic + lexical overlap",
        "semantic_lexical_role": "semantic + lexical overlap + source-role scoring",
        "full_hybrid": "full production hybrid selector",
    }[variant]
    return result


def run_variant_cases(cases: List[Dict[str, Any]], variant: str) -> List[Dict[str, Any]]:
    rows = [evaluate_variant(case, variant) for case in cases]
    for index, row in enumerate(rows):
        row["latency_phase"] = "cold_start" if index == 0 else "warm"
    return rows


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {}
    for variant in ABLATION_VARIANTS:
        variant_rows = [row for row in rows if row["method"] == variant]
        if not variant_rows:
            continue
        warm_rows = [row for row in variant_rows if row["latency_phase"] == "warm"]
        summary[variant] = {
            "cases": len(variant_rows),
            "mean_precision": round(statistics.mean(row["precision"] for row in variant_rows), 3),
            "mean_recall": round(statistics.mean(row["recall"] for row in variant_rows), 3),
            "mean_f1": round(statistics.mean(row["f1"] for row in variant_rows), 3),
            "mean_mrr": round(statistics.mean(row["mrr"] for row in variant_rows), 3),
            "mean_hit_rate": round(statistics.mean(row["hit_rate"] for row in variant_rows), 3),
            "mean_context_relevance": round(
                statistics.mean(row["context_relevance"] for row in variant_rows), 3
            ),
            "mean_latency_ms": round(statistics.mean(row["latency_ms"] for row in variant_rows), 2),
            "cold_start_latency_ms": round(variant_rows[0]["latency_ms"], 2),
            "warm_mean_latency_ms": round(statistics.mean(row["latency_ms"] for row in warm_rows), 2)
            if warm_rows else None,
            "error_cases": sum(row["error_type"] != "none" for row in variant_rows),
        }
    return summary


def write_outputs(rows: List[Dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"retrieval_ablation_{timestamp}.json"
    csv_path = output_dir / f"retrieval_ablation_cases_{timestamp}.csv"
    payload = {
        "created_at": timestamp,
        "dataset": "research/evaluation_cases.json",
        "variants": list(ABLATION_VARIANTS),
        "protocol": [
            "semantic_only",
            "semantic_plus_lexical",
            "semantic_lexical_role",
            "full_hybrid",
        ],
        "metrics": [
            "precision", "recall", "f1", "mrr", "hit_rate",
            "context_relevance", "latency_ms", "latency_phase",
        ],
        "summary": aggregate(rows),
        "case_results": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    fields = [
        "case_id", "category", "query", "method", "ablation_stage",
        "precision", "recall", "f1", "mrr", "hit_rate", "context_relevance",
        "latency_ms", "latency_phase", "error_type", "missing_sources",
        "unexpected_sources",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the contribution of hybrid retrieval components.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--worker-variant", choices=ABLATION_VARIANTS, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    cases = load_cases(args.cases.resolve())

    if args.worker_variant:
        if not args.worker_output:
            raise SystemExit("--worker-output is required with --worker-variant")
        args.worker_output.write_text(
            json.dumps(run_variant_cases(cases, args.worker_variant), indent=2),
            encoding="utf-8",
        )
        return

    rows = []
    with tempfile.TemporaryDirectory(prefix="policy_tracker_ablation_") as temp_dir:
        for variant in ABLATION_VARIANTS:
            worker_output = Path(temp_dir) / f"{variant}.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--cases", str(args.cases.resolve()),
                "--worker-variant", variant,
                "--worker-output", str(worker_output),
            ]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            if completed.returncode:
                raise RuntimeError(f"{variant} worker failed:\n{completed.stderr[-2000:]}")
            rows.extend(json.loads(worker_output.read_text(encoding="utf-8")))

    json_path, csv_path = write_outputs(rows, args.output_dir)
    print(json.dumps({
        "cases": len(cases),
        "summary": aggregate(rows),
        "json": str(json_path),
        "csv": str(csv_path),
    }, indent=2))


if __name__ == "__main__":
    main()
