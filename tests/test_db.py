"""Database layer: SQLite round trip, MySQL schema, settings and the fall-back behaviour."""
from datetime import datetime

import pytest
import streamlit as st
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from core import db


@pytest.fixture()
def clean_env(tmp_path, monkeypatch):
    for k in ("CCM_MYSQL_HOST", "CCM_MYSQL_PORT", "CCM_MYSQL_USER", "CCM_MYSQL_PASSWORD", "CCM_MYSQL_DATABASE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CCM_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("CCM_AUTO_SEED", "0")
    monkeypatch.setenv("CCM_BACKEND", "auto")
    st.cache_data.clear()
    st.cache_resource.clear()
    yield monkeypatch
    st.cache_data.clear()
    st.cache_resource.clear()


def _reading(**kw):
    base = {"timestamp": "2026-11-18 10:30:00", "block": "Main Block", "floor": 2, "area_type": "classroom",
            "download_mbps": 42.5, "upload_mbps": 11.0, "latency_ms": 35.0, "signal_strength": 4.0,
            "device_type": "iPhone", "network_name": "Student-WiFi", "method": "manual", "note": "ok"}
    return {**base, **kw}


def test_mysql_schema_compiles():
    ddl = str(CreateTable(db.readings).compile(dialect=mysql.dialect()))
    assert "AUTO_INCREMENT" in ddl and "DATETIME" in ddl and "VARCHAR(64)" in ddl


def test_not_configured_means_sqlite(clean_env):
    assert db.mysql_settings() is None
    assert db.backend_info().kind == "sqlite"


def test_settings_come_from_env(clean_env):
    clean_env.setenv("CCM_MYSQL_USER", "campus")
    clean_env.setenv("CCM_MYSQL_DATABASE", "campus_wifi")
    clean_env.setenv("CCM_MYSQL_PASSWORD", "p@ss:word/with#symbols")
    s = db.mysql_settings()
    assert s["host"] == "localhost" and int(s["port"]) == 3306 and s["database"] == "campus_wifi"
    # odd characters in the password must survive URL building
    assert db._mysql_url(s).password == "p@ss:word/with#symbols"


def test_unreachable_mysql_falls_back_to_sqlite(clean_env):
    for k, v in {"HOST": "127.0.0.1", "PORT": "1", "USER": "x", "DATABASE": "y", "PASSWORD": "z"}.items():
        clean_env.setenv(f"CCM_MYSQL_{k}", v)
    info = db.backend_info()
    assert info.kind == "sqlite"
    assert "MySQL" in info.note and "z" not in info.note.replace("MySQL", "")  # message never leaks the password


def test_strict_mode_raises_instead_of_falling_back(clean_env):
    for k, v in {"HOST": "127.0.0.1", "PORT": "1", "USER": "x", "DATABASE": "y"}.items():
        clean_env.setenv(f"CCM_MYSQL_{k}", v)
    clean_env.setenv("CCM_BACKEND", "mysql")
    with pytest.raises(Exception):
        db.get_engine()


def test_bad_database_name_is_rejected(clean_env):
    with pytest.raises(ValueError):
        db._connect_mysql({"user": "u", "password": "", "host": "localhost", "port": 3306, "database": "x`; DROP"})


def test_insert_and_load_round_trip(clean_env):
    new_id = db.insert_reading(_reading())
    assert new_id == 1
    df = db.load_readings(True)
    assert len(df) == 1 and df.loc[0, "hour"] == 10 and df.loc[0, "block"] == "Main Block"
    assert df.loc[0, "timestamp"] == datetime(2026, 11, 18, 10, 30)
    assert db.count_by_method() == {"manual": 1}


def test_seed_runs_once_and_demo_can_be_hidden(clean_env):
    clean_env.setenv("CCM_AUTO_SEED", "1")
    db.insert_reading(_reading())  # init_db seeds the empty database first
    assert len(db.load_readings(True)) == 1501
    assert len(db.load_readings(False)) == 1
    db.init_db()  # second call must not seed again
    st.cache_data.clear()
    assert len(db.load_readings(True)) == 1501
