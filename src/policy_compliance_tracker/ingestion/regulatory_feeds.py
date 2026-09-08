import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional

from ..config import REGULATION_DIR
from ..storage.tracker_store import (
    get_regulation_file_by_path,
    log_audit,
    upsert_regulation_file,
    utc_now,
)


DEFAULT_FEEDS = [
    {
        "name": "RBI Updates",
        "regulator": "RBI",
        "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx",
        "fallback_urls": ["https://www.rbi.org.in/"],
    },
    {
        "name": "SEBI Circulars",
        "regulator": "SEBI",
        "url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0",
        "fallback_urls": ["https://www.sebi.gov.in/"],
    },
    {
        "name": "CERT-In Advisories",
        "regulator": "CERT-In",
        "url": "https://www.cert-in.org.in/",
        "fallback_urls": [],
    },
    {
        "name": "PCI DSS Updates",
        "regulator": "PCI DSS",
        "url": "https://www.pcisecuritystandards.org/document_library/",
        "fallback_urls": ["https://www.pcisecuritystandards.org/"],
    },
    {
        "name": "ISO Updates",
        "regulator": "ISO",
        "url": "https://www.iso.org/news.html",
        "fallback_urls": ["https://www.iso.org/"],
    },
]

DEFAULT_FETCH_RETRIES = 3
RETRY_DELAY_SECONDS = 0.5


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self.links.append(href)


def fetch_url(
    url: str,
    timeout: int = 20,
    retries: int = DEFAULT_FETCH_RETRIES,
) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Regulatory feed URLs must use HTTPS and include a host.")

    last_error: Optional[Exception] = None
    for attempt in range(max(1, retries)):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ComplianceAgent/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
                return response.read()
        except Exception as exc:  # network providers expose several exception types
            last_error = exc
            if attempt + 1 < max(1, retries):
                time.sleep(RETRY_DELAY_SECONDS * (2**attempt))

    raise RuntimeError(f"Unable to fetch regulatory source after {retries} attempts: {url}") from last_error


def _feed_cache_path(destination_dir: str, feed_name: str) -> str:
    cache_key = hashlib.sha256(feed_name.encode("utf-8")).hexdigest()[:16]
    return os.path.join(destination_dir, ".feed_cache", f"{cache_key}.html")


def _feed_cache_metadata_path(destination_dir: str, feed_name: str) -> str:
    cache_key = hashlib.sha256(feed_name.encode("utf-8")).hexdigest()[:16]
    return os.path.join(destination_dir, ".feed_cache", f"{cache_key}.json")


def fetch_feed_page(feed: Dict[str, Any], destination_dir: str) -> tuple[bytes, str, bool]:
    """Fetch a feed page, trying configured official fallbacks and then cache."""
    urls = [feed["url"], *feed.get("fallback_urls", [])]
    errors: List[str] = []
    for url in dict.fromkeys(urls):
        try:
            page = fetch_url(url)
            cache_path = _feed_cache_path(destination_dir, feed["name"])
            metadata_path = _feed_cache_metadata_path(destination_dir, feed["name"])
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as cache_file:
                cache_file.write(page)
            with open(metadata_path, "w", encoding="utf-8") as metadata_file:
                json.dump({"source_url": url}, metadata_file)
            return page, url, False
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    cache_path = _feed_cache_path(destination_dir, feed["name"])
    if os.path.exists(cache_path):
        cached_source_url = feed["url"]
        metadata_path = _feed_cache_metadata_path(destination_dir, feed["name"])
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, encoding="utf-8") as metadata_file:
                    cached_source_url = json.load(metadata_file).get("source_url", cached_source_url)
            except (OSError, json.JSONDecodeError, AttributeError):
                cached_source_url = feed["url"]
        with open(cache_path, "rb") as cache_file:
            return cache_file.read(), cached_source_url, True

    detail = "; ".join(errors)
    raise RuntimeError(f"No live or cached regulatory source was available for {feed['name']}. {detail}")


def discover_pdf_links(page_url: str, html_bytes: bytes) -> List[str]:
    parser = LinkParser()
    parser.feed(html_bytes.decode("utf-8", errors="ignore"))

    links = []
    for href in parser.links:
        absolute = urllib.parse.urljoin(page_url, href)
        if ".pdf" in absolute.lower():
            links.append(absolute)

    return sorted(set(links))


def safe_file_name(regulator: str, url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path) or "regulation.pdf"
    name = urllib.parse.unquote(name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return f"{regulator}_{name}"


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_pdf(content: bytes) -> bool:
    return content.lstrip().startswith(b"%PDF-")


def register_feed_file(
    path: str,
    feed: Dict[str, str],
    source_url: str,
    status: str,
) -> Dict[str, Any]:
    normalized_path = os.path.normpath(path)
    existing = get_regulation_file_by_path(normalized_path)
    stat = os.stat(normalized_path)
    current_hash = file_sha256(normalized_path)
    same_processed_file = (
        existing
        and existing.get("status") == "processed"
        and existing.get("sha256") == current_hash
    )
    record_status = existing["status"] if same_processed_file else status
    now = utc_now()

    return upsert_regulation_file(
        {
            "file_path": normalized_path,
            "file_name": os.path.basename(normalized_path),
            "sha256": current_hash,
            "status": record_status,
            "size_bytes": stat.st_size,
            "modified_at": now,
            "source_url": source_url,
            "feed_name": feed["name"],
            "downloaded_at": existing.get("downloaded_at") if same_processed_file else now,
            "regulator_source": feed["regulator"],
        }
    )


def analyze_feed_file(path: str) -> Dict[str, Any]:
    from .regulation_monitor import process_regulation_file

    return process_regulation_file(path)


def ingest_feeds(
    feeds: Optional[Iterable[Dict[str, str]]] = None,
    destination_dir: str = REGULATION_DIR,
    limit_per_feed: int = 5,
    analyze_downloads: bool = True,
) -> List[Dict[str, Any]]:
    os.makedirs(destination_dir, exist_ok=True)
    results: List[Dict[str, Any]] = []

    for feed in feeds or DEFAULT_FEEDS:
        name = feed["name"]
        regulator = feed["regulator"]
        url = feed["url"]
        try:
            if url.lower().endswith(".pdf"):
                pdf_links = [url]
                feed_source_url = url
                cache_used = False
            else:
                page, feed_source_url, cache_used = fetch_feed_page(feed, destination_dir)
                pdf_links = discover_pdf_links(feed_source_url, page)[:limit_per_feed]

            if not pdf_links:
                message = "No PDF links discovered"
                if cache_used:
                    message += "; using cached feed page"
                results.append({"feed": name, "status": "no_pdf_found", "message": message})
                continue

            for pdf_url in pdf_links:
                file_name = safe_file_name(regulator, pdf_url)
                destination = os.path.normpath(os.path.join(destination_dir, file_name))
                if os.path.exists(destination):
                    file_record = register_feed_file(destination, feed, pdf_url, "downloaded")
                    result: Dict[str, Any] = {
                        "feed": name,
                        "status": "exists",
                        "file": destination,
                        "source_url": pdf_url,
                    }
                    if cache_used:
                        result["message"] = "Live feed unavailable; used cached feed page"
                    if analyze_downloads and file_record.get("status") != "processed":
                        analysis_result = analyze_feed_file(destination)
                        result.update(
                            {
                                "analysis_status": analysis_result.get("status"),
                                "tracker_id": analysis_result.get("tracker_id"),
                                "message": analysis_result.get("message") or analysis_result.get("change"),
                            }
                        )
                    elif file_record.get("status") == "processed":
                        result["analysis_status"] = "unchanged"
                        result["tracker_id"] = file_record.get("tracker_id")
                    results.append(result)
                    continue

                content = fetch_url(pdf_url)
                if not looks_like_pdf(content):
                    results.append(
                        {
                            "feed": name,
                            "status": "error",
                            "source_url": pdf_url,
                            "message": "Downloaded content was not a valid PDF.",
                        }
                    )
                    continue

                with open(destination, "wb") as output:
                    output.write(content)

                register_feed_file(destination, feed, pdf_url, "downloaded")
                log_audit(
                    "regulatory_feed",
                    name,
                    "pdf_ingested",
                    {"url": pdf_url, "file": destination},
                )
                result = {
                    "feed": name,
                    "status": "downloaded",
                    "file": destination,
                    "source_url": pdf_url,
                }
                if cache_used:
                    result["message"] = "Live feed unavailable; used cached feed page"
                if analyze_downloads:
                    analysis_result = analyze_feed_file(destination)
                    result.update(
                        {
                            "analysis_status": analysis_result.get("status"),
                            "tracker_id": analysis_result.get("tracker_id"),
                            "message": analysis_result.get("message") or analysis_result.get("change"),
                        }
                    )
                results.append(result)
        except Exception as exc:
            results.append({"feed": name, "status": "error", "message": str(exc)})

    return results
