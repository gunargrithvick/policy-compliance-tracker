"""Dependency-light metrics shared by research experiments and tests."""

from typing import Any, Dict, Iterable, List


def normalize_source(source: str) -> str:
    return source.replace("/", "\\").lower()


def source_overlap_score(expected_sources: set, returned_sources: set) -> float:
    if not expected_sources and not returned_sources:
        return 1.0
    if not expected_sources or not returned_sources:
        return 0.0
    return len(expected_sources & returned_sources) / len(expected_sources | returned_sources)


def metric_record(
    case: Dict[str, Any],
    method: str,
    returned_sources: Iterable[str],
    latency_ms: float,
    context_score: float,
    ranking: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    expected = {normalize_source(source) for source in case["expected_sources"]}
    returned_list = [normalize_source(source) for source in returned_sources]
    returned = set(returned_list)
    true_positive = expected & returned
    correct_no_match = not expected and not returned
    precision = (
        1.0 if correct_no_match else len(true_positive) / len(returned)
        if returned else 0.0
    )
    recall = (
        1.0 if correct_no_match else len(true_positive) / len(expected)
        if expected else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    reciprocal_rank = 0.0
    for rank, source in enumerate(returned_list, start=1):
        if source in expected:
            reciprocal_rank = 1 / rank
            break
    missing = sorted(expected - returned)
    extra = sorted(returned - expected)

    if missing and extra:
        error_type = "mixed"
    elif missing:
        error_type = "missed_expected_source"
    elif extra:
        error_type = "unexpected_source"
    else:
        error_type = "none"

    result = {
        "case_id": case["case_id"],
        "category": case.get("category", "unspecified"),
        "query": case["query"],
        "method": method,
        "expected_sources": sorted(expected),
        "returned_sources": sorted(returned),
        "missing_sources": missing,
        "unexpected_sources": extra,
        "error_type": error_type,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "mrr": round(reciprocal_rank, 3),
        "hit_rate": round(source_overlap_score(expected, returned), 3),
        "context_relevance": round(context_score, 3),
        "latency_ms": round(latency_ms, 2),
    }
    if ranking is not None:
        result["ranking"] = ranking
    return result
