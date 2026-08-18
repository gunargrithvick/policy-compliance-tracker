"""Run reproducible RAG-versus-keyword retrieval experiments.

Run from the repository root after building the Chroma index:
    python research/run_experiments.py
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
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (ROOT, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

try:
    from policy_compliance_tracker.agent.compliance_agent import get_vector_db, read_source_text  # noqa: E402
    from policy_compliance_tracker.retrieval.rag_eval import (  # noqa: E402
        EVAL_CANDIDATE_SOURCES,
        context_relevance,
        retrieve_evaluation_docs,
    )
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"Missing project dependency '{exc.name}'. "
        "Install the project dependencies with: "
        "python -m pip install -r requirements.txt"
    ) from exc

from research.keyword_baseline import retrieve_keyword_sources  # noqa: E402
from research.metrics import metric_record  # noqa: E402


DEFAULT_CASES = ROOT / "research" / "evaluation_cases.json"
DEFAULT_OUTPUT_DIR = ROOT / "research" / "results"
METHODS = ("rag_hybrid", "semantic_top_k", "keyword_baseline")


def load_cases(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        cases = json.load(handle)
    if not cases:
        raise ValueError("The evaluation dataset is empty.")
    return cases


def evaluate_rag(case: Dict[str, Any]) -> Dict[str, Any]:
    start = time.perf_counter()
    docs = retrieve_evaluation_docs(case["query"], EVAL_CANDIDATE_SOURCES)
    latency_ms = (time.perf_counter() - start) * 1000
    returned = [doc.metadata.get("source", "") for doc in docs if doc.metadata.get("source")]
    return metric_record(
        case,
        "rag_hybrid",
        returned,
        latency_ms,
        context_relevance(case["query"], docs, case.get("expected_terms", [])),
    )


def evaluate_keyword(case: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        "data/policies\\Data_Privacy_Policy.pdf",
        "data/policies\\Information_Security_Policy.pdf",
        "data/controls\\Core_Control_Matrix.pdf",
    ]
    start = time.perf_counter()
    returned, ranking = retrieve_keyword_sources(case["query"], candidates, top_k=2)
    latency_ms = (time.perf_counter() - start) * 1000
    context = "\n".join(read_source_text(source) for source in returned)
    terms = {term.lower() for term in case.get("expected_terms", [])}
    context_score = sum(term in context.lower() for term in terms) / len(terms) if terms else 0.0
    return metric_record(case, "keyword_baseline", returned, latency_ms, context_score, ranking)


def evaluate_semantic(case: Dict[str, Any]) -> Dict[str, Any]:
    start = time.perf_counter()
    docs = get_vector_db().similarity_search(case["query"], k=5)
    candidates = set(EVAL_CANDIDATE_SOURCES)
    returned = []
    selected_docs = []
    for doc in docs:
        source = doc.metadata.get("source", "")
        if source not in candidates or source in returned:
            continue
        returned.append(source)
        selected_docs.append(doc)
    latency_ms = (time.perf_counter() - start) * 1000
    context = context_relevance(
        case["query"],
        selected_docs,
        case.get("expected_terms", []),
    )
    return metric_record(case, "semantic_top_k", returned, latency_ms, context)


def run_method_cases(cases: List[Dict[str, Any]], method: str) -> List[Dict[str, Any]]:
    evaluators = {
        "rag_hybrid": evaluate_rag,
        "semantic_top_k": evaluate_semantic,
        "keyword_baseline": evaluate_keyword,
    }
    try:
        evaluator = evaluators[method]
    except KeyError as exc:
        raise ValueError(f"Unsupported evaluation method: {method}") from exc

    rows = [evaluator(case) for case in cases]
    for index, row in enumerate(rows):
        row["latency_phase"] = "cold_start" if index == 0 else "warm"
    return rows


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    methods = sorted({row["method"] for row in rows})
    summary = {}
    for method in methods:
        method_rows = [row for row in rows if row["method"] == method]
        summary[method] = {
            "cases": len(method_rows),
            "mean_precision": round(statistics.mean(row["precision"] for row in method_rows), 3),
            "mean_recall": round(statistics.mean(row["recall"] for row in method_rows), 3),
            "mean_f1": round(statistics.mean(row["f1"] for row in method_rows), 3),
            "mean_mrr": round(statistics.mean(row["mrr"] for row in method_rows), 3),
            "mean_hit_rate": round(statistics.mean(row["hit_rate"] for row in method_rows), 3),
            "mean_context_relevance": round(statistics.mean(row["context_relevance"] for row in method_rows), 3),
            "mean_latency_ms": round(statistics.mean(row["latency_ms"] for row in method_rows), 2),
            "cold_start_latency_ms": round(
                statistics.mean(
                    row["latency_ms"]
                    for row in method_rows
                    if row.get("latency_phase") == "cold_start"
                ),
                2,
            ) if any(row.get("latency_phase") == "cold_start" for row in method_rows) else None,
            "warm_mean_latency_ms": round(
                statistics.mean(
                    row["latency_ms"]
                    for row in method_rows
                    if row.get("latency_phase") == "warm"
                ),
                2,
            ) if any(row.get("latency_phase") == "warm" for row in method_rows) else None,
            "error_cases": sum(row["error_type"] != "none" for row in method_rows),
        }
    return summary


def write_outputs(rows: List[Dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"retrieval_experiment_{timestamp}.json"
    csv_path = output_dir / f"retrieval_cases_{timestamp}.csv"
    payload = {
        "created_at": timestamp,
        "dataset": "research/evaluation_cases.json",
        "methods": ["rag_hybrid", "semantic_top_k", "keyword_baseline"],
        "metrics": [
            "precision", "recall", "f1", "mrr", "hit_rate",
            "context_relevance", "latency_ms",
            "latency_phase",
        ],
        "summary": aggregate(rows),
        "case_results": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    fields = [
        "case_id", "category", "query", "method", "precision", "recall", "f1", "mrr",
        "hit_rate", "context_relevance", "latency_ms", "latency_phase", "error_type",
        "missing_sources", "unexpected_sources",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare hybrid RAG retrieval with a keyword baseline.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--worker-method", choices=METHODS, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    cases = load_cases(args.cases.resolve())

    if args.worker_method:
        if not args.worker_output:
            raise SystemExit("--worker-output is required with --worker-method")
        args.worker_output.write_text(
            json.dumps(run_method_cases(cases, args.worker_method), indent=2),
            encoding="utf-8",
        )
        return

    # Each method runs in a fresh worker process, so its first case measures its
    # own cold start instead of inheriting another method's initialized state.
    rows = []
    with tempfile.TemporaryDirectory(prefix="policy_tracker_eval_") as temp_dir:
        for method in METHODS:
            worker_output = Path(temp_dir) / f"{method}.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--cases",
                str(args.cases.resolve()),
                "--worker-method",
                method,
                "--worker-output",
                str(worker_output),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"{method} worker failed:\n{completed.stderr[-2000:]}"
                )
            rows.extend(json.loads(worker_output.read_text(encoding="utf-8")))

    json_path, csv_path = write_outputs(rows, args.output_dir)
    print(json.dumps({"cases": len(cases), "summary": aggregate(rows), "json": str(json_path), "csv": str(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
