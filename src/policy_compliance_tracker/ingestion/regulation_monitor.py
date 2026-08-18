import hashlib
import io
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import REGULATION_DIR
from ..storage.tracker_store import (
    fetch_processed_regulations,
    find_file_by_hash,
    get_tracker_by_file_id,
    log_audit,
    mark_regulation_error,
    mark_regulation_processed,
    upsert_regulation_file,
    utc_now,
)


class MissingDependencyError(RuntimeError):
    pass


REGULATOR_PATTERNS = {
    "RBI": ["rbi", "reserve bank of india"],
    "SEBI": ["sebi", "securities and exchange board of india"],
    "CERT-In": ["cert-in", "indian computer emergency response team"],
    "PCI DSS": ["pci dss", "payment card industry"],
    "ISO": ["iso/iec", "iso 27001", "iso 27701"],
    "GDPR": ["gdpr", "general data protection regulation"],
}


VERSION_SUFFIX_PATTERN = re.compile(
    r"\b(v(?:ersion)?\s*\d+|rev(?:ision)?\s*\d+|draft\s*\d+|final)\b",
    re.IGNORECASE,
)


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_html_header(path: str) -> bool:
    with open(path, "rb") as file:
        header = file.read(32).lstrip().lower()
    return header.startswith((b"<!doctype", b"<html", b"<!doc"))


def invalid_pdf_message(path: str) -> Optional[str]:
    if has_html_header(path):
        return "Invalid PDF file: the file contains HTML instead of PDF content."
    return None


def extract_pdf_text(path: str) -> str:
    try:
        from langchain_community.document_loaders import PyPDFLoader
    except ImportError as exc:
        raise MissingDependencyError(
            "PDF processing dependency is missing. Run: python -m pip install -r requirements.txt"
        ) from exc

    loader = PyPDFLoader(path)
    pages = loader.load()
    return "\n\n".join(page.page_content for page in pages).strip()


def extract_pdf_bytes(content: bytes) -> str:
    """Extract text from an uploaded PDF without writing it to disk."""
    if not content or not content.lstrip().startswith(b"%PDF"):
        raise ValueError("The uploaded file is not a valid PDF.")

    try:
        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(content)).pages
        text = "\n\n".join(page.extract_text() or "" for page in pages).strip()
    except Exception as exc:
        raise ValueError(f"The PDF could not be read: {exc}") from exc

    if not text:
        raise ValueError("The PDF contains no extractable text.")
    return text


def analyze_regulation_text(
    regulation_text: str,
    regulation_metadata: Optional[Dict[str, Any]] = None,
    persist: bool = False,
    file_id: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        from ..agent.compliance_agent import analyze_regulation
    except ImportError as exc:
        raise MissingDependencyError(
            "AI analysis dependencies are missing. Run: python -m pip install -r requirements.txt"
        ) from exc

    return analyze_regulation(
        regulation_text,
        regulation_metadata=regulation_metadata,
        persist=persist,
        file_id=file_id,
    )


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("multi-factor", "multi factor")
    text = text.replace("two-factor", "two factor")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def significant_tokens(text: str) -> set:
    stop_words = {
        "about", "after", "against", "also", "and", "any", "are", "for",
        "from", "have", "into", "must", "not", "shall", "that", "the",
        "this", "with", "within", "will",
    }
    return {
        token
        for token in normalize_text(text).split()
        if len(token) > 3 and token not in stop_words
    }


def token_similarity(left: str, right: str) -> float:
    left_tokens = significant_tokens(left)
    right_tokens = significant_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0

    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, normalize_text(left)[:4000], normalize_text(right)[:4000]).ratio()
    return round((jaccard * 0.65) + (sequence * 0.35), 4)


def detect_regulator(text: str, path: str) -> str:
    haystack = normalize_text(f"{path} {text[:4000]}")
    for regulator, markers in REGULATOR_PATTERNS.items():
        if any(marker in haystack for marker in markers):
            return regulator
    return "Unknown"


def clean_title(text: str, path: str) -> str:
    candidate_lines = [
        line.strip(" -:\t")
        for line in text.splitlines()[:20]
        if 12 <= len(line.strip()) <= 140
    ]

    for line in candidate_lines:
        if not re.search(r"^(page|table|figure|\d+)$", line, re.IGNORECASE):
            return re.sub(r"\s+", " ", line)

    file_name = os.path.splitext(os.path.basename(path))[0]
    return file_name.replace("_", " ").replace("-", " ").strip().title()


def semantic_key(text: str, path: str) -> str:
    regulator = detect_regulator(text, path)
    title = clean_title(text, path)
    title = VERSION_SUFFIX_PATTERN.sub("", title)
    title = re.sub(r"\b20\d{2}\b", "", title)
    title = re.sub(r"\s+", " ", title).strip()

    normalized = normalize_text(f"{regulator} {title}")

    if any(term in normalize_text(text[:6000]) for term in ["mfa", "multi factor authentication"]):
        return normalize_text(f"{regulator} MFA Circular")
    if "know your customer" in normalize_text(text[:6000]) or "kyc" in normalize_text(text[:6000]):
        return normalize_text(f"{regulator} KYC Update")

    return normalized or normalize_text(os.path.basename(path))


def money_to_int(value: str) -> int:
    number = re.sub(r"[^0-9]", "", value)
    return int(number) if number else 0


def extract_money_thresholds(text: str) -> List[Tuple[int, str]]:
    patterns = [
        r"(?:>|above|over|greater than|exceeding)\s*(?:rs\.?|inr|₹)\s*[\d,]+",
        r"(?:rs\.?|inr|₹)\s*[\d,]+",
    ]
    values: List[Tuple[int, str]] = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = match.group(0)
            amount = money_to_int(raw)
            if amount and amount not in seen:
                seen.add(amount)
                values.append((amount, raw.strip()))
    return values


def format_rupee(amount: int) -> str:
    return "INR " + f"{amount:,}"


def detect_change_impact(old_text: str, new_text: str) -> Dict[str, Any]:
    if not old_text:
        return {
            "change_detected": False,
            "change_summary": "No prior version available for comparison.",
            "change_impact": "Not applicable",
        }

    old_thresholds = extract_money_thresholds(old_text)
    new_thresholds = extract_money_thresholds(new_text)

    if old_thresholds and new_thresholds:
        old_amount = old_thresholds[0][0]
        new_amount = new_thresholds[0][0]
        if old_amount != new_amount:
            direction = "lowered" if new_amount < old_amount else "raised"
            impact = "High" if new_amount < old_amount else "Medium"
            return {
                "change_detected": True,
                "change_summary": (
                    f"Threshold changed: {format_rupee(old_amount)} -> "
                    f"{format_rupee(new_amount)} ({direction})."
                ),
                "change_impact": impact,
            }

    similarity = token_similarity(old_text, new_text)
    if similarity < 0.72:
        return {
            "change_detected": True,
            "change_summary": "Substantive wording changed from the prior version.",
            "change_impact": "Medium",
        }

    return {
        "change_detected": False,
        "change_summary": "No material threshold or wording change detected.",
        "change_impact": "Low",
    }


def find_prior_version(
    key: str,
    text: str,
    current_path: str,
    current_hash: str,
) -> Optional[Dict[str, Any]]:
    candidates = []
    for record in fetch_processed_regulations():
        if record["file_path"] == current_path or record["sha256"] == current_hash:
            continue

        same_key = record.get("semantic_key") == key
        similarity = token_similarity(text, record.get("content_text") or "")
        if same_key or similarity >= 0.78:
            candidates.append((record.get("version") or 1, similarity, record))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def iter_regulation_pdfs(regulation_dir: str = REGULATION_DIR) -> Iterable[str]:
    if not os.path.exists(regulation_dir):
        return []

    pdfs = []
    for root, _dirs, files in os.walk(regulation_dir):
        for file_name in files:
            if file_name.lower().endswith(".pdf"):
                pdfs.append(os.path.join(root, file_name))
    return sorted(pdfs)


def process_regulation_file(path: str) -> Dict[str, Any]:
    path = os.path.normpath(path)
    stat = os.stat(path)
    sha256 = file_sha256(path)

    message = invalid_pdf_message(path)
    if message:
        file_record = upsert_regulation_file(
            {
                "file_path": path,
                "file_name": os.path.basename(path),
                "sha256": sha256,
                "status": "error",
                "size_bytes": stat.st_size,
                "modified_at": datetime_from_timestamp(stat.st_mtime),
                "analysis_error": message,
            }
        )
        log_audit("regulation_file", str(file_record["id"]), "invalid_pdf", message)
        return {"file": path, "status": "error", "message": message}

    existing_duplicate = find_file_by_hash(sha256)
    if existing_duplicate and existing_duplicate["file_path"] != path:
        duplicate_record = upsert_regulation_file(
            {
                "file_path": path,
                "file_name": os.path.basename(path),
                "sha256": sha256,
                "status": "duplicate",
                "duplicate_of_file_id": existing_duplicate["id"],
                "size_bytes": stat.st_size,
                "modified_at": utc_now(),
            }
        )
        log_audit(
            "regulation_file",
            str(duplicate_record["id"]),
            "duplicate_detected",
            {"duplicate_of_file_id": existing_duplicate["id"]},
        )
        return {
            "file": path,
            "status": "duplicate",
            "message": f"Exact duplicate of {existing_duplicate['file_name']}",
        }

    try:
        text = extract_pdf_text(path)
    except MissingDependencyError:
        raise
    except Exception as exc:
        message = f"Could not extract PDF text: {exc}"
        file_record = upsert_regulation_file(
            {
                "file_path": path,
                "file_name": os.path.basename(path),
                "sha256": sha256,
                "status": "error",
                "size_bytes": stat.st_size,
                "modified_at": datetime_from_timestamp(stat.st_mtime),
                "analysis_error": message[:2000],
            }
        )
        log_audit("regulation_file", str(file_record["id"]), "pdf_extract_failed", message[:2000])
        return {"file": path, "status": "error", "message": message}

    key = semantic_key(text, path)
    regulator = detect_regulator(text, path)
    title = clean_title(text, path)
    prior = find_prior_version(key, text, path, sha256)
    version = (prior.get("version") or 1) + 1 if prior else 1
    prior_tracker = get_tracker_by_file_id(prior["id"]) if prior else None
    change = detect_change_impact(prior.get("content_text") if prior else "", text)

    file_record = upsert_regulation_file(
        {
            "file_path": path,
            "file_name": os.path.basename(path),
            "sha256": sha256,
            "semantic_key": key,
            "title": title,
            "regulator": regulator,
            "version": version,
            "supersedes_file_id": prior["id"] if prior else None,
            "status": "processing",
            "size_bytes": stat.st_size,
            "modified_at": datetime_from_timestamp(stat.st_mtime),
            "content_text": text,
        }
    )

    log_audit(
        "regulation_file",
        str(file_record["id"]),
        "detected",
        {"path": path, "sha256": sha256, "version": version},
    )

    metadata = {
        "title": title,
        "regulator": regulator,
        "version": version,
        "semantic_key": key,
        "source_path": path,
        "source_url": file_record.get("source_url"),
        "feed_name": file_record.get("feed_name"),
        "downloaded_at": file_record.get("downloaded_at"),
        "regulator_source": file_record.get("regulator_source"),
        "supersedes_file_id": prior["id"] if prior else None,
        "supersedes_tracker_id": prior_tracker["tracker_id"] if prior_tracker else None,
        **change,
    }

    try:
        result = analyze_regulation_text(
            text,
            regulation_metadata=metadata,
            persist=True,
            file_id=file_record["id"],
        )
    except MissingDependencyError:
        raise
    except Exception as exc:
        mark_regulation_error(file_record["id"], str(exc))
        return {"file": path, "status": "error", "message": str(exc)}

    tracker_id = (result.get("tracker_record") or {}).get("tracker_id")
    mark_regulation_processed(file_record["id"], tracker_id or "unknown")

    return {
        "file": path,
        "status": "processed",
        "tracker_id": tracker_id,
        "version": version,
        "supersedes": prior_tracker["tracker_id"] if prior_tracker else None,
        "change": change.get("change_summary"),
    }


def datetime_from_timestamp(timestamp: float) -> str:
    from datetime import datetime

    return datetime.utcfromtimestamp(timestamp).replace(microsecond=0).isoformat() + "Z"


def scan_regulation_directory(regulation_dir: str = REGULATION_DIR) -> List[Dict[str, Any]]:
    results = []
    for path in iter_regulation_pdfs(regulation_dir):
        sha256 = file_sha256(path)
        from ..storage.tracker_store import get_regulation_file_by_path

        existing = get_regulation_file_by_path(os.path.normpath(path))
        if existing and existing.get("sha256") == sha256 and existing.get("status") == "processed":
            results.append({"file": path, "status": "unchanged", "message": "Already processed"})
            continue
        if existing and existing.get("sha256") == sha256 and existing.get("status") in {"error", "duplicate"}:
            results.append(
                {
                    "file": path,
                    "status": existing.get("status"),
                    "message": existing.get("analysis_error") or "Previously recorded; no change detected.",
                }
            )
            continue

        try:
            results.append(process_regulation_file(path))
        except Exception as exc:
            results.append({"file": path, "status": "error", "message": str(exc)})

    return results
