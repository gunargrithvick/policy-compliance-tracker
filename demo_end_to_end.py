import json

from scheduled_monitor import run_monitor_cycle
from tracker_store import fetch_tracker_entries


def main() -> None:
    result = run_monitor_cycle(include_feeds=False)
    trackers = fetch_tracker_entries()
    demo_summary = {
        "scan_results": result["scan_results"],
        "tracker_count": len(trackers),
        "latest_tracker": trackers[0] if trackers else None,
    }
    print(json.dumps(demo_summary, indent=2, default=str))


if __name__ == "__main__":
    main()
