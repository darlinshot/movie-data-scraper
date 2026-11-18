from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
STATE_DIR = ROOT / "state"

DOANHTHUPHIM_URL = "https://doanhthuphim.vn/tong-hop"
BOXOFFICEVIETNAM_URL = "https://v1.boxofficevietnam.com/"

MOVIES_CSV = DATA_DIR / "movies.csv"
UNMATCHED_CSV = DATA_DIR / "unmatched_movies.csv"
LOG_CSV = DATA_DIR / "collection_log.csv"
TICKETS_WEB_CSV = DATA_DIR / "tickets_sold_web.csv"
FULL_EXPORT_CSV = DATA_DIR / "full_export.csv"

DTP_PROGRESS = STATE_DIR / "doanhthuphim_movies.jsonl"
BOV_PROGRESS = STATE_DIR / "boxoffice_matches.jsonl"
WEB_TICKETS_PROGRESS = STATE_DIR / "web_tickets_progress.jsonl"

REQUEST_DELAY_MIN = 0.8
REQUEST_DELAY_MAX = 1.8
RETRY_COUNT = 3
RETRY_BACKOFF = 1.5
NAV_TIMEOUT_MS = 60000

AUTO_MATCH_THRESHOLD = 92
REVIEW_THRESHOLD = 80
