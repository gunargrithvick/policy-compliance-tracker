from typing import Any, Dict, Iterable, List

from compliance_agent import (
    CONTROL_SOURCES,
    POLICY_SOURCES,
    get_vector_db,
    normalize_text,
    read_source_text,
    text_relevance_score,
)
from tracker_store import save_rag_evaluation


EVAL_CANDIDATE_SOURCES = POLICY_SOURCES + CONTROL_SOURCES
EVAL_RETRIEVAL_K = 5
MIN_LEXICAL_SCORE = 4
STRONG_LEXICAL_SCORE = 10
SECONDARY_TYPE_LEXICAL_SCORE = 7
RELATIVE_SELECTION_FLOOR = 0.75
CROSS_TYPE_SELECTION_FLOOR = 0.60


DEFAULT_EVAL_SET = [
    {
        "query": "multi factor authentication for high value transactions",
        "expected_sources": CONTROL_SOURCES + ["data/policies\\Information_Security_Policy.pdf"],
        "expected_terms": ["authentication", "mfa", "access"],
    },
    {
        "query": "personal data breach notification within 72 hours",
        "expected_sources": ["data/policies\\Data_Privacy_Policy.pdf"],
        "expected_terms": ["breach", "privacy", "data"],
    },
    {
        "query": "audit logging monitoring and investigation controls",
        "expected_sources": CONTROL_SOURCES,
        "expected_terms": ["audit", "logging", "monitoring"],
    },
    {
        "query": "password complexity strong password requirements",
        "expected_sources": CONTROL_SOURCES + ["data/policies\\Information_Security_Policy.pdf"],
        "expected_terms": ["password", "complexity", "requirements"],
    },
    {
        "query": "personal data consent management processing",
        "expected_sources": CONTROL_SOURCES + ["data/policies\\Data_Privacy_Policy.pdf"],
        "expected_terms": ["consent", "personal", "data"],
    },
    {
        "query": "data retention deletion schedules",
        "expected_sources": CONTROL_SOURCES + ["data/policies\\Data_Privacy_Policy.pdf"],
        "expected_terms": ["retention", "deletion", "schedules"],
    },
    {
        "query": "least privilege quarterly access reviews",
        "expected_sources": CONTROL_SOURCES + ["data/policies\\Information_Security_Policy.pdf"],
        "expected_terms": ["access", "privilege", "reviews"],
    },
    {
        "query": "sensitive data encryption at rest and in transit",
        "expected_sources": CONTROL_SOURCES + ["data/policies\\Data_Privacy_Policy.pdf"],
        "expected_terms": ["encryption", "sensitive", "transit"],
    },
    {
        "query": "personal data access restrictions",
        "expected_sources": ["data/policies\\Data_Privacy_Policy.pdf"],
        "expected_terms": ["personal", "data", "access"],
    },
    {
        "query": "security incident response reporting within 24 hours",
        "expected_sources": ["data/policies\\Information_Security_Policy.pdf"],
        "expected_terms": ["incident", "response", "reported"],
    },
]


def normalize_source(source: str) -> str:
    return source.replace("/", "\\").lower()


def source_overlap_score(expected_sources: set, returned_sources: set) -> float:
    if not expected_sources and not returned_sources:
        return 1.0
    if not expected_sources or not returned_sources:
        return 0.0

    return len(expected_sources & returned_sources) / len(expected_sources | returned_sources)


def context_relevance(query: str, docs: Iterable[Any], expected_terms: Iterable[str]) -> float:
    terms = {term.lower() for term in expected_terms}
    query_terms = {term.lower() for term in query.split() if len(term) > 3}
    wanted = terms or query_terms

    if not wanted:
        return 0.0

    context = normalize_text(" ".join(getattr(doc, "page_content", "") for doc in docs))
    hits = sum(1 for term in wanted if term in context)
    return round(hits / len(wanted), 3)


def doc_identity(doc: Any) -> Any:
    return (
        doc.metadata.get("source"),
        doc.metadata.get("page"),
        getattr(doc, "page_content", "")[:120],
    )


def source_role_bonus(query: str, source: str) -> float:
    query_text = normalize_text(query)
    normalized_source = normalize_source(source)
    is_control_source = "controls\\control_matrix.pdf" in normalized_source
    is_policy_source = "\\policies\\" in normalized_source

    if is_control_source and any(
        term in query_text
        for term in [
            "control",
            "controls",
            "matrix",
        ]
    ):
        return 8.0

    if is_control_source and any(
        term in query_text
        for term in [
            "audit",
            "logging",
            "monitoring",
            "review",
            "reviews",
            "incident",
            "response",
            "authentication",
            "mfa",
            "encryption",
            "retention",
            "consent",
        ]
    ):
        return 4.0

    if is_policy_source and any(
        term in query_text
        for term in [
            "policy",
            "privacy",
            "personal data",
            "breach",
            "security",
            "access",
            "incident",
        ]
    ):
        return 2.0

    return 0.0


def source_kind(source: str) -> str:
    normalized_source = normalize_source(source)
    if "controls\\control_matrix.pdf" in normalized_source:
        return "control"
    if "\\policies\\" in normalized_source:
        return "policy"
    return "source"


def vector_affinity(score: float, best_score: float, worst_score: float) -> float:
    score_range = max(worst_score - best_score, 0.001)
    return max(0.0, 1.0 - ((score - best_score) / score_range)) * 10.0


def select_evaluation_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    eligible = [
        candidate
        for candidate in candidates
        if candidate["lexical_score"] >= MIN_LEXICAL_SCORE
    ]

    if not eligible:
        return []

    ranked = sorted(
        eligible,
        key=lambda candidate: candidate["hybrid_score"],
        reverse=True,
    )
    top_score = ranked[0]["hybrid_score"]
    top_kind = source_kind(ranked[0]["source"])
    selected = [ranked[0]]

    for candidate in ranked[1:]:
        same_type_strong_match = (
            source_kind(candidate["source"]) == top_kind
            and candidate["lexical_score"] >= STRONG_LEXICAL_SCORE
            and candidate["hybrid_score"] >= top_score * RELATIVE_SELECTION_FLOOR
        )
        cross_type_evidence_match = (
            source_kind(candidate["source"]) != top_kind
            and candidate["lexical_score"] >= SECONDARY_TYPE_LEXICAL_SCORE
            and candidate["hybrid_score"] >= top_score * CROSS_TYPE_SELECTION_FLOOR
        )

        if not same_type_strong_match and not cross_type_evidence_match:
            continue

        selected.append(candidate)

    return selected


def retrieve_evaluation_docs(query: str, candidate_sources: Iterable[str]) -> List[Any]:
    vector_db = get_vector_db()
    best_match_by_source = {}

    for source in candidate_sources:
        source_docs = vector_db.similarity_search_with_score(
            query,
            k=EVAL_RETRIEVAL_K,
            filter={"source": source},
        )

        if source_docs:
            best_match_by_source[source] = min(
                source_docs,
                key=lambda item: item[1],
            )

    if not best_match_by_source:
        return []

    vector_scores = [score for _doc, score in best_match_by_source.values()]
    best_score = min(vector_scores)
    worst_score = max(vector_scores)

    candidates = []
    for source, (doc, vector_score) in best_match_by_source.items():
        source_text = read_source_text(source)
        lexical_score = text_relevance_score(query, source_text)
        hybrid_score = (
            lexical_score * 2.0
            + vector_affinity(vector_score, best_score, worst_score)
            + source_role_bonus(query, source)
        )
        candidates.append(
            {
                "source": source,
                "doc": doc,
                "vector_score": vector_score,
                "lexical_score": lexical_score,
                "hybrid_score": hybrid_score,
            }
        )

    selected_candidates = select_evaluation_candidates(candidates)
    docs = []
    seen_docs = set()

    for candidate in selected_candidates:
        doc = candidate["doc"]
        identity = doc_identity(doc)
        if identity in seen_docs:
            continue

        seen_docs.add(identity)
        doc.metadata["evaluation_hybrid_score"] = candidate["hybrid_score"]
        doc.metadata["evaluation_lexical_score"] = candidate["lexical_score"]
        doc.metadata["evaluation_vector_score"] = candidate["vector_score"]
        docs.append(doc)

    return docs


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    expected_sources = {normalize_source(source) for source in case["expected_sources"]}
    candidate_sources = case.get("candidate_sources") or EVAL_CANDIDATE_SOURCES
    docs = retrieve_evaluation_docs(case["query"], candidate_sources)
    returned_sources = [
        doc.metadata.get("source", "")
        for doc in docs
        if doc.metadata.get("source")
    ]
    returned_normalized = {normalize_source(source) for source in returned_sources}
    true_positive = expected_sources & returned_normalized

    precision = len(true_positive) / len(returned_normalized) if returned_normalized else 0.0
    recall = len(true_positive) / len(expected_sources) if expected_sources else 0.0
    hit_rate = source_overlap_score(expected_sources, returned_normalized)

    result = {
        "query": case["query"],
        "expected_sources": sorted(expected_sources),
        "candidate_sources": sorted(normalize_source(source) for source in candidate_sources),
        "returned_sources": returned_sources,
        "retrieved_sources": [
            doc.metadata.get("source", "")
            for doc in docs
            if doc.metadata.get("source")
        ],
        "metric_scope": "selected_evidence",
        "scoring_depth": len(docs),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "hit_rate": hit_rate,
        "context_relevance": context_relevance(
            case["query"],
            docs,
            case.get("expected_terms") or [],
        ),
    }
    save_rag_evaluation(result)
    return result


def evaluate_retrieval_quality(eval_set: Iterable[Dict[str, Any]] = DEFAULT_EVAL_SET) -> List[Dict[str, Any]]:
    return [evaluate_case(case) for case in eval_set]
