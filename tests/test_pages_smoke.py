"""Run every page headlessly (demo on, demo off, empty DB) and assert nothing raises."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [
    "app.py", "pages/1_Submit_Reading.py", "pages/2_Check_My_Spot.py", "pages/3_Heatmap.py",
    "pages/4_Peak_Hours.py", "pages/5_Dead_Zones.py", "pages/6_Admin_Priority.py", "pages/7_Database.py",
]


@pytest.fixture(params=["demo_on", "demo_off", "empty_db"])
def scenario(request, tmp_path, monkeypatch):
    monkeypatch.setenv("CCM_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CCM_BACKEND", "sqlite")  # never touch a real MySQL from tests
    monkeypatch.setenv("CCM_AUTO_SEED", "0" if request.param == "empty_db" else "1")
    # AppTest cannot resolve page links when a page (not app.py) is the entry script.
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    st.cache_data.clear()
    st.cache_resource.clear()
    yield request.param
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page, scenario):
    at = AppTest.from_file(str(ROOT / page), default_timeout=60)
    if scenario == "demo_off":
        at.session_state["include_demo"] = False
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_submission_flow_and_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("CCM_DB_PATH", str(tmp_path / "sub.db"))
    monkeypatch.setenv("CCM_AUTO_SEED", "0")
    monkeypatch.setenv("CCM_BACKEND", "sqlite")
    st.cache_data.clear()
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "pages/1_Submit_Reading.py"), default_timeout=60).run()
    for i in range(5):
        at.number_input(key="in_down").set_value(30.0 + i)
        at.number_input(key="in_lat").set_value(40.0)
        at.button[0].click().run()
        assert not at.exception
    assert at.session_state["last_result"]["down"] == 34.0
    at.number_input(key="in_down").set_value(10.0).run()
    assert at.button[0].disabled  # 6th submission blocked
    from core.db import load_readings

    st.cache_data.clear()
    assert len(load_readings(True)) == 5


def test_qr_prefill_and_poster_generator(tmp_path, monkeypatch):
    monkeypatch.setenv("CCM_DB_PATH", str(tmp_path / "qr.db"))
    monkeypatch.setenv("CCM_BACKEND", "sqlite")
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    st.cache_data.clear()
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "pages/1_Submit_Reading.py"), default_timeout=60)
    at.query_params["block"] = "Library Block"
    at.query_params["floor"] = "2"
    at.run()
    assert not at.exception
    assert at.selectbox(key="sub_block").value == "Library Block"
    assert at.selectbox(key="sub_floor").value == 2

    admin = AppTest.from_file(str(ROOT / "pages/6_Admin_Priority.py"), default_timeout=60).run()
    admin.text_input(key="poster_base").set_value("https://example.streamlit.app").run()
    assert not admin.exception
    assert len(admin.get("download_button")) >= 12  # PNG + SVG for each of the 6 blocks


def _env(monkeypatch, tmp_path, name):
    monkeypatch.setenv("CCM_DB_PATH", str(tmp_path / name))
    monkeypatch.setenv("CCM_BACKEND", "sqlite")
    monkeypatch.setenv("CCM_AUTO_SEED", "1")
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    st.cache_data.clear()
    st.cache_resource.clear()


def test_admin_pin_gate(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path, "pin.db")
    monkeypatch.setenv("CCM_ADMIN_PIN", "1234")
    at = AppTest.from_file(str(ROOT / "pages/6_Admin_Priority.py"), default_timeout=60).run()
    assert not at.exception and not at.get("download_button")  # locked
    at.text_input(key="admin_pin_input").set_value("0000").run()
    assert at.error and not at.get("download_button")
    at.text_input(key="admin_pin_input").set_value("1234").run()
    assert not at.exception and at.get("download_button")  # unlocked


def test_typo_undo_and_unlikely_numbers(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path, "undo.db")
    monkeypatch.setenv("CCM_AUTO_SEED", "0")
    at = AppTest.from_file(str(ROOT / "pages/1_Submit_Reading.py"), default_timeout=60).run()
    at.number_input(key="in_down").set_value(900.0)
    at.number_input(key="in_lat").set_value(20.0).run()
    assert at.warning and at.button[0].disabled  # needs the "numbers are right" tick
    at.checkbox(key="sub_confirm").check().run()
    assert not at.button[0].disabled
    at.button[0].click().run()
    from core.db import load_readings

    st.cache_data.clear()
    assert len(load_readings(True)) == 1
    at.button(key="undo_last").click().run()
    st.cache_data.clear()
    assert len(load_readings(True)) == 0 and not at.exception


def test_tell_it_on_weak_spot(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path, "tellit.db")
    monkeypatch.setenv("CCM_IT_EMAIL", "it@example.edu")
    at = AppTest.from_file(str(ROOT / "pages/2_Check_My_Spot.py"), default_timeout=60).run()
    assert not at.exception and not at.expander  # first spot (Main Block, ground) is healthy: no prompt
    at.selectbox[0].set_value("Library Block").run()
    at.selectbox[1].set_value(3).run()
    assert not at.exception
    assert [e.label for e in at.expander] == ["Want this fixed? Tell IT"]
    assert at.get("link_button")  # the email button appears because the IT address is set
