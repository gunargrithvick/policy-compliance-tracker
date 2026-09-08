"""Evaluate local GDPR retrieval against the openly licensed ClaimRAG-LAW set.

This is a separate legal-evidence benchmark track. ClaimRAG-LAW provides
retrieval and claim labels; it does not provide organization-specific
policy/control gold labels.

Run from the repository root:
    python research/evaluate_claimrag.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (ROOT, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from policy_compliance_tracker.agent.compliance_agent import get_vector_db  # noqa: E402


REVISION = "5cc53a3aa72a02c7cb515087fb3e2d6acfac5573"
DATASET_URL = "https://huggingface.co/datasets/SNTSVV/ClaimRAG-LAW"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
BENCHMARK_DIR = ROOT / "data" / "benchmarks" / "claimrag_law"
DEFAULT_OUTPUT_DIR = ROOT / "research" / "results"
GDPR_SOURCE = "data/regulations\\EU_GDPR_Regulation.pdf"
FILES = {
    "GDPR-RAG-LAW.json": "828d9616899cc72a3fae992d91df91350fa33aba876deeb4ae08243d37efaf75",
    "GDPR-CLAIM-LAW.json": "75e4aa64a365b54b35734f74b474f6fd57110572d946fba817604171a67ca6c4",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_benchmark(directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    base = f"{DATASET_URL}/resolve/{REVISION}/"
    hashes = {}
    for filename, expected_hash in FILES.items():
        target = directory / filename
        if not target.exists() or sha256(target) != expected_hash:
            # The base URL and filename set are fixed HTTPS benchmark inputs.
            urllib.request.urlretrieve(base + filename, target)  # nosec B310
        actual_hash = sha256(target)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"Hash mismatch for {filename}: expected {expected_hash}, got {actual_hash}"
            )
        hashes[filename] = actual_hash

    manifest = {
        "dataset": "ClaimRAG-LAW",
        "dataset_url": DATASET_URL,
        "license": "CC BY 4.0",
        "license_url": LICENSE_URL,
        "revision": REVISION,
        "files": hashes,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "notice": (
            "Preserve attribution and identify modifications. This benchmark "
            "validates legal retrieval and claim grounding, not organization-"
            "specific policy/control mappings."
        ),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_records(directory: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rag_payload = json.loads((directory / "GDPR-RAG-LAW.json").read_text(encoding="utf-8"))
    rag_records = rag_payload.get("input_data", rag_payload)
    claim_records = json.loads((directory / "GDPR-CLAIM-LAW.json").read_text(encoding="utf-8"))
    if not isinstance(rag_records, list) or not isinstance(claim_records, list):
        raise ValueError("ClaimRAG-LAW files do not contain the expected list records.")
    return rag_records, claim_records


def tokens(text: str) -> set[str]:
    stop_words = {"the", "and", "that", "this", "with", "from", "what", "does"}
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower()) if token not in stop_words}


def overlap(reference: str, candidate: str) -> float:
    wanted = tokens(reference)
    return len(wanted & tokens(candidate)) / len(wanted) if wanted else 0.0


def retrieve_gdpr(query: str, top_k: int) -> list[Any]:
    return get_vector_db().similarity_search(
        query, k=top_k, filter={"source": GDPR_SOURCE}
    )


def evaluate_rag(records: Iterable[dict[str, Any]], top_k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for record in records:
        started = time.perf_counter()
        docs = retrieve_gdpr(record["query"], top_k)
        contexts = [getattr(doc, "page_content", "") for doc in docs]
        best_overlap = max((overlap(record["relevant_chunk"], text) for text in contexts), default=0.0)
        top_overlap = overlap(record["relevant_chunk"], contexts[0]) if contexts else 0.0
        rows.append({
            "query_id": record["query_id"],
            "query": record["query"],
            "answer_correctness": record.get("answer_correctness"),
            "top_k": top_k,
            "gold_chunk_token_recall": round(best_overlap, 3),
            "top1_chunk_token_recall": round(top_overlap, 3),
            "evidence_hit": best_overlap >= 0.5,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "retrieved_pages": [doc.metadata.get("page") for doc in docs],
        })

    count = len(rows)
    summary = {
        "cases": count,
        "top_k": top_k,
        "evidence_hit_rate_at_threshold_0_5": round(sum(row["evidence_hit"] for row in rows) / count, 3) if count else 0.0,
        "mean_gold_chunk_token_recall": round(sum(row["gold_chunk_token_recall"] for row in rows) / count, 3) if count else 0.0,
        "mean_top1_chunk_token_recall": round(sum(row["top1_chunk_token_recall"] for row in rows) / count, 3) if count else 0.0,
        "mean_latency_ms": round(sum(row["latency_ms"] for row in rows) / count, 2) if count else 0.0,
    }
    return rows, summary


def summarize_claim_labels(records: list[dict[str, Any]]) -> dict[str, Any]:
    claims = [claim for record in records for claim in record.get("claims", [])]
    correctness = Counter(claim.get("claim_correctness") for claim in claims)
    entailment = Counter(claim.get("claim_entailment") for claim in claims)
    return {
        "claim_records": len(records),
        "claims": len(claims),
        "claim_correctness_counts": dict(correctness),
        "claim_entailment_counts": dict(entailment),
        "missing_or_nonstandard_label_counts": {
            "claim_correctness": sum(
                count for label, count in correctness.items()
                if label not in {"Correct", "Incorrect"}
            ),
            "claim_entailment": sum(
                count for label, count in entailment.items()
                if label not in {"Entailment", "Neutral", "Contradiction"}
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate local GDPR retrieval against ClaimRAG-LAW.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--benchmark-dir", type=Path, default=BENCHMARK_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if args.top_k < 1:
        raise SystemExit("--top-k must be positive")

    manifest = ensure_benchmark(args.benchmark_dir.resolve())
    rag_records, claim_records = load_records(args.benchmark_dir.resolve())
    rows, rag_summary = evaluate_rag(rag_records, args.top_k)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": manifest,
        "actual_record_counts": {
            "gdpr_rag_records": len(rag_records),
            "gdpr_claim_records": len(claim_records),
            "gdpr_claims": sum(len(record.get("claims", [])) for record in claim_records),
        },
        "scope": (
            "External legal benchmark for GDPR evidence retrieval and claim labels. "
            "It does not validate project-specific policy/control mappings."
        ),
        "rag_summary": rag_summary,
        "claim_summary": summarize_claim_labels(claim_records),
        "case_results": rows,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = output_dir / f"claimrag_evaluation_{timestamp}.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "rag_summary": rag_summary, "claim_summary": payload["claim_summary"]}, indent=2))


if __name__ == "__main__":
    main()
