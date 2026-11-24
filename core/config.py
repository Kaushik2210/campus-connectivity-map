"""Central configuration: paths, scoring weights, thresholds and location lookups."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOCATIONS_PATH = DATA_DIR / "locations.json"
DEFAULT_DB_PATH = DATA_DIR / "readings.db"

APP_NAME = "CampusConnectivity Map"
CAMPUS = "Christ University, Bengaluru"

METHODS = ("in_browser_test", "manual", "seeded")


def db_path() -> Path:
    """Return the SQLite path (override with the CCM_DB_PATH env var, e.g. in tests)."""
    return Path(os.environ.get("CCM_DB_PATH", str(DEFAULT_DB_PATH)))


def backend() -> str:
    """'auto' (MySQL if configured, else SQLite), 'sqlite', or 'mysql' (strict, no fallback)."""
    mode = os.environ.get("CCM_BACKEND", "auto").lower()
    return mode if mode in ("auto", "sqlite", "mysql") else "auto"


def mysql_env() -> dict:
    """MySQL settings from CCM_MYSQL_* environment variables (only the ones that are set)."""
    names = {"host": "CCM_MYSQL_HOST", "port": "CCM_MYSQL_PORT", "user": "CCM_MYSQL_USER",
             "password": "CCM_MYSQL_PASSWORD", "database": "CCM_MYSQL_DATABASE"}
    return {k: os.environ[v] for k, v in names.items() if os.environ.get(v)}


def auto_seed_enabled() -> bool:
    """Whether a brand-new database is filled with synthetic demo readings."""
    return os.environ.get("CCM_AUTO_SEED", "1") == "1"


# ---- Scoring -------------------------------------------------------------
# Quality score (0-100) = weighted blend of normalised components. Weights sum to 1.
SCORE_WEIGHTS = {"download": 0.50, "upload": 0.15, "latency": 0.20, "signal": 0.15}

DOWNLOAD_GOOD_MBPS = 50.0   # >= this earns full download marks
UPLOAD_GOOD_MBPS = 20.0     # >= this earns full upload marks
LATENCY_BEST_MS = 20.0      # <= this earns full latency marks
LATENCY_WORST_MS = 250.0    # >= this earns zero latency marks
DBM_BEST = -50.0            # dBm at/above which signal is "full"
DBM_WORST = -90.0           # dBm at/below which signal is "none"

# ---- Analysis thresholds -------------------------------------------------
MIN_CELL_READINGS = 3            # below this a heatmap cell is greyed out
CONGESTION_DROP = 0.30           # hour is congested if median is 30%+ under block median
DEFAULT_DEAD_ZONE_THRESHOLD = 40  # quality score below this = weak
DEFAULT_MIN_READINGS = 5

# ---- Submission rules ----------------------------------------------------
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_S = 600
LIMITS = {
    "download_mbps": (0.0, 1000.0),
    "upload_mbps": (0.0, 1000.0),
    "latency_ms": (1.0, 5000.0),
    "dbm": (-120.0, -20.0),
}

# ---- Time of day ---------------------------------------------------------
DAYPARTS: dict[str, tuple[int, int] | None] = {
    "All day": None,
    "Morning (6-10)": (6, 10),
    "Late morning (10-13)": (10, 13),
    "Afternoon (13-17)": (13, 17),
    "Evening (17-22)": (17, 22),
    "Night (22-6)": (22, 6),
}

# ---- Colours: red = weak, green = strong, grey = not enough data ----------
COLOR_WEAK = "#ef5b66"
COLOR_MID = "#f5c451"
COLOR_STRONG = "#3ecf8e"
COLOR_NODATA = "#2a323f"
COLORSCALE = [[0.0, COLOR_WEAK], [0.5, COLOR_MID], [1.0, COLOR_STRONG]]


# ---- Locations -----------------------------------------------------------
@lru_cache(maxsize=1)
def load_locations() -> dict:
    """Load data/locations.json (cached for the process)."""
    with open(LOCATIONS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def block_names() -> list[str]:
    """Block names in the order defined in locations.json."""
    return [b["name"] for b in load_locations()["blocks"]]


def floors_for(block: str) -> list[int]:
    """Sorted floor numbers for a block (empty list if unknown)."""
    for b in load_locations()["blocks"]:
        if b["name"] == block:
            return sorted(int(f) for f in b["floors"])
    return []


def area_types_for(block: str, floor: int) -> list[str]:
    """Area types available on a given block/floor."""
    for b in load_locations()["blocks"]:
        if b["name"] == block:
            return list(b["floors"].get(str(int(floor)), []))
    return []


def floor_label(floor: int) -> str:
    """Human label for a floor number."""
    return "Ground" if int(floor) == 0 else str(int(floor))

