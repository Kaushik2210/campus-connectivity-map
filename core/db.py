"""Storage layer: MySQL when configured, otherwise a local SQLite file.

Everything goes through SQLAlchemy, so the same code runs on both. MySQL settings come
from ``.streamlit/secrets.toml`` (``[mysql]`` section) or ``CCM_MYSQL_*`` environment
variables. If MySQL is configured but unreachable, the app falls back to SQLite and says
so in the sidebar, unless ``CCM_BACKEND=mysql`` is set (strict mode: raise instead).
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy import (
    Column, DateTime, Float, Index, Integer, MetaData, String, Table, create_engine,
    delete, func, insert, select, text,
)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import OperationalError

from core import config
from core.scoring import add_quality

COLUMNS = [
    "timestamp", "block", "floor", "area_type", "download_mbps", "upload_mbps",
    "latency_ms", "signal_strength", "device_type", "network_name", "method", "note",
]

metadata = MetaData()
readings = Table(
    "readings", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("block", String(64), nullable=False),
    Column("floor", Integer, nullable=False),
    Column("area_type", String(32), nullable=False),
    Column("download_mbps", Float, nullable=False),
    Column("upload_mbps", Float),
    Column("latency_ms", Float),
    Column("signal_strength", Float),
    Column("device_type", String(64)),
    Column("network_name", String(64)),
    Column("method", String(20), nullable=False),
    Column("note", String(255)),
    Index("idx_readings_loc", "block", "floor", "area_type"),
)
app_meta = Table(
    "app_meta", metadata,
    Column("meta_key", String(32), primary_key=True),
    Column("meta_value", String(255)),
)

_MYSQL_KEYS = ("host", "port", "user", "password", "database")
_init_lock = threading.Lock()


@dataclass(frozen=True)
class Backend:
    """Which database is in use and how it is going."""

    kind: str          # "mysql" or "sqlite"
    label: str         # short text for the sidebar
    note: str = ""     # why we fell back to SQLite, if we did


# ---- Settings --------------------------------------------------------------------------
def mysql_settings() -> dict | None:
    """MySQL connection settings from secrets.toml and/or env vars, or None if not configured."""
    s: dict = {}
    try:
        section = st.secrets.get("mysql")
        if section:
            s.update({k: section[k] for k in _MYSQL_KEYS if k in section})
    except Exception:  # no secrets file, or running outside Streamlit
        pass
    s.update(config.mysql_env())
    if not (s.get("user") and s.get("database")):
        return None
    s.setdefault("host", "localhost")
    s.setdefault("port", 3306)
    s.setdefault("password", "")
    return s


def _mysql_url(s: dict, with_database: bool = True) -> URL:
    return URL.create(
        "mysql+pymysql", username=str(s["user"]), password=str(s["password"]) or None,
        host=str(s["host"]), port=int(s["port"]),
        database=str(s["database"]) if with_database else None, query={"charset": "utf8mb4"},
    )


def _friendly_error(e: Exception, s: dict) -> str:
    code = None
    if isinstance(e, OperationalError) and getattr(e, "orig", None) is not None and e.orig.args:
        code = e.orig.args[0]
    where = f"{s['host']}:{s['port']}"
    if code == 1045:
        return "MySQL refused the username or password. Check .streamlit/secrets.toml."
    if code == 1044:
        return f"That MySQL user is not allowed to use the database '{s['database']}'."
    if code in (2002, 2003, 2006, 2013):
        return f"Could not reach MySQL at {where}. Is the MySQL service running?"
    return f"MySQL connection failed ({type(e).__name__})."


def _connect_mysql(s: dict) -> Engine:
    """Open the MySQL engine, creating the database first if it does not exist yet."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", str(s["database"])):
        raise ValueError("MySQL database name may only contain letters, digits and underscores.")
    engine = create_engine(_mysql_url(s), pool_pre_ping=True, pool_recycle=1800, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        if not (e.orig is not None and e.orig.args and e.orig.args[0] == 1049):  # 1049 = unknown database
            raise
        server = create_engine(_mysql_url(s, with_database=False), connect_args={"connect_timeout": 5})
        with server.begin() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{s['database']}` CHARACTER SET utf8mb4"))
        server.dispose()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    return engine


@st.cache_resource(ttl=60, show_spinner=False)
def _resolve(sqlite_path: str, mode: str, settings: tuple | None) -> tuple[Engine, Backend]:
    """Pick the database. Cached for a minute so a MySQL that comes back is noticed."""
    s = dict(settings) if settings else None
    note = ""
    if mode == "mysql" and not s:
        raise RuntimeError("CCM_BACKEND=mysql but MySQL is not configured (see the Database page).")
    if mode != "sqlite" and s:
        try:
            engine = _connect_mysql(s)
            return engine, Backend("mysql", f"MySQL ({s['database']} on {s['host']})")
        except Exception as e:  # noqa: BLE001
            if mode == "mysql":
                raise
            note = _friendly_error(e, s)
    engine = create_engine(URL.create("sqlite", database=sqlite_path))
    return engine, Backend("sqlite", "Local file (SQLite)", note)


def _resolved() -> tuple[Engine, Backend]:
    s = mysql_settings()
    return _resolve(str(config.db_path()), config.backend(), tuple(sorted(s.items())) if s else None)


def get_engine() -> Engine:
    """The SQLAlchemy engine for the active database."""
    return _resolved()[0]


def backend_info() -> Backend:
    """Which database we are using (and why, if we fell back to SQLite)."""
    return _resolved()[1]


def recheck() -> None:
    """Forget the cached connection so the next call tries MySQL again."""
    _resolve.clear()
    st.cache_data.clear()


# ---- Writes ----------------------------------------------------------------------------
def _prepare(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        row = {c: r.get(c) for c in COLUMNS}
        if isinstance(row["timestamp"], str):
            row["timestamp"] = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        if row["note"]:
            row["note"] = str(row["note"])[:255]
        out.append(row)
    return out


def init_db() -> None:
    """Create tables; on a brand-new empty database also load the synthetic demo rows."""
    engine = get_engine()
    with _init_lock:
        config.db_path().parent.mkdir(parents=True, exist_ok=True)
        metadata.create_all(engine)
        with engine.begin() as conn:
            if conn.execute(select(app_meta.c.meta_value).where(app_meta.c.meta_key == "initialised")).first():
                return
            empty = conn.execute(select(func.count()).select_from(readings)).scalar_one() == 0
            if empty and config.auto_seed_enabled():
                from core.seed import generate_seed_readings

                conn.execute(insert(readings), _prepare(generate_seed_readings()))
            conn.execute(insert(app_meta).values(meta_key="initialised", meta_value="1"))


def insert_reading(reading: dict) -> int:
    """Insert one reading (dict with the keys in COLUMNS); returns its new id."""
    init_db()
    with get_engine().begin() as conn:
        return int(conn.execute(insert(readings), _prepare([reading])[0]).inserted_primary_key[0])


def delete_reading(reading_id: int) -> bool:
    """Remove one student reading by id (demo rows can never be deleted this way). True if a row went."""
    with get_engine().begin() as conn:
        res = conn.execute(delete(readings).where(readings.c.id == int(reading_id), readings.c.method != "seeded"))
    return res.rowcount == 1


def reseed_demo_data(n: int = 1500) -> int:
    """Replace all synthetic rows with a fresh batch (real readings are untouched)."""
    from core.seed import generate_seed_readings

    init_db()
    with get_engine().begin() as conn:
        conn.execute(delete(readings).where(readings.c.method == "seeded"))
        conn.execute(insert(readings), _prepare(generate_seed_readings(n)))
    return n


# ---- Reads -----------------------------------------------------------------------------
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Parse timestamps and add hour, weekday, is_weekend and quality_score."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).reset_index(drop=True)
    df["hour"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.dayofweek
    df["weekday_name"] = df["timestamp"].dt.day_name().str[:3]
    df["is_weekend"] = df["weekday"] >= 5
    return add_quality(df)


@st.cache_data(show_spinner=False, ttl=60)
def load_readings(include_demo: bool = True) -> pd.DataFrame:
    """All readings (optionally excluding seeded rows), enriched. Cached; clear after writes."""
    init_db()
    query = select(readings).order_by(readings.c.timestamp)
    if not include_demo:
        query = query.where(readings.c.method != "seeded")
    with get_engine().connect() as conn:
        df = pd.read_sql_query(query, conn)
    return enrich(df)


def count_by_method() -> dict[str, int]:
    """Row counts per method, e.g. {'seeded': 1500, 'manual': 3}."""
    init_db()
    with get_engine().connect() as conn:
        rows = conn.execute(select(readings.c.method, func.count()).group_by(readings.c.method)).all()
    return {m: int(n) for m, n in rows}
