import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

load_dotenv()

CHROMA_DB_PATH = "compliance_db"
TOP_K = 5

TRACKER_DB_PATH = os.getenv(
    "TRACKER_DB_PATH",
    os.path.join("compliance_db", "tracker.sqlite3")
)

REGULATION_DIR = os.getenv(
    "REGULATION_DIR",
    os.path.join("data", "regulations")
)

TRACKER_STATUS_VALUES = [
    "Open",
    "In Review",
    "In Progress",
    "Implemented",
    "Validated",
    "Closed",
]

TRACKER_PRIORITY_VALUES = [
    "Critical",
    "High",
    "Medium",
    "Low",
    "Review",
]
