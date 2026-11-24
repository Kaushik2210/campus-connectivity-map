"""Block x floor heatmap with filters and metric toggle."""
from __future__ import annotations

import streamlit as st

from core import config
from core.scoring import daypart_mask
from core.ui import block_order, grid_heatmap, page_setup, require_data

df = page_setup("Heatmap", ":material/grid_on:")
st.title("Campus Wi-Fi map")
st.caption("Each square is one floor of one block. Green is good, red is poor. Grey means we do not have enough readings yet, so we do not guess.")
require_data(df)

with st.sidebar:
    st.header("Narrow it down")
    daypart = st.selectbox("When?", list(config.DAYPARTS))
    daytype = st.radio("Which days?", ["All days", "Weekdays", "Weekends"])
    areas = sorted(df["area_type"].unique())
    area_sel = st.multiselect("What kind of place?", areas, default=areas)
    nets = sorted(df["network_name"].dropna().unique())
    net_sel = st.multiselect("Wi-Fi network", nets, default=nets)

metric = st.radio("Show me", ["Download (Mbps)", "Quality score", "Latency (ms)"], horizontal=True)
col, title, zmin, zmax, rev = {
    "Download (Mbps)": ("download_mbps", "Median download (Mbps)", 0, config.DOWNLOAD_GOOD_MBPS, False),
    "Quality score": ("quality_score", "Median quality (0-100)", 0, 100, False),
    "Latency (ms)": ("latency_ms", "Median latency (ms)", config.LATENCY_BEST_MS, config.LATENCY_WORST_MS, True),
}[metric]

f = df[daypart_mask(df["hour"], daypart) & df["area_type"].isin(area_sel)]
f = f[f["network_name"].isin(net_sel) | f["network_name"].isna()]
if daytype == "Weekdays":
    f = f[~f["is_weekend"]]
elif daytype == "Weekends":
    f = f[f["is_weekend"]]

if f.empty:
    st.warning("No readings match those filters. Try choosing more options.", icon=":material/filter_alt_off:")
    st.stop()

blocks = block_order(set(df["block"]) | set(config.block_names()))
floors = sorted(set(df["floor"]) | {x for b in config.block_names() for x in config.floors_for(b)})
agg = f.groupby(["floor", "block"]).agg(value=(col, "median"), n=("id", "size"))
fig = grid_heatmap(
    agg, floors, blocks, [config.floor_label(x) for x in floors], blocks,
    value_col="value", count_col="n", min_n=config.MIN_CELL_READINGS, zmin=zmin, zmax=zmax,
    cbar_title=title, reverse=rev, x_title="Block", y_title="Floor", height=max(380, 70 * len(floors) + 120),
)
st.plotly_chart(fig, width="stretch")

good = agg.loc[agg["n"] >= config.MIN_CELL_READINGS, "value"]
if len(good) >= 2:
    best_k = good.idxmin() if rev else good.idxmax()
    worst_k = good.idxmax() if rev else good.idxmin()
    place = lambda k: f"{k[1]}, {'ground floor' if k[0] == 0 else 'floor ' + str(k[0])}"  # noqa: E731
    st.markdown(f"**In plain words:** the best spot right now is **{place(best_k)}** and the weakest is **{place(worst_k)}**.")

enough = int((agg["n"] >= config.MIN_CELL_READINGS).sum())
st.caption(
    f"Based on {len(f):,} readings. {enough} squares have enough data. The rest are grey, including floors that do not exist."
)

with st.expander("See the numbers as a table"):
    shown = agg["value"].where(agg["n"] >= config.MIN_CELL_READINGS).unstack("block").reindex(index=floors, columns=blocks)
    shown.index = [config.floor_label(x) for x in floors]
    shown.index.name = "Floor"
    st.dataframe(shown.map(lambda v: "not enough data" if v != v else f"{v:.0f}"), width="stretch")
