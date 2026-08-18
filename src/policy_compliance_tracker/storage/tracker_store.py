import json
import os
import hashlib
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from ..config import TRACKER_DB_PATH, TRACKER_STATUS_VALUES


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@contextmanager
def connect():
    os.makedirs(os.path.dirname(TRACKER_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(TRACKER_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def has_actionable_text(value: Optional[str]) -> bool:
    if not value:
        return False

    normalized = value.strip().lower()
    if not normalized:
        return False

    non_actionable = {
        "none",
        "not available",
        "not applicable",
        "no matching internal policy found",
        "no policy change reason recorded.",
        "no required policy update recorded.",
    }

    return normalized not in non_actionable


def normalize_regulation_text(value: Optional[str]) -> str:
    if not value:
        return ""

    text = value.strip().lower()
    text = text.replace("multi-factor", "multi factor")
    text = text.replace("two-factor", "two factor")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def regulation_fingerprint(value: Optional[str]) -> Optional[str]:
    normalized = normalize_regulation_text(value)
    if not normalized:
        return None

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


RESOLVED_STATUSES = {"Closed", "Validated"}


def tracker_identity_text(record: Dict[str, Any]) -> str:
    for field in ("regulatory_update", "regulation_title", "compliance_obligation"):
        value = record.get(field)
        if has_actionable_text(value):
            return str(value)
    return ""


def tracker_dedupe_key(record: Dict[str, Any]) -> str:
    fingerprint = record.get("regulation_fingerprint")
    if fingerprint:
        return f"fingerprint:{fingerprint}"

    identity = tracker_identity_text(record)
    fingerprint = regulation_fingerprint(identity)
    if fingerprint:
        return f"fingerprint:{fingerprint}"

    return f"tracker:{record.get('tracker_id') or ''}"


def tracker_sort_key(record: Dict[str, Any]) -> tuple:
    status = record.get("status")
    resolved_rank = 0 if status in RESOLVED_STATUSES else 1
    return (
        resolved_rank,
        record.get("updated_at") or record.get("created_at") or "",
        record.get("tracker_id") or "",
    )


def deduplicate_tracker_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(tracker_dedupe_key(entry), []).append(entry)

    canonical = [
        sorted(group, key=tracker_sort_key, reverse=False)[0]
        for group in grouped.values()
    ]
    return sorted(
        canonical,
        key=lambda entry: (entry.get("updated_at") or "", entry.get("tracker_id") or ""),
        reverse=True,
    )


def consolidate_duplicate_trackers() -> Dict[str, int]:
    init_db()
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM tracker_entries
                ORDER BY updated_at DESC, tracker_id DESC
                """
            ).fetchall()
        )

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(tracker_dedupe_key(row), []).append(row)

        removed = 0
        groups_merged = 0
        now = utc_now()

        for group in grouped.values():
            if len(group) <= 1:
                continue

            keep = sorted(group, key=tracker_sort_key, reverse=False)[0]
            duplicate_ids = [
                row["tracker_id"]
                for row in group
                if row["tracker_id"] != keep["tracker_id"]
            ]
            if not duplicate_ids:
                continue

            placeholders = ",".join("?" for _ in duplicate_ids)
            conn.execute(
                f"""
                UPDATE notifications
                SET tracker_id = ?, read_at = COALESCE(read_at, ?)
                WHERE tracker_id IN ({placeholders})
                """,
                [keep["tracker_id"], now, *duplicate_ids],
            )
            if keep.get("status") in RESOLVED_STATUSES:
                conn.execute(
                    """
                    UPDATE notifications
                    SET read_at = COALESCE(read_at, ?)
                    WHERE tracker_id = ?
                    """,
                    (now, keep["tracker_id"]),
                )
            conn.execute(
                f"""
                DELETE FROM tracker_entries
                WHERE tracker_id IN ({placeholders})
                """,
                duplicate_ids,
            )
            removed += len(duplicate_ids)
            groups_merged += 1

    return {"groups_merged": groups_merged, "trackers_removed": removed}


def clear_tracker_data() -> Dict[str, int]:
    init_db()
    with connect() as conn:
        counts = {
            "notifications": conn.execute(
                "SELECT COUNT(*) AS value FROM notifications"
            ).fetchone()["value"],
            "tracker_entries": conn.execute(
                "SELECT COUNT(*) AS value FROM tracker_entries"
            ).fetchone()["value"],
            "audit_trail": conn.execute(
                "SELECT COUNT(*) AS value FROM audit_trail"
            ).fetchone()["value"],
        }
        conn.execute("DELETE FROM notifications")
        conn.execute("DELETE FROM tracker_entries")
        conn.execute("DELETE FROM audit_trail")
        # A cleared demo workspace should restart generated alert and audit IDs.
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('notifications', 'audit_trail')"
        )
    return counts


def tracker_texts_match(left: Optional[str], right: Optional[str]) -> bool:
    left_normalized = normalize_regulation_text(left)
    right_normalized = normalize_regulation_text(right)
    if not left_normalized or not right_normalized:
        return False

    if left_normalized == right_normalized:
        return True

    shorter, longer = sorted(
        [left_normalized, right_normalized],
        key=len,
    )
    if len(shorter) >= 40 and shorter in longer:
        return True

    left_tokens = {
        token for token in left_normalized.split()
        if len(token) > 2 and token not in STOP_WORDS_FOR_MATCHING
    }
    right_tokens = {
        token for token in right_normalized.split()
        if len(token) > 2 and token not in STOP_WORDS_FOR_MATCHING
    }
    if not left_tokens or not right_tokens:
        return False

    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap >= 0.86


STOP_WORDS_FOR_MATCHING = {
    "all",
    "and",
    "are",
    "for",
    "from",
    "must",
    "new",
    "not",
    "the",
    "this",
    "to",
    "with",
}


def ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS regulation_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                semantic_key TEXT,
                title TEXT,
                regulator TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                supersedes_file_id INTEGER,
                duplicate_of_file_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                size_bytes INTEGER,
                modified_at TEXT,
                detected_at TEXT NOT NULL,
                processed_at TEXT,
                analysis_error TEXT,
                content_text TEXT,
                source_url TEXT,
                feed_name TEXT,
                downloaded_at TEXT,
                regulator_source TEXT,
                FOREIGN KEY (supersedes_file_id) REFERENCES regulation_files(id),
                FOREIGN KEY (duplicate_of_file_id) REFERENCES regulation_files(id)
            );

            CREATE INDEX IF NOT EXISTS idx_regulation_files_sha
                ON regulation_files(sha256);
            CREATE INDEX IF NOT EXISTS idx_regulation_files_semantic
                ON regulation_files(semantic_key, version);

            CREATE TABLE IF NOT EXISTS tracker_entries (
                tracker_id TEXT PRIMARY KEY,
                regulation_file_id INTEGER,
                regulation_title TEXT,
                regulator TEXT,
                version INTEGER,
                supersedes_tracker_id TEXT,
                status TEXT NOT NULL,
                owner TEXT,
                priority TEXT,
                risk_score INTEGER,
                risk_score_max INTEGER DEFAULT 25,
                confidence REAL,
                regulatory_update TEXT,
                compliance_obligation TEXT,
                impacted_policy TEXT,
                required_policy_update TEXT,
                impacted_control TEXT,
                control_gap TEXT,
                recommended_enhancement TEXT,
                due_date TEXT,
                evidence TEXT,
                affected_controls_count INTEGER,
                affected_policies_count INTEGER,
                policy_change_required INTEGER DEFAULT 0,
                policy_change_reason TEXT,
                change_detected INTEGER DEFAULT 0,
                change_summary TEXT,
                change_impact TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_path TEXT,
                source_url TEXT,
                feed_name TEXT,
                downloaded_at TEXT,
                regulator_source TEXT,
                regulation_fingerprint TEXT,
                analysis_json TEXT,
                obligations_structured TEXT,
                evidence_records TEXT,
                retrieval_diagnostics TEXT,
                mapping_graph TEXT,
                 review_required INTEGER DEFAULT 0,
                 review_reason TEXT,
                 analysis_provider TEXT DEFAULT 'rule_based',
                FOREIGN KEY (regulation_file_id) REFERENCES regulation_files(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tracker_status
                ON tracker_entries(status);
            CREATE INDEX IF NOT EXISTS idx_tracker_owner
                ON tracker_entries(owner);
            CREATE INDEX IF NOT EXISTS idx_tracker_priority
                ON tracker_entries(priority);

            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id TEXT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'Dashboard',
                created_at TEXT NOT NULL,
                read_at TEXT,
                FOREIGN KEY (tracker_id) REFERENCES tracker_entries(tracker_id)
            );

            CREATE TABLE IF NOT EXISTS rag_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                expected_sources TEXT,
                returned_sources TEXT,
                metric_scope TEXT DEFAULT 'legacy_multi_source',
                scoring_depth INTEGER,
                precision REAL,
                recall REAL,
                f1 REAL,
                mrr REAL,
                hit_rate REAL,
                context_relevance REAL,
                created_at TEXT NOT NULL
            );
            """
        )
        ensure_columns(
            conn,
            "regulation_files",
            {
                "source_url": "TEXT",
                "feed_name": "TEXT",
                "downloaded_at": "TEXT",
                "regulator_source": "TEXT",
            },
        )
        ensure_columns(
            conn,
            "tracker_entries",
            {
                "policy_change_required": "INTEGER DEFAULT 0",
                "policy_change_reason": "TEXT",
                "source_url": "TEXT",
                "feed_name": "TEXT",
                "downloaded_at": "TEXT",
                "regulator_source": "TEXT",
                "regulation_fingerprint": "TEXT",
                "obligations_structured": "TEXT",
                "evidence_records": "TEXT",
                "retrieval_diagnostics": "TEXT",
                "mapping_graph": "TEXT",
                 "review_required": "INTEGER DEFAULT 0",
                 "review_reason": "TEXT",
                 "analysis_provider": "TEXT DEFAULT 'rule_based'",
            },
        )
        ensure_columns(
            conn,
            "rag_evaluations",
            {
                "metric_scope": "TEXT DEFAULT 'legacy_multi_source'",
                "scoring_depth": "INTEGER",
                "f1": "REAL",
                "mrr": "REAL",
            },
        )
        rows = conn.execute(
            """
            SELECT tracker_id, regulatory_update, regulation_title
            FROM tracker_entries
            WHERE regulation_fingerprint IS NULL
               OR TRIM(regulation_fingerprint) = ''
            """
        ).fetchall()
        for row in rows:
            fingerprint = regulation_fingerprint(
                row["regulatory_update"] or row["regulation_title"]
            )
            if fingerprint:
                conn.execute(
                    """
                    UPDATE tracker_entries
                    SET regulation_fingerprint = ?
                    WHERE tracker_id = ?
                    """,
                    (fingerprint, row["tracker_id"]),
                )


def next_tracker_id() -> str:
    init_db()
    prefix = f"RIT-{datetime.utcnow().strftime('%Y%m%d')}"
    with connect() as conn:
        row = conn.execute(
            """
            SELECT tracker_id
            FROM tracker_entries
            WHERE tracker_id LIKE ?
            ORDER BY tracker_id DESC
            LIMIT 1
            """,
            (f"{prefix}-%",),
        ).fetchone()

    if not row:
        return f"{prefix}-001"

    try:
        sequence = int(row["tracker_id"].rsplit("-", 1)[1]) + 1
    except (IndexError, ValueError):
        sequence = 1

    return f"{prefix}-{sequence:03d}"


def log_audit(entity_type: str, entity_id: str, action: str, details: Any = None) -> None:
    init_db()
    if details is not None and not isinstance(details, str):
        details = json.dumps(details, default=str)

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_trail(entity_type, entity_id, action, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, action, details, utc_now()),
        )


def get_regulation_file_by_path(file_path: str) -> Optional[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM regulation_files WHERE file_path = ?",
            (file_path,),
        ).fetchone()
    return row_to_dict(row)


def find_file_by_hash(sha256: str) -> Optional[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM regulation_files
            WHERE sha256 = ? AND status = 'processed'
            ORDER BY processed_at DESC
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()
    return row_to_dict(row)


def fetch_processed_regulations() -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM regulation_files
            WHERE status = 'processed'
            ORDER BY processed_at DESC, id DESC
            """
        ).fetchall()
    return rows_to_dicts(rows)


def upsert_regulation_file(file_info: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    existing = get_regulation_file_by_path(file_info["file_path"])
    now = utc_now()

    values = {
        "file_path": file_info["file_path"],
        "file_name": file_info.get("file_name") or os.path.basename(file_info["file_path"]),
        "sha256": file_info["sha256"],
        "semantic_key": file_info.get("semantic_key"),
        "title": file_info.get("title"),
        "regulator": file_info.get("regulator"),
        "version": int(file_info.get("version") or 1),
        "supersedes_file_id": file_info.get("supersedes_file_id"),
        "duplicate_of_file_id": file_info.get("duplicate_of_file_id"),
        "status": file_info.get("status") or (existing["status"] if existing else "pending"),
        "size_bytes": file_info.get("size_bytes"),
        "modified_at": file_info.get("modified_at"),
        "detected_at": existing["detected_at"] if existing else now,
        "processed_at": file_info.get("processed_at", existing["processed_at"] if existing else None),
        "analysis_error": file_info.get("analysis_error", existing["analysis_error"] if existing else None),
        "content_text": file_info.get("content_text", existing["content_text"] if existing else None),
        "source_url": file_info.get("source_url", existing["source_url"] if existing else None),
        "feed_name": file_info.get("feed_name", existing["feed_name"] if existing else None),
        "downloaded_at": file_info.get("downloaded_at", existing["downloaded_at"] if existing else None),
        "regulator_source": file_info.get("regulator_source", existing["regulator_source"] if existing else None),
    }

    with connect() as conn:
        if existing:
            conn.execute(
                """
                UPDATE regulation_files
                SET file_name = :file_name,
                    sha256 = :sha256,
                    semantic_key = :semantic_key,
                    title = :title,
                    regulator = :regulator,
                    version = :version,
                    supersedes_file_id = :supersedes_file_id,
                    duplicate_of_file_id = :duplicate_of_file_id,
                    status = :status,
                    size_bytes = :size_bytes,
                    modified_at = :modified_at,
                    processed_at = :processed_at,
                    analysis_error = :analysis_error,
                    content_text = :content_text,
                    source_url = :source_url,
                    feed_name = :feed_name,
                    downloaded_at = :downloaded_at,
                    regulator_source = :regulator_source
                WHERE file_path = :file_path
                """,
                values,
            )
        else:
            conn.execute(
                """
                INSERT INTO regulation_files(
                    file_path, file_name, sha256, semantic_key, title, regulator,
                    version, supersedes_file_id, duplicate_of_file_id, status,
                    size_bytes, modified_at, detected_at, processed_at,
                    analysis_error, content_text, source_url, feed_name,
                    downloaded_at, regulator_source
                )
                VALUES (
                    :file_path, :file_name, :sha256, :semantic_key, :title,
                    :regulator, :version, :supersedes_file_id,
                    :duplicate_of_file_id, :status, :size_bytes, :modified_at,
                    :detected_at, :processed_at, :analysis_error, :content_text,
                    :source_url, :feed_name, :downloaded_at, :regulator_source
                )
                """,
                values,
            )

        row = conn.execute(
            "SELECT * FROM regulation_files WHERE file_path = ?",
            (file_info["file_path"],),
        ).fetchone()

    return dict(row)


def mark_regulation_processed(file_id: int, tracker_id: str) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            UPDATE regulation_files
            SET status = 'processed', processed_at = ?, analysis_error = NULL
            WHERE id = ?
            """,
            (utc_now(), file_id),
        )
    log_audit("regulation_file", str(file_id), "processed", {"tracker_id": tracker_id})


def mark_regulation_error(file_id: int, error: str) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            UPDATE regulation_files
            SET status = 'error', processed_at = ?, analysis_error = ?
            WHERE id = ?
            """,
            (utc_now(), error[:2000], file_id),
        )
    log_audit("regulation_file", str(file_id), "analysis_failed", error[:2000])


def get_tracker_by_file_id(file_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM tracker_entries
            WHERE regulation_file_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (file_id,),
        ).fetchone()
    return row_to_dict(row)


def save_tracker_entry(
    tracker_record: Dict[str, Any],
    analysis_result: Optional[Dict[str, Any]] = None,
    file_id: Optional[int] = None,
) -> Dict[str, Any]:
    init_db()
    now = utc_now()
    record = dict(tracker_record)
    tracker_id = record.get("tracker_id") or next_tracker_id()
    existing = None

    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM tracker_entries WHERE tracker_id = ?",
            (tracker_id,),
        ).fetchone()

    created_at = existing["created_at"] if existing else now
    status = record.get("status") or (existing["status"] if existing else "Open")
    if status not in TRACKER_STATUS_VALUES:
        status = "Open"

    policy_change_required = 1 if record.get("policy_change_required") else 0
    policy_change_reason = record.get("policy_change_reason")
    impacted_policy = record.get("impacted_policy")
    required_policy_update = record.get("required_policy_update")

    if not policy_change_required and has_actionable_text(impacted_policy):
        policy_change_required = 1
        policy_change_reason = (
            policy_change_reason
            or (
                required_policy_update
                if has_actionable_text(required_policy_update)
                else "Impacted policy identified; compliance team review required to confirm update wording."
            )
        )

    computed_fingerprint = (
        record.get("regulation_fingerprint")
        or regulation_fingerprint(record.get("regulatory_update"))
        or regulation_fingerprint(record.get("regulation_title"))
    )

    values = {
        "tracker_id": tracker_id,
        "regulation_file_id": file_id or record.get("regulation_file_id"),
        "regulation_title": record.get("regulation_title"),
        "regulator": record.get("regulator"),
        "version": record.get("version") or 1,
        "supersedes_tracker_id": record.get("supersedes_tracker_id"),
        "status": status,
        "owner": record.get("owner") or "Compliance Team",
        "priority": record.get("priority") or "Review",
        "risk_score": record.get("risk_score") or 0,
        "risk_score_max": record.get("risk_score_max") or 25,
        "confidence": record.get("confidence") or 0,
        "regulatory_update": record.get("regulatory_update"),
        "compliance_obligation": record.get("compliance_obligation"),
        "impacted_policy": impacted_policy,
        "required_policy_update": required_policy_update,
        "impacted_control": record.get("impacted_control"),
        "control_gap": record.get("control_gap"),
        "recommended_enhancement": record.get("recommended_enhancement"),
        "due_date": record.get("due_date"),
        "evidence": record.get("evidence"),
        "affected_controls_count": record.get("affected_controls_count") or 0,
        "affected_policies_count": record.get("affected_policies_count") or 0,
        "policy_change_required": policy_change_required,
        "policy_change_reason": policy_change_reason,
        "change_detected": 1 if record.get("change_detected") else 0,
        "change_summary": record.get("change_summary"),
        "change_impact": record.get("change_impact"),
        "created_at": created_at,
        "updated_at": now,
        "source_path": record.get("source_path"),
        "source_url": record.get("source_url"),
        "feed_name": record.get("feed_name"),
        "downloaded_at": record.get("downloaded_at"),
        "regulator_source": record.get("regulator_source"),
        "regulation_fingerprint": computed_fingerprint,
        "analysis_json": json.dumps(analysis_result or {}, default=str),
        "obligations_structured": json.dumps(record.get("obligations_structured") or [], default=str),
        "evidence_records": json.dumps(record.get("evidence_records") or [], default=str),
        "retrieval_diagnostics": json.dumps(record.get("retrieval_diagnostics") or {}, default=str),
        "mapping_graph": json.dumps(record.get("mapping_graph") or [], default=str),
         "review_required": 1 if record.get("review_required") else 0,
         "review_reason": record.get("review_reason") or "",
         "analysis_provider": record.get("analysis_provider") or "rule_based",
    }

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tracker_entries(
                tracker_id, regulation_file_id, regulation_title, regulator,
                version, supersedes_tracker_id, status, owner, priority,
                risk_score, risk_score_max, confidence, regulatory_update,
                compliance_obligation, impacted_policy, required_policy_update,
                impacted_control, control_gap, recommended_enhancement,
                due_date, evidence, affected_controls_count,
                affected_policies_count, policy_change_required,
                policy_change_reason, change_detected, change_summary,
                change_impact, created_at, updated_at, source_path,
                source_url, feed_name, downloaded_at, regulator_source,
                regulation_fingerprint, analysis_json, obligations_structured,
                 evidence_records, retrieval_diagnostics, mapping_graph,
                 review_required, review_reason, analysis_provider
            )
            VALUES (
                :tracker_id, :regulation_file_id, :regulation_title,
                :regulator, :version, :supersedes_tracker_id, :status,
                :owner, :priority, :risk_score, :risk_score_max, :confidence,
                :regulatory_update, :compliance_obligation, :impacted_policy,
                :required_policy_update, :impacted_control, :control_gap,
                :recommended_enhancement, :due_date, :evidence,
                :affected_controls_count, :affected_policies_count,
                :policy_change_required, :policy_change_reason,
                :change_detected, :change_summary, :change_impact,
                :created_at, :updated_at, :source_path, :source_url,
                :feed_name, :downloaded_at, :regulator_source,
                :regulation_fingerprint, :analysis_json, :obligations_structured,
                 :evidence_records, :retrieval_diagnostics, :mapping_graph,
                 :review_required, :review_reason, :analysis_provider
            )
            ON CONFLICT(tracker_id) DO UPDATE SET
                regulation_file_id = excluded.regulation_file_id,
                regulation_title = excluded.regulation_title,
                regulator = excluded.regulator,
                version = excluded.version,
                supersedes_tracker_id = excluded.supersedes_tracker_id,
                status = excluded.status,
                owner = excluded.owner,
                priority = excluded.priority,
                risk_score = excluded.risk_score,
                risk_score_max = excluded.risk_score_max,
                confidence = excluded.confidence,
                regulatory_update = excluded.regulatory_update,
                compliance_obligation = excluded.compliance_obligation,
                impacted_policy = excluded.impacted_policy,
                required_policy_update = excluded.required_policy_update,
                impacted_control = excluded.impacted_control,
                control_gap = excluded.control_gap,
                recommended_enhancement = excluded.recommended_enhancement,
                due_date = excluded.due_date,
                evidence = excluded.evidence,
                affected_controls_count = excluded.affected_controls_count,
                affected_policies_count = excluded.affected_policies_count,
                policy_change_required = excluded.policy_change_required,
                policy_change_reason = excluded.policy_change_reason,
                change_detected = excluded.change_detected,
                change_summary = excluded.change_summary,
                change_impact = excluded.change_impact,
                updated_at = excluded.updated_at,
                source_path = excluded.source_path,
                source_url = excluded.source_url,
                feed_name = excluded.feed_name,
                downloaded_at = excluded.downloaded_at,
                regulator_source = excluded.regulator_source,
                regulation_fingerprint = excluded.regulation_fingerprint,
                analysis_json = excluded.analysis_json,
                obligations_structured = excluded.obligations_structured,
                evidence_records = excluded.evidence_records,
                retrieval_diagnostics = excluded.retrieval_diagnostics,
                 mapping_graph = excluded.mapping_graph,
                 review_required = excluded.review_required,
                 review_reason = excluded.review_reason,
                 analysis_provider = excluded.analysis_provider
            """,
            values,
        )

        row = conn.execute(
            "SELECT * FROM tracker_entries WHERE tracker_id = ?",
            (tracker_id,),
        ).fetchone()

    action = "tracker_updated" if existing else "tracker_created"
    log_audit("tracker", tracker_id, action, {"priority": values["priority"], "owner": values["owner"]})

    if not existing and values["priority"] in {"Critical", "High"}:
        create_notification(
            tracker_id,
            f"New {values['priority']} regulation impact",
            (
                f"{values['regulation_title'] or 'Regulatory update'} requires "
                f"{values['owner']} review. Affected controls: "
                f"{values['affected_controls_count']}."
            ),
            values["priority"],
        )

    return dict(row)


def find_tracker_by_fingerprint(fingerprint: Optional[str]) -> Optional[Dict[str, Any]]:
    if not fingerprint:
        return None

    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM tracker_entries
            WHERE regulation_fingerprint = ?
            ORDER BY
                CASE
                    WHEN status IN ('Closed', 'Validated') THEN 0
                    ELSE 1
                END,
                created_at DESC,
                tracker_id DESC
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()

    return row_to_dict(row)


def find_tracker_for_regulation_texts(
    regulation_texts: Iterable[Optional[str]],
    fingerprint: Optional[str],
) -> Optional[Dict[str, Any]]:
    existing = find_tracker_by_fingerprint(fingerprint)
    if existing:
        return existing

    candidate_texts = [
        text for text in regulation_texts
        if has_actionable_text(text)
    ]
    if not candidate_texts:
        return None

    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tracker_entries
            ORDER BY
                CASE
                    WHEN status IN ('Closed', 'Validated') THEN 0
                    ELSE 1
                END,
                created_at DESC,
                tracker_id DESC
            """
        ).fetchall()

    for row in rows:
        row_texts = [
            row["regulatory_update"],
            row["regulation_title"],
            row["compliance_obligation"],
        ]
        for candidate_text in candidate_texts:
            if any(
                tracker_texts_match(candidate_text, row_text)
                for row_text in row_texts
            ):
                return row_to_dict(row)

    return None


def find_tracker_for_regulation_text(
    regulation_text: str,
    fingerprint: Optional[str],
) -> Optional[Dict[str, Any]]:
    return find_tracker_for_regulation_texts([regulation_text], fingerprint)


def save_analysis_result(
    analysis_result: Dict[str, Any],
    regulation_text: str,
    metadata: Optional[Dict[str, Any]] = None,
    file_id: Optional[int] = None,
) -> Dict[str, Any]:
    metadata = metadata or {}
    record = dict(analysis_result.get("tracker_record") or {})
    fingerprint = regulation_fingerprint(regulation_text)
    existing_duplicate = find_tracker_for_regulation_texts(
        [
            regulation_text,
            record.get("regulatory_update"),
            record.get("regulation_title"),
            record.get("compliance_obligation"),
        ],
        fingerprint,
    )
    duplicate_status = existing_duplicate.get("status") if existing_duplicate else None

    if existing_duplicate and not record.get("tracker_id"):
        record["tracker_id"] = existing_duplicate["tracker_id"]
        record["status"] = existing_duplicate["status"]

    record["regulation_fingerprint"] = fingerprint
    record.setdefault("regulation_title", metadata.get("title") or "Manual regulatory update")
    record.setdefault("regulator", metadata.get("regulator") or "Unknown")
    record.setdefault("version", metadata.get("version") or 1)
    record.setdefault("supersedes_tracker_id", metadata.get("supersedes_tracker_id"))
    record.setdefault("source_path", metadata.get("source_path") or "Manual input")
    record.setdefault("source_url", metadata.get("source_url"))
    record.setdefault("feed_name", metadata.get("feed_name"))
    record.setdefault("downloaded_at", metadata.get("downloaded_at"))
    record.setdefault("regulator_source", metadata.get("regulator_source"))
    record.setdefault("change_detected", bool(metadata.get("change_detected")))
    record.setdefault("change_summary", metadata.get("change_summary"))
    record.setdefault("change_impact", metadata.get("change_impact"))

    saved = save_tracker_entry(record, analysis_result=analysis_result, file_id=file_id)
    saved["analysis_action"] = "reused_existing_tracker" if existing_duplicate else "created_tracker"
    saved["matched_existing_tracker"] = bool(existing_duplicate)
    saved["matched_existing_status"] = duplicate_status
    saved["matched_existing_resolved"] = duplicate_status in RESOLVED_STATUSES
    return saved


def tracker_matches_filters(entry: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    for key in ["status", "owner", "priority", "regulator"]:
        value = filters.get(key)
        if value and value != "All" and entry.get(key) != value:
            return False

    search = filters.get("search")
    if search:
        haystack = " ".join(
            str(entry.get(field) or "")
            for field in [
                "tracker_id",
                "regulation_title",
                "impacted_policy",
                "impacted_control",
                "required_policy_update",
                "owner",
                "evidence",
                "source_url",
                "feed_name",
            ]
        ).lower()
        if search.lower() not in haystack:
            return False

    return True


def fetch_tracker_entries(
    filters: Optional[Dict[str, Any]] = None,
    include_duplicates: bool = False,
) -> List[Dict[str, Any]]:
    init_db()
    filters = filters or {}

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tracker_entries
            ORDER BY updated_at DESC, tracker_id DESC
            """
        ).fetchall()

    entries = rows_to_dicts(rows)
    if not include_duplicates:
        entries = deduplicate_tracker_entries(entries)
    if filters:
        entries = [
            entry for entry in entries
            if tracker_matches_filters(entry, filters)
        ]
    return entries


def update_tracker_status(tracker_id: str, status: str, actor: str = "Dashboard") -> None:
    init_db()
    if status not in TRACKER_STATUS_VALUES:
        raise ValueError(f"Unsupported tracker status: {status}")

    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM tracker_entries WHERE tracker_id = ?",
            (tracker_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Tracker not found: {tracker_id}")

        old_status = row["status"]
        conn.execute(
            """
            UPDATE tracker_entries
            SET status = ?, updated_at = ?
            WHERE tracker_id = ?
            """,
            (status, utc_now(), tracker_id),
        )
        if status in RESOLVED_STATUSES:
            conn.execute(
                """
                UPDATE notifications
                SET read_at = COALESCE(read_at, ?)
                WHERE tracker_id = ?
                """,
                (utc_now(), tracker_id),
            )

    log_audit(
        "tracker",
        tracker_id,
        "status_changed",
        {"from": old_status, "to": status, "actor": actor},
    )


def create_notification(
    tracker_id: Optional[str],
    title: str,
    message: str,
    severity: str = "Medium",
    channel: str = "Dashboard",
) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO notifications(tracker_id, title, message, severity, channel, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tracker_id, title, message, severity, channel, utc_now()),
        )


def fetch_notifications(unread_only: bool = False, limit: int = 20) -> List[Dict[str, Any]]:
    init_db()
    query = "SELECT * FROM notifications"
    params: List[Any] = []
    if unread_only:
        query += " WHERE read_at IS NULL"
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return rows_to_dicts(rows)


def mark_notification_read(notification_id: int) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            "UPDATE notifications SET read_at = ? WHERE id = ?",
            (utc_now(), notification_id),
        )


def mark_all_notifications_read() -> int:
    init_db()
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE notifications SET read_at = ? WHERE read_at IS NULL",
            (utc_now(),),
        )
        return cursor.rowcount


def fetch_processing_history(limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM regulation_files
            ORDER BY detected_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


def fetch_audit_trail(limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM audit_trail
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


def tracker_summary_counts() -> Dict[str, Any]:
    init_db()
    entries = fetch_tracker_entries()
    open_entries = [
        entry for entry in entries
        if entry.get("status") not in RESOLVED_STATUSES
    ]
    active_tracker_ids = {
        entry.get("tracker_id")
        for entry in open_entries
        if entry.get("tracker_id")
    }

    with connect() as conn:
        unread_rows = conn.execute(
            """
            SELECT tracker_id
            FROM notifications
            WHERE read_at IS NULL
            """
        ).fetchall()

    unread = sum(
        1
        for row in unread_rows
        if row["tracker_id"] is None or row["tracker_id"] in active_tracker_ids
    )

    return {
        "total": len(entries),
        "open": len(open_entries),
        "critical": len(
            [
                entry for entry in open_entries
                if entry.get("priority") == "Critical"
            ]
        ),
        "unread_notifications": unread,
    }


def save_rag_evaluation(result: Dict[str, Any]) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO rag_evaluations(
                query, expected_sources, returned_sources, metric_scope,
                scoring_depth, precision, recall, f1, mrr, hit_rate,
                context_relevance, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.get("query"),
                json.dumps(result.get("expected_sources") or []),
                json.dumps(result.get("returned_sources") or []),
                result.get("metric_scope") or "top_1",
                result.get("scoring_depth"),
                result.get("precision"),
                result.get("recall"),
                result.get("f1"),
                result.get("mrr"),
                result.get("hit_rate"),
                result.get("context_relevance"),
                utc_now(),
            ),
        )


def fetch_rag_evaluations(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM rag_evaluations
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)
