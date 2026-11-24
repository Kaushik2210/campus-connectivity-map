"""Scoring and analysis helpers (pure pandas/numpy, no Streamlit)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core import config

LOC_KEYS = ["block", "floor", "area_type"]


def _clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)


def normalise_download(mbps) -> np.ndarray:
    """Map download Mbps to 0-1 (DOWNLOAD_GOOD_MBPS or more = 1)."""
    return _clip01(np.asarray(mbps, dtype=float) / config.DOWNLOAD_GOOD_MBPS)


def normalise_upload(mbps) -> np.ndarray:
    """Map upload Mbps to 0-1 (UPLOAD_GOOD_MBPS or more = 1)."""
    return _clip01(np.asarray(mbps, dtype=float) / config.UPLOAD_GOOD_MBPS)


def normalise_latency(ms) -> np.ndarray:
    """Map latency to 0-1, lower is better (<= best = 1, >= worst = 0)."""
    span = config.LATENCY_WORST_MS - config.LATENCY_BEST_MS
    return _clip01(1.0 - (np.asarray(ms, dtype=float) - config.LATENCY_BEST_MS) / span)


def normalise_signal(value) -> np.ndarray:
    """Map signal to 0-1. Values < 0 are read as dBm, otherwise as 1-5 bars."""
    arr = np.asarray(value, dtype=float)
    bars = _clip01((arr - 1.0) / 4.0)
    dbm = _clip01((arr - config.DBM_WORST) / (config.DBM_BEST - config.DBM_WORST))
    return np.where(arr < 0, dbm, bars)


def quality_score(download, upload=np.nan, latency=np.nan, signal=np.nan):
    """Quality score 0-100: weighted blend of download, upload, latency and signal.

    Weights come from ``config.SCORE_WEIGHTS``. Missing (NaN) components are
    left out and the remaining weights are renormalised, so a reading without
    upload or latency is still scored fairly. Accepts scalars or arrays.
    """
    comps = np.vstack(
        [
            np.atleast_1d(normalise_download(download)),
            np.atleast_1d(normalise_upload(upload)) * np.ones(np.shape(np.atleast_1d(download))),
            np.atleast_1d(normalise_latency(latency)) * np.ones(np.shape(np.atleast_1d(download))),
            np.atleast_1d(normalise_signal(signal)) * np.ones(np.shape(np.atleast_1d(download))),
        ]
    )
    w = np.array(
        [config.SCORE_WEIGHTS[k] for k in ("download", "upload", "latency", "signal")]
    )[:, None]
    valid = ~np.isnan(comps)
    num = np.where(valid, comps, 0.0) * w
    den = (valid * w).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(den > 0, 100.0 * num.sum(axis=0) / den, np.nan)
    return float(score[0]) if np.ndim(download) == 0 else score


def add_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with a ``quality_score`` column."""
    out = df.copy()
    num = lambda c: pd.to_numeric(out[c], errors="coerce").to_numpy(dtype=float)  # noqa: E731
    out["quality_score"] = quality_score(
        num("download_mbps"), num("upload_mbps"), num("latency_ms"), num("signal_strength")
    ) if len(out) else pd.Series(dtype=float)
    return out


def confidence_level(n: int) -> str:
    """Confidence label from sample size."""
    if n >= 15:
        return "High"
    if n >= 6:
        return "Medium"
    return "Low"


def daypart_mask(hours: pd.Series, name: str) -> pd.Series:
    """Boolean mask of rows whose hour falls in the named daypart."""
    span = config.DAYPARTS.get(name)
    if span is None:
        return pd.Series(True, index=hours.index)
    start, end = span
    if start < end:
        return (hours >= start) & (hours < end)
    return (hours >= start) | (hours < end)  # wraps midnight


def worst_daypart(sub: pd.DataFrame, min_readings: int = 2) -> str:
    """Daypart with the lowest median download (needs ``min_readings`` rows)."""
    best_name, best_val = "n/a", np.inf
    for name in config.DAYPARTS:
        if name == "All day":
            continue
        part = sub.loc[daypart_mask(sub["hour"], name), "download_mbps"]
        if len(part) >= min_readings and part.median() < best_val:
            best_name, best_val = name, float(part.median())
    return best_name


def place_name(block: str, floor: int, area: str) -> str:
    """Readable place name, e.g. 'Library Block, floor 3 (library)'."""
    floor_text = "ground floor" if int(floor) == 0 else f"floor {int(floor)}"
    kind = "open area" if area == "ground" else area
    return f"{block}, {floor_text} ({kind})"


def location_stats(df: pd.DataFrame, weak_threshold: float) -> pd.DataFrame:
    """Per location (block+floor+area_type) summary used by dead zones and priority."""
    cols = LOC_KEYS + [
        "location", "readings", "median_quality", "median_download", "median_upload",
        "median_latency", "share_weak", "confidence", "worst_time",
    ]
    if df.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for (block, floor, area), sub in df.groupby(LOC_KEYS, sort=True):
        q = sub["quality_score"]
        rows.append(
            {
                "block": block, "floor": int(floor), "area_type": area,
                "location": place_name(block, floor, area),
                "readings": len(sub),
                "median_quality": float(q.median()),
                "median_download": float(sub["download_mbps"].median()),
                "median_upload": float(sub["upload_mbps"].median()),
                "median_latency": float(sub["latency_ms"].median()),
                "share_weak": float((q < weak_threshold).mean()),
                "confidence": confidence_level(len(sub)),
                "worst_time": worst_daypart(sub),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def priority_table(stats: pd.DataFrame, min_readings: int = 3) -> pd.DataFrame:
    """Rank locations by priority = weakness x reading volume x consistency.

    weakness = (100 - median quality) / 100; volume = number of readings (a proxy
    for affected users); consistency = share of readings below the weak threshold.
    The score is rescaled so the top location is 100.
    """
    s = stats[stats["readings"] >= min_readings].copy()
    if s.empty:
        s["priority_score"] = pd.Series(dtype=float)
        s["action"] = pd.Series(dtype=str)
        return s
    raw = (100.0 - s["median_quality"]) / 100.0 * s["readings"] * s["share_weak"]
    top = raw.max()
    s["priority_score"] = 100.0 * raw / top if top > 0 else 0.0
    s["action"] = s.apply(recommended_action, axis=1)
    return s.sort_values("priority_score", ascending=False).reset_index(drop=True)


def recommended_action(row: pd.Series) -> str:
    """One-line suggested fix based on how consistently the spot is weak."""
    if row["share_weak"] >= 0.7:
        return "Coverage gap: survey access-point placement or add an AP"
    if row["worst_time"] != "n/a" and row["share_weak"] >= 0.3:
        return f"Congestion around {row['worst_time']}: add capacity / balance load"
    return "Intermittent weak spot: re-survey before spending"


def find_congestion_windows(
    df: pd.DataFrame,
    drop_threshold: float = config.CONGESTION_DROP,
    min_readings: int = config.MIN_CELL_READINGS,
    group_col: str = "block",
    value_col: str = "download_mbps",
) -> pd.DataFrame:
    """Hours where the median drops ``drop_threshold`` or more below the group's own median.

    ``df`` needs ``group_col``, ``hour`` and ``value_col``. Hours with fewer than
    ``min_readings`` rows are ignored. Returns one row per flagged (group, hour).
    """
    cols = [group_col, "hour", "readings", "hour_median", "baseline", "drop"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    baseline = df.groupby(group_col)[value_col].median().rename("baseline").reset_index()
    hourly = (
        df.groupby([group_col, "hour"])[value_col]
        .agg(hour_median="median", readings="size")
        .reset_index()
        .merge(baseline, on=group_col)
    )
    hourly["drop"] = 1.0 - hourly["hour_median"] / hourly["baseline"]
    mask = (
        (hourly["readings"] >= min_readings)
        & (hourly["baseline"] > 0)
        & (hourly["drop"] >= drop_threshold - 1e-9)
    )
    return hourly.loc[mask, cols].sort_values([group_col, "hour"]).reset_index(drop=True)


def merge_windows(flagged: pd.DataFrame, group_col: str = "block") -> pd.DataFrame:
    """Merge consecutive flagged hours into windows (end_hour is exclusive)."""
    cols = [group_col, "start_hour", "end_hour", "readings", "median_speed", "baseline", "drop"]
    if flagged.empty:
        return pd.DataFrame(columns=cols)
    out = []
    for grp, sub in flagged.groupby(group_col, sort=True):
        sub = sub.sort_values("hour")
        run: list[pd.Series] = []
        for _, r in sub.iterrows():
            if run and int(r["hour"]) != int(run[-1]["hour"]) + 1:
                out.append(_close_window(grp, run, group_col))
                run = []
            run.append(r)
        out.append(_close_window(grp, run, group_col))
    return pd.DataFrame(out, columns=cols).sort_values("drop", ascending=False).reset_index(drop=True)


def _close_window(grp, run: list[pd.Series], group_col: str) -> dict:
    return {
        group_col: grp,
        "start_hour": int(run[0]["hour"]),
        "end_hour": int(run[-1]["hour"]) + 1,
        "readings": int(sum(r["readings"] for r in run)),
        "median_speed": float(np.mean([r["hour_median"] for r in run])),
        "baseline": float(run[0]["baseline"]),
        "drop": float(np.mean([r["drop"] for r in run])),
    }


# ---- Plain-language helpers ------------------------------------------------------------
def score_label(score: float) -> str:
    """Turn a 0-100 quality score into a word students understand."""
    if score >= 75:
        return "Great"
    if score >= 55:
        return "Good"
    if score >= 40:
        return "Okay"
    if score >= 20:
        return "Poor"
    return "Barely usable"


def speed_meaning(mbps: float) -> str:
    """Say what a download speed means in everyday terms."""
    if mbps < 2:
        return "too slow to load most web pages"
    if mbps < 5:
        return "enough for messages, but slow for almost everything else"
    if mbps < 15:
        return "fine for browsing, though video may stutter"
    if mbps < 30:
        return "good enough for video lectures"
    return "smooth, even for video calls"


def hour_label(hour: int) -> str:
    """12-hour clock label, e.g. 13 -> '1 pm'."""
    h = int(hour) % 24
    return f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"


def fastest_hour(df: pd.DataFrame, min_readings: int = 30) -> tuple[int, float] | None:
    """Hour when speeds are best *relative to each block's own normal* (fair across areas).

    Returns (hour, ratio) where ratio 1.2 means 20% faster than usual, or None if there is
    not enough data.
    """
    if df.empty:
        return None
    rel = df["download_mbps"] / df.groupby("block")["download_mbps"].transform("median")
    g = rel.groupby(df["hour"]).agg(["median", "size"])
    g = g[g["size"] >= min_readings]
    if g.empty:
        return None
    return int(g["median"].idxmax()), float(g["median"].max())


def time_ago(ts, now=None) -> str:
    """Friendly relative time, e.g. '3 hours ago' or 'yesterday'."""
    now = now if now is not None else pd.Timestamp.now()
    secs = max((pd.Timestamp(now) - pd.Timestamp(ts)).total_seconds(), 0)
    if secs < 3600:
        return f"{max(int(secs // 60), 1)} min ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = int(secs // 86400)
    return "yesterday" if d == 1 else f"{d} days ago"


def trend(spot: pd.DataFrame, now=None, window_days: int = 14, min_each: int = 3, steady_within: float = 5.0) -> dict | None:
    """Is a place getting better or worse? Compares the last ``window_days`` with the window before.

    Returns {"direction": "better"|"worse"|"steady", "delta": points} or None when either
    window has fewer than ``min_each`` readings.
    """
    if spot.empty:
        return None
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now()
    edge = now - pd.Timedelta(days=window_days)
    recent = spot[spot["timestamp"] > edge]["quality_score"]
    prior = spot[(spot["timestamp"] <= edge) & (spot["timestamp"] > edge - pd.Timedelta(days=window_days))]["quality_score"]
    if len(recent) < min_each or len(prior) < min_each:
        return None
    delta = float(recent.median() - prior.median())
    direction = "steady" if abs(delta) < steady_within else ("better" if delta > 0 else "worse")
    return {"direction": direction, "delta": delta}


def reading_warnings(download, upload=None, latency=None) -> list[str]:
    """Friendly 'are you sure?' notes for numbers that look unlikely (not errors, just worth a second look)."""
    notes = []
    if download is not None and download > 300:
        notes.append("That download is very fast for campus Wi-Fi. Please check it is in Mbps (not MB/s or Kbps).")
    if latency is not None and latency < 3:
        notes.append("A latency under 3 ms is unusual for Wi-Fi. Please check the number.")
    if download and upload and upload > 20 and upload > 3 * download:
        notes.append("Your upload is much higher than your download. Did the two get swapped?")
    return notes


def trend_table(df: pd.DataFrame, now=None, min_each: int = 3) -> pd.DataFrame:
    """Per place: is it getting better or worse (last 2 weeks vs the 2 weeks before)?"""
    cols = ["location", "direction", "delta"]
    rows = []
    for (block, floor, area), spot in df.groupby(LOC_KEYS, sort=True):
        tr = trend(spot, now, min_each=min_each)
        if tr:
            rows.append({"location": place_name(block, floor, area), **tr})
    return pd.DataFrame(rows, columns=cols)
