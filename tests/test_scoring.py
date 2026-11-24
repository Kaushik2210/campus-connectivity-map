import numpy as np
import pandas as pd
import pytest

from core import config
from core.scoring import (
    confidence_level, daypart_mask, hour_label, score_label, speed_meaning, find_congestion_windows, merge_windows, quality_score,
)


def test_perfect_reading_scores_100():
    assert quality_score(100, 50, 10, 5) == pytest.approx(100.0)


def test_worst_reading_scores_0():
    assert quality_score(0, 0, 500, 1) == pytest.approx(0.0)


def test_weights_sum_to_one():
    assert sum(config.SCORE_WEIGHTS.values()) == pytest.approx(1.0)


def test_download_dominates():
    only_download = quality_score(50, 0, 250, 1)  # everything else worst
    assert only_download == pytest.approx(50.0)


def test_missing_components_are_renormalised():
    # Only download + signal known, both perfect -> still 100, not 65.
    assert quality_score(80, np.nan, np.nan, 5) == pytest.approx(100.0)


def test_dbm_signal_is_supported():
    strong = quality_score(50, 20, 20, -50)
    weak = quality_score(50, 20, 20, -90)
    assert strong > weak


def test_vectorised_matches_scalar():
    arr = quality_score(np.array([10.0, 60.0]), np.array([5.0, 25.0]), np.array([100.0, 15.0]), np.array([2.0, 5.0]))
    assert arr[0] == pytest.approx(quality_score(10, 5, 100, 2))
    assert arr[1] == pytest.approx(quality_score(60, 25, 15, 5))


def test_confidence_levels():
    assert (confidence_level(3), confidence_level(8), confidence_level(30)) == ("Low", "Medium", "High")


def test_daypart_wraps_midnight():
    hours = pd.Series([23, 2, 12])
    assert daypart_mask(hours, "Night (22-6)").tolist() == [True, True, False]


def _frame():
    rows = []
    for hour in range(8, 16):
        speed = 40.0 if hour in (11, 12) else 100.0
        rows += [{"block": "A", "hour": hour, "download_mbps": speed + d} for d in (-1, 0, 1)]
    rows += [{"block": "B", "hour": h, "download_mbps": 50.0} for h in range(8, 16) for _ in range(3)]
    return pd.DataFrame(rows)


def test_congestion_windows_flag_slow_hours_only():
    flagged = find_congestion_windows(_frame(), 0.30, 3)
    assert set(flagged["block"]) == {"A"}
    assert flagged["hour"].tolist() == [11, 12]
    assert (flagged["drop"] > 0.5).all()


def test_congestion_ignores_thin_hours():
    df = _frame()
    df = df[~((df["block"] == "A") & (df["hour"] == 12) & (df["download_mbps"] != 40))]  # leaves 1 reading at 12h
    assert find_congestion_windows(df, 0.30, 3)["hour"].tolist() == [11]


def test_merge_windows_joins_consecutive_hours():
    win = merge_windows(find_congestion_windows(_frame(), 0.30, 3))
    assert len(win) == 1
    assert (win.loc[0, "start_hour"], win.loc[0, "end_hour"]) == (11, 13)


def test_empty_inputs_do_not_crash():
    empty = pd.DataFrame(columns=["block", "hour", "download_mbps"])
    assert find_congestion_windows(empty).empty
    assert merge_windows(find_congestion_windows(empty)).empty


def test_score_labels():
    assert [score_label(s) for s in (90, 60, 45, 25, 5)] == ["Great", "Good", "Okay", "Poor", "Barely usable"]


def test_speed_meaning_and_hour_label():
    assert "too slow" in speed_meaning(1)
    assert "video calls" in speed_meaning(80)
    assert (hour_label(0), hour_label(9), hour_label(12), hour_label(13)) == ("12 am", "9 am", "12 pm", "1 pm")


def test_place_name_is_readable():
    from core.scoring import place_name

    assert place_name("Library Block", 3, "library") == "Library Block, floor 3 (library)"
    assert place_name("Food Court", 0, "ground") == "Food Court, ground floor (open area)"


def test_fastest_hour_is_relative_to_each_block():
    from core.scoring import fastest_hour

    rows = [{"block": "A", "hour": 9, "download_mbps": 120.0}] * 30 + [{"block": "A", "hour": 12, "download_mbps": 60.0}] * 30
    rows += [{"block": "B", "hour": 23, "download_mbps": 10.0}] * 30  # a slow block must not drag its hour down unfairly
    hour, ratio = fastest_hour(pd.DataFrame(rows))
    assert hour == 9 and ratio > 1


def test_time_ago():
    from core.scoring import time_ago

    now = pd.Timestamp("2026-11-19 12:00")
    assert time_ago("2026-11-19 11:30", now) == "30 min ago"
    assert time_ago("2026-11-19 09:00", now) == "3 hours ago"
    assert time_ago("2026-11-18 11:00", now) == "yesterday"
    assert time_ago("2026-11-14 12:00", now) == "5 days ago"


def _spot(recent_q, prior_q, n=4):
    now = pd.Timestamp("2026-11-23 12:00")
    rows = [{"timestamp": now - pd.Timedelta(days=2 + i), "quality_score": recent_q} for i in range(n)]
    rows += [{"timestamp": now - pd.Timedelta(days=16 + i), "quality_score": prior_q} for i in range(n)]
    return pd.DataFrame(rows), now


def test_trend_directions():
    from core.scoring import trend

    df, now = _spot(60, 40)
    assert trend(df, now)["direction"] == "better"
    df, now = _spot(30, 50)
    assert trend(df, now)["direction"] == "worse"
    df, now = _spot(52, 50)
    assert trend(df, now)["direction"] == "steady"


def test_trend_needs_enough_readings():
    from core.scoring import trend

    df, now = _spot(60, 40, n=2)
    assert trend(df, now) is None
    assert trend(df.iloc[0:0], now) is None


def test_reading_warnings():
    from core.scoring import reading_warnings

    assert reading_warnings(40, 10, 30) == []
    assert len(reading_warnings(900, 10, 30)) == 1
    assert len(reading_warnings(40, 10, 1)) == 1
    assert len(reading_warnings(5, 60, 30)) == 1  # upload far above download


def test_trend_table_lists_each_place():
    from core.scoring import trend_table

    now = pd.Timestamp("2026-11-23 12:00")
    rows = []
    for i in range(4):
        rows += [
            {"block": "A", "floor": 1, "area_type": "classroom", "timestamp": now - pd.Timedelta(days=2 + i), "quality_score": 70.0},
            {"block": "A", "floor": 1, "area_type": "classroom", "timestamp": now - pd.Timedelta(days=16 + i), "quality_score": 40.0},
            {"block": "B", "floor": 0, "area_type": "ground", "timestamp": now - pd.Timedelta(days=2 + i), "quality_score": 30.0},  # no older data
        ]
    out = trend_table(pd.DataFrame(rows), now)
    assert out["location"].tolist() == ["A, floor 1 (classroom)"]
    assert out.loc[0, "direction"] == "better"
