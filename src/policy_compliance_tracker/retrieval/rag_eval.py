import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ..agent.compliance_agent import (
    CONTROL_SOURCES,
    POLICY_SOURCES,
    get_vector_db,
    normalize_text,
    read_source_text,
    text_relevance_score,
    display_source_name,
    extract_control_records,
    policy_topic_matches,
    control_topic_matches,
)
from ..storage.tracker_store import save_rag_evaluation


EVAL_CANDIDATE_SOURCES = POLICY_SOURCES + CONTROL_SOURCES
EVAL_RETRIEVAL_K = 5
MIN_LEXICAL_SCORE = 4
STRONG_LEXICAL_SCORE = 10
SECONDARY_TYPE_LEXICAL_SCORE = 4
RELATIVE_SELECTION_FLOOR = 0.75
# Keep a well-supported policy/control companion even when the other source
# type has the stronger vector score. Compliance queries often need both.
CROSS_TYPE_SELECTION_FLOOR = 0.30

ABLATION_VARIANTS = (
    "semantic_only",
    "semantic_plus_lexical",
    "semantic_lexical_role",
    "full_hybrid",
)


_LEGACY_EVAL_SET = [
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


def load_evaluation_cases(path: Path | None = None) -> List[Dict[str, Any]]:
    """Load the shared labelled research set, with a safe legacy fallback."""
    cases_path = path or Path(__file__).resolve().parents[3] / "research" / "evaluation_cases.json"
    try:
        with cases_path.open("r", encoding="utf-8") as handle:
            cases = json.load(handle)
        if isinstance(cases, list) and cases:
            return cases
    except (OSError, json.JSONDecodeError):
        pass
    return list(_LEGACY_EVAL_SET)


DEFAULT_EVAL_SET = load_evaluation_cases()


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
    is_control_source = "\\controls\\" in normalized_source
    is_policy_source = "\\policies\\" in normalized_source

    policy_role_terms = {
        "business_continuity_policy.pdf": {
            "continuity", "disaster recovery", "recovery", "restoration", "resilience",
            "communication paths", "unresolved gaps", "remediation owners",
        },
        "data_governance_policy.pdf": {
            "data classification", "business impact", "data quality", "lineage",
            "data owner", "accountable owner", "approved use", "records management",
        },
        "financial_crime_policy.pdf": {
            "transaction monitoring", "screening", "sanctions", "counterparty",
            "unusual", "suspicious", "potential matches", "material transactions",
        },
    }

    if is_policy_source:
        for policy_name, terms in policy_role_terms.items():
            if policy_name in normalized_source and any(term in query_text for term in terms):
                return 4.0

    if is_control_source and any(
        term in query_text
        for term in [
            "continuity",
            "disaster recovery",
            "data classification",
            "business impact",
            "data quality",
            "lineage",
            "screening",
            "sanctions",
            "counterparty",
            "transaction monitoring",
            "unusual",
            "suspicious",
        ]
    ):
        return 4.0

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
    if "\\controls\\" in normalized_source:
        return "control"
    if "\\policies\\" in normalized_source:
        return "policy"
    return "source"


def source_topic_matches(query: str, source: str) -> bool:
    """Reject generic lexical matches from an unrelated policy/control file."""
    kind = source_kind(source)

    if kind == "policy":
        return policy_topic_matches(query, display_source_name(source))

    if kind == "control":
        controls = extract_control_records(read_source_text(source))
        return any(control_topic_matches(query, control["id"]) for control in controls)

    return True


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
        same_type_domain_match = (
            source_kind(candidate["source"]) == top_kind
            and candidate["lexical_score"] >= 3
            and candidate["hybrid_score"] >= top_score * CROSS_TYPE_SELECTION_FLOOR
        )
        cross_type_evidence_match = (
            source_kind(candidate["source"]) != top_kind
            and candidate["lexical_score"] >= 3
            and candidate["hybrid_score"] >= top_score * CROSS_TYPE_SELECTION_FLOOR
        )

        if not same_type_strong_match and not same_type_domain_match and not cross_type_evidence_match:
            continue

        selected.append(candidate)

    return selected


def retrieve_evaluation_docs(query: str, candidate_sources: Iterable[str]) -> List[Any]:
    vector_db = get_vector_db()
    best_match_by_source = {}

    for source in candidate_sources:
        if not source_topic_matches(query, source):
            continue

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
        # A domain-supported source may have only a few exact words in a
        # short control row. Give that evidence a small transparent lift so
        # it can compete with a longer unrelated document.
        if source_topic_matches(query, source):
            lexical_score += 2
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


def _ablation_source_candidates(query: str, candidate_sources: Iterable[str]) -> List[Dict[str, Any]]:
    """Build the same source-level candidate pool for controlled variants."""
    vector_db = get_vector_db()
    best_match_by_source = {}

    for source in candidate_sources:
        source_docs = vector_db.similarity_search_with_score(
            query,
            k=EVAL_RETRIEVAL_K,
            filter={"source": source},
        )
        if source_docs:
            best_match_by_source[source] = min(source_docs, key=lambda item: item[1])

    if not best_match_by_source:
        return []

    vector_scores = [score for _doc, score in best_match_by_source.values()]
    best_score = min(vector_scores)
    worst_score = max(vector_scores)
    candidates = []
    for source, (doc, vector_score) in best_match_by_source.items():
        lexical_score = text_relevance_score(query, read_source_text(source))
        candidates.append(
            {
                "source": source,
                "doc": doc,
                "vector_score": vector_score,
                "vector_affinity": vector_affinity(vector_score, best_score, worst_score),
                "lexical_score": lexical_score,
                "source_role_bonus": source_role_bonus(query, source),
            }
        )
    return candidates


def retrieve_ablation_docs(
    query: str,
    candidate_sources: Iterable[str],
    variant: str,
) -> List[Any]:
    """Retrieve documents for one cumulative hybrid-component stage."""
    if variant not in ABLATION_VARIANTS:
        raise ValueError(f"Unsupported ablation variant: {variant}")

    vector_db = get_vector_db()
    candidate_sources = list(candidate_sources)

    if variant == "semantic_only":
        docs = vector_db.similarity_search(query, k=EVAL_RETRIEVAL_K)
        selected = []
        seen_sources = set()
        allowed_sources = set(candidate_sources)
        for doc in docs:
            source = doc.metadata.get("source", "")
            if source not in allowed_sources or source in seen_sources:
                continue
            seen_sources.add(source)
            selected.append(doc)
        return selected

    if variant == "full_hybrid":
        return retrieve_evaluation_docs(query, candidate_sources)

    candidates = [
        candidate
        for candidate in _ablation_source_candidates(query, candidate_sources)
        if candidate["lexical_score"] >= MIN_LEXICAL_SCORE
    ]
    if not candidates:
        return []

    for candidate in candidates:
        score = candidate["lexical_score"] * 2.0 + candidate["vector_affinity"]
        if variant == "semantic_lexical_role":
            score += candidate["source_role_bonus"]
        candidate["ablation_score"] = score

    candidates.sort(key=lambda candidate: candidate["ablation_score"], reverse=True)
    selected = []
    for candidate in candidates[:EVAL_RETRIEVAL_K]:
        doc = candidate["doc"]
        doc.metadata["evaluation_ablation_variant"] = variant
        doc.metadata["evaluation_ablation_score"] = candidate["ablation_score"]
        selected.append(doc)
    return selected


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
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    mrr = 0.0
    for rank, source in enumerate(returned_sources, start=1):
        if normalize_source(source) in expected_sources:
            mrr = 1 / rank
            break
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
        "f1": round(f1, 3),
        "mrr": round(mrr, 3),
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
