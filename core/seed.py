"""Synthetic demo data. Every row is marked method="seeded" and is NOT real.

Patterns baked in (so the analysis pages have something to find):
  * 10-13h is heavily congested, 14-16h moderately; hostels also slow in the evening
  * ground floors are strongest, speed falls with height
  * library and hostel top floors are weak
  * three obvious dead zones (see DEAD_ZONES)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from core import config

BLOCK_BASE_MBPS = {
    "Main Block": 78, "Block 2": 72, "Library Block": 68,
    "Science Block": 74, "Food Court": 58, "Hostel Block": 52,
}
BLOCK_POPULARITY = {
    "Main Block": 1.6, "Block 2": 1.2, "Library Block": 1.3,
    "Science Block": 1.1, "Food Court": 0.9, "Hostel Block": 1.4,
}
AREA_FACTOR = {"ground": 1.15, "classroom": 1.0, "library": 0.92, "canteen": 0.8, "hostel": 0.85}
DEAD_ZONES = {  # (block, floor, area_type) -> speed multiplier
    ("Library Block", 3, "library"): 0.09,
    ("Hostel Block", 5, "hostel"): 0.08,
    ("Science Block", 3, "classroom"): 0.13,
}
DEAD_NOTES = ["Keeps dropping", "Video calls impossible here", "Barely any signal", "Page loads time out"]


def _hour_weights(area: str) -> dict[int, float]:
    base = {8: .5, 9: 1, 10: 1.3, 11: 1.4, 12: 1.4, 13: 1.2, 14: 1.1, 15: 1.0, 16: .8, 17: .4, 18: .3}
    if area == "hostel":
        return {7: .6, 8: .6, 9: .3, 10: .3, 11: .3, 12: .5, 13: .5, 14: .4, 15: .4, 16: .5,
                17: .8, 18: 1.2, 19: 1.6, 20: 1.8, 21: 1.8, 22: 1.4, 23: .8}
    if area == "canteen":
        return {9: .3, 10: .5, 11: 1.2, 12: 2.2, 13: 2.2, 14: 1.3, 15: .8, 16: .5, 17: .3}
    if area == "library":
        return {9: .8, 10: 1, 11: 1.3, 12: 1.2, 13: 1.0, 14: 1.3, 15: 1.4, 16: 1.2, 17: 1.0, 18: .6}
    return base


def _peak_factor(hour: int, area: str) -> float:
    if 10 <= hour < 13:
        return 0.45
    if hour == 13:
        return 0.8
    if 14 <= hour < 16:
        return 0.58
    if area == "hostel" and 20 <= hour <= 23:
        return 0.62
    return 1.0


def generate_seed_readings(n: int = 1500, seed: int = 42, now: datetime | None = None) -> list[dict]:
    """Generate ``n`` synthetic readings over the 28 days before ``now``."""
    rng = np.random.default_rng(seed)
    now = now or datetime.now()
    locs, weights = [], []
    for block in config.block_names():
        floors = config.floors_for(block)
        for floor in floors:
            for area in config.area_types_for(block, floor):
                w = BLOCK_POPULARITY.get(block, 1.0) * (1.4 if floor == 0 else 1.0)
                w *= {"classroom": 1.3, "library": 1.2, "canteen": 1.4, "hostel": 1.0, "ground": 0.7}.get(area, 1)
                locs.append((block, floor, area, max(floors)))
                weights.append(w)
    p = np.array(weights) / np.sum(weights)

    day_offsets = np.arange(1, 29)
    day_w = np.array([0.3 if (now - timedelta(days=int(d))).weekday() >= 5 else 1.0 for d in day_offsets])
    day_p = day_w / day_w.sum()

    rows: list[dict] = []
    for _ in range(n):
        block, floor, area, top = locs[rng.choice(len(locs), p=p)]
        hw = _hour_weights(area)
        hours = np.array(list(hw))
        hp = np.array(list(hw.values()), dtype=float)
        hour = int(rng.choice(hours, p=hp / hp.sum()))
        day = now - timedelta(days=int(rng.choice(day_offsets, p=day_p)))
        ts = day.replace(hour=hour, minute=int(rng.integers(0, 60)), second=int(rng.integers(0, 60)), microsecond=0)

        base = BLOCK_BASE_MBPS.get(block, 60) * AREA_FACTOR.get(area, 1.0)
        base *= max(0.45, 1.0 - 0.07 * floor)
        if floor == top and area in ("library", "hostel"):
            base *= 0.6
        dead = DEAD_ZONES.get((block, floor, area), 1.0)
        down = base * dead * _peak_factor(hour, area) * (1.12 if ts.weekday() >= 5 else 1.0)
        down = float(np.clip(down * rng.lognormal(0, 0.25), 0.3, 300))
        up = float(np.clip(down * rng.uniform(0.25, 0.5), 0.1, 150))
        lat = float(np.clip((15 + 1800 / (down + 10)) * rng.lognormal(0, 0.2), 8, 900))
        ratio = min(down / 70.0, 1.0) ** 0.6
        bars = int(np.clip(round(1 + 4 * ratio + rng.normal(0, 0.5)), 1, 5))
        if dead < 0.2:
            bars = int(rng.integers(1, 3))
        network = "Hostel-WiFi" if area == "hostel" and rng.random() < 0.85 else (
            "Student-WiFi" if rng.random() < 0.7 else "Campus-WiFi")
        note = str(rng.choice(DEAD_NOTES)) if dead < 0.2 and rng.random() < 0.15 else None
        rows.append(
            {
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "block": block, "floor": int(floor),
                "area_type": area, "download_mbps": round(down, 2), "upload_mbps": round(up, 2),
                "latency_ms": round(lat, 1), "signal_strength": float(bars),
                "device_type": str(rng.choice(config.load_locations()["devices"])),
                "network_name": network, "method": "seeded", "note": note,
            }
        )
    return rows


if __name__ == "__main__":  # python -m core.seed  -> replace demo rows in the DB
    from core.db import reseed_demo_data

    print(f"Inserted {reseed_demo_data()} synthetic readings.")
