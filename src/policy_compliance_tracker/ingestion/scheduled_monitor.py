import argparse
import json
import os
import time
from datetime import datetime
from typing import Any, Dict

from ..config import REGULATION_DIR
from ..storage.tracker_store import init_db, log_audit
from .regulation_monitor import scan_regulation_directory
from .regulatory_feeds import DEFAULT_FEEDS, ingest_feeds


DEFAULT_INTERVAL_SECONDS = int(os.getenv("MONITOR_INTERVAL_SECONDS", "3600"))


def run_monitor_cycle(
    include_feeds: bool = True,
    feed_limit: int = 5,
    analyze_feeds: bool = True,
) -> Dict[str, Any]:
    init_db()
    started_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    result: Dict[str, Any] = {
        "started_at": started_at,
        "regulation_dir": REGULATION_DIR,
        "feed_results": [],
        "scan_results": [],
    }

    if include_feeds:
        result["feed_results"] = ingest_feeds(
            DEFAULT_FEEDS,
            limit_per_feed=feed_limit,
            analyze_downloads=analyze_feeds,
        )

    result["scan_results"] = scan_regulation_directory(REGULATION_DIR)
    result["finished_at"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    log_audit(
        "scheduled_monitor",
        "cycle",
        "completed",
        {
            "include_feeds": include_feeds,
            "feed_count": len(result["feed_results"]),
            "scan_count": len(result["scan_results"]),
            "started_at": started_at,
            "finished_at": result["finished_at"],
        },
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run scheduled regulatory feed and folder monitoring."
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Delay between monitor cycles when running continuously.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one monitor cycle and exit.",
    )
    parser.add_argument(
        "--skip-feeds",
        action="store_true",
        help="Scan the local regulation folder only.",
    )
    parser.add_argument(
        "--feed-limit",
        type=int,
        default=5,
        help="Maximum PDF links to process per configured feed.",
    )
    parser.add_argument(
        "--no-feed-analysis",
        action="store_true",
        help="Download feed PDFs without immediately analyzing them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    while True:
        result = run_monitor_cycle(
            include_feeds=not args.skip_feeds,
            feed_limit=args.feed_limit,
            analyze_feeds=not args.no_feed_analysis,
        )
        print(json.dumps(result, indent=2, default=str))

        if args.once:
            return

        time.sleep(max(60, args.interval_seconds))


if __name__ == "__main__":
    main()
