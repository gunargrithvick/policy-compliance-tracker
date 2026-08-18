from typing import Any, Dict, Optional, TypedDict
import hashlib
import json
import os
import re
import time

from langgraph.graph import StateGraph, END

from ..config import CHROMA_DB_PATH, TOP_K
from ..providers.analysis_providers import PROVIDER_LABELS, ProviderError, invoke_provider


USE_LLM_ANALYSIS = os.getenv("USE_LLM_ANALYSIS", "").lower() in {
    "1",
    "true",
    "yes",
}

llm = None
llm_clients = {}
db = None
retriever = None
SOURCE_TEXT_CACHE = {}
SOURCE_TEXT_CACHE_FILE = os.path.join(CHROMA_DB_PATH, "source_text_cache.json")


class _ProviderClient:
    def __init__(self, provider):
        self.provider = provider

    def invoke(self, prompt):
        return invoke_provider(self.provider, prompt)


def resolve_analysis_provider(provider=None):
    configured = provider or os.getenv("AI_PROVIDER")
    value = (configured or ("ollama" if USE_LLM_ANALYSIS else "rule_based")).strip().lower()
    if value not in PROVIDER_LABELS:
        raise ProviderError(f"Unsupported analysis provider: {value}")
    return value


def get_llm(provider="ollama"):
    provider = resolve_analysis_provider(provider)
    if provider == "rule_based":
        raise ProviderError("Rule-based analysis does not use a language model.")

    if provider not in llm_clients:
        if provider == "ollama":
            from langchain_ollama import ChatOllama

            llm_clients[provider] = ChatOllama(
                model=os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
                temperature=0,
            )
        else:
            llm_clients[provider] = _ProviderClient(provider)
    return llm_clients[provider]


def get_vector_db():

    global db

    if db is None:
        from langchain_chroma import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        db = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            ),
            collection_name="langchain",
        )

    return db


def get_retriever():

    global retriever

    if retriever is None:
        retriever = get_vector_db().as_retriever(
            search_kwargs={"k": TOP_K}
        )

    return retriever

POLICY_SOURCES = [
    "data/policies\\Data_Privacy_Policy.pdf",
    "data/policies\\Information_Security_Policy.pdf",
    "data/policies\\Business_Continuity_Policy.pdf",
    "data/policies\\Data_Governance_Policy.pdf",
    "data/policies\\Financial_Crime_Policy.pdf",
]

CONTROL_SOURCES = [
    "data/controls\\Core_Control_Matrix.pdf",
    "data/controls\\Supplemental_Control_Matrix.pdf",
]

SOURCE_DISPLAY_NAMES = {
    "data/policies\\Data_Privacy_Policy.pdf": "Data Privacy Policy",
    "data/policies\\Information_Security_Policy.pdf": "Information Security Policy",
    "data/policies\\Business_Continuity_Policy.pdf": "Business Continuity Policy",
    "data/policies\\Data_Governance_Policy.pdf": "Data Governance Policy",
    "data/policies\\Financial_Crime_Policy.pdf": "Financial Crime Policy",
    "data/controls\\Core_Control_Matrix.pdf": "Core Control Matrix",
    "data/controls\\Supplemental_Control_Matrix.pdf": "Supplemental Control Matrix",
}

DEADLINE_PATTERN = re.compile(
    r"\b("
    r"within\s+\d+\s+(?:calendar\s+|business\s+)?(?:hours?|days?|weeks?|months?|years?)|"
    r"by|before|deadline|due|effective|starting|"
    r"no later than|on or before|immediate|immediately|"
    r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|20\d{2}"
    r")\b",
    re.IGNORECASE
)

MONTH_NAMES = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

DEADLINE_VALUE_PATTERNS = [
    re.compile(
        r"\bwithin\s+\d+\s+(?:calendar\s+|business\s+)?(?:hours?|days?|weeks?|months?|years?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:immediate|immediately)\b", re.IGNORECASE),
    re.compile(
        rf"\b(?:no later than|on or before|due by|deadline(?: is|:)?|by|before|"
        rf"effective(?: from)?|starting(?: from)?)\s+"
        rf"(?:"
        rf"\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{2,4}}|"
        rf"\d{{1,2}}\s+(?:{MONTH_NAMES})\s+20\d{{2}}|"
        rf"(?:{MONTH_NAMES})\s+\d{{1,2}},?\s+20\d{{2}}|"
        rf"20\d{{2}}|"
        rf"\d+\s+(?:calendar\s+|business\s+)?(?:hours?|days?|weeks?|months?|years?)"
        rf")\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", re.IGNORECASE),
    re.compile(
        rf"\b(?:\d{{1,2}}\s+(?:{MONTH_NAMES})|(?:{MONTH_NAMES})\s+\d{{1,2}},?)\s+20\d{{2}}\b",
        re.IGNORECASE,
    ),
]

REGULATOR_PATTERNS = [
    ("RBI", re.compile(r"\bRBI\b|Reserve Bank of India", re.IGNORECASE)),
    ("SEBI", re.compile(r"\bSEBI\b|Securities and Exchange Board of India", re.IGNORECASE)),
    ("CERT-In", re.compile(r"\bCERT[-\s]?In\b|Indian Computer Emergency Response Team", re.IGNORECASE)),
    ("PCI DSS", re.compile(r"\bPCI[-\s]?DSS\b|Payment Card Industry Data Security Standard", re.IGNORECASE)),
    ("ISO", re.compile(r"\bISO(?:/IEC)?\s*\d{4,5}\b|\bISO\b", re.IGNORECASE)),
    ("GDPR", re.compile(r"\bGDPR\b|General Data Protection Regulation", re.IGNORECASE)),
]

STOP_WORDS = {
    "about",
    "above",
    "accounts",
    "after",
    "against",
    "all",
    "and",
    "any",
    "are",
    "for",
    "from",
    "have",
    "high",
    "into",
    "must",
    "new",
    "not",
    "of",
    "or",
    "per",
    "requires",
    "the",
    "this",
    "to",
    "transactions",
    "value",
    "with",
}

CONTROL_KEYWORD_GROUPS = [
    {"mfa", "multi factor authentication", "two factor authentication", "authentication"},
    {"password", "credential", "credentials"},
    {"encryption", "encrypt", "encrypted"},
    {"access", "privileged", "permission", "permissions"},
    {"incident", "breach", "response"},
    {"audit", "logging", "logs", "monitoring", "investigation", "investigations"},
    {"consent"},
    {"retain", "retention", "retained", "deletion", "delete"},
]

POLICY_TOPIC_TERMS = {
    "Data Privacy Policy": {
        "privacy",
        "personal data",
        "personal information",
        "sensitive data",
        "encrypt sensitive information",
        "personal and sensitive information",
        "consent",
        "data retention",
        "retention schedule",
        "personal data retained",
        "personal data deletion",
        "delete personal data",
        "data breach",
        "data breaches",
    },
    "Information Security Policy": {
        "information security",
        "security",
        "mfa",
        "multi factor",
        "authentication",
        "password",
        "passwords",
        "credential",
        "least privilege",
        "access control",
        "access review",
        "access reviews",
        "security log",
        "security logs",
        "incident",
        "response",
        "vendor",
        "vendors",
        "third party",
        "third parties",
        "critical system",
        "critical systems",
        "audit",
        "logging",
        "logs",
        "security monitoring",
        "security investigation",
        "security investigations",
        "suspicious activities",
    },
    "Business Continuity Policy": {
        "business continuity",
        "continuity plan",
        "continuity planning",
        "disaster recovery",
        "recovery time",
        "recovery point",
        "recovery objectives",
        "service restoration",
        "restoration",
        "recovery",
        "resilience",
        "backup restoration",
        "restoration test",
        "continuity testing",
        "responsible owner",
        "responsible owners",
        "critical service",
        "communication paths",
        "planned intervals",
        "test results",
        "unresolved gaps",
        "remediation owners",
        "service owner",
    },
    "Data Governance Policy": {
        "data classification",
        "classification",
        "information asset",
        "classify sensitive information",
        "classify information",
        "data quality",
        "data lineage",
        "lineage",
        "data flow",
        "data flows",
        "records management",
        "business records",
        "records retention",
        "records disposal",
        "sensitivity",
        "data owner",
        "data ownership",
        "data catalog",
        "stored",
        "business impact",
        "accountable owner",
        "accountable data owner",
        "approved use",
        "important data domain",
        "material reporting",
        "operational decisions",
        "data quality review",
    },
    "Financial Crime Policy": {
        "transaction monitoring",
        "sanctions screening",
        "sanctions",
        "sanctions list",
        "screening",
        "due diligence",
        "customer due diligence",
        "counterparty due diligence",
        "counterparty screening",
        "financial crime",
        "unusual activity",
        "unusual transaction",
        "monitoring alert",
        "defined review points",
        "review points",
        "material transactions",
        "risk-based rules",
        "unusual patterns",
        "suspicious patterns",
        "relevant transactions",
        "before approval",
        "potential matches",
        "escalated for investigation",
        "investigation",
    },
}

CONTROL_TOPIC_TERMS = {
    "C001": {"mfa", "multi factor", "authentication", "privileged", "critical system", "critical systems"},
    "C002": {"password", "passwords", "credential"},
    "C003": {"least privilege", "access control", "access review", "access reviews"},
    "C004": {"encryption", "encrypt", "encrypted"},
    "C005": {"incident", "incidents", "breach", "breaches", "response"},
    "C006": {"audit", "logging", "logs", "security log", "security logs"},
    "C007": {"consent"},
    "C008": {"data retention", "retain personal data", "personal data retained", "retention schedule", "deletion", "delete"},
    "C009": {"data classification", "classification", "classify information", "classify", "classify sensitive information", "sensitivity", "data governance"},
    "C010": {"continuity testing", "continuity plan testing", "test continuity", "test continuity procedures", "disaster recovery test", "disaster recovery procedures", "disaster recovery restoration test", "planned intervals", "unresolved gaps", "test gaps", "resilience testing"},
    "C011": {"backup restoration", "restoration test", "restore backups", "backup recovery"},
    "C012": {"sanctions screening", "sanctions list", "screening", "counterparty screening", "defined review points", "review points", "relevant transactions", "before approval"},
    "C013": {"transaction monitoring", "financial crime monitoring", "unusual transaction", "unusual activity", "unusual patterns", "suspicious patterns", "monitor transactions", "transaction patterns", "monitoring alert"},
}

TRACKER_SECTION_LABELS = {
    "Summary",
    "Compliance Obligations",
    "Deadlines",
    "Impacted Policies",
    "Required Updates",
    "Evidence",
    "Impacted Controls",
    "Control Gaps",
    "Recommended Enhancements",
}


def vector_affinity(score, best_score, worst_score):
    """Convert Chroma's distance score into a comparable ranking signal."""
    score_range = max(worst_score - best_score, 0.001)
    return max(0.0, 1.0 - ((score - best_score) / score_range)) * 10.0


def retrieve_source_docs(query, sources):

    vector_db = get_vector_db()
    scored_docs = []
    best_doc_by_source = {}
    complexity = query_complexity(query)
    retrieval_k = TOP_K if complexity == "complex" else max(3, TOP_K - 1)

    for source in sources:
        source_docs = vector_db.similarity_search_with_score(
            query,
            k=retrieval_k,
            filter={"source": source}
        )
        scored_docs.extend(source_docs)

    scored_docs.sort(key=lambda item: item[1])

    vector_scores = [score for _doc, score in scored_docs]
    best_score = min(vector_scores) if vector_scores else 0.0
    worst_score = max(vector_scores) if vector_scores else 1.0
    ranked_docs = []
    for doc, vector_score in scored_docs:
        lexical_score = text_relevance_score(query, doc.page_content)
        hybrid_score = (
            lexical_score * 2.0
            + vector_affinity(vector_score, best_score, worst_score)
        )
        ranked_docs.append((hybrid_score, doc, lexical_score, vector_score))
        source = doc.metadata.get("source")
        if source and (
            source not in best_doc_by_source
            or hybrid_score > best_doc_by_source[source][0]
        ):
            best_doc_by_source[source] = (
                hybrid_score,
                doc,
                lexical_score,
                vector_score,
            )

    ranked_docs.sort(key=lambda item: item[0], reverse=True)

    selected_docs = []
    selected_ids = set()

    for source in sources:
        best_match = best_doc_by_source.get(source)

        if not best_match:
            continue

        _hybrid_score, doc, lexical_score, vector_score = best_match
        doc.metadata["retrieval_strategy"] = "hybrid"
        doc.metadata["retrieval_query_complexity"] = complexity
        doc.metadata["retrieval_lexical_score"] = lexical_score
        doc.metadata["retrieval_vector_score"] = vector_score
        doc_id = getattr(doc, "id", None) or (
            doc.metadata.get("source"),
            doc.metadata.get("page"),
            doc.page_content[:120],
        )
        selected_ids.add(doc_id)
        selected_docs.append(doc)

    for _hybrid_score, doc, lexical_score, vector_score in ranked_docs:
        if len(selected_docs) >= TOP_K:
            break

        doc.metadata["retrieval_strategy"] = "hybrid"
        doc.metadata["retrieval_query_complexity"] = complexity
        doc.metadata["retrieval_lexical_score"] = lexical_score
        doc.metadata["retrieval_vector_score"] = vector_score

        doc_id = getattr(doc, "id", None) or (
            doc.metadata.get("source"),
            doc.metadata.get("page"),
            doc.page_content[:120],
        )

        if doc_id in selected_ids:
            continue

        selected_ids.add(doc_id)
        selected_docs.append(doc)

    if not selected_docs and sources:
        # Corrective fallback for indexes whose source metadata is incomplete.
        fallback_docs = vector_db.similarity_search_with_score(
            query,
            k=TOP_K,
        )
        allowed_sources = set(sources)
        for doc, vector_score in fallback_docs:
            if doc.metadata.get("source") not in allowed_sources:
                continue
            doc.metadata["retrieval_strategy"] = "corrective_fallback"
            doc.metadata["retrieval_query_complexity"] = complexity
            selected_docs.append(doc)
            if len(selected_docs) >= TOP_K:
                break

    return selected_docs


def display_source_name(source):

    return SOURCE_DISPLAY_NAMES.get(
        source,
        source.split("\\")[-1].replace("_", " ").replace(".pdf", "")
    )


def source_page_reference(doc):

    source = doc.metadata.get("source", "unknown source")
    page = doc.metadata.get("page")
    page_text = f", page {page + 1}" if isinstance(page, int) else ""

    return f"{source}{page_text}"


def format_docs(docs):

    formatted_docs = []

    for doc in docs:
        source = doc.metadata.get("source", "unknown source")
        page = doc.metadata.get("page")
        page_text = f", page {page + 1}" if isinstance(page, int) else ""

        formatted_docs.append(
            f"[{source}{page_text}]\n{doc.page_content[:700]}"
        )

    return "\n\n".join(formatted_docs)


def append_evidence_section(text, evidence_lines):

    if not evidence_lines or "Evidence:" in text:
        return text

    return (
        f"{text.strip()}\n\n"
        "Evidence:\n"
        f"{chr(10).join(evidence_lines)}"
    ).strip()


def parse_labeled_sections(text):

    sections = {}
    current_label = None

    for line in text.splitlines():
        stripped = strip_markdown_heading(line).strip()

        if not stripped:
            continue

        label_match = re.match(r"^([A-Za-z][A-Za-z &/()-]+):\s*(.*)$", stripped)

        if label_match:
            label = label_match.group(1).strip()
            value = label_match.group(2).strip()

            if label in TRACKER_SECTION_LABELS:
                current_label = label
                sections.setdefault(current_label, [])

                if value:
                    sections[current_label].append(value.strip("- "))

                continue

        if current_label:
            sections[current_label].append(stripped.strip("- "))

    return sections


def combine_items(*item_groups):

    combined = []

    for items in item_groups:
        for item in items:
            if item and item not in combined:
                combined.append(item)

    return combined


def join_tracker_items(items, default="Not available"):

    cleaned_items = [
        item.strip().rstrip(".")
        for item in items
        if item and item.strip()
    ]

    return "; ".join(cleaned_items) if cleaned_items else default


OWNER_RULES = [
    (
        "IAM Team",
        [
            "mfa",
            "multi factor authentication",
            "authentication",
            "access",
            "privileged",
            "identity",
        ],
    ),
    (
        "Security Engineering",
        [
            "network",
            "encryption",
            "logging",
            "monitoring",
            "incident",
            "vulnerability",
        ],
    ),
    (
        "Privacy Office",
        [
            "privacy",
            "personal data",
            "breach",
            "consent",
            "retention",
            "data subject",
        ],
    ),
    (
        "GRC Team",
        [
            "policy",
            "control",
            "audit",
            "compliance",
            "governance",
            "risk",
        ],
    ),
]


def has_real_control_gap(control_gaps):

    return any(
        "no additional control gap" not in gap.lower()
        and "not specified" not in gap.lower()
        for gap in control_gaps
    )


def penalty_score(regulation):

    text = normalize_text(regulation)

    if any(term in text for term in ["penalty", "fine", "sanction", "turnover"]):
        return 5

    if any(term in text for term in ["mandatory", "must", "shall", "required"]):
        return 3

    return 1


def urgency_score(deadlines):

    text = normalize_text(" ".join(deadlines))

    if any(term in text for term in ["immediate", "immediately", "72 hours", "within"]):
        return 5

    if re.search(r"\b20\d{2}\b", text):
        return 3

    return 1


def severity_score(regulation, control_gaps):

    text = normalize_text(regulation)
    score = 2

    if any(term in text for term in ["must", "shall", "required", "mandatory"]):
        score += 1

    if any(term in text for term in ["high value", "personal data", "breach", "critical"]):
        score += 1

    if has_real_control_gap(control_gaps):
        score += 1

    return min(score, 5)


def calculate_risk_score(regulation, control_gaps, impacted_policies, impacted_controls, deadlines):

    affected_scope = min(5, len(impacted_controls) + len(impacted_policies))
    score = (
        severity_score(regulation, control_gaps) * 2
        + affected_scope * 2
        + penalty_score(regulation)
        + urgency_score(deadlines)
    )

    return min(score, 25)


def priority_from_risk(score):

    if score >= 18:
        return "Critical"

    if score >= 14:
        return "High"

    if score >= 8:
        return "Medium"

    if score > 0:
        return "Low"

    return "Review"


def tracker_owner(impacted_policies, impacted_controls):

    combined_text = normalize_text(
        " ".join(impacted_policies + impacted_controls)
    )
    owners = []

    for owner, keywords in OWNER_RULES:
        if any(keyword in combined_text for keyword in keywords):
            owners.append(owner)

    if owners:
        return " + ".join(owners[:2])

    if impacted_policies or impacted_controls:
        return "GRC Team"

    return "Compliance Team"


def confidence_score(impacted_policies, impacted_controls, evidence, control_gaps):

    score = 45

    if impacted_policies:
        score += 15

    if impacted_controls:
        score += 15

    score += min(20, len(evidence) * 5)

    if has_real_control_gap(control_gaps):
        score += 5

    return min(score, 95)


def count_real_items(items):

    return len(
        [
            item for item in items
            if item and "no matching" not in item.lower()
            and "not available" not in item.lower()
            and "not specified" not in item.lower()
        ]
    )


def query_complexity(text):
    """Classify the request so retrieval can be measured by query difficulty."""
    normalized = normalize_text(text)
    token_count = len(normalized.split())
    multi_step_markers = {
        "and", "across", "compare", "exception", "deadline", "impact",
        "policy", "control", "requirement", "requirements",
    }
    marker_count = sum(marker in normalized for marker in multi_step_markers)

    if token_count <= 8 and marker_count <= 1:
        return "simple"
    if token_count >= 20 or marker_count >= 4:
        return "complex"
    return "standard"


def extract_regulatory_obligations(regulation):
    """Extract only explicit obligation sentences from supplied text.

    This is intentionally deterministic: it does not invent obligations or
    complete missing legal details with outside knowledge.
    """
    text = re.sub(r"\s+", " ", (regulation or "")).strip()
    if not text:
        return []

    sentences = [
        sentence.strip(" -")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if sentence.strip(" -")
    ]
    obligation_pattern = re.compile(
        r"\b(must|shall|required to|is required to|need to|needs to|"
        r"should|prohibited|may not|no later than|within|immediately)\b",
        re.IGNORECASE,
    )
    selected = [sentence for sentence in sentences if obligation_pattern.search(sentence)]
    if not selected and sentences:
        selected = sentences[:1]

    obligations = []
    for index, sentence in enumerate(selected, start=1):
        deadline = regulation_deadline(sentence)
        obligations.append(
            {
                "obligation_id": f"OBL-{index:03d}",
                "text": sentence,
                "deadline": deadline if deadline != "Not specified in provided regulation." else None,
                "explicit": bool(obligation_pattern.search(sentence)),
            }
        )
    return obligations


def excerpt_for_query(text, query, limit=280):
    compact = re.sub(r"\s+", " ", (text or "")).strip()
    if len(compact) <= limit:
        return compact

    query_tokens = [
        token for token in normalize_text(query).split()
        if len(token) > 3 and token not in STOP_WORDS
    ]
    lowered = compact.lower()
    positions = [lowered.find(token) for token in query_tokens if lowered.find(token) >= 0]
    start = max(min(positions) - 80, 0) if positions else 0
    return compact[start:start + limit].strip()


def build_evidence_records(regulation, policies, controls):
    records = []
    for policy in policies:
        score = policy_relevance_score(regulation, policy)
        if score < 4:
            continue
        records.append(
            {
                "evidence_type": "policy",
                "name": policy["name"],
                "source": policy["source"],
                "reference": policy["source"],
                "page": None,
                "excerpt": excerpt_for_query(policy["text"], regulation),
                "relevance_score": score,
                "supports": "policy_mapping",
            }
        )

    for control in controls:
        score = control_relevance_score(regulation, control)
        if score < 4:
            continue
        source = control.get("source", "data/controls\\Core_Control_Matrix.pdf")
        records.append(
            {
                "evidence_type": "control",
                "name": f"{control['id']} {control['name']}",
                "source": source,
                "reference": f"{display_source_name(source)} row {control['id']}",
                "page": None,
                "excerpt": excerpt_for_query(
                    f"{control['name']}: {control['description']}",
                    regulation,
                ),
                "relevance_score": score,
                "supports": "control_mapping",
            }
        )
    return records


def build_mapping_graph(obligations, policies, controls, owner):
    edges = []
    for obligation in obligations:
        obligation_id = obligation["obligation_id"]
        for policy in policies:
            edges.append(
                {
                    "from": obligation_id,
                    "relation": "mapped_to_policy",
                    "to": policy["name"],
                }
            )
        for control in controls:
            edges.append(
                {
                    "from": obligation_id,
                    "relation": "mapped_to_control",
                    "to": f"{control['id']} {control['name']}",
                }
            )
    if owner and obligations:
        edges.append(
            {
                "from": obligations[0]["obligation_id"],
                "relation": "assigned_to",
                "to": owner,
            }
        )
    return edges


def policy_change_decision(impacted_policies, required_updates):
    has_policy = count_real_items(impacted_policies) > 0
    actionable_updates = [
        update
        for update in required_updates
        if update
        and "no matching" not in update.lower()
        and "not available" not in update.lower()
        and "not specified" not in update.lower()
    ]

    if has_policy and actionable_updates:
        return True, join_tracker_items(actionable_updates)

    if has_policy:
        return True, "Impacted policy identified; compliance team review required to confirm update wording."

    return False, "No matching internal policy requiring change was identified from the provided policy library."


def build_impact_tracker_record(state):

    summary_sections = parse_labeled_sections(state["summary"])
    mapping_sections = parse_labeled_sections(state["mapping"])
    control_sections = parse_labeled_sections(state["control_matrix"])
    metadata = state.get("regulation_metadata", {}) or {}

    summary = summary_sections.get("Summary", [])
    obligations = summary_sections.get("Compliance Obligations", [])
    deadlines = summary_sections.get("Deadlines", [])
    impacted_policies = mapping_sections.get("Impacted Policies", [])
    required_updates = mapping_sections.get("Required Updates", [])
    impacted_controls = control_sections.get("Impacted Controls", [])
    control_gaps = control_sections.get("Control Gaps", [])
    enhancements = control_sections.get("Recommended Enhancements", [])
    evidence = combine_items(
        mapping_sections.get("Evidence", []),
        control_sections.get("Evidence", [])
    )

    risk_score = calculate_risk_score(
        state["regulation"],
        control_gaps,
        impacted_policies,
        impacted_controls,
        deadlines
    )
    priority = priority_from_risk(risk_score)
    owner = tracker_owner(
        impacted_policies,
        impacted_controls
    )
    confidence = confidence_score(
        impacted_policies,
        impacted_controls,
        evidence,
        control_gaps
    )
    policy_change_required, policy_change_reason = policy_change_decision(
        impacted_policies,
        required_updates
    )

    obligations_structured = extract_regulatory_obligations(state["regulation"])
    evidence_records = build_evidence_records(
        state["regulation"],
        state.get("relevant_policies", []),
        state.get("relevant_controls", []),
    )
    evidence_quality = round(
        min(
            100.0,
            sum(min(record["relevance_score"], 20) for record in evidence_records)
            / max(len(evidence_records), 1)
            * 5,
        ),
        1,
    )
    retrieval_diagnostics = {
        "strategy": state.get("retrieval_diagnostics", {}).get(
            "strategy", "hybrid_deterministic"
        ),
        "query_complexity": state.get("retrieval_diagnostics", {}).get(
            "query_complexity", query_complexity(state["regulation"])
        ),
        "candidate_policies": len(state.get("policy_records", [])),
        "selected_policies": len(state.get("relevant_policies", [])),
        "candidate_controls": len(state.get("control_records", [])),
        "selected_controls": len(state.get("relevant_controls", [])),
        "evidence_count": len(evidence_records),
        "evidence_quality": evidence_quality,
        "corrective_action": (
            "human_review_required"
            if not evidence_records or evidence_quality < 35
            else "none"
        ),
    }
    review_required = (
        priority == "Critical"
        or not evidence_records
        or evidence_quality < 35
    )
    review_reason = (
        "Critical impact requires human approval before policy action."
        if priority == "Critical"
        else "Evidence was insufficient for an automatic mapping decision."
        if not evidence_records or evidence_quality < 35
        else ""
    )

    return {
        "tracker_id": metadata.get("tracker_id"),
        "regulation_title": metadata.get("title") or join_tracker_items(summary),
        "regulator": metadata.get("regulator") or infer_regulator(state["regulation"]),
        "version": metadata.get("version") or 1,
        "supersedes_tracker_id": metadata.get("supersedes_tracker_id"),
        "regulatory_update": join_tracker_items(summary),
        "compliance_obligation": join_tracker_items(obligations),
        "impacted_policy": join_tracker_items(impacted_policies),
        "required_policy_update": join_tracker_items(required_updates),
        "policy_change_required": policy_change_required,
        "policy_change_reason": policy_change_reason,
        "impacted_control": join_tracker_items(impacted_controls),
        "control_gap": join_tracker_items(control_gaps),
        "recommended_enhancement": join_tracker_items(enhancements),
        "priority": priority,
        "risk_score": risk_score,
        "risk_score_max": 25,
        "owner": owner,
        "due_date": join_tracker_items(deadlines),
        "status": "Open",
        "evidence": join_tracker_items(evidence),
        "confidence": confidence,
        "affected_controls_count": count_real_items(impacted_controls),
        "affected_policies_count": count_real_items(impacted_policies),
        "change_detected": bool(metadata.get("change_detected")),
        "change_summary": metadata.get("change_summary") or "No prior version available for comparison.",
        "change_impact": metadata.get("change_impact") or "Not applicable",
        "analysis_provider": state.get("analysis_provider", "rule_based"),
        "obligations_structured": obligations_structured,
        "evidence_records": evidence_records,
        "retrieval_diagnostics": retrieval_diagnostics,
        "mapping_graph": build_mapping_graph(
            obligations_structured,
            state.get("relevant_policies", []),
            state.get("relevant_controls", []),
            owner,
        ),
        "review_required": review_required,
        "review_reason": review_reason,
        "source_path": metadata.get("source_path"),
        "source_url": metadata.get("source_url"),
        "feed_name": metadata.get("feed_name"),
        "downloaded_at": metadata.get("downloaded_at"),
        "regulator_source": metadata.get("regulator_source"),
    }


def format_impact_tracker_record(record):

    tracker_fields = [
        ("Tracker ID", record.get("tracker_id") or "Pending persistence"),
        ("Regulation", record.get("regulation_title") or "Not available"),
        ("Regulator", record.get("regulator") or "Unknown"),
        ("Version", record.get("version") or 1),
        ("Supersedes", record.get("supersedes_tracker_id") or "None"),
        ("Regulatory Update", record.get("regulatory_update") or "Not available"),
        ("Compliance Obligation", record.get("compliance_obligation") or "Not available"),
        ("Impacted Policy", record.get("impacted_policy") or "Not available"),
        ("Required Policy Update", record.get("required_policy_update") or "Not available"),
        ("Policy Change Required", "Yes" if record.get("policy_change_required") else "No"),
        ("Policy Change Reason", record.get("policy_change_reason") or "Not available"),
        ("Impacted Control", record.get("impacted_control") or "Not available"),
        ("Control Gap", record.get("control_gap") or "Not available"),
        ("Recommended Enhancement", record.get("recommended_enhancement") or "Not available"),
        ("Risk Score", f"{record.get('risk_score', 0)}/{record.get('risk_score_max', 25)}"),
        ("Priority", record.get("priority") or "Review"),
        ("Owner", record.get("owner") or "Compliance Team"),
        ("Due Date", record.get("due_date") or "Not available"),
        ("Status", record.get("status") or "Open"),
        ("Confidence", f"{record.get('confidence', 0)}%"),
        ("Change Detected", "Yes" if record.get("change_detected") else "No"),
        ("Change Summary", record.get("change_summary") or "Not available"),
        ("Change Impact", record.get("change_impact") or "Not applicable"),
        ("Analysis Provider", record.get("analysis_provider") or "rule_based"),
        ("Review Required", "Yes" if record.get("review_required") else "No"),
        ("Review Reason", record.get("review_reason") or "None"),
        ("Structured Obligations", json.dumps(record.get("obligations_structured") or [], default=str)),
        ("Evidence Records", json.dumps(record.get("evidence_records") or [], default=str)),
        ("Retrieval Diagnostics", json.dumps(record.get("retrieval_diagnostics") or {}, default=str)),
        ("Mapping Graph", json.dumps(record.get("mapping_graph") or [], default=str)),
        ("Source URL", record.get("source_url") or "Not available"),
        ("Feed Name", record.get("feed_name") or "Not available"),
        ("Evidence", record.get("evidence") or "Not available"),
    ]

    rows = [
        "| Field | Value |",
        "|---|---|",
    ]

    for field, value in tracker_fields:
        safe_value = str(value).replace("|", "/")
        rows.append(f"| {field} | {safe_value} |")

    return "\n".join(rows)


def build_impact_tracker(state):

    return format_impact_tracker_record(
        build_impact_tracker_record(state)
    )


def policy_evidence_lines(mapping_text, policy_docs, regulation):

    mapping_text_lower = mapping_text.lower()
    evidence_by_policy = {}

    for doc in policy_docs:
        source = doc.metadata.get("source", "")
        policy_name = display_source_name(source)

        if policy_name.lower() not in mapping_text_lower:
            continue

        if text_relevance_score(regulation, doc.page_content) < 4:
            continue

        reference = source_page_reference(doc)
        evidence_by_policy.setdefault(policy_name, [])

        if reference in evidence_by_policy[policy_name]:
            continue

        evidence_by_policy[policy_name].append(reference)

    evidence = []

    for policy_name, references in evidence_by_policy.items():
        for reference in references[:2]:
            evidence.append(f"- {policy_name}: {reference}")

    return evidence


def policy_record_evidence_lines(policies):

    return [
        f"- {policy['name']}: {policy['source']}"
        for policy in policies
    ]


def control_evidence_lines(controls):

    lines = []
    for control in controls:
        source = control.get("source", "data/controls\\Core_Control_Matrix.pdf")
        lines.append(
            f"- {control['id']} {control['name']}: {source}, row {control['id']}"
        )
    return lines


def source_cache_key(source):

    return os.path.normcase(os.path.abspath(os.path.normpath(source)))


def file_sha256(path):

    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def source_file_fingerprint(path):

    stat = os.stat(path)

    return {
        "sha256": file_sha256(path),
        "size_bytes": stat.st_size,
        "modified_at": int(stat.st_mtime),
    }


def load_source_text_cache():

    if not os.path.exists(SOURCE_TEXT_CACHE_FILE):
        return {}

    try:
        with open(SOURCE_TEXT_CACHE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}


def save_source_text_cache(cache):

    os.makedirs(os.path.dirname(SOURCE_TEXT_CACHE_FILE), exist_ok=True)

    with open(SOURCE_TEXT_CACHE_FILE, "w", encoding="utf-8") as file:
        json.dump(cache, file)


def read_source_text(source):

    normalized_source = os.path.normpath(source)
    cache_key = source_cache_key(normalized_source)

    if cache_key in SOURCE_TEXT_CACHE:
        return SOURCE_TEXT_CACHE[cache_key]

    text = ""

    if os.path.exists(normalized_source):
        fingerprint = source_file_fingerprint(normalized_source)
        disk_cache = load_source_text_cache()
        cached = disk_cache.get(cache_key)

        if cached and cached.get("fingerprint") == fingerprint:
            text = cached.get("text") or ""
            SOURCE_TEXT_CACHE[cache_key] = text
            return text

        try:
            from langchain_community.document_loaders import PyPDFLoader

            pages = PyPDFLoader(normalized_source).load()
            text = "\n\n".join(
                page.page_content
                for page in pages
            ).strip()
        except Exception:
            text = ""

        if text:
            disk_cache[cache_key] = {
                "fingerprint": fingerprint,
                "text": text,
            }
            save_source_text_cache(disk_cache)

    SOURCE_TEXT_CACHE[cache_key] = text

    return text


def get_source_text(sources):

    documents = []
    seen_documents = set()

    for source in sources:
        document = read_source_text(source)

        if document and document not in seen_documents:
            seen_documents.add(document)
            documents.append(document)

    return "\n".join(documents)


def normalize_text(text):

    text = text.lower()
    text = text.replace("multi-factor", "multi factor")
    text = text.replace("two-factor", "two factor")
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def significant_tokens(text):

    return {
        token
        for token in normalize_text(text).split()
        if len(token) > 3 and token not in STOP_WORDS
    }


def topic_term_matches(text, term):

    normalized_text = normalize_text(text)
    normalized_term = normalize_text(term)

    if " " in normalized_term:
        return normalized_term in normalized_text

    return normalized_term in set(normalized_text.split())


def policy_topic_matches(regulation, policy_name):

    terms = POLICY_TOPIC_TERMS.get(policy_name, set())
    return any(topic_term_matches(regulation, term) for term in terms)


def control_topic_matches(regulation, control_id):

    terms = CONTROL_TOPIC_TERMS.get(control_id, set())
    return any(topic_term_matches(regulation, term) for term in terms)


def text_relevance_score(regulation, candidate_text):

    regulation_text = normalize_text(regulation)
    candidate_text = normalize_text(candidate_text)
    regulation_tokens = significant_tokens(regulation)
    candidate_tokens = significant_tokens(candidate_text)
    score = len(regulation_tokens & candidate_tokens)

    for keyword_group in CONTROL_KEYWORD_GROUPS:
        regulation_matches = any(
            keyword in regulation_text or keyword in regulation_tokens
            for keyword in keyword_group
        )
        candidate_matches = any(
            keyword in candidate_text or keyword in candidate_tokens
            for keyword in keyword_group
        )

        if regulation_matches and candidate_matches:
            score += 4

    if (
        "multi factor authentication" in regulation_text
        and (
            "multi factor authentication" in candidate_text
            or "mfa" in candidate_tokens
        )
    ):
        score += 8

    return score


def extract_control_records(control_text):

    compact_text = re.sub(r"\s+", " ", control_text)
    pattern = re.compile(
        r"Control ID:\s*(C\d{3})\s+"
        r"Control Name:\s*(.*?)\s+"
        r"Description:\s*(.*?)"
        r"(?=\s+Control ID:\s*C\d{3}\s+Control Name:|\s+\d+\s*$|$)",
        re.IGNORECASE
    )
    records = []
    seen_control_ids = set()

    for match in pattern.finditer(compact_text):
        control_id = match.group(1).strip()

        if control_id in seen_control_ids:
            continue

        seen_control_ids.add(control_id)
        records.append(
            {
                "id": control_id,
                "name": match.group(2).strip(),
                "description": match.group(3).strip(),
            }
        )

    return records


def get_control_records():

    records = []

    for source in CONTROL_SOURCES:
        text = get_source_text([source])

        if not text:
            continue

        for record in extract_control_records(text):
            record["source"] = source
            records.append(record)

    return records


def control_relevance_score(regulation, control):

    return text_relevance_score(
        regulation,
        f"{control['name']} {control['description']}"
    )


def select_relevant_controls(regulation, controls):

    scored_controls = sorted(
        [
            (control_relevance_score(regulation, control), control)
            for control in controls
        ],
        key=lambda item: item[0],
        reverse=True
    )

    return [
        control
        for score, control in scored_controls
        if control_topic_matches(regulation, control["id"])
        and (
            score >= 4
            or control["id"] in {"C008", "C009", "C010", "C011", "C012", "C013"}
        )
    ]


def format_control_records(controls):

    return "\n".join(
        [
            (
                f"- {control['id']} {control['name']}: "
                f"{control['description']}"
            )
            for control in controls
        ]
    )


def get_policy_records():

    records = []

    for source in POLICY_SOURCES:
        text = get_source_text([source])

        if not text:
            continue

        records.append(
            {
                "source": source,
                "name": display_source_name(source),
                "text": text,
            }
        )

    return records


def policy_relevance_score(regulation, policy):

    return text_relevance_score(
        regulation,
        f"{policy['name']} {policy['text']}"
    )


def select_relevant_policies(regulation, policies):

    scored_policies = sorted(
        [
            (policy_relevance_score(regulation, policy), policy)
            for policy in policies
        ],
        key=lambda item: item[0],
        reverse=True
    )

    return [
        policy
        for score, policy in scored_policies
        if policy_topic_matches(regulation, policy["name"])
        and (
            score >= 4
            or policy["name"] in {
                "Business Continuity Policy",
                "Data Governance Policy",
                "Financial Crime Policy",
                "Data Privacy Policy",
            }
        )
    ]


def identify_control_gaps(regulation, controls):

    regulation_text = normalize_text(regulation)
    control_text = normalize_text(format_control_records(controls))
    gap_lines = []

    if "transaction" in regulation_text and "transaction" not in control_text:
        if (
            "multi factor authentication" in regulation_text
            or "mfa" in regulation_text
        ):
            gap_lines.append(
                "- Existing MFA control does not explicitly cover high-value transaction processing."
            )
        else:
            gap_lines.append(
                "- Existing controls do not explicitly cover the transaction processing scope in the regulation."
            )

    return gap_lines


def enforce_control_gaps(text, gap_lines):

    if not gap_lines:
        return text

    gap_text = "\n".join(gap_lines)

    if "Control Gaps:" in text:
        return re.sub(
            r"Control Gaps:\s*.*?(?=\n\s*Recommended Enhancements:|$)",
            f"Control Gaps:\n{gap_text}",
            text,
            flags=re.DOTALL
        ).strip()

    if "Recommended Enhancements:" in text:
        return text.replace(
            "Recommended Enhancements:",
            f"Control Gaps:\n{gap_text}\n\nRecommended Enhancements:"
        ).strip()

    return f"{text}\n\nControl Gaps:\n{gap_text}".strip()


def remove_stray_no_match(response, no_match_text):

    lines = response.strip().splitlines()
    meaningful_lines = [
        line for line in lines
        if line.strip()
    ]

    has_no_match = any(
        line.strip().strip('"') == no_match_text
        for line in meaningful_lines
    )

    if has_no_match and len(meaningful_lines) > 1:
        lines = [
            line for line in lines
            if line.strip().strip('"') != no_match_text
        ]

    return "\n".join(lines).strip() or no_match_text


def regulation_has_deadline(regulation):

    return bool(DEADLINE_PATTERN.search(regulation))


def infer_regulator(regulation):

    for regulator, pattern in REGULATOR_PATTERNS:
        if pattern.search(regulation or ""):
            return regulator

    return "Unknown"


def strip_markdown_heading(line):

    line = line.strip()
    line = re.sub(r"^#+\s*", "", line)
    line = re.sub(r"^\d+\.\s*", "", line)
    line = line.replace("**", "")

    return line.strip()


def clean_sentence(text):

    text = re.sub(r"\s+", " ", text).strip().strip("-* ")

    if not text:
        return text

    if text[-1] not in ".!?":
        text = f"{text}."

    return text[0].upper() + text[1:]


def extract_section_items(lines, section_name):

    section_items = []
    in_section = False

    for line in lines:
        stripped = strip_markdown_heading(line)
        lower_line = stripped.lower()

        if lower_line.startswith(f"{section_name.lower()}:"):
            in_section = True
            inline_value = stripped.split(":", 1)[1].strip()

            if inline_value:
                section_items.append(inline_value)

            continue

        if lower_line.startswith(
            ("summary:", "compliance obligations:", "deadlines:")
        ):
            in_section = False

        if in_section:
            section_items.append(stripped)

    return [
        clean_sentence(item)
        for item in section_items
        if item
    ]


def regulation_obligation(regulation):

    cleaned_regulation = re.sub(r"\s+", " ", regulation).strip().strip(".")
    requirement_match = re.search(
        r"\b(?:requires?|mandates?)\b\s+(.*)",
        cleaned_regulation,
        re.IGNORECASE
    )

    if requirement_match:
        obligation = requirement_match.group(1).strip().strip(".")
        obligation = re.sub(r"^that\s+", "", obligation, flags=re.IGNORECASE)

        if not re.match(
            r"^(implement|ensure|maintain|conduct|establish|enable|require)\b",
            obligation,
            re.IGNORECASE
        ):
            obligation = f"Implement {obligation}"

        return clean_sentence(obligation)

    if re.search(r"\b(must|shall)\b", cleaned_regulation, re.IGNORECASE):
        return clean_sentence(cleaned_regulation)

    return "Not specified in provided regulation."


def regulatory_update_subject(regulation):

    obligation = regulation_obligation(regulation).rstrip(".")
    if "not specified in provided regulation" in obligation.lower():
        return "the new regulatory requirement"

    return obligation.lower()


def clean_deadline_value(value):

    return clean_sentence(value).rstrip(".")


def regulation_deadline(regulation):

    text = re.sub(r"\s+", " ", regulation).strip()

    for pattern in DEADLINE_VALUE_PATTERNS:
        match = pattern.search(text)
        if match:
            return clean_deadline_value(match.group(0))

    return "Not specified in provided regulation."


def regulation_summary(regulation):

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", regulation).strip())
        if sentence.strip()
    ]
    summary = sentences[0] if sentences else regulation

    if len(summary) > 260:
        summary = summary[:257].rstrip() + "..."

    return clean_sentence(summary)


def deterministic_summary(regulation):

    deadlines = [regulation_deadline(regulation)] if regulation_has_deadline(regulation) else [
        "Not specified in provided regulation."
    ]

    return "\n".join(
        [
            "Summary:",
            f"- {regulation_summary(regulation)}",
            "",
            "Compliance Obligations:",
            f"- {regulation_obligation(regulation)}",
            "",
            "Deadlines:",
            *[f"- {deadline}" for deadline in deadlines],
        ]
    ).strip()


def deterministic_policy_mapping(regulation, relevant_policies):

    if not relevant_policies:
        return "No matching internal policy found"

    obligation = regulatory_update_subject(regulation)
    policy_names = [policy["name"] for policy in relevant_policies]

    return "\n".join(
        [
            "Impacted Policies:",
            *[f"- {name}" for name in policy_names],
            "",
            "Required Updates:",
            *[
                f"- {name}: Review and update coverage for {obligation.lower()}."
                for name in policy_names
            ],
        ]
    ).strip()


def deterministic_control_matrix(regulation, relevant_controls, gap_lines):

    if not relevant_controls:
        return "No matching controls found in Control Matrix"

    obligation = regulatory_update_subject(regulation)
    control_lines = [
        f"- {control['id']} {control['name']}"
        for control in relevant_controls
    ]
    gaps = gap_lines or [
        "- No additional control gap identified from the provided Control Matrix excerpts."
    ]

    if gap_lines:
        enhancements = [
            f"- Update impacted controls to address {obligation.lower()}."
        ]
    else:
        enhancements = [
            "- Review control evidence against the new regulatory requirement."
        ]

    return "\n".join(
        [
            "Impacted Controls:",
            *control_lines,
            "",
            "Control Gaps:",
            *gaps,
            "",
            "Recommended Enhancements:",
            *enhancements,
        ]
    ).strip()


def clean_summary_output(response, regulation):

    regulation_lower = regulation.lower()
    cleaned_lines = []
    unsupported_terms = {
        "consent": ["consent"],
        "report": ["report"],
        "reports": ["report"],
        "documented": ["document", "record"],
        "records": ["record", "retain", "maintain"],
        "fraud": ["fraud"],
        "industry best practices": ["industry best practices"],
    }

    for line in response.strip().splitlines():
        stripped = line.strip()
        line_lower = stripped.lower()

        if not stripped or stripped == "---":
            continue

        if "[date]" in line_lower or "[insert" in line_lower:
            continue

        if line_lower.startswith("please note"):
            continue

        if any(
            term in line_lower
            and not any(source_term in regulation_lower for source_term in source_terms)
            for term, source_terms in unsupported_terms.items()
        ):
            continue

        cleaned_lines.append(stripped)

    summary_items = extract_section_items(cleaned_lines, "Summary")
    obligation_items = extract_section_items(
        cleaned_lines,
        "Compliance Obligations"
    )

    if not summary_items:
        summary_items = [clean_sentence(regulation)]

    if (
        not obligation_items
        or any(
            "not specified" in item.lower()
            or "none specified" in item.lower()
            for item in obligation_items
        )
    ):
        obligation_items = [regulation_obligation(regulation)]

    if regulation_has_deadline(regulation):
        deadline_items = extract_section_items(cleaned_lines, "Deadlines")

        if (
            not deadline_items
            or any("[date]" in item.lower() or "[insert" in item.lower() for item in deadline_items)
        ):
            deadline_items = [regulation_deadline(regulation)]
    else:
        deadline_items = ["Not specified in provided regulation."]

    return "\n".join(
        [
            "Summary:",
            *[f"- {item}" for item in summary_items],
            "",
            "Compliance Obligations:",
            *[f"- {item}" for item in obligation_items],
            "",
            "Deadlines:",
            *[f"- {item}" for item in deadline_items],
        ]
    ).strip()


def clean_model_output(response, no_match_text):

    text = remove_stray_no_match(response, no_match_text)
    has_structured_output = any(
        heading in text
        for heading in [
            "Impacted Policies:",
            "Impacted Controls:",
            "Required Updates:",
            "Control Gaps:",
        ]
    )

    cleaned_lines = []
    no_match_key = no_match_text.lower()

    for line in text.splitlines():
        if line.strip().lower() in {"option a:", "option b:"}:
            continue

        if has_structured_output and no_match_key in line.lower():
            continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).strip()

    replacements = {
        "RBI regulations": "the new regulatory requirement",
        "RBI regulation": "the new regulatory requirement",
        "RBI's": "the regulator's",
        "RBI": "the regulator",
        "PMLA": "the external regulation",
        "Banking Regulation Act": "the external regulation",
        "KYC Directions": "the external regulation",
        "GDPR": "the external regulation",
        "CCPA": "the external regulation",
        "the regulator requirements": "the regulatory requirement",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text or no_match_text


def clean_control_output(response, no_match_text, control_context, gap_lines=None):

    text = clean_model_output(response, no_match_text)
    allowed_control_ids = set(
        re.findall(r"\bC\d{3}\b", control_context)
    )

    cleaned_lines = []

    for line in text.splitlines():
        line_control_ids = re.findall(r"\bC\d{3}\b", line)

        if line_control_ids and any(
            control_id not in allowed_control_ids
            for control_id in line_control_ids
        ):
            continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).strip() or no_match_text

    return enforce_control_gaps(text, gap_lines or [])


class ComplianceState(TypedDict):

    regulation: str
    analysis_provider: str
    context: str
    summary: str
    mapping: str
    control_matrix: str
    impact_tracker: str
    tracker_record: Dict[str, Any]
    regulation_metadata: Dict[str, Any]
    policy_records: list
    relevant_policies: list
    control_records: list
    relevant_controls: list
    retrieval_diagnostics: Dict[str, Any]


def retrieve_node(state):

    start = time.time()

    if state["analysis_provider"] == "rule_based":
        state["context"] = ""
        state["retrieval_diagnostics"] = {
            "strategy": "hybrid_deterministic",
            "query_complexity": query_complexity(state["regulation"]),
            "corrective_action": "none",
        }

        print(
            f"RETRIEVE NODE: {round(time.time() - start, 2)} seconds"
        )

        return state

    docs = get_retriever().invoke(
        state["regulation"]
    )

    context = "\n".join(
        [doc.page_content[:500] for doc in docs]
    )

    state["context"] = context
    state["retrieval_diagnostics"] = {
        "strategy": "semantic_top_k",
        "query_complexity": query_complexity(state["regulation"]),
        "retrieved_chunks": len(docs),
        "retrieved_sources": sorted(
            {
                doc.metadata.get("source")
                for doc in docs
                if doc.metadata.get("source")
            }
        ),
        "corrective_action": "none" if docs else "human_review_required",
    }

    print(
        f"RETRIEVE NODE: {round(time.time() - start, 2)} seconds"
    )

    return state


def summary_node(state):

    start = time.time()

    if state["analysis_provider"] == "rule_based":
        state["summary"] = deterministic_summary(state["regulation"])

        print(
            f"SUMMARY NODE: {round(time.time() - start, 2)} seconds"
        )

        return state

    prompt = f"""
    Analyze the regulation.

    Regulation:
    {state['regulation']}

    Use ONLY the regulation text above.
    Do not use external knowledge.
    Do not infer extra obligations.
    Do not invent dates, deadlines, consent requirements, reports, records, or implementation details.
    Do not write placeholders such as [Date] or [INSERT DEADLINE].

    If a detail is not stated in the regulation, write:
    Not specified in provided regulation.

    Output exactly in this format:

    Summary:
    - ...

    Compliance Obligations:
    - ...

    Deadlines:
    - ...

    Keep the response concise.
    Limit response to 150 words.
    """

    response = get_llm(state["analysis_provider"]).invoke(prompt)

    state["summary"] = clean_summary_output(
        response.content,
        state["regulation"]
    )

    print(
        f"SUMMARY NODE: {round(time.time() - start, 2)} seconds"
    )

    return state


def mapping_node(state):

    start = time.time()

    policies = get_policy_records()
    relevant_policies = select_relevant_policies(
        state["regulation"],
        policies
    )
    state["policy_records"] = policies
    state["relevant_policies"] = relevant_policies
    no_match_text = "No matching internal policy found"

    if not relevant_policies:
        state["mapping"] = no_match_text

        print(
            f"MAPPING NODE: {round(time.time() - start, 2)} seconds"
        )

        return state

    if state["analysis_provider"] == "rule_based":
        mapping_text = deterministic_policy_mapping(
            state["regulation"],
            relevant_policies
        )
        state["mapping"] = append_evidence_section(
            mapping_text,
            policy_record_evidence_lines(relevant_policies)
        )

        print(
            f"MAPPING NODE: {round(time.time() - start, 2)} seconds"
        )

        return state

    policy_docs = retrieve_source_docs(
        state["regulation"],
        [policy["source"] for policy in relevant_policies]
    )
    if any(
        doc.metadata.get("retrieval_strategy") == "corrective_fallback"
        for doc in policy_docs
    ):
        state["retrieval_diagnostics"]["corrective_action"] = "source_metadata_fallback"
    policy_context = format_docs(policy_docs)

    if not policy_context:
        state["mapping"] = no_match_text

        print(
            f"MAPPING NODE: {round(time.time() - start, 2)} seconds"
        )

        return state

    prompt = f"""
    Regulation:
    {state['regulation']}

    Internal Policy Documents:
    {policy_context}

    You MUST use ONLY the information present in the Internal Policy Documents.

    Do not infer.
    Do not guess.
    Do not create policy names.
    Do not use external knowledge.

    You are a compliance officer.

    Identify:

    1. Impacted internal policies
    2. Required internal policy updates

    Rules:

    - Only use policy names shown in the Internal Policy Documents above.

    - Never mention RBI, PMLA,
      Banking Regulation Act,
      KYC Directions, GDPR, CCPA, or any external regulation.

    - Do not create new policy names.
    - Required updates must refer to "the new regulatory requirement".
    - Do not name the external regulation in the output.
    - Required updates must directly address the regulation.
    - Do not add unrelated updates such as encryption, consent, retention, reporting, or access review unless the regulation explicitly requires them.

    Choose exactly one response type.
    Do not print labels such as "Option A" or "Option B".

    If a matching internal policy exists, use this format:

    Impacted Policies:
    - ...

    Required Updates:
    - ...

    If no matching policy exists, output exactly:
    {no_match_text}

    Never include both the structured format and the no-match sentence.

    Keep the response concise.
    Limit response to 150 words.
    """

    response = get_llm(state["analysis_provider"]).invoke(prompt)

    mapping_text = clean_model_output(
        response.content,
        no_match_text
    )
    state["mapping"] = append_evidence_section(
        mapping_text,
        policy_evidence_lines(mapping_text, policy_docs, state["regulation"])
    )

    print(
        f"MAPPING NODE: {round(time.time() - start, 2)} seconds"
    )

    return state


def control_matrix_node(state):

    start = time.time()

    controls = get_control_records()
    relevant_controls = select_relevant_controls(
        state["regulation"],
        controls
    )
    state["control_records"] = controls
    state["relevant_controls"] = relevant_controls
    cm_context = format_control_records(relevant_controls)
    gap_lines = identify_control_gaps(
        state["regulation"],
        relevant_controls
    )
    no_match_text = "No matching controls found in Control Matrix"

    if not relevant_controls:
        state["control_matrix"] = no_match_text

        print(
            f"CONTROL MATRIX NODE: {round(time.time() - start, 2)} seconds"
        )

        return state

    if state["analysis_provider"] == "rule_based":
        control_matrix_text = deterministic_control_matrix(
            state["regulation"],
            relevant_controls,
            gap_lines
        )
        state["control_matrix"] = append_evidence_section(
            control_matrix_text,
            control_evidence_lines(relevant_controls)
        )

        print(
            f"CONTROL MATRIX NODE: {round(time.time() - start, 2)} seconds"
        )

        return state

    prompt = f"""
    Regulation:
    {state['regulation']}

    Relevant Control Matrix Records:
    {cm_context}

    You MUST use ONLY the relevant Control Matrix records above.

    You are a compliance officer mapping a regulation to the internal Control Matrix.

    Identify:

    1. Impacted controls (control IDs or names from the Control Matrix)
    2. Control gaps (controls that need to be added or updated)
    3. Recommended control enhancements

    Rules:

    - Only reference controls listed in the Relevant Control Matrix Records above.
    - Do not invent control names or IDs.
    - Never mention external regulations by name.
    - Treat a listed control as impacted only if it directly relates to the regulation.
    - If a listed control only partially covers the regulation, put the missing coverage under Control Gaps.
    - If these coverage gaps are listed, include them under Control Gaps:
      {chr(10).join(gap_lines) if gap_lines else "- No deterministic coverage gaps identified."}
    - If matching controls exist but no gap is supported, write:
      "- No additional control gap identified from the provided Control Matrix excerpts."
    - Do not say no controls were identified if you listed impacted controls.
    - Recommended enhancements must directly relate to the impacted controls or gaps.

    Choose exactly one response type.
    Do not print labels such as "Option A" or "Option B".

    If matching controls exist, use this format:

    Impacted Controls:
    - ...

    Control Gaps:
    - ...

    Recommended Enhancements:
    - ...

    If no matching controls exist, output exactly:
    {no_match_text}

    Never include both the structured format and the no-match sentence.

    Keep the response concise.
    Limit response to 200 words.
    """

    response = get_llm(state["analysis_provider"]).invoke(prompt)

    control_matrix_text = clean_control_output(
        response.content,
        no_match_text,
        cm_context,
        gap_lines
    )
    state["control_matrix"] = append_evidence_section(
        control_matrix_text,
        control_evidence_lines(relevant_controls)
    )

    print(
        f"CONTROL MATRIX NODE: {round(time.time() - start, 2)} seconds"
    )

    return state


def tracker_node(state):

    start = time.time()

    state["tracker_record"] = build_impact_tracker_record(state)
    state["impact_tracker"] = format_impact_tracker_record(
        state["tracker_record"]
    )

    print(
        f"TRACKER NODE: {round(time.time() - start, 2)} seconds"
    )

    return state


builder = StateGraph(ComplianceState)

builder.add_node("retrieve", retrieve_node)
builder.add_node("summary", summary_node)
builder.add_node("mapping", mapping_node)
builder.add_node("control_matrix", control_matrix_node)
builder.add_node("tracker", tracker_node)

builder.set_entry_point("retrieve")

builder.add_edge("retrieve", "summary")
builder.add_edge("summary", "mapping")
builder.add_edge("mapping", "control_matrix")
builder.add_edge("control_matrix", "tracker")
builder.add_edge("tracker", END)

graph = builder.compile()


def analyze_regulation(
    regulation,
    regulation_metadata: Optional[Dict[str, Any]] = None,
    persist: bool = False,
    file_id: Optional[int] = None,
    analysis_provider: Optional[str] = None,
):

    total_start = time.time()
    selected_provider = resolve_analysis_provider(analysis_provider)

    result = graph.invoke(
        {
            "regulation": regulation,
            "analysis_provider": selected_provider,
            "context": "",
            "summary": "",
            "mapping": "",
            "control_matrix": "",
            "impact_tracker": "",
            "tracker_record": {},
            "regulation_metadata": regulation_metadata or {},
            "policy_records": [],
            "relevant_policies": [],
            "control_records": [],
            "relevant_controls": [],
            "retrieval_diagnostics": {},
        }
    )

    if persist:
        from ..storage.tracker_store import save_analysis_result

        saved_record = save_analysis_result(
            result,
            regulation,
            metadata=regulation_metadata or {},
            file_id=file_id,
        )
        result["tracker_record"] = {
            **(result.get("tracker_record") or {}),
            **saved_record,
            "change_detected": bool(saved_record.get("change_detected")),
        }
        result["impact_tracker"] = format_impact_tracker_record(
            result["tracker_record"]
        )

    print(
        f"\nTOTAL EXECUTION TIME: {round(time.time() - total_start, 2)} seconds\n"
    )

    return result


if __name__ == "__main__":

    result = analyze_regulation(
        """
        RBI requires multi-factor authentication
        for all high-value transactions.
        """
    )

    print("\nSUMMARY\n")
    print(result["summary"])

    print("\nMAPPING\n")
    print(result["mapping"])

    print("\nCONTROL MATRIX\n")
    print(result["control_matrix"])

    print("\nPOLICY COMPLIANCE TRACKER\n")
    print(result["impact_tracker"])
