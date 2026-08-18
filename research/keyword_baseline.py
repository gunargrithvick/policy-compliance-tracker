"""Simple lexical baseline used for the paper's retrieval comparison."""

import re
from typing import Dict, Iterable, List, Tuple


STOP_WORDS = {
    "about", "above", "after", "against", "all", "and", "any", "are",
    "for", "from", "have", "into", "must", "new", "not", "of", "or",
    "the", "this", "to", "with",
}


def significant_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in tokens if len(token) > 3 and token not in STOP_WORDS}


def score_source(query: str, source_text: str) -> int:
    """Count meaningful query tokens present in one complete source document."""
    query_tokens = significant_tokens(query)
    source_tokens = significant_tokens(source_text)
    return len(query_tokens & source_tokens)


def retrieve_keyword_sources(
    query: str,
    candidate_sources: Iterable[str],
    top_k: int = 2,
) -> Tuple[List[str], List[Dict[str, int]]]:
    """Return the top lexical matches without using embeddings or expected labels."""
    from policy_compliance_tracker.agent.compliance_agent import read_source_text

    ranked = []
    for source in candidate_sources:
        score = score_source(query, read_source_text(source))
        ranked.append({"source": source, "keyword_score": score})

    ranked.sort(key=lambda item: (-item["keyword_score"], item["source"]))
    selected = [item for item in ranked if item["keyword_score"] > 0][:top_k]
    return [item["source"] for item in selected], ranked
